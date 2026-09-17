# dp - offline tests for modem.py SIM handling. No device needed: AT/serial/params
# are mocked. Covers the four SIM scenarios:
#   1. no SIM          -> fast retries, then 10s backoff with CFUN re-init probe
#   2. SIM, no network -> stays SEARCHING, registration published
#   3. SIM, registered -> CONNECTING (roaming honored), QMI failures logged
#   4. SIM swap        -> removal detected via failed ICCID reads, change via new ICCID
import subprocess
from unittest.mock import patch

from openpilot.common.hardware.comma import modem


class FakePPP:
  def kill(self): pass
  def cleanup_routes(self): pass
  def reset_data_port(self): pass


class FakeModem(modem.Modem):
  """Modem with serial/AT, params and state publishing stubbed out."""

  def __init__(self):
    super().__init__()
    self._ppp = FakePPP()
    self.at_log = []
    self.sim_present = False
    self.creg = "0,0"       # <n>,<stat> for AT+CREG?/AT+CGREG?
    self.params = {}
    self.published = []

  def _at(self, cmd):
    self.at_log.append(cmd)
    if cmd == "AT+CGSN":
      return ["865167060850998"]
    if cmd == "AT+QCCID":
      return ["+QCCID: 89610149328109000041"] if self.sim_present else []
    if cmd == "AT+CIMI":
      return ["505015606889107"] if self.sim_present else []
    if cmd == "AT+GMR":
      return ["EG25GGBR07A08M2G"]
    if cmd in ("AT+CREG?", "AT+CGREG?"):
      return [f"+{cmd[3:-1]}: {self.creg}"]
    return ["OK"]

  def _init_at_channel(self):
    return True

  def _read_param(self, key):
    return self.params.get(key, "")

  def _publish_state(self, **kwargs):
    self.S.update(kwargs)
    self.published.append(dict(kwargs))


class TestModemBase:
  def setup_method(self):
    self.now = 1000.0
    self._patches = [
      patch.object(modem.time, "monotonic", lambda: self.now),
      patch.object(modem.time, "sleep", lambda s: None),
      patch.object(modem.os.path, "exists", lambda p: True),
    ]
    for p in self._patches:
      p.start()
    self.m = FakeModem()

  def teardown_method(self):
    for p in self._patches:
      p.stop()

  def tick_init(self, dt=1.0):
    st = self.m._do_initializing()
    self.now += dt
    return st


class TestNoSim(TestModemBase):
  """Case 1: no SIM inserted."""

  def test_fast_retries_then_backoff_probe(self):
    for _ in range(modem.INIT_FAST_RETRIES - 1):
      assert self.tick_init() == modem.State.INITIALIZING
    assert "AT+CFUN=0" not in self.m.at_log

    # hitting the limit: publish identity (imei) + CFUN re-init + enter backoff
    assert self.tick_init() == modem.State.INITIALIZING
    assert "AT+CFUN=0" in self.m.at_log and "AT+CFUN=1" in self.m.at_log
    assert any(p.get("imei") for p in self.m.published), "IMEI must be published without a SIM"

    # inside the backoff window: no AT traffic at all
    n = len(self.m.at_log)
    for _ in range(int(modem.NO_SIM_POLL_INTERVAL) - 2):
      assert self.tick_init() == modem.State.INITIALIZING
    assert len(self.m.at_log) == n

    # after the window: another probe incl. SIM re-init
    self.now += modem.NO_SIM_POLL_INTERVAL
    cfuns = self.m.at_log.count("AT+CFUN=0")
    self.tick_init()
    assert self.m.at_log.count("AT+CFUN=0") == cfuns + 1

  def test_sim_inserted_during_backoff_recovers(self):
    for _ in range(modem.INIT_FAST_RETRIES):
      self.tick_init()
    self.m.sim_present = True
    self.now += modem.NO_SIM_POLL_INTERVAL
    assert self.tick_init() == modem.State.SEARCHING
    assert self.m._init_fails == 0

  def test_sim_present_no_backoff(self):
    self.m.sim_present = True
    assert self.tick_init() == modem.State.SEARCHING
    assert "AT+CFUN=0" not in self.m.at_log


class TestRegistration(TestModemBase):
  """Cases 2 + 3: SIM present, network denies / accepts registration."""

  def setup_method(self):
    super().setup_method()
    self.m.sim_present = True
    assert self.tick_init() == modem.State.SEARCHING

  def test_denied_stays_searching_and_publishes(self):
    self.m.creg = "2,3"  # denied
    assert self.m._do_searching() == modem.State.SEARCHING
    assert self.m.S["registration"] == "denied"

  def test_registered_home_connects(self):
    self.m.creg = "2,1"  # home
    assert self.m._do_searching() == modem.State.CONNECTING

  def test_roaming_blocked_without_param(self):
    self.m.creg = "2,5"  # roaming, GsmRoaming unset
    assert self.m._do_searching() == modem.State.SEARCHING
    assert self.m.S["registration"] == "roaming"

  def test_roaming_allowed_with_param(self):
    self.m.params["GsmRoaming"] = "1"
    self.m._roaming_allowed = self.m._is_roaming_allowed()
    self.m.creg = "2,5"
    assert self.m._do_searching() == modem.State.CONNECTING


class TestQMIFailureLogging(TestModemBase):
  """Case 3 sub-case: registered but data call rejected (e.g. wrong APN)."""

  def test_start_network_failure_logged(self, caplog):
    q = modem.QMISession()
    fail = subprocess.CompletedProcess([], 1, stdout="", stderr="error: couldn't start network: cause 33 option-unsubscribed")
    ok = subprocess.CompletedProcess([], 0, stdout="", stderr="")
    with patch.object(modem.subprocess, "run", return_value=ok), \
         patch.object(modem.QMISession, "_qmicli", return_value=fail), \
         patch.object(modem.QMISession, "_param", return_value="badapn"):
      q.start()
    assert any("QMI start-network failed" in r.message and "cause 33" in r.message for r in caplog.records)


class TestSimSwap(TestModemBase):
  """Case 4: SIM removed or exchanged while running."""

  def setup_method(self):
    super().setup_method()
    self.m.sim_present = True
    assert self.tick_init() == modem.State.SEARCHING

  def test_removal_detected_after_consecutive_failures(self):
    self.m.sim_present = False
    for i in range(modem.ICCID_FAIL_LIMIT - 1):
      self.m._check_iccid(modem.State.SEARCHING)
      assert not self.m._sim_change, f"tripped too early at {i + 1}"
    self.m._check_iccid(modem.State.SEARCHING)
    assert self.m._sim_change

  def test_transient_read_failures_do_not_trigger(self):
    for _ in range(modem.ICCID_FAIL_LIMIT * 2):
      self.m.sim_present = False
      self.m._check_iccid(modem.State.SEARCHING)
      self.m.sim_present = True
      self.m._check_iccid(modem.State.SEARCHING)
    assert not self.m._sim_change

  def test_new_iccid_triggers_sim_change(self):
    orig_at = self.m._at
    def at_new_sim(cmd):
      if cmd == "AT+QCCID":
        return ["+QCCID: 89014103333720483441"]
      return orig_at(cmd)
    self.m._at = at_new_sim
    self.m._check_iccid(modem.State.SEARCHING)
    assert self.m._sim_change
