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

ALKA (Always-on Lane Keeping Assist) control logic.

Encapsulates ALKA activation state - enabled flag, minimum-enable speed with
hysteresis, and the resulting active state - in one dedicated module so the
logic stays cohesive and adds no merge-conflict surface to upstream openpilot
files. Consumed by controlsd (per-frame active-state computation via the Alka
class) and selfdrived (enabled check via alka_enabled()).
"""
from opendbc.safety import ALTERNATIVE_EXPERIENCE
from openpilot.common.constants import CV

ALKA_SPEED_HYST_MS = 2.0 * CV.KPH_TO_MS  # hysteresis band (2 km/h) to stop threshold flicker


def alka_enabled(CP) -> bool:
  """Whether ALKA is armed. Init-time only: CP.alternativeExperience is frozen
  after card sets it during fingerprinting, so callers cache this once."""
  return bool(CP.alternativeExperience & ALTERNATIVE_EXPERIENCE.ALKA)


def alka_speed_gate(v_ego: float, min_speed_ms: float, prev_ok: bool) -> bool:
  """Whether ALKA may be active at the current speed, with hysteresis.

  - min_speed_ms <= 0 disables the gate (always allowed).
  - Turns on when v_ego >= min_speed_ms.
  - Once on, stays on until v_ego < (min_speed_ms - ALKA_SPEED_HYST_MS),
    so speed hovering at the threshold does not toggle the gate.
  """
  if min_speed_ms <= 0.0:
    return True
  threshold = min_speed_ms - (ALKA_SPEED_HYST_MS if prev_ok else 0.0)
  return v_ego >= threshold


class Alka:
  """ALKA activation state for controlsd (one instance per drive).

  `enabled` and `min_speed_ms` are resolved once at construction (init-time
  config); `active` and the hysteresis latch are updated per frame via update().
  """

  def __init__(self, enabled: bool, min_speed_ms: float):
    self.enabled = enabled
    self.min_speed_ms = min_speed_ms
    self.active = False
    self.armed = False
    self._speed_ok = False

  @classmethod
  def from_params(cls, CP, params) -> "Alka":
    # Value is stored in the driver's display unit (km/h or mph); convert to m/s.
    speed_factor = CV.KPH_TO_MS if params.get_bool("IsMetric") else CV.MPH_TO_MS
    min_speed_ms = (params.get("dp_lat_alka_min_speed", return_default=True) or 0) * speed_factor
    return cls(alka_enabled(CP), min_speed_ms)

  def update(self, v_ego: float, lkas_on: bool, gear_ok: bool, calibrated: bool,
             seatbelt_unlatched: bool, door_open: bool) -> bool:
    """Recompute ALKA active state for this frame. Returns self.active."""
    if not self.enabled:
      self.active = False
      self.armed = False
      return self.active
    # What the driver switched on, with none of the situational gates below. Observers
    # that want intent (the chime) use this; only actual steering uses self.active.
    self.armed = lkas_on
    # gate on speed with hysteresis (min_speed_ms <= 0 disables the gate)
    self._speed_ok = alka_speed_gate(v_ego, self.min_speed_ms, self._speed_ok)
    self.active = lkas_on and gear_ok and calibrated and self._speed_ok \
                  and not seatbelt_unlatched and not door_open
    return self.active
