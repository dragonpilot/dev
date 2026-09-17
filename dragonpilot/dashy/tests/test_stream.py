# Copyright (c) 2026, Rick Lan
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, and/or sublicense,
# for non-commercial purposes only, subject to the following conditions:
#
# - The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
# - Commercial use (e.g. use in a product, service, or activity intended to
#   generate revenue) is prohibited without explicit written permission from
#   the copyright holder.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Tier 3 — data stream smoke test.

Asserts a dashyState frame with our marker reaches an SSE client over
/api/stream. Survives the aiohttp -> stdlib refactor: only the server's
framework changes, not the SSE wire contract this reads.
"""

import json
import subprocess
import sys
import time

from openpilot.common.basedir import BASEDIR
from openpilot.common.test import OpenpilotTestCase
from dragonpilot.dashy.tests.helpers import server, server_factory  # noqa: F401

# Runs as a fresh process so cereal picks up the server's OPENPILOT_PREFIX from
# the inherited env (cereal binds the prefix at import).
_PUBLISHER = """
import time
from openpilot.cereal import messaging
pm = messaging.PubMaster(['dashyState'])
while True:
    m = messaging.new_message('dashyState')
    m.dashyState.json = '{"marker": 4242}'
    pm.send('dashyState', m)
    time.sleep(0.02)
"""


class TestDashyStream(OpenpilotTestCase):
  def test_stream_delivers_dashystate(self, server):  # noqa: F811
    pub = subprocess.Popen(
      [sys.executable, "-c", _PUBLISHER],
      cwd=BASEDIR,
      env=server.env,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
    )
    try:
      time.sleep(0.8)  # let the publisher come up and the server's SubMaster latch
      if pub.poll() is not None:
        self.fail("publisher exited early:\n" + pub.stdout.read()[:400])
      frame = server.sse_recv_one("/api/stream", timeout=6)
      assert json.loads(frame).get("marker") == 4242
    finally:
      pub.terminate()
      try:
        pub.wait(timeout=5)
      except Exception:
        pub.kill()
