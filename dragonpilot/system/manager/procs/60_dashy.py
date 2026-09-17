from opendbc.car.structs import car
from openpilot.common.params import Params
from openpilot.system.manager.process import PythonProcess
from openpilot.system.manager.process_config import always_run, only_onroad, and_


# dp - dashy. The gating predicate lives beside the processes that use it, so neither
# touches process_config.py.
def dashy(started: bool, params: Params, CP: car.CarParams) -> bool:
  return params.get_bool("dp_dev_dashy")


PROCS = [
  PythonProcess("serverd", "dragonpilot.dashy.serverd", always_run),
  PythonProcess("dashyd", "dragonpilot.dashy.dashyd", and_(dashy, only_onroad)),
]
