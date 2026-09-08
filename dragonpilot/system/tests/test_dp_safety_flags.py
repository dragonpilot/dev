"""Every brand's <Brand>SafetyFlags value must equal its counterpart constant in the
corresponding opendbc/safety/modes/*.h header.

Those values are a wire contract: CarInterface ORs them into
CP.safetyConfigs[].safetyParam, panda receives the integer and compares it against
its own constants. A python-side renumber that is not mirrored in C means panda
applies a different flag than the car code intended, with no error anywhere.

dp renumbers the *car-side* enums freely (ToyotaFlags.RADAR_FILTER moved twice while
composing pre-toyota), and those enums share member names with the safety enums
(LOCK_CTRL exists in both ToyotaFlags and ToyotaSafetyFlags). This test pins the half
that must not move.

This is the PARENT test: it discovers brands and checks them generically, so it runs on
whatever branch it lands on - min, full, or any brand/* - and covers brands that did not
exist when it was written (brand/mg/base adds a whole new one).

A brand feature that touches safety adds its OWN file asserting its specific flag and
expected value, e.g. dragonpilot/.../tests/test_<feature>_safety.py:

    from openpilot.system.tests.test_dp_safety_flags import assert_safety_flag
    def test_lock_ctrl_flag():
      assert_safety_flag("toyota", "LOCK_CTRL", 32 << 8)

That pins the number a feature actually depends on. The generic tests here only prove
the two sides AGREE - if a rebase moved both together they would still pass, which is
exactly the case the per-feature assertion catches.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CAR = REPO / "opendbc_repo" / "opendbc" / "car"
SAF = REPO / "opendbc_repo" / "opendbc" / "safety" / "modes"

# Upstream spells the C constants three different ways, so a brand is not "missing its C
# side" just because it does not use PARAM_ - rivian/tesla do have counterparts.
# {b} is the brand prefix, e.g. TOYOTA.
C_PATTERNS = (
  r"{b}_PARAM_([A-Z0-9_]+)",   # TOYOTA_PARAM_ALT_BRAKE - most brands
  r"{b}_FLAG_([A-Z0-9_]+)",    # TESLA_FLAG_FSD_14
  r"FLAG_{b}_([A-Z0-9_]+)",    # FLAG_RIVIAN_LONG_CONTROL, FLAG_VOLKSWAGEN_LONG_CONTROL
)


def _discover() -> dict[str, tuple[str, list[str], str]]:
  """brand dir -> (python enum class, header files, C prefix).

  Discovered rather than listed: a hardcoded table silently omits new brands, which is
  the failure this test exists to prevent.
  """
  found: dict[str, tuple[str, list[str], str]] = {}
  for values in sorted(CAR.glob("*/values.py")):
    brand = values.parent.name
    m = re.search(r"^class (\w*SafetyFlags)\(", values.read_text(), re.M)
    if not m:
      continue
    cls = m.group(1)
    prefix = re.sub(r"SafetyFlags$", "", cls).upper()
    headers = sorted(h.name for h in SAF.glob(f"{brand}*.h"))
    found[brand] = (cls, headers, prefix)
  return found


PAIRS = _discover()

# Known upstream asymmetries: python and C spell the same concept differently. Anything
# NOT listed here that appears on only one side is a bug - typically a dp feature adding
# a flag to one side and forgetting the other, which gives an AttributeError at car init
# or a flag panda silently ignores.
ALLOWED_PY_ONLY = {
  "hyundai": {"LONG"},                                # C calls it LONGITUDINAL
  "subaru":  {"LONG",                                 # C calls it LONGITUDINAL
              "PREGLOBAL_REVERSED_DRIVER_TORQUE"},     # C: SUBARU_PG_PARAM_REVERSED_DRIVER_TORQUE
  "ford":    {"LONG_CONTROL"},                         # C calls it LONGITUDINAL
  "tesla":   {"LONG_CONTROL"},                         # C calls it LONGITUDINAL_CONTROL
  # mg.h reads only ALT_BRAKE and NON_EV; interface.py still ORs LONG_CONTROL into
  # safetyParam, so panda ignores that bit. Dead rather than dangerous - listed here so
  # the check passes on brand/mg/base, but worth deciding on.
  "mg":      {"LONG_CONTROL"},
}
ALLOWED_C_ONLY = {
  "hyundai": {"LONGITUDINAL"},
  "subaru":  {"LONGITUDINAL"},
  "ford":    {"LONGITUDINAL"},
  "tesla":   {"LONGITUDINAL_CONTROL"},
}


def _py_members(brand: str, cls: str) -> dict[str, int]:
  s = (CAR / brand / "values.py").read_text()
  if f"class {cls}" not in s:
    return {}
  b = s[s.index(f"class {cls}"):]
  for stop in ("\nclass ", "\ndef "):
    if stop in b:
      b = b[:b.index(stop)]
  out: dict[str, int] = {}
  for line in b.splitlines():
    m = re.match(r"\s+([A-Z][A-Z0-9_]*)\s*=\s*([^#]+)", line)   # tolerate trailing comments
    if not m:
      continue
    try:
      out[m.group(1)] = int(eval(m.group(2).strip()))
    except Exception:
      pass
  return out


def _c_members(headers: list[str], prefix: str) -> dict[str, int]:
  out: dict[str, int] = {}
  for h in headers:
    p = SAF / h
    if not p.exists():
      continue
    s = p.read_text()
    m = re.search(rf"{prefix}_PARAM_OFFSET\s*=\s*(\d+)", s)
    off = int(m.group(1)) if m else 0
    for pat in C_PATTERNS:
      for name, expr in re.findall(pat.format(b=prefix) + r"\s*=\s*([^;,}]+)", s):
        if name == "OFFSET":
          continue
        e = expr.replace("UL", "").replace("U", "").replace(f"{prefix}_PARAM_OFFSET", str(off))
        try:
          out[name] = int(eval(e))
        except Exception:
          pass
  return out


def assert_safety_flag(brand: str, flag: str, expected: int) -> None:
  """Assert a specific flag has `expected` on BOTH sides. For per-feature tests on
  brand/* branches - see the module docstring."""
  cls, headers, prefix = PAIRS[brand]
  py, c = _py_members(brand, cls), _c_members(headers, prefix)
  assert flag in py, f"{brand}: {cls}.{flag} is missing (python side)"
  assert flag in c, f"{brand}: no C counterpart for {flag} in {headers}"
  assert py[flag] == expected, f"{brand}: {cls}.{flag}={py[flag]}, feature expects {expected}"
  assert c[flag] == expected, f"{brand}: C {prefix} {flag}={c[flag]}, feature expects {expected}"


def _shared_cases():
  cases = []
  for brand, (cls, headers, prefix) in PAIRS.items():
    py, c = _py_members(brand, cls), _c_members(headers, prefix)
    for name in sorted(set(py) & set(c)):
      cases.append(pytest.param(brand, name, py[name], c[name], id=f"{brand}-{name}"))
  return cases


@pytest.mark.parametrize("brand,flag,py_value,c_value", _shared_cases())
def test_safety_flag_matches_header(brand, flag, py_value, c_value):
  """A mismatch means panda applies a different flag than the car code set."""
  assert py_value == c_value, (
    f"{brand}: SafetyFlags.{flag}={py_value} but C {PAIRS[brand][2]} {flag}={c_value}. "
    f"These cross to panda - renumber the car-side <Brand>Flags enum instead."
  )


@pytest.mark.parametrize("brand", sorted(PAIRS))
def test_no_unexpected_one_sided_safety_flag(brand):
  """A flag on only one side is usually a feature that updated python or C, not both."""
  cls, headers, prefix = PAIRS[brand]
  py, c = _py_members(brand, cls), _c_members(headers, prefix)
  py_only = set(py) - set(c) - ALLOWED_PY_ONLY.get(brand, set())
  c_only = set(c) - set(py) - ALLOWED_C_ONLY.get(brand, set())
  assert not py_only, f"{brand}: {cls} has {sorted(py_only)} with no C counterpart in {headers}"
  assert not c_only, f"{brand}: C {prefix} {sorted(c_only)} has no {cls} counterpart"


def test_pairings_are_all_found():
  """Guard the test itself: if a rename silently empties a side, the cases above vanish
  and everything 'passes'."""
  assert len(PAIRS) >= 9, f"only discovered {sorted(PAIRS)} - has the layout changed?"
  for brand, (cls, headers, prefix) in PAIRS.items():
    py = _py_members(brand, cls)
    assert py, f"{brand}: no members parsed from {cls} - has it been renamed?"
    assert headers, f"{brand}: no {brand}*.h headers found under {SAF}"
