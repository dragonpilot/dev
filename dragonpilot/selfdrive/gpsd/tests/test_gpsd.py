import math
from types import SimpleNamespace

import numpy as np

from openpilot.cereal import custom
from dragonpilot.selfdrive.gpsd.gpsd import GPSKalman, LiveGPS, wrap_angle

M_PER_DEG_LAT = 111_320.0


def _gps(lat=37.0, lon=-122.0, alt=10.0, acc=3.0, speed=0.0, bearing=0.0,
         vned=None, speed_acc=0.3, ts=1):
  if vned is None:  # default: NED velocity consistent with speed + bearing
    br = math.radians(bearing)
    vned = (speed * math.cos(br), speed * math.sin(br), 0.0)
  return SimpleNamespace(latitude=lat, longitude=lon, altitude=alt,
                         horizontalAccuracy=acc, verticalAccuracy=acc,
                         speed=speed, bearingDeg=bearing, vNED=list(vned),
                         speedAccuracy=speed_acc, bearingAccuracyDeg=1.0,
                         unixTimestampMillis=ts)


def _pose(yaw=0.0, vx=0.0, vy=0.0, vz=0.0, valid=True, tilt=0.0, vel_std=0.1):
  # `tilt` gives orientationNED a non-zero component so LiveGPS treats livePose as present
  return SimpleNamespace(
    orientationNED=SimpleNamespace(valid=valid, x=tilt, y=0.0, z=yaw,
                                   xStd=0.01, yStd=0.01, zStd=0.02),
    velocityDevice=SimpleNamespace(valid=valid, x=vx, y=vy, z=vz,
                                   xStd=vel_std, yStd=vel_std, zStd=vel_std),
  )


# ---- pure Kalman math ----

def test_wrap_angle():
  assert abs(wrap_angle(3 * math.pi) - (-math.pi)) < 1e-9 or abs(wrap_angle(3 * math.pi) - math.pi) < 1e-9
  assert abs(wrap_angle(0.3) - 0.3) < 1e-9
  assert abs(wrap_angle(-0.3) + 0.3) < 1e-9


def test_kalman_position_converges_and_tightens():
  kf = GPSKalman()
  kf.reset(np.zeros(2))
  u0 = kf.pos_uncertainty
  target = np.array([5.0, -3.0])
  for _ in range(60):
    kf.update_position(target, 3.0)
  assert kf.pos_uncertainty < u0                       # measurements reduce uncertainty
  assert np.linalg.norm(kf.pos - target) < 1.0         # converges to the measurement


def test_kalman_yaw_calibrates():
  kf = GPSKalman()
  kf.reset(np.zeros(2))
  assert kf.yaw_uncertainty >= 0.5                     # starts uncalibrated
  true_offset = 0.3
  for _ in range(100):
    kf.update_yaw(gps_bearing=true_offset, pose_yaw=0.0, bearing_std=0.15)
  assert kf.yaw_uncertainty < 0.5                      # becomes calibrated
  assert abs(wrap_angle(kf.yaw_offset - true_offset)) < 0.05


def test_adaptive_process_noise_scales_with_vel_std():
  # #1: position uncertainty growth tracks the livePose velocity std
  def _fresh():
    kf = GPSKalman()
    kf.reset(np.zeros(2))
    return kf
  lo, hi, fb = _fresh(), _fresh(), _fresh()
  vel = np.array([10.0, 0.0, 0.0])
  for _ in range(20):
    lo.predict(vel, 0.05, vel_std=0.05)   # confident livePose velocity
    hi.predict(vel, 0.05, vel_std=3.0)    # uncertain livePose velocity
    fb.predict(vel, 0.05)                 # vel_std=None -> fixed POS_NOISE fallback
  assert hi.pos_uncertainty > lo.pos_uncertainty   # more velocity doubt -> more position doubt
  assert fb.pos_uncertainty > lo.pos_uncertainty   # fallback still grows (regression guard)


# ---- LiveGPS end-to-end (exercises the cereal liveGPS message) ----

def test_get_msg_uninitialized():
  msg = LiveGPS().get_msg(1_000_000)
  assert msg.liveGPS.status == custom.LiveGPS.Status.uninitialized
  assert msg.liveGPS.gpsOK is False


def test_stationary_initializes_and_passes_position():
  g = LiveGPS()
  t = 0.0
  for i in range(20):
    t = i * 0.05
    g.handle_pose(_pose(vx=0.0))                       # not moving
    g.handle_gps(t, _gps(lat=37.0, lon=-122.0, ts=i))
    g.update(t)
  out = g.get_msg(int(t * 1e9)).liveGPS
  assert out.gpsOK is True                             # fresh GPS + origin set
  assert abs(out.latitude - 37.0) < 1e-4
  assert abs(out.longitude + 122.0) < 1e-4
  assert out.status == custom.LiveGPS.Status.uncalibrated  # bearing can't calibrate at standstill


def test_moving_calibrates_bearing_and_reports_valid():
  g = LiveGPS()
  t = 0.0
  for i in range(400):
    t = i * 0.05
    dist_north = 10.0 * t                              # GPS advances north, consistent with velocity
    lat = 37.0 + dist_north / M_PER_DEG_LAT
    g.handle_pose(_pose(yaw=0.0, vx=10.0, tilt=0.05))  # heading north, livePose present
    g.handle_gps(t, _gps(lat=lat, lon=-122.0, acc=3.0, speed=10.0, bearing=0.0, ts=i))
    g.update(t)

  out = g.get_msg(int(t * 1e9)).liveGPS
  assert g.kf.yaw_uncertainty < 0.5                    # bearing calibrated
  assert out.status == custom.LiveGPS.Status.valid
  assert out.gpsOK is True
  assert out.latitude > 37.0                           # tracked northward motion
  assert out.bearingDeg < 5.0 or out.bearingDeg > 355.0  # heading ~north


def test_uses_gps_velocity_over_stale_bearing_for_heading():
  # #2: heading must follow GPS velocity (vNED), not a wrong reported bearingDeg
  g = LiveGPS()
  t = 0.0
  for i in range(400):
    t = i * 0.05
    lat = 37.0 + (10.0 * t) / M_PER_DEG_LAT
    g.handle_pose(_pose(yaw=0.0, vx=10.0, tilt=0.05))
    # bearingDeg deliberately WRONG (180); vNED says due north -> heading tracks vNED
    g.handle_gps(t, _gps(lat=lat, lon=-122.0, acc=3.0, speed=10.0, bearing=180.0,
                         vned=(10.0, 0.0, 0.0), speed_acc=0.2, ts=i))
    g.update(t)
  out = g.get_msg(int(t * 1e9)).liveGPS
  assert g.kf.yaw_uncertainty < 0.5
  assert out.bearingDeg < 5.0 or out.bearingDeg > 355.0  # ~north (vNED), not 180 (bearingDeg)
