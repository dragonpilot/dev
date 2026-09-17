#!/usr/bin/env python3
import os
import sys
from openpilot.common.basedir import BASEDIR
from dragonpilot.system.ui.lib.multilang import TRANSLATIONS_DIR, multilang

LANGUAGES_FILE = os.path.join(str(TRANSLATIONS_DIR), "languages.json")
POT_FILE = os.path.join(str(TRANSLATIONS_DIR), "dragonpilot.pot")


def update_translations():
  files = []
  for root, _, filenames in os.walk(os.path.join(BASEDIR, "dragonpilot")):
    for filename in filenames:
      if filename.endswith(".py"):
        files.append(os.path.relpath(os.path.join(root, filename), BASEDIR))

  # Create main translation file
  cmd = ("xgettext -L Python --keyword=tr --keyword=trn:1,2 --keyword=tr_noop --from-code=UTF-8 " +
         "--flag=tr:1:python-brace-format --flag=trn:1:python-brace-format --flag=trn:2:python-brace-format " +
         f"-D {BASEDIR} -o {POT_FILE} {' '.join(files)}")

  ret = os.system(cmd)
  assert ret == 0

  # Also extract dashy's web UI strings (JavaScript) into the same template.
  # The frontend now lives in the separate dashy-web repo; only its built
  # dist/ is vendored here (where tr() calls are minified and unscannable),
  # so scan dashy-web's src and append the tr()/tr_noop() literals via
  # --join-existing. Override the location with DASHY_SRC; if the source
  # isn't present (e.g. dashy-web isn't checked out), this is skipped but
  # loudly warns, since a silent skip here would let msgmerge strip every
  # dashy string from all .po files with no error.
  dashy_src = os.environ.get("DASHY_SRC") or os.path.join(BASEDIR, "..", "dashy-web", "src")
  dashy_src = os.path.realpath(dashy_src)
  if os.path.isdir(dashy_src):
    js_files = [os.path.relpath(os.path.join(root, fn), dashy_src)
                for root, _, filenames in os.walk(dashy_src)
                for fn in filenames if fn.endswith(".js")]
    if js_files:
      cmd = ("xgettext -L JavaScript --keyword=tr --keyword=tr_noop --from-code=UTF-8 "
             "--join-existing "
             f"-D {dashy_src} -o {POT_FILE} {' '.join(js_files)}")
      ret = os.system(cmd)
      assert ret == 0
  else:
    msg = f"update_translations: WARNING - dashy-web source not found at {dashy_src}, skipping dashy UI string extraction (set DASHY_SRC to override)"
    print(msg, file=sys.stderr)

  # Generate/update translation files for each language
  for name in multilang.languages.values():
    po_file = os.path.join(TRANSLATIONS_DIR, f"dragonpilot_{name}.po")
    mo_file = os.path.join(TRANSLATIONS_DIR, f"dragonpilot_{name}.mo")

    if os.path.exists(po_file):
      cmd = f"msgmerge --update --no-fuzzy-matching --backup=none --sort-output {po_file} {POT_FILE}"
      ret = os.system(cmd)
      assert ret == 0
    else:
      cmd = f"msginit -l {name} --no-translator --input {POT_FILE} --output-file {po_file}"
      ret = os.system(cmd)
      assert ret == 0

    # Compile .po to .mo
    cmd = f"msgfmt {po_file} -o {mo_file}"
    ret = os.system(cmd)
    assert ret == 0


if __name__ == "__main__":
  update_translations()
