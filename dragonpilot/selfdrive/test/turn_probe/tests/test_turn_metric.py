from dragonpilot.selfdrive.test.turn_probe.turn_metric import path_divergence, verdict

# 33-point horizon; baseline goes straight (y=0), turn bends right (y negative in far half)
STRAIGHT = [0.0] * 33
BEND_RIGHT = [0.0] * 16 + [-(i * 0.8) for i in range(17)]   # grows to ~-12.8 m
BEND_LEFT = [0.0] * 16 + [(i * 0.8) for i in range(17)]


def test_divergence_sign_and_magnitude():
    d_right = path_divergence(STRAIGHT, BEND_RIGHT)
    d_left = path_divergence(STRAIGHT, BEND_LEFT)
    assert d_right < -2.0
    assert d_left > 2.0


def test_no_divergence_when_identical():
    assert abs(path_divergence(STRAIGHT, STRAIGHT)) < 1e-9


def test_verdict():
    assert verdict(path_divergence(STRAIGHT, BEND_RIGHT), "turnRight") is True
    assert verdict(path_divergence(STRAIGHT, BEND_RIGHT), "turnLeft") is False
    assert verdict(path_divergence(STRAIGHT, BEND_LEFT), "turnLeft") is True
    assert verdict(0.5, "turnRight") is False   # below threshold -> not a real turn
