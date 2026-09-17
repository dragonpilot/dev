from openpilot.system.manager.process import PythonProcess
from openpilot.system.manager.process_config import only_onroad

# dp - GPS + livePose fusion -> liveGPS (see dragonpilot/selfdrive/gpsd)
PROCS = [
  PythonProcess("gpsd", "dragonpilot.selfdrive.gpsd.gpsd", only_onroad),
]
