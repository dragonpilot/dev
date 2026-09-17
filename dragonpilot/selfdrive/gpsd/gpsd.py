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

GPS Location Service - GPS + livePose fusion with Kalman filter.
- Position: 2D Kalman filter fusing GPS with livePose velocity
- Bearing: livePose yaw + GPS-calibrated offset (with slow drift correction)
"""
import numpy as np
from openpilot.cereal import messaging, custom

from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.common.transformations.coordinates import LocalCoord
from openpilot.common.swaglog import cloudlog
from openpilot.common.gps import get_gps_location_service


def wrap_angle(x):
  return np.arctan2(np.sin(x), np.cos(x))


class GPSKalman:
  """
  3D Kalman filter for GPS fusion.
  State: [north, east, yaw_offset] where yaw_offset calibrates livePose to true north.
  Adapts automatically to GPS accuracy (ublox vs qcom).
  """
  # Process noise
  POS_NOISE = 0.5      # m²/s - position uncertainty growth (fallback when livePose std unknown)
  YAW_NOISE = 0.0001   # rad²/s - yaw offset drift (~0.6°/min)
  VEL_STD_MIN = 0.05   # m/s - floor on livePose velocity std used for adaptive noise

  def __init__(self):
    self.x = np.zeros(3)         # [north, east, yaw_offset]
    self.P = np.diag([100.0, 100.0, 1.0])  # uncertainty (position high, yaw moderate)

  def get_yaw(self, pose_yaw):
    """Get calibrated yaw from pose yaw + estimated offset."""
    return wrap_angle(pose_yaw + self.x[2])

  def predict(self, vel_ned, dt, vel_std=None):
    """Predict state using velocity from livePose.

    vel_std: 1-sigma horizontal speed uncertainty from livePose (m/s). When given,
    the position process noise is derived from it (variance of the position
    increment = var(velocity) * dt^2), so dead-reckoning is trusted exactly as much
    as livePose trusts its own velocity. Falls back to POS_NOISE when unavailable.
    """
    # Position prediction
    self.x[0] += vel_ned[0] * dt
    self.x[1] += vel_ned[1] * dt
    # yaw_offset: no change (constant), just add process noise

    # Position process noise: adaptive from livePose velocity uncertainty when known
    if vel_std is not None:
      pos_var = (max(vel_std, self.VEL_STD_MIN) * dt) ** 2
    else:
      pos_var = self.POS_NOISE * dt

    # Process noise - more yaw drift when stopped (gyro drift accumulates)
    speed = np.linalg.norm(vel_ned[:2])
    yaw_noise = self.YAW_NOISE if speed > 1.0 else self.YAW_NOISE * 10
    Q = np.diag([pos_var, pos_var, yaw_noise * dt])
    self.P += Q

  def update_position(self, gps_ned, gps_accuracy):
    """Update position with GPS measurement."""
    # Observation matrix: observe [north, east], not yaw_offset
    H = np.array([[1, 0, 0],
                  [0, 1, 0]])

    # Measurement noise from GPS accuracy
    R = np.eye(2) * (gps_accuracy ** 2)

    # Innovation
    z = gps_ned[:2]
    y = z - H @ self.x

    # Kalman gain
    S = H @ self.P @ H.T + R
    det = S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0]
    if abs(det) < 1e-10:
      return
    S_inv = np.array([[S[1, 1], -S[0, 1]],
                      [-S[1, 0], S[0, 0]]]) / det
    K = self.P @ H.T @ S_inv

    # Update
    self.x += K @ y
    self.P = (np.eye(3) - K @ H) @ self.P
    self._ensure_positive_definite()

  def update_yaw(self, gps_bearing, pose_yaw, bearing_std):
    """Update yaw_offset with GPS bearing measurement."""
    # Observation: yaw_offset = gps_bearing - pose_yaw
    # H = [0, 0, 1] - we observe yaw_offset directly
    H = np.array([[0, 0, 1]])

    # Measurement noise from GPS bearing uncertainty
    R = np.array([[bearing_std ** 2]])

    # Expected yaw_offset from GPS
    observed_offset = wrap_angle(gps_bearing - pose_yaw)

    # Innovation (handle angle wrapping)
    predicted_offset = self.x[2]
    y = np.array([wrap_angle(observed_offset - predicted_offset)])

    # Kalman gain
    S = H @ self.P @ H.T + R
    K = self.P @ H.T / S[0, 0]

    # Update
    self.x += (K @ y).flatten()
    self.x[2] = wrap_angle(self.x[2])  # keep yaw_offset wrapped
    self.P = (np.eye(3) - K @ H) @ self.P
    self._ensure_positive_definite()

  def _ensure_positive_definite(self):
    """Ensure covariance stays positive definite. Reinit if corrupted."""
    self.P = (self.P + self.P.T) / 2
    if np.any(np.diag(self.P) < 0):
      cloudlog.warning("gpsd: negative covariance detected, reinitializing filter")
      self.P = np.diag([100.0, 100.0, 1.0])
      return
    min_var = np.array([0.01, 0.01, 0.0001])  # minimum variances
    for i in range(3):
      self.P[i, i] = max(self.P[i, i], min_var[i])

  def reset(self, pos, yaw_offset=None):
    """Reset to known position, optionally with yaw offset."""
    self.x[0] = pos[0]
    self.x[1] = pos[1]
    if yaw_offset is not None:
      self.x[2] = yaw_offset
      self.P = np.diag([1.0, 1.0, 0.1])  # low uncertainty
    else:
      self.P = np.diag([1.0, 1.0, self.P[2, 2]])  # keep yaw uncertainty

  @property
  def pos(self):
    """Position [north, east]."""
    return self.x[:2]

  @property
  def yaw_offset(self):
    """Yaw offset estimate."""
    return self.x[2]

  @property
  def pos_uncertainty(self):
    """Position uncertainty (meters)."""
    return np.sqrt(max(0.0, (self.P[0, 0] + self.P[1, 1]) / 2))

  @property
  def yaw_uncertainty(self):
    """Yaw offset uncertainty (radians)."""
    return np.sqrt(max(0.0, self.P[2, 2]))


class LiveGPS:
  """
  GPS + livePose fusion with 3D Kalman filter.
  - Position: Kalman filter fusing GPS with livePose velocity
  - Bearing: Kalman-estimated yaw_offset + livePose yaw
  """
  GPS_MIN_SPEED = 5.0             # m/s (18 km/h) - need speed for reliable GPS bearing
  GPS_MAX_ACCURACY = 50.0         # m - reject very bad GPS
  BEARING_STD_BASE = 0.1          # rad (~6°) - base GPS bearing uncertainty
  BEARING_STD_PER_ACC = 0.02      # rad per meter of GPS accuracy

  def __init__(self):
    # pose inputs
    self.orientation_ned = np.zeros(3)
    self.vel_device = np.zeros(3)
    self.vel_device_std = np.zeros(3)  # livePose velocity 1-sigma (device frame)

    # gps inputs
    self.gps = None
    self.last_gps_t = 0.0
    self.unix_timestamp_millis = 0

    # Kalman filter: [north, east, yaw_offset]
    self.origin = None            # LocalCoord of first GPS fix
    self.kf = GPSKalman()         # 3D Kalman filter
    self.altitude = 0.0           # altitude tracked separately (1D)
    self.last_gps_update_t = 0.0  # track when we last updated Kalman with GPS

    # timing
    self.last_t = None
    self.last_pose_yaw = None     # for yaw rate calculation
    self.live_pose_ok = False     # for monitoring

  # -----------------------------
  # inputs
  # -----------------------------

  def handle_pose(self, pose):
    if pose.orientationNED.valid:
      self.orientation_ned[:] = [
        pose.orientationNED.x,
        pose.orientationNED.y,
        pose.orientationNED.z,
      ]
    if pose.velocityDevice.valid:
      self.vel_device[:] = [
        pose.velocityDevice.x,
        pose.velocityDevice.y,
        pose.velocityDevice.z,
      ]
      self.vel_device_std[:] = [
        pose.velocityDevice.xStd,
        pose.velocityDevice.yStd,
        pose.velocityDevice.zStd,
      ]
    # For monitoring
    self.live_pose_ok = pose.orientationNED.valid and pose.velocityDevice.valid

  def handle_gps(self, t, gps):
    if gps.horizontalAccuracy > 0 and gps.horizontalAccuracy > self.GPS_MAX_ACCURACY:
      return
    if abs(gps.latitude) < 0.1 or abs(gps.longitude) < 0.1:
      return

    self.gps = gps
    self.last_gps_t = t
    self.unix_timestamp_millis = gps.unixTimestampMillis

  def _gps_course(self):
    """Heading + ground speed from GPS. Prefers the NED velocity vector (vNED):
    its Doppler course is far cleaner than position-derived bearing, and its
    uncertainty follows the receiver's speedAccuracy. Falls back to the reported
    bearingDeg when vNED is unavailable.
    Returns (course_rad, ground_speed_mps, course_std_rad)."""
    gps = self.gps
    vned = list(gps.vNED) if len(gps.vNED) >= 2 else []
    if len(vned) >= 2 and (abs(vned[0]) > 1e-3 or abs(vned[1]) > 1e-3):
      v_n, v_e = vned[0], vned[1]
      ground_speed = float(np.hypot(v_n, v_e))
      course = float(np.arctan2(v_e, v_n))  # NED: 0 = north, + = east
      # angular 1-sigma from speed accuracy: dtheta ~ speedAccuracy / speed
      speed_acc = gps.speedAccuracy if gps.speedAccuracy > 0 else 1.0
      course_std = float(np.clip(speed_acc / max(ground_speed, 0.5),
                                 self.BEARING_STD_BASE, 1.0))
      return course, ground_speed, course_std
    # fallback: receiver-reported bearing + accuracy-scaled uncertainty
    gps_acc = gps.horizontalAccuracy if gps.horizontalAccuracy > 0 else 15.0
    course_std = self.BEARING_STD_BASE + self.BEARING_STD_PER_ACC * gps_acc
    return float(np.radians(gps.bearingDeg)), float(gps.speed), course_std

  # -----------------------------
  # core update
  # -----------------------------

  def update(self, t):
    dt = (t - self.last_t) if self.last_t else 0.05
    self.last_t = t

    if self.gps is None:
      return

    # initialize origin on first GPS
    if self.origin is None:
      self.origin = LocalCoord.from_geodetic([self.gps.latitude, self.gps.longitude, self.gps.altitude])
      self.kf.reset(np.zeros(2))
      self.altitude = self.gps.altitude
      cloudlog.info(f"gpsd: origin set at {self.gps.latitude:.6f}, {self.gps.longitude:.6f}")
      return

    # get current yaw from Kalman (pose_yaw + estimated yaw_offset)
    pose_yaw = self.orientation_ned[2]
    yaw = self.kf.get_yaw(pose_yaw)

    # transform velocity from device frame to NED
    cos_yaw, sin_yaw = np.cos(yaw), np.sin(yaw)
    vel_ned = np.array([
      self.vel_device[0] * cos_yaw - self.vel_device[1] * sin_yaw,
      self.vel_device[0] * sin_yaw + self.vel_device[1] * cos_yaw,
      -self.vel_device[2]
    ])

    # Kalman predict: propagate position using livePose velocity
    # Skip prediction when stationary (GPS wanders, IMU drifts)
    # Threshold 0.1 m/s - above noise (~0.04) but catches actual stops
    speed = np.linalg.norm(self.vel_device[:2])
    is_moving = speed > 0.1
    if is_moving:
      # horizontal speed 1-sigma from livePose (rotation-invariant) -> adaptive noise
      vel_std = float(np.linalg.norm(self.vel_device_std[:2]))
      self.kf.predict(vel_ned, dt, vel_std=vel_std if vel_std > 0.0 else None)

    # Kalman update: only on NEW GPS data (not stale)
    # Skip position update when stopped - prevents GPS wander from moving position
    new_gps = self.last_gps_t > self.last_gps_update_t
    if new_gps and is_moving:
      self.last_gps_update_t = self.last_gps_t
      gps_ned = self.origin.geodetic2ned([self.gps.latitude, self.gps.longitude, self.gps.altitude])
      gps_accuracy = self.gps.horizontalAccuracy if self.gps.horizontalAccuracy > 0 else 15.0

      # Check for hard reset (large error after tunnel/GPS loss)
      error = np.linalg.norm(gps_ned[:2] - self.kf.pos)
      if error > 100.0 and gps_accuracy < 20.0:
        # GPS is good but we're far off - full reset (new origin, fresh Kalman)
        yaw_err_deg = np.degrees(self.kf.yaw_uncertainty)
        cloudlog.warning(f"gpsd: hard reset, error={error:.1f}m, yaw_unc={yaw_err_deg:.1f}°, gps_acc={gps_accuracy:.1f}m, livePoseOk={self.live_pose_ok}")
        # Reset origin to current GPS - starts fresh
        self.origin = LocalCoord.from_geodetic([self.gps.latitude, self.gps.longitude, self.gps.altitude])
        self.kf = GPSKalman()  # fresh Kalman filter
        self.kf.reset(np.zeros(2))  # position (0,0) at new origin
        self.altitude = self.gps.altitude
        return  # skip normal update this frame
      else:
        # Position update - adapts to GPS accuracy:
        # - ublox (2-5m): high gain, trusts GPS
        # - qcom (10-30m): low gain, trusts IMU more
        self.kf.update_position(gps_ned, gps_accuracy)

      # simple altitude tracking (no Kalman needed)
      self.altitude = 0.9 * self.altitude + 0.1 * self.gps.altitude

      # Yaw update from GPS *velocity* (Doppler course-over-ground): cleaner than
      # position-derived bearing and weighted by the receiver's speed accuracy.
      gps_course, ground_speed, course_std = self._gps_course()
      if ground_speed > self.GPS_MIN_SPEED:
        # compute yaw rate to check if driving straight
        yaw_rate = 0.0
        if self.last_pose_yaw is not None and dt > 0:
          yaw_rate = abs(wrap_angle(pose_yaw - self.last_pose_yaw)) / dt

        # GPS course is unreliable during turns - increase uncertainty
        bearing_std = course_std
        if yaw_rate > 0.1:  # turning - GPS course lags
          bearing_std *= 3.0

        self.kf.update_yaw(gps_course, pose_yaw, bearing_std)

    self.last_pose_yaw = pose_yaw

  # -----------------------------
  # output
  # -----------------------------

  def get_msg(self, log_mono_time):
    msg = messaging.new_message("liveGPS", valid=True)
    msg.logMonoTime = log_mono_time
    out = msg.liveGPS

    t = log_mono_time * 1e-9
    gps_fresh = self.gps is not None and (t - self.last_gps_t) < 5.0
    pos_initialized = self.origin is not None
    # yaw is calibrated when uncertainty < 0.5 rad (~30°)
    yaw_calibrated = self.kf.yaw_uncertainty < 0.5

    if pos_initialized:
      # position from Kalman filter (NED -> geodetic)
      pos_ned = np.array([self.kf.pos[0], self.kf.pos[1], self.altitude])
      geodetic = self.origin.ned2geodetic(pos_ned)
      out.latitude = float(geodetic[0])
      out.longitude = float(geodetic[1])
      out.altitude = float(geodetic[2])
      out.speed = float(np.linalg.norm(self.vel_device[:2]))

      # horizontalAccuracy from Kalman uncertainty
      out.horizontalAccuracy = float(self.kf.pos_uncertainty)
      out.verticalAccuracy = float(self.gps.verticalAccuracy) if hasattr(self.gps, 'verticalAccuracy') and self.gps.verticalAccuracy > 0 else 15.0

      # bearing from Kalman (pose_yaw + estimated yaw_offset)
      has_livePose = np.any(self.orientation_ned != 0)
      if yaw_calibrated and has_livePose and gps_fresh:
        yaw = self.kf.get_yaw(self.orientation_ned[2])
        out.bearingDeg = float(np.degrees(yaw) % 360)
        out.status = custom.LiveGPS.Status.valid
      else:
        # fallback to raw GPS bearing
        out.bearingDeg = float(self.gps.bearingDeg)
        out.status = custom.LiveGPS.Status.uncalibrated
    elif self.gps is not None:
      # have GPS but not initialized yet - pass through raw
      out.latitude = float(self.gps.latitude)
      out.longitude = float(self.gps.longitude)
      out.altitude = float(self.gps.altitude)
      out.speed = float(self.gps.speed)
      out.bearingDeg = float(self.gps.bearingDeg)
      out.horizontalAccuracy = float(self.gps.horizontalAccuracy) if self.gps.horizontalAccuracy > 0 else 20.0
      out.status = custom.LiveGPS.Status.uncalibrated
    else:
      out.status = custom.LiveGPS.Status.uninitialized

    # gpsOK = position is usable (bearing calibration tracked separately via status)
    out.gpsOK = gps_fresh and pos_initialized
    out.unixTimestampMillis = self.unix_timestamp_millis
    out.lastGpsTimestamp = int(self.last_gps_t * 1e9)

    # livePose health - for monitoring
    out.livePoseOk = self.live_pose_ok

    return msg

def main():
  import os
  params = Params()

  # EXT=1 forces gpsLocationExternal (ublox), EXT=0 forces gpsLocation (qcom)
  ext_override = os.environ.get("EXT")
  if ext_override == "1":
    gps_service = "gpsLocationExternal"
    cloudlog.info("gpsd: EXT=1, using gpsLocationExternal (ublox)")
  elif ext_override == "0":
    gps_service = "gpsLocation"
    cloudlog.info("gpsd: EXT=0, using gpsLocation (qcom)")
  else:
    gps_service = get_gps_location_service(params)

  pm = messaging.PubMaster(["liveGPS"])
  sm = messaging.SubMaster([gps_service, "deviceMotion"], ignore_alive=[gps_service])

  gps = LiveGPS()
  rk = Ratekeeper(20)

  while True:
    try:
      sm.update(0)

      if sm.logMonoTime["deviceMotion"] > 0:
        t = sm.logMonoTime["deviceMotion"] * 1e-9
        log_mono_time = sm.logMonoTime["deviceMotion"]
      else:
        log_mono_time = int(rk.frame * 1e9 / 20)
        t = log_mono_time * 1e-9

      if sm.updated[gps_service]:
        gps.handle_gps(t, sm[gps_service])

      if sm.updated["deviceMotion"] and sm.valid["deviceMotion"]:
        gps.handle_pose(sm["deviceMotion"])

      gps.update(t)
      pm.send("liveGPS", gps.get_msg(log_mono_time))

    except Exception:
      cloudlog.exception("gpsd: error in main loop")

    rk.keep_time()


if __name__ == "__main__":
  main()
