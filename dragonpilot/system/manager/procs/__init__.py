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

Dragonpilot managed-process contributions.

A feature ships ONE file here, `NN_<name>.py`, exporting `PROCS`:

    from openpilot.system.manager.process import PythonProcess
    from openpilot.system.manager.process_config import always_run, only_onroad, and_

    def _enabled(started, params, CP) -> bool:
      return params.get_bool("dp_dev_dashy")

    PROCS = [
      PythonProcess("serverd", "dragonpilot.dashy.serverd", always_run),
      PythonProcess("dashyd", "dragonpilot.dashy.dashyd", and_(_enabled, only_onroad)),
    ]

`process_config.py` then needs one line: `procs += dp_procs()`.

This covers BOTH anchors features used to share in that file - the gating-predicate
region and the `procs` list. The predicate now lives beside the process that uses it,
in the feature's own file, so neither can collide. Features contribute a variable
number of processes (one adds six), which is why this globs a directory rather than
using pre-allocated slots like cereal/services.py.

The NN_ prefix fixes load order; it rarely matters for processes but keeps the composed
list deterministic across rebuilds.

A file that fails to import is reported and skipped - one broken feature must not stop
the manager from starting. The name is printed so it is not silent.

NOTE on the circular import: feature files import gating helpers (`always_run`,
`only_onroad`, `and_`, `or_`) from `process_config`, which is the module that calls
`dp_procs()`. That works only because the call sits at the *end* of `process_config.py`,
after those helpers are defined - by then the partially-initialised module has them.
So a feature may import anything defined ABOVE the `procs += dp_procs()` line, and
nothing defined below it. Keep the call where it is.
"""
import importlib.util
import sys
from pathlib import Path


def dp_procs() -> list:
  """Collect PROCS from every dragonpilot/system/manager/procs/NN_*.py."""
  out: list = []
  here = Path(__file__).parent
  for py in sorted(here.glob("*.py")):
    if py.name == "__init__.py":
      continue
    mod_name = f"_dp_procs_{py.stem.replace('-', '_').replace('.', '_')}"
    try:
      spec = importlib.util.spec_from_file_location(mod_name, py)
      mod = importlib.util.module_from_spec(spec)
      sys.modules[mod_name] = mod
      spec.loader.exec_module(mod)
      out += list(getattr(mod, "PROCS", []))
    except Exception as e:
      print(f"[dp.procs] failed to load {py.name}: {e}")
  return out
