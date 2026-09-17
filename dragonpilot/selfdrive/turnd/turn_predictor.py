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

Turn Predictor (turnd) - habit lookup over turn_log.csv. NOT a model: given a
logged location + approach heading, return the outcome you usually pick there.
Memorization only - predicts at intersections you've driven, nowhere else.
Prove this predicts your real routes before reaching for a geometry model.
"""
import csv
import math
from collections import Counter

# --- tunables ---
LOC_CELL_M = 20.0          # location grid cell size (~GPS accuracy); keys tolerate jitter
BEARING_BUCKET_DEG = 45.0  # approach-heading bucket; same spot, other direction -> other turn
MIN_COUNT = 3              # need this many visits before we call it a habit

PREDICT_OUTCOMES = ("left", "right", "straight")  # ignore "ambiguous" rows


def _loc_cell(lat: float, lon: float) -> tuple[int, int]:
  """Location -> integer grid cell (~LOC_CELL_M on a side)."""
  dlat = LOC_CELL_M / 111320.0
  dlon = LOC_CELL_M / (111320.0 * max(0.01, math.cos(math.radians(lat))))
  return round(lat / dlat), round(lon / dlon)


def _bearing_bucket(bearing_deg: float) -> int:
  return int((bearing_deg % 360.0) // BEARING_BUCKET_DEG)


def build_table(rows) -> dict:
  """rows: iterable of dicts (CSV or otherwise) with lat, lon, entry_bearing,
  outcome. Returns {(ci, cj, bb): Counter(outcome -> n)}."""
  table: dict[tuple[int, int, int], Counter] = {}
  for r in rows:
    outcome = r["outcome"]
    if outcome not in PREDICT_OUTCOMES:
      continue
    try:
      lat = float(r["lat"])
      lon = float(r["lon"])
      bearing = float(r["entry_bearing"])
    except (KeyError, ValueError, TypeError):
      continue
    ci, cj = _loc_cell(lat, lon)
    key = (ci, cj, _bearing_bucket(bearing))
    table.setdefault(key, Counter())[outcome] += 1
  return table


def predict(table: dict, lat: float, lon: float, bearing_deg: float):
  """Return (outcome, confidence, n) for this approach, or None if we've never
  been here enough. Aggregates the 3x3 location-cell neighborhood (same bearing
  bucket) so GPS jitter across a cell boundary doesn't lose the match."""
  ci, cj = _loc_cell(lat, lon)
  bb = _bearing_bucket(bearing_deg)
  hist: Counter = Counter()
  for di in (-1, 0, 1):
    for dj in (-1, 0, 1):
      c = table.get((ci + di, cj + dj, bb))
      if c:
        hist.update(c)
  n = sum(hist.values())
  if n < MIN_COUNT:
    return None
  outcome, count = hist.most_common(1)[0]
  return outcome, count / n, n


def load_table(path: str) -> dict:
  """Build a table straight from a turn_log.csv path. Missing file -> empty."""
  try:
    with open(path, newline="") as f:
      return build_table(csv.DictReader(f))
  except FileNotFoundError:
    return {}
