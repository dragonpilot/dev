import os
import pytest
from openpilot.cereal import log
from dragonpilot.selfdrive.modeld.probe_desire import probe_desire_override

NONE = int(log.Desire.none)
TURNL = int(log.Desire.turnLeft)
TURNR = int(log.Desire.turnRight)


@pytest.fixture(autouse=True)
def _clear_env():
    for k in ("PROBE_DESIRE", "PROBE_FRAME_START", "PROBE_FRAME_END"):
        os.environ.pop(k, None)
    yield
    for k in ("PROBE_DESIRE", "PROBE_FRAME_START", "PROBE_FRAME_END"):
        os.environ.pop(k, None)


def test_noop_when_unset():
    assert probe_desire_override(NONE, 100) == NONE
    assert probe_desire_override(TURNL, 100) == TURNL  # never touches a real desire


def test_forces_within_window():
    os.environ["PROBE_DESIRE"] = "turnRight"
    os.environ["PROBE_FRAME_START"] = "100"
    os.environ["PROBE_FRAME_END"] = "140"
    assert probe_desire_override(NONE, 99) == NONE     # before window
    assert probe_desire_override(NONE, 100) == TURNR   # window start
    assert probe_desire_override(NONE, 140) == TURNR   # window end
    assert probe_desire_override(NONE, 141) == NONE    # after window


def test_defaults_to_full_range_when_no_window():
    os.environ["PROBE_DESIRE"] = "turnLeft"
    assert probe_desire_override(NONE, 0) == TURNL
    assert probe_desire_override(NONE, 10_000) == TURNL
