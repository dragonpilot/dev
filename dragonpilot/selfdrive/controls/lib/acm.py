"""
Copyright (c) 2025, Rick Lan

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

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import atexit
import os
import time
import numpy as np
from opendbc.car.structs import car
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog

# Configuration parameters
SPEED_RATIO = 0.98  # Must be within 2% over cruise speed
TTC_THRESHOLD = 3.0  # seconds - disable ACM when lead is within this time

# Emergency thresholds - IMMEDIATELY disable ACM
EMERGENCY_TTC = 2.0  # seconds - emergency situation
EMERGENCY_RELATIVE_SPEED = 10.0  # m/s (~36 km/h closing speed - only for rapid closing)
EMERGENCY_DECEL_THRESHOLD = -1.5  # m/s² - if MPC wants this much braking, emergency disable

# Safety cooldown after lead detection
LEAD_COOLDOWN_TIME = 0.5  # seconds - brief cooldown to handle sensor glitches

# Speed-based distance scaling - more practical for real traffic
SPEED_BP = [0., 10., 20., 30.]  # m/s (0, 36, 72, 108 km/h)
MIN_DIST_V = [15., 20., 25., 30.]  # meters - closer to original 25m baseline


# --- Coast/drag data logger (collect-only) ---------------------------------
# Records (v_ego, a_ego, sin_pitch) ONLY during a clean freewheel: no gas/brake,
# OP not commanding accel, in drive, straight, moving, and sustained a beat for
# steady-state. On flat ground a_ego = -drag(v) directly; sin_pitch lets an offline
# fit filter flat / remove gravity to identify this car's coast (rolling + aero).
# Feeds a future per-car coast model; nothing in the controller reads it yet.
# Writes to the dp media dir, OUTSIDE realdata/ (uploader/deleter never walk it).
COAST_LOG_PATH = "/data/media/0/dp_logs/coast_log.csv"
COAST_LOG_HEADER = "# dp_coast_log v1"
COAST_LOG_COLUMNS = "v_ego,a_ego,sin_pitch"
COAST_V_MIN = 5.0           # m/s; below this, coast is dominated by creep/drivetrain
COAST_ACCEL_NEUTRAL = 0.05  # m/s²; |OP commanded accel| under this = not driving/braking
COAST_STEER_MAX = 5.0       # deg; straight-ahead only (avoid cornering scrub)
COAST_SETTLE = 1.0          # s of continuous coast before trusting steady-state
COAST_FLUSH_DT = 60.0       # s; append cadence (also flushed on shutdown)


class CoastLogger:
  """Collect-only freewheel-coast sampler for offline per-car drag identification.
  Never raises into the planner; all I/O is swallowed."""

  def __init__(self, path=COAST_LOG_PATH):
    self._path = path
    self._buf: list[tuple[float, float, float]] = []
    self._coast_frames = 0
    self._frames = 0
    self._settle = max(1, int(COAST_SETTLE / DT_MDL))
    self._flush_every = max(1, int(COAST_FLUSH_DT / DT_MDL))
    atexit.register(self._flush)  # flush end-of-drive samples on shutdown (SIGINT grace)

  def _coasting(self, sm) -> bool:
    cs = sm['carState']
    cc = sm['carControl']
    if len(cc.orientationNED) != 3:
      return False
    return (not cs.gasPressed and not cs.brakePressed
            and abs(cc.actuators.accel) < COAST_ACCEL_NEUTRAL
            and cs.gearShifter == car.CarState.GearShifter.drive
            and cs.vEgo > COAST_V_MIN
            and abs(cs.steeringAngleDeg) < COAST_STEER_MAX)

  def update(self, sm) -> None:
    try:
      if not self._coasting(sm):
        self._coast_frames = 0
        return
      self._coast_frames += 1
      if self._coast_frames < self._settle:  # wait for steady-state
        return
      cs = sm['carState']
      sin_pitch = float(np.sin(sm['carControl'].orientationNED[1]))
      self._buf.append((cs.vEgo, cs.aEgo, sin_pitch))
      self._frames += 1
      if self._buf and self._frames % self._flush_every == 0:
        self._flush()
    except Exception:
      cloudlog.exception("CoastLogger: update failed")

  def _flush(self) -> None:
    rows, self._buf = self._buf, []  # take + clear first so RAM stays bounded
    if not rows:
      return
    try:
      os.makedirs(os.path.dirname(self._path), exist_ok=True)
      new = not os.path.exists(self._path) or os.path.getsize(self._path) == 0
      with open(self._path, "a") as f:
        if new:
          f.write(COAST_LOG_HEADER + "\n" + COAST_LOG_COLUMNS + "\n")
        f.writelines(f"{v:.3f},{a:.3f},{s:.5f}\n" for v, a, s in rows)
    except Exception:
      cloudlog.exception("CoastLogger: flush failed")


class ACM:
  def __init__(self):
    self.enabled = False
    self._is_speed_over_cruise = False
    self._has_lead = False
    self._active_prev = False
    self._last_lead_time = 0.0  # Track when we last saw a lead

    self.active = False
    self.just_disabled = False

    self._coast_logger = CoastLogger()

  def log_coast(self, sm) -> None:
    """Always-on coast/drag logging — runs regardless of ACM being enabled."""
    self._coast_logger.update(sm)

  def _check_emergency_conditions(self, lead, v_ego, current_time):
    """Check for emergency conditions that require immediate ACM disable."""
    if not lead or not lead.present:
      return False

    self.lead_ttc = lead.dRel / max(v_ego, 0.1)
    relative_speed = v_ego - lead.vLead  # Positive = closing

    # Speed-adaptive minimum distance
    min_dist_for_speed = np.interp(v_ego, SPEED_BP, MIN_DIST_V)

    # Emergency disable conditions - only for truly dangerous situations
    # Require BOTH close distance AND (fast closing OR very short TTC)
    if lead.dRel < min_dist_for_speed and (
        self.lead_ttc < EMERGENCY_TTC or
        relative_speed > EMERGENCY_RELATIVE_SPEED):

      self._last_lead_time = current_time
      if self.active:  # Only log if we're actually disabling
        cloudlog.warning(f"ACM emergency disable: dRel={lead.dRel:.1f}m, TTC={self.lead_ttc:.1f}s, relSpeed={relative_speed:.1f}m/s")
      return True

    return False

  def _update_lead_status(self, lead, v_ego, current_time):
    """Update lead vehicle detection status."""
    if lead and lead.present:
      self.lead_ttc = lead.dRel / max(v_ego, 0.1)

      if self.lead_ttc < TTC_THRESHOLD:
        self._has_lead = True
        self._last_lead_time = current_time
      else:
        self._has_lead = False
    else:
      self._has_lead = False
      self.lead_ttc = float('inf')

  def _check_cooldown(self, current_time):
    """Check if we're still in cooldown period after lead detection."""
    time_since_lead = current_time - self._last_lead_time
    return time_since_lead < LEAD_COOLDOWN_TIME

  def _should_activate(self, user_ctrl_lon, v_ego, v_cruise, in_cooldown):
    """Determine if ACM should be active based on all conditions."""
    self._is_speed_over_cruise = v_ego > (v_cruise * SPEED_RATIO)

    return (not user_ctrl_lon and
            not self._has_lead and
            not in_cooldown and
            self._is_speed_over_cruise)

  def update_states(self, cc, rs, user_ctrl_lon, v_ego, v_cruise):
    """Update ACM state with multiple safety checks."""
    # Basic validation
    if not self.enabled or len(cc.orientationNED) != 3:
      self.active = False
      return

    current_time = time.monotonic()
    lead = rs.leadOne

    # Check emergency conditions first (highest priority)
    if self._check_emergency_conditions(lead, v_ego, current_time):
      self.active = False
      self._active_prev = self.active
      return

    # Update normal lead status
    self._update_lead_status(lead, v_ego, current_time)

    # Check cooldown period
    in_cooldown = self._check_cooldown(current_time)

    # Determine if ACM should be active
    self.active = self._should_activate(user_ctrl_lon, v_ego, v_cruise, in_cooldown)

    # Track state changes for logging
    self.just_disabled = self._active_prev and not self.active
    if self.active and not self._active_prev:
      cloudlog.info(f"ACM activated: v_ego={v_ego*3.6:.1f} km/h, v_cruise={v_cruise*3.6:.1f} km/h")
    elif self.just_disabled:
      cloudlog.info("ACM deactivated")

    self._active_prev = self.active

  def update_a_desired_trajectory(self, a_desired_trajectory):
    """
    Modify acceleration trajectory to allow coasting.
    SAFETY: Check for any strong braking request and abort.
    """
    if not self.active:
      return a_desired_trajectory

    # SAFETY CHECK: If MPC wants significant braking, DON'T suppress it
    min_accel = np.min(a_desired_trajectory)
    if min_accel < EMERGENCY_DECEL_THRESHOLD:
      cloudlog.warning(f"ACM aborting: MPC requested {min_accel:.2f} m/s² braking")
      self.active = False  # Immediately deactivate
      return a_desired_trajectory  # Return unmodified trajectory

    # Only suppress very mild braking (> -1.0 m/s²)
    # This allows coasting but preserves any meaningful braking
    modified_trajectory = np.copy(a_desired_trajectory)
    for i in range(len(modified_trajectory)):
      if -1.0 < modified_trajectory[i] < 0:
        # Only suppress very gentle braking for cruise control
        modified_trajectory[i] = 0.0
      # Any braking stronger than -1.0 m/s² is preserved!

    return modified_trajectory
