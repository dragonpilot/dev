"""
Copyright (c) 2026, Rick Lan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, and/or sublicense,
for non-commercial purposes only, subject to the following conditions:

- The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.
- Commercial use (e.g. use in a product, service, or activity intended to
  generate revenue) is prohibited without explicit written permission from
  the copyright holder.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

ESCC radar interceptor module.
"""
from enum import StrEnum, auto

from opendbc.can import CANParser
from opendbc.car.hyundai.values import HyundaiFlags


class EsccBus(StrEnum):
  """dp - a get_can_parsers key names a parser, not a bus. This parser reads bus 0, the
  same bus as Bus.pt; only its DBC differs, so it needs a key of its own but no entry in
  upstream's Bus enum. Owning it here keeps this feature out of opendbc/car/__init__.py."""
  escc = auto()


class ESCC:
  """The ESCC interceptor PCB blocks the stock radar's SCC11-SCC14, re-broadcasts the
  radar's AEB state and lead object on 0x2AB, and passes FCA11/FCA12 through untouched.
  Non-USE_FCA cars actuate AEB through SCC12 - which openpilot transmits while engaged -
  so the radar's live AEB signals must be spliced back into our SCC12 (update_scc12)."""

  MSG_ID = 0x2AB

  def __init__(self, flags: int):
    self.enabled = bool(flags & HyundaiFlags.ESCC.value)
    self.cmd_act = 0          # AEB_CmdAct
    self.aeb_warning = 0      # CF_VSM_Warn_SCC12
    self.aeb_dec_cmd_act = 0  # CF_VSM_DecCmdAct_SCC12
    self.aeb_dec_cmd = 0      # CR_VSM_DecCmd_SCC12

  def update_states(self, cp_escc: CANParser) -> None:
    vl = cp_escc.vl["ESCC"]
    self.cmd_act = vl["AEB_CmdAct"]
    self.aeb_warning = vl["CF_VSM_Warn_SCC12"]
    self.aeb_dec_cmd_act = vl["CF_VSM_DecCmdAct_SCC12"]
    self.aeb_dec_cmd = vl["CR_VSM_DecCmd_SCC12"]

  def update_scc12(self, values: dict) -> None:
    values["AEB_CmdAct"] = self.cmd_act
    values["CF_VSM_Warn"] = self.aeb_warning
    values["CF_VSM_DecCmdAct"] = self.aeb_dec_cmd_act
    values["CR_VSM_DecCmd"] = self.aeb_dec_cmd
    # the radar's own AEB is active, tell the dash so
    values["AEB_Status"] = 2

  def get_parser(self) -> CANParser:
    return CANParser("hyundai_escc", [("ESCC", 50)], 0)


def enable_radar_tracks(can_recv, can_send, bus=0, addr=0x7d0, timeout=0.1, retry=2) -> bool:
  """dp - reconfigure the Mando SCC radar (UDS 0x2E on data id 0x0142) to output radar
  track points 0x500-0x51F on bus 1. Persistent across drives: the first ESCC drive uses
  the single-lead fallback, later drives fingerprint 0x500 and use full tracks."""
  from opendbc.car import uds
  from opendbc.car.carlog import carlog
  from opendbc.car.isotp_parallel_query import IsoTpParallelQuery

  DIAG_REQUEST = bytes([uds.SERVICE_TYPE.DIAGNOSTIC_SESSION_CONTROL, 0x07])
  DIAG_RESPONSE = bytes([uds.SERVICE_TYPE.DIAGNOSTIC_SESSION_CONTROL + 0x40, 0x07])
  WRITE_REQUEST = bytes([uds.SERVICE_TYPE.WRITE_DATA_BY_IDENTIFIER])
  WRITE_RESPONSE = bytes([uds.SERVICE_TYPE.WRITE_DATA_BY_IDENTIFIER + 0x40])
  CONFIG_DATA_ID = bytes([0x01, 0x42])
  TRACKS_ENABLED = bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x01])

  for i in range(retry):
    try:
      query = IsoTpParallelQuery(can_send, can_recv, bus, [addr], [DIAG_REQUEST], [DIAG_RESPONSE])
      for _ in query.get_data(timeout):
        query = IsoTpParallelQuery(can_send, can_recv, bus, [addr],
                                   [WRITE_REQUEST + CONFIG_DATA_ID + TRACKS_ENABLED], [WRITE_RESPONSE])
        query.get_data(0)
        carlog.warning("ESCC: radar tracks enabled")
        return True
    except Exception as e:
      carlog.exception(f"ESCC: radar tracks exception: {e}")
    carlog.warning(f"ESCC: radar tracks retry ({i + 1}) ...")
  carlog.warning("ESCC: radar tracks failed")
  return False
