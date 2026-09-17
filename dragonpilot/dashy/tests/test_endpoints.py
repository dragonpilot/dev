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

"""Tier 1 — HTTP contract tests (black-box, via a real serverd subprocess).

These assert the wire contract, not aiohttp internals, so they are the intended
acceptance suite for the aiohttp -> stdlib+SSE refactor.
"""

from openpilot.common.test import OpenpilotTestCase
from dragonpilot.dashy.tests.helpers import server, server_factory, _param_registered, ACCEL_PROFILES_KEY  # noqa: F401


class TestDashyEndpoints(OpenpilotTestCase):
  def test_init_shape(self, server):  # noqa: F811
    d = server.get_json("/api/init")
    assert {"dp_dev_dashy", "isOffroad", "i18n"} <= set(d)
    assert isinstance(d["i18n"], dict)

  def test_settings_shape_and_brand_gating(self, server):  # noqa: F811
    d = server.get_json("/api/settings")
    assert isinstance(d.get("settings"), list) and d["settings"]
    for sec in d["settings"]:
      assert "title" in sec and isinstance(sec.get("settings"), list)
    assert "languages" in d and "i18n" in d
    titles = [s["title"] for s in d["settings"]]
    # seeded brand is toyota -> non-matching brand sections must be hidden
    assert not any(t in ("Honda", "HKG", "VAG", "Mazda") for t in titles)

  def test_accel_config_available_with_op_long(self, server):  # noqa: F811
    if not _param_registered(ACCEL_PROFILES_KEY):
      self.skipTest("dp_lon_accel_profiles not registered (min-feat/lon/accel-eq not composed in)")
    assert server.status("/api/accel_eq/config") == 200
    cfg = server.get_json("/api/accel_eq/config")
    assert {"max_pts", "min_pts", "min_gap", "speed_ceil", "max_accel_ceil"} <= set(cfg)

  def test_accel_config_gated_off_without_op_long(self, server_factory):  # noqa: F811
    if not _param_registered(ACCEL_PROFILES_KEY):
      self.skipTest("dp_lon_accel_profiles not registered (min-feat/lon/accel-eq not composed in)")
    s = server_factory(op_long=False)
    assert s.status("/api/accel_eq/config") == 404

  def test_habit_meta_and_full(self, server):  # noqa: F811
    meta = server.get_json("/api/accel_eq/habit?meta=1")
    assert meta["count"] > 0 and meta["bands"] > 0

    full = server.get_json("/api/accel_eq/habit")
    assert isinstance(full["points"], list) and full["points"]
    env = full["envelope"]
    assert {"lower", "mid", "upper"} <= set(env)
    for band in env.values():  # each line non-increasing
      vals = [v for _, v in band]
      assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
    lo = {round(s, 1): v for s, v in env["lower"]}  # upper >= mid >= lower
    md = {round(s, 1): v for s, v in env["mid"]}
    up = {round(s, 1): v for s, v in env["upper"]}
    common = set(lo) & set(md) & set(up)
    assert common
    for k in common:
      assert up[k] >= md[k] >= lo[k]

  def test_habit_missing_file_is_empty(self, server_factory):  # noqa: F811
    s = server_factory(habit_csv=None)
    assert s.get_json("/api/accel_eq/habit?meta=1") == {"count": 0, "bands": 0}
    assert s.get_json("/api/accel_eq/habit")["points"] == []

  def test_habit_reset_archives_log(self, server):  # noqa: F811
    from pathlib import Path
    csv = Path(server.data_dir, "accel_log.csv")
    archive = Path(server.data_dir, "accel_log.pre_grade.csv")
    assert csv.exists()                       # server fixture seeds a populated log
    st, body = server.post_json("/api/accel_eq/habit/reset", {})
    assert st == 200
    assert body == {"count": 0}
    assert not csv.exists()
    assert archive.exists()
    assert server.get_json("/api/accel_eq/habit?meta=1") == {"count": 0, "bands": 0}

  def test_habit_reset_idempotent_without_log(self, server_factory):  # noqa: F811
    s = server_factory(habit_csv=None)
    st, body = s.post_json("/api/accel_eq/habit/reset", {})
    assert st == 200
    assert body == {"count": 0}

  def test_unknown_param_is_403(self, server):  # noqa: F811
    st, _ = server.post_json("/api/settings/params/NotARealParam", {"value": True})
    assert st == 403

  def test_param_roundtrip(self, server):  # noqa: F811
    ok = (True, "1", 1, "true")
    st, _ = server.post_json("/api/settings/params/ExperimentalMode", {"value": True})
    assert st == 200
    got = server.poll_json("/api/settings/params/ExperimentalMode", lambda d: d.get("value") in ok)
    assert got["value"] in ok

  def test_needs_restart_triggers_onroad_cycle(self, server):  # noqa: F811
    settings = server.get_json("/api/settings")["settings"]
    key = next((it["key"] for sec in settings for it in sec["settings"] if it.get("needs_restart") and str(it.get("type", "")).startswith("toggle")), None)
    if not key:
      self.skipTest("no needs_restart param in the served settings schema")
    server.post_json(f"/api/settings/params/{key}", {"value": True})
    assert server.poll_param("OnroadCycleRequested", True) is True

  def test_files_listing_and_traversal_blocked(self, server):  # noqa: F811
    names = [f["name"] for f in server.get_json("/api/files?path=/")["files"]]
    assert "drive1.txt" in names and "drive2.txt" in names
    assert server.status("/api/files?path=../../../../etc") == 404

  def test_no_cache_headers_on_assets(self, server):  # noqa: F811
    try:
      r = server.get("/index.html")
    except Exception:
      self.skipTest("web/dist not built")
    assert "no-cache" in r.headers.get("Cache-Control", "") or "no-store" in r.headers.get("Cache-Control", "")
