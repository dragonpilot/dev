from openpilot.system.manager.process import PythonProcess
from openpilot.system.manager.process_config import only_onroad

# dp - Turn Assist logger (turnd v1): records low-speed turn habits
# (see dragonpilot/selfdrive/turnd)
# NOTE: depends on liveGPS from the separate gpsd min-feat; inert if gpsd isn't composed in.
# 0.11.2 removed the restart_if_crash kwarg and the manager mechanism behind it. Nothing to
# re-add: turnd.main() already loops forever around _run(), swallowing fatals and retrying
# at 5s, so the process cannot exit on an exception and the kwarg was always redundant.
PROCS = [
  PythonProcess("turnd", "dragonpilot.selfdrive.turnd.turnd", only_onroad),
]
