import os

from opendbc.car.structs import car
from openpilot.common.params import Params
from openpilot.system.manager.process import PythonProcess

LITE = os.getenv("LITE") is not None


# dp - beepd replaces soundd on LITE hardware. Gating predicate lives here with the
# process. The LITE-related *edits* to upstream proc entries (micd, soundd,
# dmonitoringmodeld, dmonitoringd, modem) stay in process_config.py - they modify
# existing entries rather than adding new ones, so they cannot move here.
def beep(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and params.get_bool("dp_dev_beep")


PROCS = [
  PythonProcess("beepd", "dragonpilot.selfdrive.ui.beepd", beep, enabled=LITE),
]
