import numpy as np

# Signed lateral divergence between two predicted paths, averaged over the far
# half of the horizon (where a turn shows up). +left / -right (openpilot frame).
def path_divergence(baseline_y, turn_y):
    b = np.asarray(baseline_y, dtype=float)
    t = np.asarray(turn_y, dtype=float)
    n = min(len(b), len(t))
    far = slice(n // 2, n)
    return float(np.mean(t[far] - b[far]))


# The model "really turns" if the desire bent the path in the expected direction
# by more than `threshold` meters (default 2 m) over the far horizon.
def verdict(divergence, direction, threshold=2.0):
    if direction == "turnLeft":
        return divergence > threshold
    if direction == "turnRight":
        return divergence < -threshold
    return False
