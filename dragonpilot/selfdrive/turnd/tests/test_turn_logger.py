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

Tests for the turn logger (turnd): sign convention (device yaw z is +clockwise =
right, verified vs GPS), outcome labeling, the blinker->watch->resolve state
machine, full-path capture with a pre-arm buffer, the CSV writer, and _build_sample
against real cereal messages.
"""
import math
import unittest


class TestYawHeading(unittest.TestCase):
  def test_yaw_heading_change(self):
    from dragonpilot.selfdrive.turnd.turn_logger import yaw_heading_change
    self.assertAlmostEqual(yaw_heading_change(math.radians(90)), 90.0)    # +yaw = right (clockwise)
    self.assertAlmostEqual(yaw_heading_change(-math.radians(45)), -45.0)  # -yaw = left


class TestOutcomeLabel(unittest.TestCase):
  def test_label_outcome(self):
    from dragonpilot.selfdrive.turnd.turn_logger import label_outcome
    self.assertEqual(label_outcome(90.0), "right")    # +heading_change = clockwise = right
    self.assertEqual(label_outcome(-90.0), "left")
    self.assertEqual(label_outcome(5.0), "straight")
    self.assertEqual(label_outcome(-10.0), "straight")
    self.assertEqual(label_outcome(30.0), "ambiguous")   # between STRAIGHT_ANGLE_MAX and TURN_ANGLE_MIN
    self.assertEqual(label_outcome(-30.0), "ambiguous")


def _sample(**kw):
  from dragonpilot.selfdrive.turnd.turn_logger import TurnSample
  base = dict(t=0.0, unix_ms=0, lat=37.0, lon=-122.0, bearing_deg=0.0, gps_valid=True,
              gps_accuracy=3.0, v_ego=5.0, left_blinker=False, right_blinker=False,
              gear_ok=True, yaw_rate=0.0)
  base.update(kw)
  return TurnSample(**base)


def _maneuver(yaw_rate, blinker="right", n=40, pre=0, pre_lat=1.0, arm_lat=2.0, unix_ms=0):
  """Build samples for one maneuver: `pre` moving approach frames (blinker off, at
  pre_lat), then `n` armed frames at `yaw_rate` (at arm_lat), then a blinker-off frame."""
  samples = []
  t = 0.0
  for _ in range(pre):
    samples.append(_sample(t=t, lat=pre_lat, unix_ms=unix_ms))
    t += 0.05
  bk = {"left_blinker": True} if blinker == "left" else {"right_blinker": True}
  for _ in range(n):
    samples.append(_sample(t=t, yaw_rate=yaw_rate, lat=arm_lat, unix_ms=unix_ms, **bk))
    t += 0.05
  samples.append(_sample(t=t, lat=arm_lat, unix_ms=unix_ms))  # blinker off -> resolve
  return samples


def _run(lg, samples):
  """Feed samples; return the last non-None result (the resolved path list), else None."""
  result = None
  for s in samples:
    r = lg.update(s)
    if r is not None:
      result = r
  return result


class TestTurnLogger(unittest.TestCase):
  def test_right_turn_resolves_path(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger
    rows = _run(TurnLogger(), _maneuver(+1.0, blinker="right"))  # +yaw = right
    self.assertIsInstance(rows, list)
    self.assertGreater(len(rows), 1)                     # a path, not a single point
    self.assertTrue(all(r["outcome"] == "right" for r in rows))
    self.assertTrue(all(r["blinker"] == "right" for r in rows))
    self.assertGreater(rows[0]["heading_change"], 45.0)  # positive = right
    self.assertEqual(len({r["maneuver_id"] for r in rows}), 1)          # one maneuver id
    self.assertEqual([r["seq"] for r in rows], list(range(len(rows))))  # ordered

  def test_left_turn_resolves_path(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger
    rows = _run(TurnLogger(), _maneuver(-1.0, blinker="left"))  # -yaw = left
    self.assertTrue(all(r["outcome"] == "left" for r in rows))
    self.assertLess(rows[0]["heading_change"], -45.0)

  def test_pre_arm_approach_is_prepended(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger
    # 15 approach frames (blinker off) at pre_lat before the turn at arm_lat
    rows = _run(TurnLogger(), _maneuver(+1.0, blinker="right", pre=15, pre_lat=1.0, arm_lat=2.0))
    self.assertEqual(rows[0]["lat"], 1.0)   # path starts in the approach, not at the blinker

  def test_no_start_when_fast(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger, TURN_SPEED_MAX
    lg = TurnLogger()
    self.assertIsNone(lg.update(_sample(left_blinker=True, v_ego=TURN_SPEED_MAX + 5)))
    self.assertIsNone(lg.update(_sample(t=0.2, left_blinker=False)))

  def test_no_start_when_gps_bad(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger
    lg = TurnLogger()
    self.assertIsNone(lg.update(_sample(left_blinker=True, gps_valid=False)))
    self.assertIsNone(lg.update(_sample(t=0.2, left_blinker=False)))

  def test_no_start_when_reverse(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger
    lg = TurnLogger()
    self.assertIsNone(lg.update(_sample(left_blinker=True, gear_ok=False)))
    self.assertIsNone(lg.update(_sample(t=0.2, left_blinker=False)))

  def test_no_start_when_stationary(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger
    lg = TurnLogger()
    self.assertIsNone(lg.update(_sample(left_blinker=True, v_ego=0.0)))
    self.assertIsNone(lg.update(_sample(t=0.2, left_blinker=False)))

  def test_timeout_resolves_straight(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger, WATCH_TIMEOUT
    lg = TurnLogger()
    self.assertIsNone(lg.update(_sample(t=0.0, left_blinker=True)))
    rows = lg.update(_sample(t=WATCH_TIMEOUT + 0.1, left_blinker=True, yaw_rate=0.0))
    self.assertIsInstance(rows, list)
    self.assertTrue(all(r["outcome"] == "straight" for r in rows))

  def test_stuck_blinker_yields_one_resolve(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger, WATCH_TIMEOUT
    lg = TurnLogger()
    self.assertIsNone(lg.update(_sample(t=0.0, left_blinker=True)))
    first = lg.update(_sample(t=WATCH_TIMEOUT + 0.1, left_blinker=True, yaw_rate=0.0))
    self.assertIsInstance(first, list)
    # blinker stays stuck on -> must NOT re-arm/emit again
    t = WATCH_TIMEOUT + 0.2
    resolves = []
    while t < 2 * WATCH_TIMEOUT + 1.0:
      r = lg.update(_sample(t=t, left_blinker=True, yaw_rate=0.0))
      if r is not None:
        resolves.append(r)
      t += 0.5
    self.assertEqual(len(resolves), 0)
    # once it clears, re-arm works
    self.assertIsNone(lg.update(_sample(t=t, left_blinker=False)))
    self.assertIsNone(lg.update(_sample(t=t + 0.1, left_blinker=True)))
    self.assertIsInstance(lg.update(_sample(t=t + 0.2, left_blinker=False)), list)

  def test_maneuver_id_uses_unix_ms(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger
    lg = TurnLogger()
    self.assertIsNone(lg.update(_sample(t=0.0, left_blinker=True, unix_ms=1_700_000_000_000)))
    rows = lg.update(_sample(t=1.0, left_blinker=False, unix_ms=1_700_000_001_000))
    self.assertAlmostEqual(rows[0]["maneuver_id"], 1_700_000_000.0, places=1)


class TestCsvWriter(unittest.TestCase):
  def test_extend_flush_and_header(self):
    import tempfile
    import os
    import csv
    from dragonpilot.selfdrive.turnd.turn_logger import TurnCsvWriter, TURN_LOG_COLUMNS
    d = tempfile.mkdtemp()
    p = os.path.join(d, "turn_log.csv")
    w = TurnCsvWriter(p)
    rows_in = []
    for i in range(2):
      r = dict.fromkeys(TURN_LOG_COLUMNS, 0)
      r["seq"] = i
      r["outcome"] = "right"
      rows_in.append(r)
    w.extend(rows_in)
    w.flush()
    with open(p) as f:
      rows = list(csv.DictReader(f))
    self.assertEqual(len(rows), 2)
    self.assertEqual(list(rows[0].keys()), TURN_LOG_COLUMNS)
    self.assertEqual([r["seq"] for r in rows], ["0", "1"])

  def test_write_failure_swallowed(self):
    from dragonpilot.selfdrive.turnd.turn_logger import TurnCsvWriter, TURN_LOG_COLUMNS
    w = TurnCsvWriter("/proc/nonexistent_dir/turn_log.csv")  # unwritable
    w.extend([dict.fromkeys(TURN_LOG_COLUMNS, 0)])
    w.flush()  # must NOT raise


class FakeSubMaster:
  """Minimal duck-typed SubMaster: real cereal message payloads keyed by service name."""

  def __init__(self, msgs: dict):
    self._msgs = msgs
    self.valid = dict.fromkeys(msgs, True)

  def __getitem__(self, key):
    return getattr(self._msgs[key], key)


class TestBuildSample(unittest.TestCase):
  def test_build_sample_with_real_cereal_messages(self):
    from openpilot.cereal import custom, messaging

    from dragonpilot.selfdrive.turnd.turnd import _build_sample

    gps_msg = messaging.new_message("liveGPS", valid=True)
    gps_msg.liveGPS.latitude = 37.0
    gps_msg.liveGPS.longitude = -122.0
    gps_msg.liveGPS.bearingDeg = 10.0
    gps_msg.liveGPS.horizontalAccuracy = 3.0
    gps_msg.liveGPS.status = custom.LiveGPS.Status.valid
    gps_msg.liveGPS.unixTimestampMillis = 1_700_000_000_000

    cs_msg = messaging.new_message("carState", valid=True)
    cs_msg.carState.vEgo = 5.0
    cs_msg.carState.leftBlinker = True
    cs_msg.carState.gearShifter = "drive"

    pose_msg = messaging.new_message("livePose", valid=True)
    pose_msg.livePose.angularVelocityDevice.z = 0.5

    sm = FakeSubMaster({"liveGPS": gps_msg, "carState": cs_msg, "livePose": pose_msg})

    sample = _build_sample(1.0, sm)

    self.assertTrue(sample.gps_valid)  # bug #1 regression: int(gps.status) used to raise here
    self.assertEqual(sample.unix_ms, 1_700_000_000_000)
    self.assertEqual(sample.left_blinker, True)
    self.assertAlmostEqual(sample.v_ego, 5.0)
    self.assertAlmostEqual(sample.yaw_rate, 0.5)
    self.assertTrue(sample.gear_ok)              # drive -> ok
    cs_msg.carState.gearShifter = "reverse"
    self.assertFalse(_build_sample(1.0, sm).gear_ok)  # reverse -> excluded (parking)

  def test_build_sample_inert_when_gpsd_absent(self):
    # gpsd not running: liveGPS never received (invalid / default). _build_sample
    # must not raise, and gps_valid must be False so the logger never arms.
    from openpilot.cereal import messaging

    from dragonpilot.selfdrive.turnd.turnd import _build_sample

    sm = FakeSubMaster({
      "liveGPS": messaging.new_message("liveGPS", valid=True),   # default status = uninitialized
      "carState": messaging.new_message("carState", valid=True),
      "livePose": messaging.new_message("livePose", valid=True),
    })
    sm.valid["liveGPS"] = False  # gpsd absent

    sample = _build_sample(1.0, sm)  # must not raise
    self.assertFalse(sample.gps_valid)


if __name__ == "__main__":
  unittest.main()
