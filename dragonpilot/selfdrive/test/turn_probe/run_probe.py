#!/usr/bin/env python3
"""Phase-0 model-turn probe runner (diagnostic).

Runs modeld over one log segment twice on identical frames — baseline
(desire=none) and with the desire forced to turnLeft/turnRight over a frame
window — then compares the predicted paths to decide whether the model turns.

The desire forcing is done by probe_desire.probe_desire_override, activated via
the PROBE_DESIRE / PROBE_FRAME_START / PROBE_FRAME_END env vars set here before
running modeld through replay_process. (Env is used so it works whether
replay_process runs modeld in-process or as a subprocess.)

Frame-space note
----------------
In replay, modeld calls probe_desire_override with
``sm["roadCameraState"].frameId`` which equals the VisionIPC frame counter
(1, 2, … N — i.e. the position of the frame in the replayed segment, not the
absolute hardware frameId stored in the log which can be e.g. 5913..5972).

The CLI accepts ``--frame-start / --frame-end`` in the same absolute
roadCameraState.frameId space that shows up in the log file.  We convert those
to VisionIPC frame indices before writing the env vars, so the
probe_desire_override hook fires at the right point, and the divergence filter
uses those same converted indices to stay in sync.
"""
import argparse
import os
import numpy as np

from openpilot.tools.lib.logreader import LogReader
from openpilot.selfdrive.test.process_replay.process_replay import get_process_config, replay_process
from openpilot.selfdrive.test.process_replay.model_replay import (  # reuse frame loading + log trimming
  get_frames, trim_logs, START_FRAME, END_FRAME,
)


def _run(modeld_logs, frs, forced, vipc_start, vipc_end):
  """Run modeld through replay_process.

  modeld_logs must already be trimmed (trim_logs).
  vipc_start/vipc_end are in VisionIPC frame space (1-based) — the space that
  sm["roadCameraState"].frameId returns during replay.

  Returns a list of y_path arrays, one per modelV2 message, in the same order
  as the roadCameraState messages in modeld_logs (index-aligned).
  """
  if forced is None:
    os.environ.pop("PROBE_DESIRE", None)
    os.environ.pop("PROBE_FRAME_START", None)
    os.environ.pop("PROBE_FRAME_END", None)
  else:
    os.environ["PROBE_DESIRE"] = forced
    os.environ["PROBE_FRAME_START"] = str(vipc_start)
    os.environ["PROBE_FRAME_END"] = str(vipc_end)
  cfg = get_process_config("modeld")
  msgs = replay_process(cfg, list(modeld_logs), frs)
  ys = [list(m.modelV2.position.y) for m in msgs if m.which() == "modelV2"]
  return ys


def main():
  p = argparse.ArgumentParser()
  p.add_argument("--direction", choices=["turnLeft", "turnRight"], required=True)
  p.add_argument("--frame-start", type=int, required=True,
                 help="Window start in roadCameraState.frameId space (absolute, e.g. 5930)")
  p.add_argument("--frame-end", type=int, required=True,
                 help="Window end in roadCameraState.frameId space (absolute, e.g. 5950)")
  p.add_argument("--threshold", type=float, default=2.0)
  args = p.parse_args()

  from dragonpilot.selfdrive.test.turn_probe.turn_metric import path_divergence, verdict
  from openpilot.selfdrive.test.process_replay.model_replay import TEST_ROUTE, SEGMENT, get_url

  lr_raw = list(LogReader(get_url(TEST_ROUTE, SEGMENT, "rlog.zst")))
  frs = get_frames()

  # Mirror model_replay.model_replay(): trim logs to the modeld frame window
  # before handing to replay_process.
  modeld_logs = trim_logs(lr_raw, START_FRAME, END_FRAME,
                          {"roadCameraState", "wideRoadCameraState"},
                          {"roadEncodeIdx", "wideRoadEncodeIdx", "carParams", "carState", "carControl", "can"})

  # Build per-position absolute roadCameraState.frameId list from the trimmed
  # log (the nth roadCameraState in modeld_logs corresponds to VisionIPC frame
  # counter n+1, because VisionIPC starts at 1).
  rcs_frame_ids = [m.roadCameraState.frameId
                   for m in modeld_logs
                   if m.which() == "roadCameraState"]

  print(f"[probe] roadCameraState frameId range in trimmed log: "
        f"{min(rcs_frame_ids)}..{max(rcs_frame_ids)} ({len(rcs_frame_ids)} frames)")

  # Convert the user's absolute frameId window to VisionIPC frame indices
  # (1-based).  VisionIPC frame N corresponds to rcs_frame_ids[N-1].
  lo_abs, hi_abs = args.frame_start, args.frame_end
  # Find first VisionIPC index where abs frameId >= lo_abs, and last where <= hi_abs.
  vipc_indices = [i + 1 for i, fid in enumerate(rcs_frame_ids) if lo_abs <= fid <= hi_abs]
  if not vipc_indices:
    print(f"[probe] ERROR: window [{lo_abs},{hi_abs}] does not overlap with "
          f"frameId range [{min(rcs_frame_ids)},{max(rcs_frame_ids)}].")
    print(f"[probe] Pass --frame-start / --frame-end inside that range.")
    return
  vipc_start = vipc_indices[0]
  vipc_end = vipc_indices[-1]
  print(f"[probe] Converted abs frameId window [{lo_abs},{hi_abs}] "
        f"to VisionIPC window [{vipc_start},{vipc_end}] ({len(vipc_indices)} frames)")

  # Run baseline (no desire) and turn run (desire forced in VisionIPC space).
  # Both replay the same trimmed log so their modelV2 output sequences are
  # index-for-index identical in length and frame ordering.
  base = _run(modeld_logs, frs, None, 0, 0)
  turn = _run(modeld_logs, frs, args.direction, vipc_start, vipc_end)

  if len(base) != len(turn):
    print(f"[probe] WARNING: baseline has {len(base)} modelV2 msgs, turn has {len(turn)} — "
          "using min; results may be incomplete")

  # Filter divergences to the requested window.  The i-th modelV2 output
  # corresponds to VisionIPC frame i+1 (1-based), which corresponds to
  # rcs_frame_ids[i] in absolute frameId space.  Filter using absolute frameId
  # to keep the CLI contract consistent (user specifies absolute frameIds).
  n = min(len(base), len(turn), len(rcs_frame_ids))
  divs = [
    path_divergence(base[i], turn[i])
    for i in range(n)
    if lo_abs <= rcs_frame_ids[i] <= hi_abs
  ]
  div = float(np.mean(divs)) if divs else 0.0
  ok = verdict(div, args.direction, args.threshold)

  # Save trajectories (y is a fixed-length float array; no object dtype needed).
  np.save("/tmp/turn_probe_baseline.npy", np.array(base, dtype=float))
  np.save("/tmp/turn_probe_turn.npy", np.array(turn, dtype=float))
  print(f"direction={args.direction} window=[{lo_abs},{hi_abs}] frames_in_window={len(divs)} mean_divergence={div:.2f} m")
  print(f"VERDICT: model {'TURNS' if ok else 'does NOT turn'} on the {args.direction} desire "
        f"(threshold {args.threshold} m)")


if __name__ == "__main__":
  main()
