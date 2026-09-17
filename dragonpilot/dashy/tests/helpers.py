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

"""Test harness for serverd.

Black-box by design: launches the real serverd as a subprocess in an isolated
environment (a unique OPENPILOT_PREFIX for params + a temp DASHY_DATA_DIR for
files) and drives it over HTTP with urllib. Because the tests assert the HTTP
*contract* — not aiohttp internals — the same suite is meant to pass unchanged
after the planned aiohttp -> stdlib+SSE refactor.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from openpilot.common.basedir import BASEDIR

SERVERD_MODULE = "dragonpilot.dashy.serverd"
ACCEL_PROFILES_KEY = "dp_lon_accel_profiles"  # owned by the sibling min-feat/lon/accel-eq branch


def _free_port():
  s = socket.socket()
  s.bind(("127.0.0.1", 0))
  port = s.getsockname()[1]
  s.close()
  return port


def _param_registered(key):
  """dp params are branch-scoped: a key owned by a sibling min-feat branch is absent
  until that branch is composed in. Tests must not hard-depend on one."""
  from openpilot.common.params import Params, UnknownKeyName
  try:
    Params().check_key(key)
    return True
  except UnknownKeyName:
    return False


def car_params_bytes(brand="toyota", op_long=True):
  """Serialized CarParams for seeding CarParamsPersistent (drives the brand +
  openpilot-longitudinal gates)."""
  from opendbc.car.structs import car

  cp = car.CarParams.new_message()
  cp.brand = brand
  cp.openpilotLongitudinalControl = op_long
  return cp.to_bytes()


class ServerHandle:
  def __init__(self, base_url, proc, data_dir, prefix, port, env):
    self.base_url = base_url
    self.proc = proc
    self.data_dir = data_dir
    self.prefix = prefix
    self.port = port
    self.env = env  # the launch env (prefix + msgq dir), for spawning a publisher

  # --- HTTP helpers ---
  def _open(self, path, data=None, method=None, timeout=5):
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
    return urllib.request.urlopen(req, timeout=timeout)

  def get(self, path, timeout=5):
    return self._open(path, timeout=timeout)

  def get_json(self, path, timeout=5):
    return json.load(self.get(path, timeout=timeout))

  def status(self, path, timeout=5):
    """Status code for a GET, following HTTPError so 4xx doesn't raise."""
    try:
      return self.get(path, timeout=timeout).status
    except urllib.error.HTTPError as e:
      return e.code

  def post_json(self, path, body, timeout=5):
    """Returns (status, parsed_json_or_None)."""
    data = json.dumps(body).encode()
    try:
      r = self._open(path, data=data, method="POST", timeout=timeout)
      return r.status, json.load(r)
    except urllib.error.HTTPError as e:
      try:
        return e.code, json.load(e)
      except Exception:
        return e.code, None

  def param(self, key):
    """Read a param straight from this server's isolated store (to assert
    side effects like OnroadCycleRequested that aren't exposed over HTTP)."""
    os.environ["OPENPILOT_PREFIX"] = self.prefix
    from openpilot.common.params import Params

    return Params().get_bool(key)

  # A param write acks before it's visible to a closely-following read
  # (openpilot Params is eventually-consistent), so post-write reads poll.
  def poll_json(self, path, pred, timeout=2.0, interval=0.05):
    end = time.monotonic() + timeout
    d = self.get_json(path)
    while not pred(d) and time.monotonic() < end:
      time.sleep(interval)
      d = self.get_json(path)
    return d

  def poll_param(self, key, want=True, timeout=2.0, interval=0.05):
    end = time.monotonic() + timeout
    v = self.param(key)
    while v != want and time.monotonic() < end:
      time.sleep(interval)
      v = self.param(key)
    return v

  def sse_recv_one(self, path, timeout=6.0):
    """Open the SSE stream and return the payload of the first `data:` frame.
    Dependency-free streaming read over urllib."""
    r = urllib.request.urlopen(self.base_url + path, timeout=timeout)
    try:
      end = time.monotonic() + timeout
      for raw in r:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line.startswith("data:"):
          return line[5:].strip()
        if time.monotonic() > end:
          break
    finally:
      r.close()
    raise TimeoutError("no SSE data frame received")


def server_factory():
  """Yields make(**config) -> ServerHandle. Each call launches a fresh,
  isolated serverd; all are torn down at the end of the test."""
  procs, tmps, prefixes = [], [], []
  outer_prefix = os.environ.get("OPENPILOT_PREFIX")

  def make(params=None, car_brand="toyota", op_long=True, habit_csv=None, files=None, dp_dev_dashy=True):
    prefix = "dashytest_" + os.urandom(4).hex()
    data_dir = tempfile.mkdtemp(prefix="dashy_data_")
    tmps.append(data_dir)
    prefixes.append(prefix)
    # msgq needs the prefix's socket dir to exist before any pub/sub opens.
    os.makedirs(f"/dev/shm/msgq_{prefix}", exist_ok=True)

    os.environ["OPENPILOT_PREFIX"] = prefix
    from openpilot.common.params import Params

    P = Params()
    P.put_bool("dp_dev_dashy", dp_dev_dashy)
    P.put("LanguageSetting", "en")
    for k, v in (params or {}).items():
      if isinstance(v, bool):
        P.put_bool(k, v)
      else:
        P.put(k, v)
    if car_brand is not None:
      P.put("CarParamsPersistent", car_params_bytes(car_brand, op_long))

    if habit_csv is not None:
      Path(data_dir, "accel_log.csv").write_text(habit_csv)
    for name, content in (files or {}).items():
      Path(data_dir, name).write_text(content)

    port = _free_port()
    env = dict(os.environ)
    env["OPENPILOT_PREFIX"] = prefix
    env["DASHY_DATA_DIR"] = data_dir
    env["DP_LOG_DIR"] = data_dir   # accel_log.csv lives here in tests (prod: /data/media/0/dp_logs)
    proc = subprocess.Popen(
      [sys.executable, "-m", SERVERD_MODULE, "--port", str(port)],
      cwd=BASEDIR,
      env=env,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
    )
    procs.append(proc)
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
      if proc.poll() is not None:
        raise RuntimeError("serverd exited early:\n" + proc.stdout.read())
      try:
        urllib.request.urlopen(base + "/api/init", timeout=1)
        break
      except Exception:
        time.sleep(0.25)
    else:
      proc.terminate()
      raise RuntimeError("serverd did not become ready in time")
    return ServerHandle(base, proc, data_dir, prefix, port, env)

  yield make

  for proc in procs:
    proc.terminate()
    try:
      proc.wait(timeout=5)
    except Exception:
      proc.kill()
  for t in tmps:
    shutil.rmtree(t, ignore_errors=True)
  for prefix in prefixes:
    try:
      os.environ["OPENPILOT_PREFIX"] = prefix
      from openpilot.common.params import Params

      Params().clear_all()
    except Exception:
      pass
    shutil.rmtree(f"/dev/shm/msgq_{prefix}", ignore_errors=True)
  if outer_prefix is None:
    os.environ.pop("OPENPILOT_PREFIX", None)
  else:
    os.environ["OPENPILOT_PREFIX"] = outer_prefix


# ~18k rows spanning 1..32 m/s, accel decaying with speed with per-cycle spread
# so the p75/p90/p98 bands are distinguishable (and dense enough for the grid).
SAMPLE_CSV = "".join(f"{v / 10:.3f},{max(0.0, 1.6 - v / 400 + (cyc % 6) * 0.06):.3f}\n" for cyc in range(60) for v in range(10, 320))


def server(server_factory):
  """A default, fully-featured server: openpilot-longitudinal Toyota, a profile
  doc, and a populated accel log — the common case for most endpoint tests."""
  params = {}
  if _param_registered(ACCEL_PROFILES_KEY):
    params[ACCEL_PROFILES_KEY] = {  # JSON-typed param: pass a dict
      "active": "Stock",
      "use_personality": False,
      "profiles": [{"name": "Stock", "source": "Stock"}],
    }
  return server_factory(
    op_long=True,
    car_brand="toyota",
    params=params,
    habit_csv=SAMPLE_CSV,
    files={"drive1.txt": "x", "drive2.txt": "y"},
  )


def tmp_path():
  """pytest's tmp_path, as a module-level generator fixture."""
  d = tempfile.mkdtemp(prefix="dashy_tmp_")
  yield Path(d)
  shutil.rmtree(d, ignore_errors=True)
