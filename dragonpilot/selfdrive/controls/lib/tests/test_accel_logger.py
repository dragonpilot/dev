import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from opendbc.car.structs import car
from dragonpilot.selfdrive.controls.lib.accel_logger import _should_log, AccelLogger, LOG_HEADER
from openpilot.common.test import OpenpilotTestCase


def tmp_path():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


class _Approx:
    """Minimal stand-in for pytest.approx: equal within an absolute tolerance."""
    def __init__(self, val, tol=1e-6):
        self.val = val
        self.tol = tol

    def __eq__(self, other):
        return abs(other - self.val) <= self.tol

    def __repr__(self):
        return f"approx({self.val})"


def approx(val, tol=1e-6):
    return _Approx(val, tol)


def _clean(**over):
    args = {'gas': True, 'brake': False, 'blinker': False,
             'in_drive': True, 'moving': True, 'a_ego': 0.8, 'lead_ttc': 9.9, 'lat_accel': 0.2}
    args.update(over)
    return _should_log(**args)


DRIVE = car.CarState.GearShifter.drive
CP = SimpleNamespace(steerRatio=15.0, wheelbase=2.7, openpilotLongitudinalControl=True)


def _sm(**over):
    cs = {'vEgo': 10.0, 'aEgo': 0.8, 'gasPressed': True, 'brakePressed': False,
          'leftBlinker': False, 'rightBlinker': False, 'standstill': False,
          'gearShifter': DRIVE, 'steeringAngleDeg': 0.0}
    cs.update(over)
    return {
        'carState': SimpleNamespace(**cs),
        'radarState': SimpleNamespace(leadOne=SimpleNamespace(status=False, dRel=0.0)),
    }


class TestAccelLogger(OpenpilotTestCase):

    def test_clean_sample_logs(self):
        assert _clean() is True

    def test_each_condition_blocks(self):
        assert _clean(gas=False) is False
        assert _clean(a_ego=0.0) is False
        assert _clean(brake=True) is False
        assert _clean(blinker=True) is False
        assert _clean(in_drive=False) is False
        assert _clean(moving=False) is False
        assert _clean(lead_ttc=0.5) is False      # < TTC_MIN (1.0)
        assert _clean(lat_accel=5.0) is False

    def test_gas_demand_buffers(self, tmp_path):
        log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
        log.update(_sm(), 0.0)                          # driver on gas (manual or override)
        assert log._buf == [(10.0, 0.8)]

    def test_no_gas_not_logged(self, tmp_path):
        log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
        log.update(_sm(gasPressed=False), 0.0)          # OP cruising, no gas -> not logged
        assert log._buf == []

    def test_grade_correction_applied(self, tmp_path):
        log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
        log.update(_sm(aEgo=0.8), 0.3)                          # a_flat = 0.5
        assert log._buf == [(10.0, approx(0.5))]

    def test_grade_none_not_logged(self, tmp_path):
        log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
        log.update(_sm(), None)
        assert log._buf == []

    def test_no_op_long_disables_logging(self, tmp_path):
        stock = SimpleNamespace(steerRatio=15.0, wheelbase=2.7, openpilotLongitudinalControl=False)
        log = AccelLogger(stock, path=str(tmp_path / "h.csv"))
        log.update(_sm(), 0.0)
        assert log._buf == []

    def test_update_never_raises(self, tmp_path):
        log = AccelLogger(CP, path=str(tmp_path / "h.csv"))
        log.update({}, 0.0)
        assert log._buf == []

    def test_flush_writes_after_header(self, tmp_path):
        p = tmp_path / "h.csv"
        log = AccelLogger(CP, path=str(p))
        log.update(_sm(vEgo=10.0, aEgo=0.8), 0.0)
        log.update(_sm(vEgo=12.0, aEgo=0.5), 0.0)
        log._flush()
        lines = p.read_text().splitlines()
        assert lines[0] == LOG_HEADER
        assert lines[1:] == ["10.000,0.800", "12.000,0.500"]

    def test_header_written_fresh(self, tmp_path):
        p = tmp_path / "h.csv"
        AccelLogger(CP, path=str(p))
        assert p.read_text().splitlines()[0] == LOG_HEADER

    def test_header_migrates_old(self, tmp_path):
        p = tmp_path / "h.csv"
        p.write_text("10.000,0.800\n")                          # old format, no v3 header
        AccelLogger(CP, path=str(p))
        assert (tmp_path / "h.pre_v3.csv").exists()
        assert p.read_text().splitlines()[0] == LOG_HEADER

    def test_header_match_appends(self, tmp_path):
        p = tmp_path / "h.csv"
        p.write_text(LOG_HEADER + "\n7.000,1.200\n")
        AccelLogger(CP, path=str(p))
        assert not (tmp_path / "h.pre_v3.csv").exists()
        assert p.read_text().splitlines() == [LOG_HEADER, "7.000,1.200"]
