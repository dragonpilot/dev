#!/usr/bin/env python3
"""
Drift detector for the dashy openpilot-settings mirror.

We expose upstream openpilot's Toggles + Developer settings through the dashy web UI by
mirroring them into dragonpilot/settings/openpilot.*.py. This test greps the real source
to confirm every mirrored key is still referenced there, so an upstream rename/removal (or
a stale mirror entry) fails loudly instead of silently shipping a dead setting.

Grep-based on purpose: no live imports of upstream layout classes (their contents differ
per branch/version) and no hand-maintained expected-key lists. It catches dead/renamed
keys. It does NOT flag a brand-new upstream setting you haven't mirrored yet - you notice
those the moment you look at the dashy UI.

If a key is reported stale: upstream renamed/removed it (or it never existed) - update the
matching entry in dragonpilot/settings/openpilot.*.py.
"""
import unittest
from pathlib import Path

from dragonpilot.settings import SETTINGS

# Repo root (this file lives at dragonpilot/system/tests/, so four levels up).
_REPO = Path(__file__).resolve().parents[3]

# Source that defines/uses the settings we mirror: upstream settings layout + widgets
# (stock keys) and the dp dashy code (dp additions, e.g. the "Clear SSH Keys" action).
# Deliberately excludes dragonpilot/settings (the mirror itself) to avoid self-reference.
_SOURCE_ROOTS = ("openpilot/selfdrive/ui/layouts/settings", "openpilot/selfdrive/ui/widgets", "dragonpilot/dashy")

# Mirror sections whose every key must be referenced in source.
_MIRROR_SECTIONS = ("Openpilot", "Developer")


def _source_blob() -> str:
  parts = []
  for root in _SOURCE_ROOTS:
    for p in (_REPO / root).rglob("*.py"):
      parts.append(p.read_text(errors="ignore"))
  return "\n".join(parts)


def _mirror_keys(section_title: str) -> set[str]:
  for s in SETTINGS:
    if s["title"] == section_title:
      return {it["key"] for it in s["settings"]}
  return set()


class TestOpenpilotMirror(unittest.TestCase):
  def test_mirror_keys_referenced_in_source(self):
    blob = _source_blob()
    stale = {}
    for section in _MIRROR_SECTIONS:
      missing = sorted(k for k in _mirror_keys(section) if k not in blob)
      if missing:
        stale[section] = missing
    self.assertFalse(stale,
                     f"Stale mirror keys not referenced under {_SOURCE_ROOTS}: {stale}. "
                     + "Upstream likely renamed/removed them - update dragonpilot/settings/openpilot.*.py")


if __name__ == "__main__":
  unittest.main()
