#!/usr/bin/env python3
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

Dragonpilot param-surface generator.

A feature declares which consumers may read its param, on the settings item it
already ships:

    {"key": "dp_toyota_tss1_sng", "param_type": "BOOL", "car_param": True}
    {"key": "dp_lon_acm",         "param_type": "BOOL", "lon_param": True}
    {"key": "dp_ui_lead",         "param_type": "INT",  "ui_param":  True}

This script AST-walks dragonpilot/settings/*.py and writes each declaration set
into a marked region of the matching dp-owned module (see TARGETS). No upstream
file carries generated content.

  car_param -> opendbc/car/dp_params.py          DP_CAR  filled by card.py
  lon_param -> dragonpilot/.../dp_lon_params.py  DP_LON  filled by plannerd.py
  ui_param  -> dragonpilot/.../dp_ui_params.py   setattr applied by ui_state.py

car/lon emit keys only and must be BOOL: they gate behaviour and are read with
get_bool. ui emits (key, type) pairs because the UI genuinely has INT params
(speeds, modes) and needs the type to pick the right getter.

There are deliberately no bit values anywhere. An earlier design packed these into
DPFlags bitmasks, which meant every feature hand-picked a bit; five of seven
collided on 2**12/2**13 and were hand-renumbered on every rebuild. Keys carry no
number, so nothing can collide.

Why generate rather than read dragonpilot.settings at runtime: the consumers sit on
core-feat/params, which is upstream of the branch owning the settings package, and
opendbc must not import dragonpilot at all.

Hermetic: no feature module is imported. The settings directory is contributed by
downstream branches, so an absent directory simply yields nothing.
"""
import ast
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SETTINGS_DIR = SCRIPT_DIR / "dragonpilot" / "settings"

# declaration key -> (target file, marker, generated constant, shape)
TARGETS = {
  "car_param": (SCRIPT_DIR / "opendbc_repo" / "opendbc" / "car" / "dp_params.py",
                "DP_CAR_PARAMS", "DP_CAR_PARAMS_KEYS", "keys"),
  "lon_param": (SCRIPT_DIR / "dragonpilot" / "selfdrive" / "controls" / "lib" / "dp_lon_params.py",
                "DP_LON_PARAMS", "DP_LON_PARAMS_KEYS", "keys"),
  "ui_param":  (SCRIPT_DIR / "dragonpilot" / "selfdrive" / "ui" / "dp_ui_params.py",
                "DP_UI_PARAMS", "DP_UI_PARAMS", "pairs"),
}

# These gate behaviour and are read with get_bool, so anything else is a mistake.
BOOL_ONLY = {"car_param", "lon_param"}

VALID_PARAM_TYPES = {"STRING", "BOOL", "INT", "FLOAT", "TIME", "JSON", "BYTES"}


def _extract_items_node(tree: ast.AST) -> ast.List | None:
  for node in tree.body:
    if isinstance(node, ast.Assign):
      for target in node.targets:
        if isinstance(target, ast.Name) and target.id == "ITEMS":
          if not isinstance(node.value, ast.List):
            raise ValueError("ITEMS must be a list literal")
          return node.value
  return None


def _literal_or_none(node: ast.AST):
  """Return the literal value if node is a string/int/float/bool constant, else None."""
  if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
    return node.value
  return None


def extract_params(py_file: Path, decl: str) -> list[tuple[str, str | None]]:
  """Return (key, param_type) for every item in this settings file declaring `decl`."""
  tree = ast.parse(py_file.read_text())
  items_node = _extract_items_node(tree)
  if items_node is None:
    return []

  out: list[tuple[str, str | None]] = []
  for entry in items_node.elts:
    if not isinstance(entry, ast.Dict):
      continue

    fields = {}
    for k_node, v_node in zip(entry.keys, entry.values):
      if isinstance(k_node, ast.Constant) and k_node.value in ("key", decl, "param_type"):
        lit = _literal_or_none(v_node)
        if lit is None:
          raise ValueError(f"{py_file.name}: field {k_node.value!r} must be a literal")
        fields[k_node.value] = lit

    if not fields.get(decl):
      continue
    if "key" not in fields:
      raise ValueError(f"{py_file.name}: {decl} item has no key")

    key = str(fields["key"])
    ptype = fields.get("param_type")
    if ptype is not None:
      ptype = str(ptype)
      if ptype not in VALID_PARAM_TYPES:
        raise ValueError(f"{py_file.name}: {key}: unknown param_type {ptype!r}")
      if decl in BOOL_ONLY and ptype != "BOOL":
        raise ValueError(f"{py_file.name}: {key}: {decl} requires param_type BOOL, got {ptype!r}")

    out.append((key, ptype))
  return out


def collect_all(decl: str) -> tuple[tuple[str, str | None], ...]:
  """Sorted by key for determinism: two rebuilds of the same feature set match."""
  if not SETTINGS_DIR.is_dir():
    return ()

  items: list[tuple[str, str | None]] = []
  for py_file in sorted(SETTINGS_DIR.glob("*.py")):
    if py_file.name == "__init__.py":
      continue
    items += extract_params(py_file, decl)

  keys = [k for k, _ in items]
  dupes = {k for k in keys if keys.count(k) > 1}
  if dupes:
    raise ValueError(f"duplicate {decl} keys: {', '.join(sorted(dupes))}")
  return tuple(sorted(items, key=lambda kv: kv[0]))


def render_region(items: tuple[tuple[str, str | None], ...], const: str, shape: str) -> str:
  if shape == "keys":
    if not items:
      return f"{const}: tuple[str, ...] = ()\n"
    lines = [f"{const}: tuple[str, ...] = ("]
    lines += [f'  "{k}",' for k, _ in items]
    lines.append(")")
    return "\n".join(lines) + "\n"

  # pairs: the reader needs the type to pick the right Params getter
  if not items:
    return f"{const}: tuple[tuple[str, str], ...] = ()\n"
  lines = [f"{const}: tuple[tuple[str, str], ...] = ("]
  for k, ptype in items:
    if ptype is None:
      raise ValueError(f"{k}: needs param_type to be read by its consumer")
    lines.append(f'  ("{k}", "{ptype}"),')
  lines.append(")")
  return "\n".join(lines) + "\n"


def update_region(path: Path, marker: str, body: str) -> None:
  """Replace everything between the marker comments. Idempotent; no write if unchanged."""
  begin, end = f"# {marker}_BEGIN", f"# {marker}_END"
  content = path.read_text()
  lines = content.split("\n")

  i = next((n for n, line in enumerate(lines) if begin in line), None)
  j = next((n for n, line in enumerate(lines) if end in line), None)
  if i is None or j is None:
    raise ValueError(f"{path}: missing {begin} / {end} markers")
  if j < i:
    raise ValueError(f"{path}: {end} appears before {begin}")

  updated = "\n".join(lines[: i + 1] + body.rstrip("\n").split("\n") + lines[j:])
  if updated != content:
    path.write_text(updated)
    print(f"generate_dp_params: regenerated {marker} region in {path.name}")


CONSUMER_ROOTS = ("selfdrive", "system", "dragonpilot", "opendbc_repo/opendbc/car")
SKIP_PARTS = {".venv", "__pycache__", "node_modules", "site-packages"}

DICT_NAMES = {"DP_CAR": "car_param", "DP_LON": "lon_param"}


def _py_files():
  # the target modules are providers, not consumers - their docstrings show usage
  providers = {path.resolve() for path, _, _, _ in TARGETS.values()}
  for root in CONSUMER_ROOTS:
    d = SCRIPT_DIR / root
    if not d.is_dir():
      continue
    for f in sorted(d.rglob("*.py")):
      if any(p in SKIP_PARTS for p in f.parts) or f.resolve() in providers:
        continue
      # tests carry consumer snippets as fixture strings, not real consumers
      if "tests" in f.parts or f.name.startswith("test_"):
        continue
      yield f


class _ConsumerVisitor(ast.NodeVisitor):
  """Collect dp param accesses. AST rather than regex so that commented-out code,
  strings and multi-line expressions are handled the way python sees them."""

  def __init__(self):
    self.dict_reads: list[tuple[str, str, int]] = []   # (DP_CAR|DP_LON, key, lineno)
    self.dynamic: list[tuple[str, int]] = []           # non-literal subscript
    self.ui_reads: list[tuple[str, int]] = []
    self.ui_writes: set[str] = set()

  def visit_Subscript(self, node):
    if isinstance(node.value, ast.Name) and node.value.id in DICT_NAMES:
      if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        self.dict_reads.append((node.value.id, node.slice.value, node.lineno))
      else:
        self.dynamic.append((node.value.id, node.lineno))
    self.generic_visit(node)

  def visit_Call(self, node):
    # DP_CAR.get("key") - now safe at runtime, but still needs a declared key
    f = node.func
    if isinstance(f, ast.Attribute) and f.attr == "get" and isinstance(f.value, ast.Name) \
       and f.value.id in DICT_NAMES and node.args:
      a = node.args[0]
      if isinstance(a, ast.Constant) and isinstance(a.value, str):
        self.dict_reads.append((f.value.id, a.value, node.lineno))
      else:
        self.dynamic.append((f.value.id, node.lineno))
    self.generic_visit(node)

  def visit_Compare(self, node):
    # "key" in DP_CAR
    for op, comp in zip(node.ops, node.comparators):
      if isinstance(op, ast.In) and isinstance(comp, ast.Name) and comp.id in DICT_NAMES \
         and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
        self.dict_reads.append((comp.id, node.left.value, node.lineno))
    self.generic_visit(node)

  def visit_Attribute(self, node):
    # ui_state.dp_x  (read)  /  self.dp_x = ... and ui_state.dp_x = ... (write)
    if node.attr.startswith("dp_") and isinstance(node.value, ast.Name):
      if node.value.id == "ui_state":
        if isinstance(node.ctx, ast.Store):
          self.ui_writes.add(node.attr)
        else:
          self.ui_reads.append((node.attr, node.lineno))
      elif node.value.id == "self" and isinstance(node.ctx, ast.Store):
        self.ui_writes.add(node.attr)
    self.generic_visit(node)


def check_consumers(declared: dict[str, set[str]]) -> list[str]:
  """Every consumed dp param must have a provider.

  Catches the failure a rebase actually produces: the declaration or setter is
  dropped as part of a conflict region while the consumer survives, which would
  otherwise surface as a KeyError/AttributeError at runtime instead of at build.
  """
  errors: list[str] = []
  ui_written: set[str] = set()
  ui_read: list[tuple[str, str]] = []
  dynamic: list[str] = []

  for f in _py_files():
    try:
      tree = ast.parse(f.read_text(errors="ignore"))
    except (OSError, SyntaxError):
      continue
    rel = f.relative_to(SCRIPT_DIR)
    v = _ConsumerVisitor()
    v.visit(tree)

    for name, key, lineno in v.dict_reads:
      if key not in declared[DICT_NAMES[name]]:
        errors.append(f'{rel}:{lineno}: {name}["{key}"] is read but never declared '
                      f'(add "{DICT_NAMES[name]}": True to its settings item)')
    dynamic += [f"{rel}:{lineno}: {name}[<non-literal>] cannot be checked" for name, lineno in v.dynamic]
    ui_written |= v.ui_writes
    ui_read += [(a, f"{rel}:{lineno}") for a, lineno in v.ui_reads]

  for attr, where in ui_read:
    if attr not in declared["ui_param"] and attr not in ui_written:
      errors.append(f'{where}: ui_state.{attr} is read but nothing provides it '
                    f'(add "ui_param": True to its settings item, or assign it)')

  # not failures - just say so, since the check cannot see through them
  for d in dynamic:
    print(f"generate_dp_params: note: {d}")
  return errors


def main():
  try:
    declared: dict[str, set[str]] = {}
    for decl, (path, marker, const, shape) in TARGETS.items():
      items = collect_all(decl)
      declared[decl] = {k for k, _ in items}
      update_region(path, marker, render_region(items, const, shape))
      print(f"generate_dp_params: {len(items)} {decl}s")

    errors = check_consumers(declared)
    if errors:
      for e in errors:
        print(f"generate_dp_params: {e}")
      raise ValueError(f"{len(errors)} dp param consumer(s) with no provider")
  except ValueError as e:
    print(f"generate_dp_params: {e}")
    raise SystemExit(1)


if __name__ == "__main__":
  main()
