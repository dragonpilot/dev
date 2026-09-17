import os
from openpilot.cereal import log

# Diagnostic-only: force the model's desire input to a fixed value within a
# frame-id window, so the Phase-0 probe can inject turnLeft/turnRight that the
# stock DesireHelper never emits. No-op unless PROBE_DESIRE is set in the env.
def probe_desire_override(desire: int, frame_id: int) -> int:
    forced = os.environ.get("PROBE_DESIRE")
    if not forced:
        return desire
    start = int(os.environ.get("PROBE_FRAME_START", "0"))
    end = int(os.environ.get("PROBE_FRAME_END", str(10 ** 9)))
    if start <= frame_id <= end:
        return int(getattr(log.Desire, forced))
    return desire
