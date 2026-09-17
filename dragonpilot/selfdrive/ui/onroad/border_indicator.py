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

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

dp - everything dragonpilot draws on the onroad border.

Two independent indicators share the border:
  * side strips - directional: blinker and blindspot, left/right edges
  * corner Ls   - global: eGPU (chestnut) status, all four corners
"""
import math
import pyray as rl

from openpilot.selfdrive.ui import UI_BORDER_SIZE
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.system.ui.lib.application import gui_app
from dragonpilot.selfdrive.ui.lib.egpu_status import EgpuStatus, egpu_status

# side strips - blinker / blindspot
INDICATOR_BLINK_RATE_FAST = int(gui_app.target_fps * 0.25)
INDICATOR_BLINK_RATE_STD = int(gui_app.target_fps * 0.5)
INDICATOR_COLOR_BSM = rl.Color(255, 255, 0, 255)
INDICATOR_COLOR_BLINKER = rl.Color(0, 255, 0, 255)

# eGPU corners. White = healthy, orange = problem; alpha and pulse carry the
# sub-states. Deliberately far from the ALKA border blue (0x22a0dc) and the
# engaged green, which the corners are drawn on top of.
EGPU_CORNER_ARM = 90                 # px along each edge
EGPU_COLOR_OK = rl.Color(255, 255, 255, 255)
EGPU_COLOR_FAULT = rl.Color(0xFF, 0x8C, 0x00, 255)
EGPU_ALPHA_NOT_COMPILED = 0.25
EGPU_ALPHA_FALLBACK = 0.65
EGPU_PULSE_RATE = 6.0                # rad/s, matches the mici HUD

TRANSPARENT = rl.Color(0, 0, 0, 0)


def indicator_side_state(blinker_state, bsm_state, show_prev, count_prev):
  """Next (show, count, color) for one side strip. Pure, so it is testable."""
  show, count, color = show_prev, count_prev, TRANSPARENT

  if not blinker_state and not bsm_state:
    show = False
    count = 0
  else:
    count += 1

  if bsm_state and blinker_state:
    show = not show if count % INDICATOR_BLINK_RATE_FAST == 0 else show
    color = INDICATOR_COLOR_BSM
  elif blinker_state:
    show = not show if count % INDICATOR_BLINK_RATE_STD == 0 else show
    color = INDICATOR_COLOR_BLINKER
  elif bsm_state:
    show = True
    color = INDICATOR_COLOR_BSM
  else:
    show = False

  return show, count, color


class DpBorderIndicator:
  def __init__(self):
    self._show_left = False
    self._show_right = False
    self._count_left = 0
    self._count_right = 0
    self._color_left = TRANSPARENT
    self._color_right = TRANSPARENT

    self._egpu_show = False
    self._egpu_color = TRANSPARENT
    self._egpu_small_model_engaged = False

  def render(self, rect: rl.Rectangle):
    """Called once per frame, after the upstream border is drawn."""
    self._update(ui_state.sm)
    self._draw_side_strips(rect)
    if self._egpu_show:
      self._draw_egpu_corners(rect)

  # ---------- state ----------

  def _update(self, sm):
    cs = sm['carState']
    self._show_left, self._count_left, self._color_left = \
      indicator_side_state(cs.leftBlinker, cs.leftBlindspot, self._show_left, self._count_left)
    self._show_right, self._count_right, self._color_right = \
      indicator_side_state(cs.rightBlinker, cs.rightBlindspot, self._show_right, self._count_right)
    self._update_egpu(sm)

  def _update_egpu(self, sm):
    # mirrors the mici HUD: the small model latches once engaged without the big one
    if ui_state.status == UIStatus.ENGAGED and ui_state.usbgpu_active is not True \
       and not ui_state.usbgpu_loading:
      self._egpu_small_model_engaged = True
    elif ui_state.status == UIStatus.DISENGAGED:
      self._egpu_small_model_engaged = False

    status = egpu_status(
      usbgpu=ui_state.usbgpu,
      usbgpu_compiled=ui_state.usbgpu_compiled,
      usbgpu_active=ui_state.usbgpu_active,
      usbgpu_loading=ui_state.usbgpu_loading,
      chestnut_present=sm['deviceState'].chestnutPresent,
      model_started=sm.recv_frame['modelV2'] > ui_state.started_frame,
      model_alive=sm.alive['modelV2'],
      small_model_engaged=self._egpu_small_model_engaged,
    )

    if status == EgpuStatus.ABSENT:
      self._egpu_show = False
      return

    base, alpha = EGPU_COLOR_OK, 1.0
    if status == EgpuStatus.NOT_COMPILED:
      alpha = EGPU_ALPHA_NOT_COMPILED
    elif status == EgpuStatus.LOADING:
      pulse = 0.5 - 0.5 * math.cos(rl.get_time() * EGPU_PULSE_RATE)
      alpha = 0.35 + 0.65 * pulse
    elif status == EgpuStatus.FALLBACK:
      base, alpha = EGPU_COLOR_FAULT, EGPU_ALPHA_FALLBACK
    elif status == EgpuStatus.FAILED:
      base = EGPU_COLOR_FAULT

    self._egpu_show = True
    self._egpu_color = rl.Color(base.r, base.g, base.b, int(255 * alpha))

  # ---------- drawing ----------

  def _draw_side_strips(self, rect: rl.Rectangle):
    y = int(rect.y + 4 * UI_BORDER_SIZE)
    height = int(rect.height - 8 * UI_BORDER_SIZE)
    if self._show_left:
      rl.draw_rectangle(int(rect.x), y, UI_BORDER_SIZE, height, self._color_left)
    if self._show_right:
      rl.draw_rectangle(int(rect.x + rect.width - UI_BORDER_SIZE), y, UI_BORDER_SIZE, height, self._color_right)

  def _draw_egpu_corners(self, rect: rl.Rectangle):
    # An L at each corner, arms growing inward so they stay on screen.
    arm, b = EGPU_CORNER_ARM, UI_BORDER_SIZE
    color = self._egpu_color
    x0, y0 = int(rect.x), int(rect.y)
    x1, y1 = int(rect.x + rect.width), int(rect.y + rect.height)
    for right in (False, True):
      for bottom in (False, True):
        hx = x1 - arm if right else x0
        vx = x1 - b if right else x0
        hy = y1 - b if bottom else y0
        vy = y1 - arm if bottom else y0
        rl.draw_rectangle(hx, hy, arm, b, color)      # horizontal arm
        rl.draw_rectangle(vx, vy, b, arm, color)      # vertical arm
