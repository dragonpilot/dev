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

Tests for the turn predictor (turnd): habit-LUT build/predict over turn_log.csv.
"""
import unittest


def _row(lat, lon, entry_bearing, outcome):
  return {"lat": lat, "lon": lon, "entry_bearing": entry_bearing, "outcome": outcome}


class TestTurnPredictor(unittest.TestCase):
  def test_majority_habit_predicted(self):
    from dragonpilot.selfdrive.turnd.turn_predictor import build_table, predict
    # same intersection, same approach heading: 4 lefts, 1 straight
    rows = [_row(37.0, -122.0, 90.0, "left")] * 4 + [_row(37.0, -122.0, 90.0, "straight")]
    table = build_table(rows)
    out = predict(table, 37.0, -122.0, 90.0)
    self.assertIsNotNone(out)
    outcome, conf, n = out
    self.assertEqual(outcome, "left")
    self.assertEqual(n, 5)
    self.assertAlmostEqual(conf, 0.8)

  def test_below_min_count_is_none(self):
    from dragonpilot.selfdrive.turnd.turn_predictor import build_table, predict
    table = build_table([_row(37.0, -122.0, 90.0, "left")])  # only 1 visit
    self.assertIsNone(predict(table, 37.0, -122.0, 90.0))

  def test_opposite_approach_is_separate(self):
    from dragonpilot.selfdrive.turnd.turn_predictor import build_table, predict
    # same spot approached northbound (left) vs southbound (right) -> distinct keys
    rows = [_row(37.0, -122.0, 0.0, "left")] * 3 + [_row(37.0, -122.0, 180.0, "right")] * 3
    table = build_table(rows)
    self.assertEqual(predict(table, 37.0, -122.0, 0.0)[0], "left")
    self.assertEqual(predict(table, 37.0, -122.0, 180.0)[0], "right")

  def test_ambiguous_rows_ignored(self):
    from dragonpilot.selfdrive.turnd.turn_predictor import build_table, predict
    rows = [_row(37.0, -122.0, 90.0, "ambiguous")] * 5
    self.assertIsNone(predict(build_table(rows), 37.0, -122.0, 90.0))

  def test_gps_jitter_across_cell_boundary_still_matches(self):
    from dragonpilot.selfdrive.turnd.turn_predictor import build_table, predict
    # ~10 m north of the logged spot: neighbor-cell aggregation must still find it
    rows = [_row(37.0, -122.0, 90.0, "left")] * 3
    table = build_table(rows)
    self.assertEqual(predict(table, 37.0 + 10 / 111320.0, -122.0, 90.0)[0], "left")

  def test_unknown_location_is_none(self):
    from dragonpilot.selfdrive.turnd.turn_predictor import build_table, predict
    table = build_table([_row(37.0, -122.0, 90.0, "left")] * 3)
    self.assertIsNone(predict(table, 40.0, -74.0, 90.0))  # never been here


if __name__ == "__main__":
  unittest.main()
