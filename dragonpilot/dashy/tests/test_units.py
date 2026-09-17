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

"""Tier 2 — pure-logic unit tests (import the dashy_server package directly)."""

import os

from openpilot.common.test import OpenpilotTestCase
from dragonpilot.dashy.dashy_server import config, habit, http, i18n
from dragonpilot.dashy.dashy_server.habit import _habit_grid, _habit_bands, _read_accel_log
from dragonpilot.dashy.tests.helpers import tmp_path  # noqa: F401


def _samples(speed, accels):
  return [(speed, a) for a in accels]


class TestDashyUnits(OpenpilotTestCase):
  # ---- path safety ----
  def test_get_safe_path_within(self, tmp_path, monkeypatch):  # noqa: F811
    root = os.path.realpath(str(tmp_path))
    monkeypatch.setattr(config, "DEFAULT_DIR", root)
    assert http.get_safe_path("sub/dir") == os.path.join(root, "sub", "dir")
    assert http.get_safe_path("/") == root

  def test_get_safe_path_traversal_blocked(self, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "DEFAULT_DIR", os.path.realpath(str(tmp_path)))
    assert http.get_safe_path("../../../../etc/passwd") is None

  # ---- accel-log parsing ----
  def test_read_accel_log_parses_and_skips_bad(self, tmp_path):  # noqa: F811
    f = tmp_path / "accel_log.csv"
    f.write_text("1.0,0.5\nbad line\n2.0,0.4\n,\n3.0,x\n4.0,0.3\n")
    assert habit._read_accel_log(str(f)) == [(1.0, 0.5), (2.0, 0.4), (4.0, 0.3)]

  def test_read_accel_log_missing_file(self):
    assert habit._read_accel_log("/no/such/accel_log.csv") == []

  # ---- habit grid / points / bands ----
  def test_habit_grid_skips_thin_windows(self):
    samples = [(7.0 + (i % 5) * 0.1, 0.5) for i in range(200)]  # dense ~7 m/s
    samples += [(35.0, 0.5)] * 3  # thin high-speed tail
    speeds = [s for s, _ in habit._habit_grid(samples, min_w=60)]
    assert speeds and all(4.0 <= s <= 12.0 for s in speeds)  # only the dense region
    assert not any(s > 30 for s in speeds)  # thin tail dropped

  def test_habit_points_caps(self):
    pts = habit._habit_points([(float(i % 30), 0.5) for i in range(10000)], cap=2000)
    assert len(pts) <= 2000 and all(len(p) == 2 for p in pts)

  def test_habit_band_is_non_increasing(self):
    grid = [(float(i), sorted([1.0 - i * 0.05 + (k % 3) * 0.02 for k in range(100)])) for i in range(20)]
    vals = [v for _, v in habit._habit_band(grid, 0.9)]
    assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))

  def test_habit_bands_ordered_and_labeled(self):
    grid = [(float(i), sorted([max(0.0, 1.5 - i * 0.05 + (k % 10) * 0.05) for k in range(100)])) for i in range(15)]
    b = habit._habit_bands(grid)
    assert set(b) == {"lower", "mid", "upper"}
    lo = {round(s, 1): v for s, v in b["lower"]}
    md = {round(s, 1): v for s, v in b["mid"]}
    up = {round(s, 1): v for s, v in b["upper"]}
    assert md and all(up[k] >= md[k] >= lo[k] for k in md)

  # ---- i18n map building ----
  def test_build_i18n_map_filters_header_plurals_and_empties(self, monkeypatch):
    class _Cat:
      _catalog = {"": "hdr", "Hello": "Bonjour", "Empty": "", "a\x00b": "plural-form"}

    class _Tr:
      _dragon_translation = _Cat()

      def _ensure_loaded(self):
        pass

    monkeypatch.setattr(i18n, "dp_multilang", _Tr())
    assert i18n._build_i18n_map() == {"Hello": "Bonjour"}

  def test_habit_grid_min_w_is_60(self):
    # 60 samples in one window -> a grid point forms; 59 does not (v1 dense-data threshold)
    assert any(abs(gs - 10.0) <= 1.5 for gs, _ in _habit_grid(_samples(10.0, [1.5] * 60)))
    assert not any(abs(gs - 10.0) <= 1.5 for gs, _ in _habit_grid(_samples(10.0, [1.5] * 59)))

  def test_habit_bands_are_p75_p90_p98(self):
    # a window with a known spread -> bands pick the 75/90/98th of the window
    accels = [0.5, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0] * 8   # 64 samples
    grid = _habit_grid(_samples(10.0, accels))
    bands = _habit_bands(grid)
    assert set(bands) == {'lower', 'mid', 'upper'}
    # ordered lower (p75) <= mid (p90) <= upper (p98) at the populated speed
    lo = [v for s, v in bands['lower'] if abs(s - 10.0) <= 0.5][0]
    mid = [v for s, v in bands['mid'] if abs(s - 10.0) <= 0.5][0]
    up = [v for s, v in bands['upper'] if abs(s - 10.0) <= 0.5][0]
    assert lo <= mid <= up

  def test_header_line_ignored(self):
    import os
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(p, "w") as f:
      f.write("# dp_accel_log v2\n10.000,1.500\n12.000,1.200\n")
    assert _read_accel_log(p) == [(10.0, 1.5), (12.0, 1.2)]
    os.remove(p)
