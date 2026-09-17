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

Turn Assist Logger daemon - records low-speed turn habits to CSV for model training.
"""
import os
import time

from openpilot.cereal import messaging, custom
from opendbc.car.structs import car
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog

from dragonpilot.selfdrive.turnd.turn_logger import TurnLogger, TurnCsvWriter, TurnSample, GPS_ACC_MAX

# Dedicated dp dir on the persistent media partition — OUTSIDE realdata/ so it doesn't
# collide with loggerd's uploader/deleter (which assume realdata entries are segment dirs).
TURN_LOG_PATH = "/data/media/0/dp_logs/turn_log.csv"
_OLD_TURN_LOG = "/data/media/0/realdata/turn_log.csv"   # pre-move location; migrated on start


def _migrate_old():
  # One-time relocation of a pre-existing turn_log.csv from the old realdata/ location.
  try:
    if os.path.exists(_OLD_TURN_LOG) and not os.path.exists(TURN_LOG_PATH):
      os.makedirs(os.path.dirname(TURN_LOG_PATH), exist_ok=True)
      os.replace(_OLD_TURN_LOG, TURN_LOG_PATH)
  except Exception:
    cloudlog.exception("turnd: migrate failed")


def _build_sample(t, sm) -> TurnSample:
  gps = sm["liveGPS"]
  cs = sm["carState"]
  pose = sm["livePose"]

  gps_valid = bool(sm.valid["liveGPS"]) and gps.status == custom.LiveGPS.Status.valid and gps.horizontalAccuracy < GPS_ACC_MAX
  gear_ok = cs.gearShifter not in (car.CarState.GearShifter.reverse,
                                   car.CarState.GearShifter.park,
                                   car.CarState.GearShifter.neutral)

  return TurnSample(
    t=t, unix_ms=gps.unixTimestampMillis, lat=gps.latitude, lon=gps.longitude,
    bearing_deg=gps.bearingDeg, gps_valid=gps_valid, gps_accuracy=gps.horizontalAccuracy,
    v_ego=cs.vEgo, left_blinker=cs.leftBlinker, right_blinker=cs.rightBlinker,
    gear_ok=gear_ok, yaw_rate=pose.angularVelocityDevice.z,
  )


def _run():
  # Always logs in the background (onroad) — no opt-in toggle.
  # liveGPS is in ignore_alive: if gpsd isn't running, sm stays usable and
  # gps_valid just stays False (no arming), so turnd is inert, never broken.
  sm = messaging.SubMaster(["liveGPS", "carState", "livePose"], ignore_alive=["liveGPS"])
  _migrate_old()
  logger = TurnLogger()
  writer = TurnCsvWriter(TURN_LOG_PATH)
  rk = Ratekeeper(20)

  cloudlog.info("turnd started")
  try:
    while True:
      try:
        sm.update(0)
        if sm.updated["carState"]:
          now = time.monotonic()
          rows = logger.update(_build_sample(now, sm))
          if rows:
            writer.extend(rows)
          writer.maybe_flush(now)
      except Exception:
        cloudlog.exception("turnd: error in main loop")
      rk.keep_time()
  finally:
    # manager stops us with SIGINT on offroad/shutdown (5s grace) -> KeyboardInterrupt
    # lands here; write the buffered block so end-of-drive events aren't lost.
    writer.flush()


def main():
  # turnd is non-critical and must NEVER take the system down. If this process
  # exits, selfdrived flags processNotRunning (NO_ENTRY / SOFT_DISABLE) and
  # blocks engagement. So never propagate out of main: swallow any fatal
  # (setup) error, stay alive, and retry. The per-cycle loop above handles
  # per-frame errors without tearing down setup.
  while True:
    try:
      _run()
    except Exception:
      cloudlog.exception("turnd: fatal error; retrying in 5s")
    time.sleep(5)


if __name__ == "__main__":
  main()
