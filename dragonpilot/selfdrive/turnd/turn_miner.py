#!/usr/bin/env python3
"""
Copyright (c) 2026, Rick Lan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, and/or sublicense,
for non-commercial purposes only, subject to the following conditions:

- The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.
- Commercial use (e.g. use in a product, service, or activity intended to
  generate revenue) is prohibited without explicit written permission from
  the copyright holder.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Turn Miner - pure logic: extract blinker-signaled turns from recorded openpilot
rlog segments into a per-turn CSV. Reads a directory of segments, writes
turn_mined.csv; the companion turn_report.py ranks which onboard signal predicts
a turn earliest. Run offline over any pulled realdata mirror:
  python -m dragonpilot.selfdrive.turnd.turn_miner <realdata_dir> <out.csv>
"""
import os
from dataclasses import dataclass

from openpilot.common.swaglog import cloudlog

from dragonpilot.selfdrive.turnd.turn_logger import (
  yaw_heading_change, label_outcome, TURN_SPEED_MIN, TURN_SPEED_MAX,
)

DP_LOGS_DIR = "/data/media/0/dp_logs"
REALDATA_DIR = "/data/media/0/realdata"
MINE_PATH = os.path.join(DP_LOGS_DIR, "turn_mined.csv")


MIN_TURN_DUR = 1.0
PRE_S = 5.0
POST_S = 2.0

MINE_COLUMNS = [
  "segment", "maneuver_id", "seq", "t_rel", "v_ego", "blinker", "yaw_rate",
  "heading_change", "outcome", "model_curv", "desire_turn_l", "desire_turn_r",
  "ll_prob_l", "ll_prob_r", "lat", "lon",
]


@dataclass
class Sample:
  t: float
  v_ego: float
  left_blinker: bool
  right_blinker: bool
  yaw_rate: float
  model_curv: float
  desire_turn_l: float
  desire_turn_r: float
  ll_prob_l: float
  ll_prob_r: float
  lat: float
  lon: float


def _blinker(s: Sample) -> str:
  if s.left_blinker and not s.right_blinker:
    return "L"
  if s.right_blinker and not s.left_blinker:
    return "R"
  return "."


def _emit(seg: str, mid: int, window: list[Sample]) -> list[dict]:
  yaw_sum = sum(window[i].yaw_rate * (window[i].t - window[i - 1].t) for i in range(1, len(window)))
  hc = round(yaw_heading_change(yaw_sum), 2)
  outcome = label_outcome(hc)
  t0 = window[0].t
  rows = []
  for i, p in enumerate(window):
    rows.append({
      "segment": seg, "maneuver_id": mid, "seq": i, "t_rel": round(p.t - t0, 3),
      "v_ego": round(p.v_ego, 2), "blinker": _blinker(p), "yaw_rate": round(p.yaw_rate, 4),
      "heading_change": hc, "outcome": outcome, "model_curv": round(p.model_curv, 5),
      "desire_turn_l": round(p.desire_turn_l, 4), "desire_turn_r": round(p.desire_turn_r, 4),
      "ll_prob_l": round(p.ll_prob_l, 4), "ll_prob_r": round(p.ll_prob_r, 4),
      "lat": p.lat, "lon": p.lon,
    })
  return rows


def extract_turns(samples, segment: str) -> list[dict]:
  buf = list(samples)
  n = len(buf)
  rows: list[dict] = []
  mid = 0
  # skip any maneuver already in progress at the stream start (began in a previous segment)
  i = 0
  while i < n and _blinker(buf[i]) != ".":
    i += 1
  while i < n:
    bl = _blinker(buf[i])
    if bl == ".":
      i += 1
      continue
    start = i                                  # blinker rising edge
    j = i
    while j < n and _blinker(buf[j]) == bl:    # held in the same direction
      j += 1
    if j >= n:
      break                                    # blinker still on at stream end -> incomplete -> skip
    core_start, core_end = start, j - 1
    i = j                                      # resume after this maneuver
    if buf[core_end].t - buf[core_start].t < MIN_TURN_DUR:
      continue
    if not (TURN_SPEED_MIN < buf[core_start].v_ego < TURN_SPEED_MAX):
      continue
    ws = core_start
    while ws > 0 and buf[core_start].t - buf[ws - 1].t < PRE_S:
      ws -= 1
    we = core_end
    while we < n - 1 and buf[we + 1].t - buf[core_end].t < POST_S:
      we += 1
    rows.extend(_emit(segment, mid, buf[ws:we + 1]))
    mid += 1
  return rows


def read_segment(rlog_path: str) -> list[Sample]:
  if not os.path.isfile(rlog_path):
    return []
  try:
    from openpilot.tools.lib.logreader import LogReader
  except Exception as e:
    cloudlog.warning(f"turn_miner: LogReader unavailable: {e}")
    return []
  v_ego = 0.0
  lb = rb = False
  yaw = lat = lon = 0.0
  samples: list[Sample] = []
  try:
    for msg in LogReader(rlog_path):
      w = msg.which()
      if w == "carState":
        cs = msg.carState
        v_ego, lb, rb = cs.vEgo, cs.leftBlinker, cs.rightBlinker
      elif w == "livePose":
        yaw = msg.livePose.angularVelocityDevice.z
      elif w in ("gpsLocation", "gpsLocationExternal"):
        g = getattr(msg, w)
        lat, lon = g.latitude, g.longitude
      elif w == "modelV2":
        m = msg.modelV2
        ds, ll = m.meta.desireState, m.laneLineProbs
        samples.append(Sample(
          t=msg.logMonoTime * 1e-9, v_ego=v_ego, left_blinker=lb, right_blinker=rb,
          yaw_rate=yaw, model_curv=m.action.desiredCurvature,
          desire_turn_l=ds[1] if len(ds) > 1 else 0.0, desire_turn_r=ds[2] if len(ds) > 2 else 0.0,
          ll_prob_l=ll[1] if len(ll) > 1 else 0.0, ll_prob_r=ll[2] if len(ll) > 2 else 0.0,
          lat=lat, lon=lon,
        ))
  except Exception as e:
    cloudlog.warning(f"turn_miner: read failed for {rlog_path}: {e}")
    return samples
  return samples


def mine_segment(seg_path: str, writer) -> int:
  rows = extract_turns(read_segment(os.path.join(seg_path, "rlog.zst")), os.path.basename(seg_path))
  if rows:
    writer.writerows(rows)
  return len(rows)


def mine_dir(realdata_dir: str, out_path: str) -> int:
  """Mine every segment (a dir containing rlog.zst) under realdata_dir into out_path. Returns rows written."""
  import csv
  segs = sorted(os.path.join(realdata_dir, n) for n in os.listdir(realdata_dir)
                if os.path.isfile(os.path.join(realdata_dir, n, "rlog.zst")))
  os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
  total = 0
  with open(out_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=MINE_COLUMNS)
    w.writeheader()
    for s in segs:
      total += mine_segment(s, w)
  return total


if __name__ == "__main__":
  import sys
  src = sys.argv[1] if len(sys.argv) > 1 else REALDATA_DIR
  dst = sys.argv[2] if len(sys.argv) > 2 else MINE_PATH
  print(f"mined {mine_dir(src, dst)} turn-rows from {src} -> {dst}")
