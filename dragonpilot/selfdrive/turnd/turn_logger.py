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

Turn Logger (turnd) - pure logic for the turn-habit logger: outcome labeling and
the TurnLogger blinker->watch->resolve state machine, which records the whole turn
PATH (a rolling pre-arm approach buffer + sampled points through the maneuver),
plus a buffered CSV writer. The path (a per-maneuver position cloud / curve) is the
data a later turn-assist "database" needs - a single entry point can't locate a
trigger. Collect-first: nothing consumes this yet.
"""
import csv
import math
import os
from collections import deque
from dataclasses import dataclass

from openpilot.common.constants import CV
from openpilot.common.swaglog import cloudlog

# --- tunables (starting points; refined from collected data) ---
TURN_SPEED_MAX = 40 * CV.KPH_TO_MS   # above this we don't arm (highway)
TURN_SPEED_MIN = 3 * CV.KPH_TO_MS    # below this we don't sample (standstill -> stale GPS)
WATCH_TIMEOUT = 25.0                 # s; covers waiting at a light with blinker on
TURN_ANGLE_MIN = 45.0                # deg; |Δheading| above this => a turn
STRAIGHT_ANGLE_MAX = 20.0            # deg; |Δheading| below this => straight
FLUSH_DT = 300.0                     # s; CSV flush cadence (also flushed on shutdown)
GPS_ACC_MAX = 10.0                   # m; max horizontal accuracy to trust a fix
PATH_STRIDE = 5                      # log a path point every Nth 20 Hz frame (~4 Hz)
PRE_ARM_SAMPLES = 20                 # rolling approach points kept before arm (~5 s at 4 Hz)


def yaw_heading_change(yaw_rate_sum_rad: float) -> float:
  """Integrated device yaw (summed yaw_rate*dt, radians) -> degrees. Device
  angularVelocityDevice.z is +clockwise, so positive = RIGHT (verified against the
  GPS exit-minus-entry bearing on real drives)."""
  return math.degrees(yaw_rate_sum_rad)


def label_outcome(heading_change_deg: float) -> str:
  """Hindsight label from the resolved heading change (positive = right, clockwise)."""
  if heading_change_deg > TURN_ANGLE_MIN:
    return "right"
  if heading_change_deg < -TURN_ANGLE_MIN:
    return "left"
  if abs(heading_change_deg) < STRAIGHT_ANGLE_MAX:
    return "straight"
  return "ambiguous"


@dataclass
class TurnSample:
  t: float
  unix_ms: int
  lat: float
  lon: float
  bearing_deg: float
  gps_valid: bool
  gps_accuracy: float
  v_ego: float
  left_blinker: bool
  right_blinker: bool
  gear_ok: bool
  yaw_rate: float


TURN_LOG_COLUMNS = [
  "maneuver_id", "seq", "ts", "lat", "lon", "bearing", "v_ego",
  "yaw_rate", "gps_accuracy", "blinker", "outcome", "heading_change",
]


class TurnLogger:
  """Blinker-triggered turn observation state machine that captures the whole turn
  path. update(sample) returns a list of path row dicts when a maneuver resolves,
  else None. A rolling pre-arm approach buffer is prepended on arm so the curve
  isn't truncated when the blinker comes on late."""

  def __init__(self):
    self._watching = False
    self._require_blinker_off = False  # set after a timeout resolve with blinker still on
    self._frame = 0
    self._pre: deque = deque(maxlen=PRE_ARM_SAMPLES)  # rolling approach buffer
    self._path: list = []
    self._entry = None
    self._prev_t = 0.0
    self._yaw_sum = 0.0

  def _blinker_dir(self, s: TurnSample):
    if s.left_blinker and not s.right_blinker:
      return "left"
    if s.right_blinker and not s.left_blinker:
      return "right"
    return None

  def _sample_ok(self, s: TurnSample) -> bool:
    return s.gps_valid and s.v_ego > TURN_SPEED_MIN

  def update(self, s: TurnSample):
    self._frame += 1
    sample_now = (self._frame % PATH_STRIDE == 0)

    if not self._watching:
      if sample_now and self._sample_ok(s):
        self._pre.append(s)  # keep a rolling approach buffer for the next maneuver
      if self._require_blinker_off:
        if self._blinker_dir(s) is None:
          self._require_blinker_off = False
        return None
      if (self._blinker_dir(s) is not None and TURN_SPEED_MIN < s.v_ego < TURN_SPEED_MAX
          and s.gear_ok and s.gps_valid):
        self._watching = True
        self._entry = s
        self._prev_t = s.t
        self._yaw_sum = 0.0
        self._path = list(self._pre)  # seed with the approach curve
        if not self._path or self._path[-1] is not s:
          self._path.append(s)        # ensure the arm point is in the path
      return None

    # watching: integrate heading (yaw) for the label, and sample the path
    dt = max(0.0, s.t - self._prev_t)
    self._prev_t = s.t
    self._yaw_sum += s.yaw_rate * dt
    if sample_now and self._sample_ok(s):
      self._path.append(s)

    blinker_off = self._blinker_dir(s) is None
    if blinker_off or (s.t - self._entry.t) >= WATCH_TIMEOUT:
      if not blinker_off:
        # timed out with the blinker still on: don't re-arm until it clears
        self._require_blinker_off = True
      if self._sample_ok(s) and (not self._path or self._path[-1] is not s):
        self._path.append(s)          # capture the exit point
      return self._resolve()
    return None

  def _resolve(self):
    e = self._entry
    hc_val = yaw_heading_change(self._yaw_sum)
    outcome = label_outcome(hc_val)
    hc = round(hc_val, 2)
    blinker = self._blinker_dir(e)
    mid = round(e.unix_ms / 1000.0, 3) if e.unix_ms > 0 else round(e.t, 3)
    rows = []
    for i, p in enumerate(self._path):
      pts = round(p.unix_ms / 1000.0, 3) if p.unix_ms > 0 else round(p.t, 3)
      rows.append({
        "maneuver_id": mid, "seq": i, "ts": pts,
        "lat": p.lat, "lon": p.lon, "bearing": round(p.bearing_deg, 1),
        "v_ego": round(p.v_ego, 2), "yaw_rate": round(p.yaw_rate, 4),
        "gps_accuracy": round(p.gps_accuracy, 2),
        "blinker": blinker, "outcome": outcome, "heading_change": hc,
      })
    self._watching = False
    self._path = []
    return rows


class TurnCsvWriter:
  """Buffered, append-only CSV writer. All I/O failures are swallowed (rows
  dropped) so the logger can never raise into the daemon loop."""

  def __init__(self, path: str):
    self.path = path
    self._buf: list[dict] = []
    self._last_flush = 0.0

  def append(self, row: dict):
    self._buf.append(row)

  def extend(self, rows):
    self._buf.extend(rows)

  def maybe_flush(self, now: float):
    if now - self._last_flush >= FLUSH_DT:
      self.flush()
      self._last_flush = now

  def flush(self):
    if not self._buf:
      return
    try:
      os.makedirs(os.path.dirname(self.path), exist_ok=True)
      new = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
      with open(self.path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TURN_LOG_COLUMNS, extrasaction="ignore")
        if new:
          w.writeheader()
        w.writerows(self._buf)
      self._buf.clear()
    except Exception:
      cloudlog.exception("turnd: CSV flush failed")
      self._buf.clear()  # drop; never let the buffer grow unbounded
