import unittest

from dragonpilot.selfdrive.ui.lib.egpu_status import EgpuStatus, egpu_status


def status(**kw):
  """Healthy running eGPU by default; override one signal per test."""
  args = dict(usbgpu=True, usbgpu_compiled=True, usbgpu_active=True,
              usbgpu_loading=False, chestnut_present=True,
              model_started=True, model_alive=True, small_model_engaged=False)
  args.update(kw)
  return egpu_status(**args)


class TestEgpuStatus(unittest.TestCase):
  def test_running(self):
    self.assertEqual(status(), EgpuStatus.RUNNING)

  def test_absent_wins_over_everything(self):
    # no chestnut -> nothing is drawn, regardless of any other signal
    self.assertEqual(status(usbgpu=False), EgpuStatus.ABSENT)
    self.assertEqual(status(usbgpu=False, usbgpu_compiled=False, usbgpu_active=False),
                     EgpuStatus.ABSENT)

  def test_not_compiled(self):
    # attached but the big model was never built for this install
    self.assertEqual(status(usbgpu_compiled=False), EgpuStatus.NOT_COMPILED)

  def test_loading_explicit(self):
    self.assertEqual(status(usbgpu_loading=True), EgpuStatus.LOADING)

  def test_loading_before_modeld_decides(self):
    # UsbGpuActive is None and modelV2 has not arrived yet
    self.assertEqual(status(usbgpu_active=None, model_started=False), EgpuStatus.LOADING)

  def test_failed_when_param_says_inactive(self):
    self.assertEqual(status(usbgpu_active=False), EgpuStatus.FAILED)

  def test_failed_when_unplugged_mid_drive(self):
    # ui_state.usbgpu stays sticky onroad, but chestnutPresent goes false
    self.assertEqual(status(chestnut_present=False), EgpuStatus.FAILED)

  def test_failed_when_big_model_dies(self):
    self.assertEqual(status(model_alive=False), EgpuStatus.FAILED)

  def test_failed_when_never_activated(self):
    # modelV2 arriving while UsbGpuActive is still None means it never came up
    self.assertEqual(status(usbgpu_active=None, model_started=True), EgpuStatus.FAILED)

  def test_fallback_needs_a_failure(self):
    # engaged on the small model, but only counts once the big model has failed
    self.assertEqual(status(small_model_engaged=True, usbgpu_active=False),
                     EgpuStatus.FALLBACK)
    self.assertEqual(status(small_model_engaged=True), EgpuStatus.RUNNING)

  def test_not_compiled_outranks_failure(self):
    # a never-built model is the more actionable message
    self.assertEqual(status(usbgpu_compiled=False, usbgpu_active=False),
                     EgpuStatus.NOT_COMPILED)


if __name__ == "__main__":
  unittest.main()
