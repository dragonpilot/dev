import unittest
from types import SimpleNamespace
from unittest import mock

import pyray as rl

from openpilot.selfdrive.ui import UI_BORDER_SIZE
from openpilot.selfdrive.ui.ui_state import UIStatus
from dragonpilot.selfdrive.ui.onroad import border_indicator as bo
from dragonpilot.selfdrive.ui.onroad.border_indicator import (
  DpBorderIndicator, indicator_side_state,
  INDICATOR_BLINK_RATE_FAST, INDICATOR_BLINK_RATE_STD,
  INDICATOR_COLOR_BSM, INDICATOR_COLOR_BLINKER, TRANSPARENT,
  EGPU_CORNER_ARM, EGPU_COLOR_OK, EGPU_COLOR_FAULT,
  EGPU_ALPHA_NOT_COMPILED, EGPU_ALPHA_FALLBACK,
)

W, H = 2160, 1080


def rgba(c):
  return (c.r, c.g, c.b, c.a)


class FakeSm:
  """Minimal SubMaster stand-in. __getitem__ must live on the type, not the instance."""
  def __init__(self, data, recv_frame, alive):
    self._data, self.recv_frame, self.alive = data, recv_frame, alive

  def __getitem__(self, k):
    return self._data[k]


def fake_sm(chestnut_present=True, model_recv=10, model_alive=True,
            left_blinker=False, right_blinker=False,
            left_bsm=False, right_bsm=False):
  cs = SimpleNamespace(leftBlinker=left_blinker, rightBlinker=right_blinker,
                       leftBlindspot=left_bsm, rightBlindspot=right_bsm)
  data = {'carState': cs, 'deviceState': SimpleNamespace(chestnutPresent=chestnut_present)}
  return FakeSm(data, {'modelV2': model_recv}, {'modelV2': model_alive})


def fake_ui_state(status=UIStatus.DISENGAGED, usbgpu=True, compiled=True,
                  active=True, loading=False, started_frame=0):
  return SimpleNamespace(status=status, usbgpu=usbgpu, usbgpu_compiled=compiled,
                         usbgpu_active=active, usbgpu_loading=loading,
                         started_frame=started_frame)


# --------------------------------------------------------------------------
# side strips (pure)
# --------------------------------------------------------------------------
class TestIndicatorSideState(unittest.TestCase):
  def test_idle_clears_and_resets_count(self):
    show, count, color = indicator_side_state(False, False, True, 7)
    self.assertFalse(show)
    self.assertEqual(count, 0)
    self.assertEqual(rgba(color), rgba(TRANSPARENT))

  def test_bsm_alone_is_solid(self):
    show, count, color = indicator_side_state(False, True, False, 0)
    self.assertTrue(show)
    self.assertEqual(rgba(color), rgba(INDICATOR_COLOR_BSM))
    for _ in range(INDICATOR_BLINK_RATE_FAST * 3):
      show, count, _ = indicator_side_state(False, True, show, count)
      self.assertTrue(show)

  def test_blinker_toggles_at_standard_rate(self):
    show, _, color = indicator_side_state(True, False, False, INDICATOR_BLINK_RATE_STD - 1)
    self.assertTrue(show)
    self.assertEqual(rgba(color), rgba(INDICATOR_COLOR_BLINKER))

  def test_blinker_holds_between_toggles(self):
    show, _, _ = indicator_side_state(True, False, False, 0)
    self.assertFalse(show)

  def test_bsm_plus_blinker_blinks_fast_and_is_yellow(self):
    show, _, color = indicator_side_state(True, True, False, INDICATOR_BLINK_RATE_FAST - 1)
    self.assertTrue(show)
    self.assertEqual(rgba(color), rgba(INDICATOR_COLOR_BSM))

  def test_count_accumulates_while_active(self):
    count = 0
    for i in range(1, 6):
      _, count, _ = indicator_side_state(True, False, False, count)
      self.assertEqual(count, i)


# --------------------------------------------------------------------------
# eGPU state -> colour mapping
# --------------------------------------------------------------------------
class TestEgpuColorMapping(unittest.TestCase):
  def _update(self, ui, sm=None):
    o = DpBorderIndicator()
    with mock.patch.object(bo, 'ui_state', ui):
      o._update_egpu(sm or fake_sm())
    return o

  def test_absent_hides(self):
    o = self._update(fake_ui_state(usbgpu=False))
    self.assertFalse(o._egpu_show)

  def test_running_is_solid_white(self):
    o = self._update(fake_ui_state())
    self.assertTrue(o._egpu_show)
    self.assertEqual(rgba(o._egpu_color), rgba(EGPU_COLOR_OK))

  def test_not_compiled_is_dim_white(self):
    o = self._update(fake_ui_state(compiled=False))
    self.assertEqual(o._egpu_color.r, EGPU_COLOR_OK.r)
    self.assertEqual(o._egpu_color.a, int(255 * EGPU_ALPHA_NOT_COMPILED))

  def test_failed_is_solid_orange(self):
    o = self._update(fake_ui_state(active=False))
    self.assertEqual(rgba(o._egpu_color), rgba(EGPU_COLOR_FAULT))

  def test_fallback_is_dim_orange(self):
    ui = fake_ui_state(status=UIStatus.ENGAGED, active=False)
    o = self._update(ui)  # ENGAGED + not active -> latches small model, and active False -> failed
    self.assertEqual(o._egpu_color.r, EGPU_COLOR_FAULT.r)
    self.assertEqual(o._egpu_color.a, int(255 * EGPU_ALPHA_FALLBACK))

  def test_loading_pulses_within_bounds(self):
    seen = set()
    for t in (0.0, 0.15, 0.3, 0.45):
      with mock.patch.object(bo.rl, 'get_time', return_value=t):
        o = self._update(fake_ui_state(loading=True))
      self.assertTrue(o._egpu_show)
      self.assertEqual(o._egpu_color.r, EGPU_COLOR_OK.r)
      self.assertGreaterEqual(o._egpu_color.a, int(255 * 0.35) - 1)
      self.assertLessEqual(o._egpu_color.a, 255)
      seen.add(o._egpu_color.a)
    self.assertGreater(len(seen), 1, "pulse should vary with time")

  def test_unplugged_mid_drive_is_failure_not_absent(self):
    # ui_state.usbgpu is sticky onroad, but chestnutPresent drops
    o = self._update(fake_ui_state(), fake_sm(chestnut_present=False))
    self.assertTrue(o._egpu_show)
    self.assertEqual(rgba(o._egpu_color), rgba(EGPU_COLOR_FAULT))


# --------------------------------------------------------------------------
# small-model latch
# --------------------------------------------------------------------------
class TestSmallModelLatch(unittest.TestCase):
  def test_latches_on_engage_without_big_model(self):
    o = DpBorderIndicator()
    with mock.patch.object(bo, 'ui_state', fake_ui_state(status=UIStatus.ENGAGED, active=False)):
      o._update_egpu(fake_sm())
    self.assertTrue(o._egpu_small_model_engaged)

  def test_does_not_latch_when_big_model_is_active(self):
    o = DpBorderIndicator()
    with mock.patch.object(bo, 'ui_state', fake_ui_state(status=UIStatus.ENGAGED, active=True)):
      o._update_egpu(fake_sm())
    self.assertFalse(o._egpu_small_model_engaged)

  def test_clears_on_disengage(self):
    o = DpBorderIndicator()
    o._egpu_small_model_engaged = True
    with mock.patch.object(bo, 'ui_state', fake_ui_state(status=UIStatus.DISENGAGED)):
      o._update_egpu(fake_sm())
    self.assertFalse(o._egpu_small_model_engaged)


# --------------------------------------------------------------------------
# drawing: geometry and order
# --------------------------------------------------------------------------
class TestDrawing(unittest.TestCase):
  def _capture(self, fn):
    calls = []
    with mock.patch.object(bo.rl, 'draw_rectangle', side_effect=lambda x, y, w, h, c: calls.append((x, y, w, h, c))):
      fn()
    return calls

  def test_corners_draw_eight_arms_all_on_screen(self):
    o = DpBorderIndicator()
    o._egpu_color = EGPU_COLOR_OK
    calls = self._capture(lambda: o._draw_egpu_corners(rl.Rectangle(0, 0, W, H)))
    self.assertEqual(len(calls), 8, "4 corners x 2 arms")
    for x, y, w, h, _ in calls:
      self.assertGreaterEqual(x, 0)
      self.assertGreaterEqual(y, 0)
      self.assertLessEqual(x + w, W, f"arm at {x} overflows right edge")
      self.assertLessEqual(y + h, H, f"arm at {y} overflows bottom edge")

  def test_each_corner_gets_one_horizontal_and_one_vertical_arm(self):
    o = DpBorderIndicator()
    o._egpu_color = EGPU_COLOR_OK
    calls = self._capture(lambda: o._draw_egpu_corners(rl.Rectangle(0, 0, W, H)))
    horiz = [c for c in calls if c[2] == EGPU_CORNER_ARM and c[3] == UI_BORDER_SIZE]
    vert = [c for c in calls if c[2] == UI_BORDER_SIZE and c[3] == EGPU_CORNER_ARM]
    self.assertEqual(len(horiz), 4)
    self.assertEqual(len(vert), 4)
    # one arm pair anchored at each of the four corners
    self.assertEqual({(c[0], c[1]) for c in horiz},
                     {(0, 0), (W - EGPU_CORNER_ARM, 0), (0, H - UI_BORDER_SIZE),
                      (W - EGPU_CORNER_ARM, H - UI_BORDER_SIZE)})

  def test_corners_do_not_overlap_side_strips(self):
    strip_top = 4 * UI_BORDER_SIZE
    strip_bottom = H - 4 * UI_BORDER_SIZE
    o = DpBorderIndicator()
    o._egpu_color = EGPU_COLOR_OK
    calls = self._capture(lambda: o._draw_egpu_corners(rl.Rectangle(0, 0, W, H)))
    for x, y, w, h, _ in calls:
      self.assertTrue(y + h <= strip_top or y >= strip_bottom,
                      f"arm y{y}..{y + h} intrudes into the strip band {strip_top}..{strip_bottom}")

  def test_render_draws_corners_after_strips(self):
    o = DpBorderIndicator()
    ui = fake_ui_state()
    sm = fake_sm(left_bsm=True)  # force a left strip
    with mock.patch.object(bo, 'ui_state', SimpleNamespace(sm=sm, **vars(ui))):
      calls = self._capture(lambda: o.render(rl.Rectangle(0, 0, W, H)))
    self.assertEqual(len(calls), 1 + 8, "one strip + eight corner arms")
    strip_h = H - 8 * UI_BORDER_SIZE
    self.assertEqual(calls[0][3], strip_h, "the strip must be drawn first")

  def test_render_skips_corners_when_absent(self):
    o = DpBorderIndicator()
    ui = fake_ui_state(usbgpu=False)
    sm = fake_sm(left_bsm=True)
    with mock.patch.object(bo, 'ui_state', SimpleNamespace(sm=sm, **vars(ui))):
      calls = self._capture(lambda: o.render(rl.Rectangle(0, 0, W, H)))
    self.assertEqual(len(calls), 1, "strip only, no corners")


if __name__ == "__main__":
  unittest.main()
