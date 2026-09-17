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

"""Tier 2 — smoke + drift coverage for dashyd.py (previously untested)."""

from openpilot.common.test import OpenpilotTestCase

# dragonpilot-specific services owned by other min-feat branches. _available_topics()
# drops these when their branch isn't composed in; see dashyd's docstring.
DP_OPTIONAL_TOPICS = {"controlsStateExt"}


class TestDashyd(OpenpilotTestCase):
  def test_import_smoke(self):
    import dragonpilot.dashy.dashyd  # noqa: F401

  def test_topics_are_real_cereal_services(self):
    from openpilot.cereal.services import SERVICE_LIST
    from dragonpilot.dashy import dashyd
    unknown = (set(dashyd.TOPICS) - DP_OPTIONAL_TOPICS) - set(SERVICE_LIST)
    assert not unknown, f"dashyd.TOPICS has unknown cereal service(s): {sorted(unknown)}"
