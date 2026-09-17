import math

from opendbc.can import CANParser
from opendbc.car import Bus, structs
from opendbc.car.interfaces import RadarInterfaceBase
from opendbc.car.hyundai.values import DBC, HyundaiFlags

RADAR_START_ADDR = 0x500
RADAR_MSG_COUNT = 32

# POC for parsing corner radars: https://github.com/commaai/openpilot/pull/24221/


def get_radar_can_parser(CP):
  if Bus.radar not in DBC[CP.carFingerprint]:
    return None

  messages = [(f"RADAR_TRACK_{addr:x}", 50) for addr in range(RADAR_START_ADDR, RADAR_START_ADDR + RADAR_MSG_COUNT)]
  return CANParser(DBC[CP.carFingerprint][Bus.radar], messages, 1)


class RadarInterface(RadarInterfaceBase):
  def __init__(self, CP):
    super().__init__(CP)
    self.updated_messages = set()
    self.trigger_msg = RADAR_START_ADDR + RADAR_MSG_COUNT - 1

    self.radar_off_can = CP.radarUnavailable
    self.rcp = get_radar_can_parser(CP)

    # dp - ESCC without fingerprinted radar tracks: single lead from the interceptor message
    from opendbc.car.hyundai.escc import ESCC
    self.escc = ESCC(CP.flags)
    self.use_escc_lead = bool(CP.flags & HyundaiFlags.ESCC_LEAD.value)
    if self.use_escc_lead:
      self.rcp = self.escc.get_parser()
      self.trigger_msg = ESCC.MSG_ID

  def update(self, can_strings):
    if self.radar_off_can or (self.rcp is None):
      return super().update(None)

    vls = self.rcp.update(can_strings)
    self.updated_messages.update(vls)

    if self.trigger_msg not in self.updated_messages:
      return None

    rr = self._update(self.updated_messages)
    self.updated_messages.clear()

    return rr

  def _update(self, updated_messages):
    ret = structs.RadarData()
    if self.rcp is None:
      return ret

    if not self.rcp.can_valid:
      ret.errors.canError = True

    # dp - ESCC single-lead fallback
    if self.use_escc_lead:
      msg = self.rcp.vl["ESCC"]
      if msg["ACC_ObjStatus"]:
        if 0 not in self.pts:
          self.pts[0] = structs.RadarData.RadarPoint()
          self.pts[0].trackId = self.track_id
          self.track_id += 1
        self.pts[0].measured = True
        self.pts[0].dRel = msg["ACC_ObjDist"]
        self.pts[0].yRel = -msg["ACC_ObjLatPos"]
        self.pts[0].vRel = msg["ACC_ObjRelSpd"]
        self.pts[0].aRel = float("nan")
        self.pts[0].yvRel = float("nan")
      else:
        self.pts.pop(0, None)
      ret.points = list(self.pts.values())
      return ret

    for addr in range(RADAR_START_ADDR, RADAR_START_ADDR + RADAR_MSG_COUNT):
      msg = self.rcp.vl[f"RADAR_TRACK_{addr:x}"]

      if addr not in self.pts:
        self.pts[addr] = structs.RadarData.RadarPoint()
        self.pts[addr].trackId = self.track_id
        self.track_id += 1

      valid = msg['STATE'] in (3, 4)
      if valid:
        azimuth = math.radians(msg['AZIMUTH'])
        self.pts[addr].dRel = math.cos(azimuth) * msg['LONG_DIST']
        self.pts[addr].yRel = 0.5 * -math.sin(azimuth) * msg['LONG_DIST']
        self.pts[addr].vRel = msg['REL_SPEED']

      else:
        del self.pts[addr]

    ret.points = list(self.pts.values())
    return ret
