"""
dp - eGPU (chestnut) status, reduced to a single enum.

The mici UI splits this across two widgets: a readiness icon on the home screen
(layouts/home.py) and a four-state running icon in the onroad HUD
(onroad/hud_renderer.py). tici/tizi have neither, so the onroad border corners
carry the whole story. This module holds the state decision only - no drawing -
so it can be unit tested and, if the mici HUD is ever refactored, shared.
"""
from enum import Enum


class EgpuStatus(Enum):
  ABSENT = "absent"            # no chestnut attached -> draw nothing
  NOT_COMPILED = "not_compiled"  # attached, but the big model was never built
  LOADING = "loading"          # big model is coming up
  FAILED = "failed"            # attached and compiled, but not running
  FALLBACK = "fallback"        # engaged on the small model after a big-model failure
  RUNNING = "running"          # modeld is running on the eGPU


def egpu_status(usbgpu: bool, usbgpu_compiled: bool, usbgpu_active: bool | None,
                usbgpu_loading: bool, chestnut_present: bool,
                model_started: bool, model_alive: bool,
                small_model_engaged: bool) -> EgpuStatus:
  """Collapse the eGPU signals into one state.

  Mirrors the big_failed/loading composition in mici's hud_renderer so the two
  UIs cannot drift on what "failed" means.

  usbgpu          -- chestnut attached (ui_state.usbgpu, sticky while onroad)
  usbgpu_compiled -- big model pkl was built (build-time sticky, latches true)
  usbgpu_active   -- UsbGpuActive param; None until modeld decides
  model_started   -- modelV2 has been received since the drive started
  """
  if not usbgpu:
    return EgpuStatus.ABSENT
  if not usbgpu_compiled:
    return EgpuStatus.NOT_COMPILED

  failed = (usbgpu_active is False or
            not chestnut_present or
            (usbgpu_active is True and model_started and not model_alive) or
            (usbgpu_active is None and model_started))
  if usbgpu_loading or (usbgpu_active is None and not failed):
    return EgpuStatus.LOADING
  if small_model_engaged and failed:
    return EgpuStatus.FALLBACK
  if failed:
    return EgpuStatus.FAILED
  return EgpuStatus.RUNNING
