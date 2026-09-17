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

Offline report: for each mined turn, how early does each candidate signal fire before the yaw
apex? Answers 'which signal predicts the turn earliest/most reliably'.
"""
import csv
import sys
from collections import defaultdict
from statistics import median

SIGNALS = {
  "desire_turn_l": (0.5, lambda r: float(r["desire_turn_l"])),
  "desire_turn_r": (0.5, lambda r: float(r["desire_turn_r"])),
  "abs_model_curv": (0.05, lambda r: abs(float(r["model_curv"]))),
  "ll_gone_l": (0.5, lambda r: 1.0 - float(r["ll_prob_l"])),
  "ll_gone_r": (0.5, lambda r: 1.0 - float(r["ll_prob_r"])),
}


def _load_turns(path: str):
  turns = defaultdict(list)
  with open(path) as f:
    for r in csv.DictReader(f):
      turns[(r["segment"], r["maneuver_id"])].append(r)
  for rows in turns.values():
    rows.sort(key=lambda r: int(r["seq"]))
  return list(turns.values())


def report(mine_csv_path: str) -> dict:
  turns = _load_turns(mine_csv_path)
  leads = {k: [] for k in SIGNALS}
  hits = {k: 0 for k in SIGNALS}
  for rows in turns:
    ts = [float(r["t_rel"]) for r in rows]
    apex_i = max(range(len(rows)), key=lambda i: abs(float(rows[i]["yaw_rate"])))
    apex_t = ts[apex_i]
    for name, (thr, get) in SIGNALS.items():
      first = next((ts[i] for i in range(apex_i + 1) if get(rows[i]) >= thr), None)
      if first is not None:
        hits[name] += 1
        leads[name].append(apex_t - first)
  n = len(turns)
  return {
    "n_turns": n,
    "signals": {k: {"hit_rate": (hits[k] / n) if n else 0.0,
                    "median_lead_s": round(median(leads[k]), 3) if leads[k] else None}
                for k in SIGNALS},
  }


if __name__ == "__main__":
  import json
  path = sys.argv[1] if len(sys.argv) > 1 else "/data/media/0/dp_logs/turn_mined.csv"
  print(json.dumps(report(path), indent=2))
