import socket
import time

import pyray as rl
from openpilot.common.qrcode import make_texture
from openpilot.common.swaglog import cloudlog

IP_REFRESH_INTERVAL = 5  # seconds


class DashyQR:
  """Shared QR code generator for dashy web UI."""

  def __init__(self):
    self._qr_texture: rl.Texture | None = None
    self._last_qr_url: str | None = None
    self._last_ip_check: float = 0

  @property
  def texture(self):
    return self._qr_texture

  @property
  def url(self) -> str | None:
    return self._last_qr_url

  @staticmethod
  def get_local_ip() -> str | None:
    try:
      s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      s.connect(("8.8.8.8", 80))
      ip = s.getsockname()[0]
      s.close()
      return ip
    except Exception:
      return None

  @staticmethod
  def get_web_ui_url() -> str:
    ip = DashyQR.get_local_ip()
    return f"http://{ip if ip else 'localhost'}:5088"

  def _generate_qr_code(self, url: str) -> None:
    try:
      if self._qr_texture and self._qr_texture.id != 0:
        rl.unload_texture(self._qr_texture)

      # inverted=True -> white modules on black with no quiet zone, matching
      # the previous fill_color="white"/back_color="black"/border=0 rendering
      self._qr_texture = make_texture(url, inverted=True)
      self._last_qr_url = url
    except Exception as e:
      cloudlog.warning(f"QR code generation failed: {e}")
      self._qr_texture = None

  def update(self, force: bool = False) -> bool:
    """Update QR code if needed. Returns True if updated."""
    now = time.monotonic()
    if not force and now - self._last_ip_check < IP_REFRESH_INTERVAL and self._qr_texture:
      return False

    self._last_ip_check = now
    url = self.get_web_ui_url()
    if url != self._last_qr_url:
      self._generate_qr_code(url)
      return True
    return False

  def force_update(self):
    """Force immediate IP check and QR regeneration."""
    self._last_ip_check = 0

  def cleanup(self):
    """Unload texture resources."""
    if self._qr_texture and self._qr_texture.id != 0:
      rl.unload_texture(self._qr_texture)
      self._qr_texture = None

  def __del__(self):
    self.cleanup()
