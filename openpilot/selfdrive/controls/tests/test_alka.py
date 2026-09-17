#!/usr/bin/env python3
"""
Tests for ALKA (Always-on Lane Keeping Assist) Python layer.

Tests the controlsd logic for computing latActive when ALKA is enabled.
Matches the logic in selfdrive/controls/controlsd.py.
"""
import unittest

from openpilot.cereal import log
from opendbc.safety import ALTERNATIVE_EXPERIENCE


class TestALKAAlternativeExperience(unittest.TestCase):
  """Test ALTERNATIVE_EXPERIENCE.ALKA constant."""

  def test_alka_constant_value(self):
    """ALKA constant should be 1024 (2^10)."""
    self.assertEqual(ALTERNATIVE_EXPERIENCE.ALKA, 1024)

  def test_alka_flag_bitwise(self):
    """ALKA flag should work with bitwise operations."""
    # Test setting ALKA flag
    exp = ALTERNATIVE_EXPERIENCE.DEFAULT | ALTERNATIVE_EXPERIENCE.ALKA
    self.assertTrue(exp & ALTERNATIVE_EXPERIENCE.ALKA)

    # Test combining with other flags
    exp = ALTERNATIVE_EXPERIENCE.DISABLE_STOCK_AEB | ALTERNATIVE_EXPERIENCE.ALKA
    self.assertTrue(exp & ALTERNATIVE_EXPERIENCE.ALKA)
    self.assertTrue(exp & ALTERNATIVE_EXPERIENCE.DISABLE_STOCK_AEB)

    # Test without ALKA
    exp = ALTERNATIVE_EXPERIENCE.DISABLE_STOCK_AEB
    self.assertFalse(exp & ALTERNATIVE_EXPERIENCE.ALKA)


class TestALKALatActive(unittest.TestCase):
  """Test latActive computation with ALKA.

  This mirrors the logic in controlsd.py:
    alka_enabled = (self.CP.alternativeExperience & ALTERNATIVE_EXPERIENCE.ALKA) != 0
    lkas_on = self.sm['carStateExt'].lkasOn
    calibrated = self.sm['extrinsicsCalibration'].calStatus == log.ExtrinsicsCalibration.Status.calibrated
    gear_ok = CS.gearShifter not in (park, neutral, reverse)
    alka_active = lkas_on and gear_ok and calibrated and not CS.seatbeltUnlatched and not CS.doorOpen
    CC.latActive = (self.sm['selfdriveState'].active or alka_active) and not CS.steerFaultTemporary and not CS.steerFaultPermanent and \
                   (not standstill or self.CP.steerAtStandstill)
  """

  def _compute_alka_active(self, alka_enabled, lkas_on, gear_ok, calibrated, seatbelt_unlatched, door_open):
    """Compute alka_active via the real Alka class (min_speed 0 = no speed gate)."""
    from dragonpilot.selfdrive.controls.lib.alka import Alka
    alka = Alka(enabled=alka_enabled, min_speed_ms=0.0)
    return alka.update(0.0, lkas_on, gear_ok, calibrated, seatbelt_unlatched, door_open)

  def _compute_lat_active(self, selfdrive_active, alka_active, steer_fault_temp, steer_fault_perm, standstill, steer_at_standstill=False):
    """Compute latActive matching controlsd.py logic."""
    return (selfdrive_active or alka_active) and not steer_fault_temp and not steer_fault_perm and \
           (not standstill or steer_at_standstill)

  def test_lat_active_normal_mode(self):
    """Without ALKA, latActive should follow selfdriveState.active."""
    alka_active = self._compute_alka_active(
      alka_enabled=False, lkas_on=True, gear_ok=True,
      calibrated=True, seatbelt_unlatched=False, door_open=False)
    lat_active = self._compute_lat_active(
      selfdrive_active=True, alka_active=alka_active,
      steer_fault_temp=False, steer_fault_perm=False, standstill=False)
    self.assertTrue(lat_active)

    # When selfdrive not active, lat should be inactive
    lat_active = self._compute_lat_active(
      selfdrive_active=False, alka_active=alka_active,
      steer_fault_temp=False, steer_fault_perm=False, standstill=False)
    self.assertFalse(lat_active)

  def test_lat_active_alka_mode(self):
    """With ALKA, latActive can be true even when selfdriveState.active is false."""
    alka_active = self._compute_alka_active(
      alka_enabled=True, lkas_on=True, gear_ok=True,
      calibrated=True, seatbelt_unlatched=False, door_open=False)
    lat_active = self._compute_lat_active(
      selfdrive_active=False, alka_active=alka_active,
      steer_fault_temp=False, steer_fault_perm=False, standstill=False)
    self.assertTrue(lat_active)

  def test_lat_active_alka_requires_lkas_on(self):
    """ALKA requires lkasOn (ACC Main ON)."""
    alka_active = self._compute_alka_active(
      alka_enabled=True, lkas_on=False, gear_ok=True,
      calibrated=True, seatbelt_unlatched=False, door_open=False)
    lat_active = self._compute_lat_active(
      selfdrive_active=False, alka_active=alka_active,
      steer_fault_temp=False, steer_fault_perm=False, standstill=False)
    self.assertFalse(lat_active)

  def test_lat_active_alka_requires_gear_ok(self):
    """ALKA requires gear not in P/N/R."""
    alka_active = self._compute_alka_active(
      alka_enabled=True, lkas_on=True, gear_ok=False,
      calibrated=True, seatbelt_unlatched=False, door_open=False)
    lat_active = self._compute_lat_active(
      selfdrive_active=False, alka_active=alka_active,
      steer_fault_temp=False, steer_fault_perm=False, standstill=False)
    self.assertFalse(lat_active)

  def test_lat_active_alka_requires_calibration(self):
    """ALKA requires calibration to be complete."""
    alka_active = self._compute_alka_active(
      alka_enabled=True, lkas_on=True, gear_ok=True,
      calibrated=False, seatbelt_unlatched=False, door_open=False)
    lat_active = self._compute_lat_active(
      selfdrive_active=False, alka_active=alka_active,
      steer_fault_temp=False, steer_fault_perm=False, standstill=False)
    self.assertFalse(lat_active)

  def test_lat_active_alka_requires_seatbelt(self):
    """ALKA requires seatbelt to be latched."""
    alka_active = self._compute_alka_active(
      alka_enabled=True, lkas_on=True, gear_ok=True,
      calibrated=True, seatbelt_unlatched=True, door_open=False)
    lat_active = self._compute_lat_active(
      selfdrive_active=False, alka_active=alka_active,
      steer_fault_temp=False, steer_fault_perm=False, standstill=False)
    self.assertFalse(lat_active)

  def test_lat_active_alka_requires_doors_closed(self):
    """ALKA requires all doors to be closed."""
    alka_active = self._compute_alka_active(
      alka_enabled=True, lkas_on=True, gear_ok=True,
      calibrated=True, seatbelt_unlatched=False, door_open=True)
    lat_active = self._compute_lat_active(
      selfdrive_active=False, alka_active=alka_active,
      steer_fault_temp=False, steer_fault_perm=False, standstill=False)
    self.assertFalse(lat_active)

  def test_lat_active_blocked_by_steer_fault_temporary(self):
    """Temporary steer fault should block lateral control regardless of ALKA."""
    alka_active = self._compute_alka_active(
      alka_enabled=True, lkas_on=True, gear_ok=True,
      calibrated=True, seatbelt_unlatched=False, door_open=False)
    lat_active = self._compute_lat_active(
      selfdrive_active=False, alka_active=alka_active,
      steer_fault_temp=True, steer_fault_perm=False, standstill=False)
    self.assertFalse(lat_active)

  def test_lat_active_blocked_by_steer_fault_permanent(self):
    """Permanent steer fault should block lateral control regardless of ALKA."""
    alka_active = self._compute_alka_active(
      alka_enabled=True, lkas_on=True, gear_ok=True,
      calibrated=True, seatbelt_unlatched=False, door_open=False)
    lat_active = self._compute_lat_active(
      selfdrive_active=False, alka_active=alka_active,
      steer_fault_temp=False, steer_fault_perm=True, standstill=False)
    self.assertFalse(lat_active)

  def test_lat_active_blocked_by_standstill(self):
    """ALKA should be blocked at standstill (latActive checks standstill)."""
    alka_active = self._compute_alka_active(
      alka_enabled=True, lkas_on=True, gear_ok=True,
      calibrated=True, seatbelt_unlatched=False, door_open=False)
    lat_active = self._compute_lat_active(
      selfdrive_active=False, alka_active=alka_active,
      steer_fault_temp=False, steer_fault_perm=False, standstill=True)
    self.assertFalse(lat_active)


class TestALKASettings(unittest.TestCase):
  """Test ALKA settings configuration."""

  def test_alka_setting_in_lateral_section(self):
    """ALKA setting should be in the Lateral section."""
    from dragonpilot.settings import SETTINGS

    lateral_section = None
    for section in SETTINGS:
      if section["title"] == "Lateral":
        lateral_section = section
        break

    self.assertIsNotNone(lateral_section, "Lateral section not found in SETTINGS")

    # Find ALKA setting
    alka_setting = None
    for setting in lateral_section["settings"]:
      if setting.get("key") == "dp_lat_alka":
        alka_setting = setting
        break

    self.assertIsNotNone(alka_setting, "dp_lat_alka setting not found")

  def test_alka_setting_has_brands(self):
    """ALKA setting brands should match safety modes with alka_allowed=true."""
    from dragonpilot.settings import SETTINGS
    from opendbc.car.structs import CarParams
    from opendbc.safety.tests.libsafety import libsafety_py

    # Map of brand names to their safety modes
    brand_to_safety_mode = {
      "toyota": CarParams.SafetyModel.toyota,
      "hyundai": CarParams.SafetyModel.hyundai,
      "honda": CarParams.SafetyModel.hondaNidec,
      "volkswagen": CarParams.SafetyModel.volkswagen,
      "subaru": CarParams.SafetyModel.subaru,
      "mazda": CarParams.SafetyModel.mazda,
      "nissan": CarParams.SafetyModel.nissan,
      "ford": CarParams.SafetyModel.ford,
      "chrysler": CarParams.SafetyModel.chrysler,
    }

    # Find ALKA setting
    alka_setting = None
    for section in SETTINGS:
      for setting in section.get("settings", []):
        if setting.get("key") == "dp_lat_alka":
          alka_setting = setting
          break

    self.assertIsNotNone(alka_setting)
    self.assertIn("brands", alka_setting)
    self.assertIsInstance(alka_setting["brands"], list)

    # Verify each brand in settings has alka_allowed=true in safety mode
    safety = libsafety_py.libsafety
    for brand in alka_setting["brands"]:
      self.assertIn(brand, brand_to_safety_mode, f"Unknown brand: {brand}")
      safety_mode = brand_to_safety_mode[brand]
      safety.set_safety_hooks(safety_mode, 0)
      safety.init_tests()
      self.assertTrue(safety.get_alka_allowed(), f"Brand {brand} should have alka_allowed=true")


class TestALKAAllConditions(unittest.TestCase):
  """Comprehensive truth table tests for all ALKA conditions."""

  def test_alka_all_conditions_truth_table(self):
    """Test all combinations of ALKA conditions."""
    # Test cases: (alka_enabled, lkas_on, gear_ok, calibrated, seatbelt_unlatched, door_open) -> expected_alka_active
    test_cases = [
      # All conditions met
      (True, True, True, True, False, False, True),
      # Missing one condition each
      (False, True, True, True, False, False, False),  # ALKA disabled
      (True, False, True, True, False, False, False),  # lkas_on false
      (True, True, False, True, False, False, False),  # gear not ok (P/N/R)
      (True, True, True, False, False, False, False),  # Not calibrated
      (True, True, True, True, True, False, False),    # Seatbelt unlatched
      (True, True, True, True, False, True, False),    # Door open
      # Multiple conditions missing
      (True, False, False, True, False, False, False),   # No lkas_on + bad gear
      (True, True, True, False, True, True, False),      # Not calibrated + seatbelt + door
    ]

    from dragonpilot.selfdrive.controls.lib.alka import Alka
    for alka_enabled, lkas_on, gear_ok, calibrated, seatbelt_unlatched, door_open, expected in test_cases:
      alka = Alka(enabled=alka_enabled, min_speed_ms=0.0)
      alka_active = alka.update(0.0, lkas_on, gear_ok, calibrated, seatbelt_unlatched, door_open)

      self.assertEqual(alka_active, expected,
                       f"Failed for alka_enabled={alka_enabled}, lkas_on={lkas_on}, gear_ok={gear_ok}, "
                       f"calibrated={calibrated}, seatbelt_unlatched={seatbelt_unlatched}, "
                       f"door_open={door_open}")

  def test_lat_active_truth_table(self):
    """Test latActive computation with various inputs."""
    # Test cases: (selfdrive_active, alka_active, steer_fault, standstill) -> expected_lat_active
    test_cases = [
      (False, False, False, False, False),  # Nothing active
      (True, False, False, False, True),    # Selfdrive only
      (False, True, False, False, True),    # ALKA only
      (True, True, False, False, True),     # Both active
      (True, False, True, False, False),    # Selfdrive but fault
      (False, True, True, False, False),    # ALKA but fault
      (True, False, False, True, False),    # Selfdrive but standstill (no steerAtStandstill)
      (False, True, False, True, False),    # ALKA but standstill
    ]

    for selfdrive_active, alka_active, steer_fault, standstill, expected in test_cases:
      lat_active = (selfdrive_active or alka_active) and not steer_fault and not standstill

      self.assertEqual(lat_active, expected,
                       f"Failed for selfdrive_active={selfdrive_active}, alka_active={alka_active}, "
                       f"steer_fault={steer_fault}, standstill={standstill}")


class TestALKASpeedGate(unittest.TestCase):
  """Test the real ALKA minimum-enable-speed gate from drive_helpers."""

  def test_gate_off_when_min_speed_zero(self):
    from dragonpilot.selfdrive.controls.lib.alka import alka_speed_gate
    # 0 disables the gate -> always allowed, regardless of speed or prev state
    self.assertTrue(alka_speed_gate(0.0, 0.0, False))
    self.assertTrue(alka_speed_gate(0.0, 0.0, True))
    self.assertTrue(alka_speed_gate(50.0, 0.0, False))

  def test_gate_activates_at_threshold(self):
    from dragonpilot.selfdrive.controls.lib.alka import alka_speed_gate
    from openpilot.common.constants import CV
    min_ms = 20 * CV.KPH_TO_MS
    # previously off, below threshold -> stays off
    self.assertFalse(alka_speed_gate(19 * CV.KPH_TO_MS, min_ms, False))
    # at / above threshold -> turns on
    self.assertTrue(alka_speed_gate(20 * CV.KPH_TO_MS, min_ms, False))
    self.assertTrue(alka_speed_gate(25 * CV.KPH_TO_MS, min_ms, False))

  def test_gate_hysteresis_holds_on(self):
    from dragonpilot.selfdrive.controls.lib.alka import alka_speed_gate
    from openpilot.common.constants import CV
    min_ms = 20 * CV.KPH_TO_MS
    # once on, stays on down to (X - 2 km/h)
    self.assertTrue(alka_speed_gate(19 * CV.KPH_TO_MS, min_ms, True))
    self.assertTrue(alka_speed_gate(18.1 * CV.KPH_TO_MS, min_ms, True))
    # below (X - 2 km/h) -> turns off
    self.assertFalse(alka_speed_gate(17.9 * CV.KPH_TO_MS, min_ms, True))

  def test_gate_no_flicker_at_threshold(self):
    from dragonpilot.selfdrive.controls.lib.alka import alka_speed_gate
    from openpilot.common.constants import CV
    min_ms = 20 * CV.KPH_TO_MS
    # hovering at 19.5 km/h: latched state decides, no oscillation
    self.assertFalse(alka_speed_gate(19.5 * CV.KPH_TO_MS, min_ms, False))
    self.assertTrue(alka_speed_gate(19.5 * CV.KPH_TO_MS, min_ms, True))


class TestAlkaClass(unittest.TestCase):
  """Test the stateful Alka class (enabled short-circuit + hysteresis latch)."""

  def test_disabled_never_active(self):
    from dragonpilot.selfdrive.controls.lib.alka import Alka
    alka = Alka(enabled=False, min_speed_ms=0.0)
    # even with all conditions satisfied, a disabled instance stays inactive
    self.assertFalse(alka.update(30.0, True, True, True, False, False))
    self.assertFalse(alka.active)

  def test_hysteresis_latch_across_updates(self):
    from dragonpilot.selfdrive.controls.lib.alka import Alka
    from openpilot.common.constants import CV
    alka = Alka(enabled=True, min_speed_ms=20 * CV.KPH_TO_MS)
    conds = dict(lkas_on=True, gear_ok=True, calibrated=True, seatbelt_unlatched=False, door_open=False)
    # accelerate up: inactive at 19, active at 20 (crosses on threshold)
    self.assertFalse(alka.update(19 * CV.KPH_TO_MS, **conds))
    self.assertTrue(alka.update(20 * CV.KPH_TO_MS, **conds))
    # decelerate: latch holds active down to 18 (20 - 2), off below
    self.assertTrue(alka.update(18.5 * CV.KPH_TO_MS, **conds))
    self.assertFalse(alka.update(17.5 * CV.KPH_TO_MS, **conds))

  def test_off_when_min_speed_zero(self):
    from dragonpilot.selfdrive.controls.lib.alka import Alka
    alka = Alka(enabled=True, min_speed_ms=0.0)
    # min_speed 0 = no gate: active from standstill when other conditions hold
    self.assertTrue(alka.update(0.0, True, True, True, False, False))


class TestALKAMinSpeedSetting(unittest.TestCase):
  """dp_lat_alka_min_speed spin item must exist with the right shape."""

  def _find(self, key):
    from dragonpilot.settings import SETTINGS
    for section in SETTINGS:
      for s in section.get("settings", []):
        if s.get("key") == key:
          return s
    return None

  def test_min_speed_setting_shape(self):
    item = self._find("dp_lat_alka_min_speed")
    self.assertIsNotNone(item, "dp_lat_alka_min_speed not found in SETTINGS")
    self.assertEqual(item["type"], "spin_button_item")
    self.assertEqual(item["min_val"], 0)
    self.assertEqual(item["max_val"], 30)  # authored in km/h; panel converts to mph for imperial
    self.assertEqual(item["step"], 5)
    self.assertEqual(item["default"], 0)
    self.assertEqual(item["depends_on"], "dp_lat_alka")
    self.assertEqual(item["param_type"], "INT")
    self.assertEqual(item["unit"], "speed")


if __name__ == "__main__":
  unittest.main()


# dp - the chime must announce driver intent, not situational gating. Chiming on
# alka.active meant every stop light below dp_lat_alka_min_speed played the pair.
def _drive(a, speeds, lkas_on=True):
  """Run update() over a speed profile, return (active, armed) per frame."""
  return [(a.update(v, lkas_on, gear_ok=True, calibrated=True,
                    seatbelt_unlatched=False, door_open=False), a.armed) for v in speeds]


def _chimes(states):
  """How many times soundd would fire, i.e. edges of the value it watches."""
  return sum(1 for i in range(1, len(states)) if states[i] != states[i - 1])


def test_speed_gate_crossing_is_silent():
  """Stop-and-go below the min-enable speed must not chime. active toggles (correct, it
  stops steering); armed must not, because the driver did nothing."""
  from dragonpilot.selfdrive.controls.lib.alka import Alka
  a = Alka(enabled=True, min_speed_ms=8.33)          # 30 km/h
  profile = [12.0] * 5 + [3.0] * 5 + [12.0] * 5 + [3.0] * 5 + [12.0] * 5
  states = _drive(a, profile)
  assert _chimes([s[0] for s in states]) == 4, "sanity: active should toggle with speed"
  assert _chimes([s[1] for s in states]) == 0, "armed must not toggle on speed alone"


def test_acc_main_toggle_still_chimes():
  """The one thing the driver actually does must still be announced."""
  from dragonpilot.selfdrive.controls.lib.alka import Alka
  a = Alka(enabled=True, min_speed_ms=0.0)
  armed = [a.update(20.0, on, gear_ok=True, calibrated=True,
                    seatbelt_unlatched=False, door_open=False) or a.armed
           for on in [True] * 3 + [False] * 3 + [True] * 3]
  assert _chimes(armed) == 2, "ACC Main off then on again = two chimes"


def test_armed_is_false_when_feature_disabled():
  from dragonpilot.selfdrive.controls.lib.alka import Alka
  a = Alka(enabled=False, min_speed_ms=0.0)
  a.update(20.0, True, gear_ok=True, calibrated=True, seatbelt_unlatched=False, door_open=False)
  assert a.armed is False
