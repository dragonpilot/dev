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

ESCC module tests.
"""
from opendbc.can import CANPacker, CANParser
from opendbc.car.hyundai.escc import ESCC, EsccBus

# HyundaiFlags.ESCC lands in Task 2; the module must not depend on values.py load order,
# so ESCC takes raw flags. 2 ** 27 is the value Task 2 assigns.
ESCC_FLAG = 2 ** 27


class TestEsccModule:
  def test_msg_id(self):
    assert ESCC.MSG_ID == 0x2AB

  def test_enabled_flag(self):
    assert ESCC(ESCC_FLAG).enabled
    assert not ESCC(0).enabled

  def test_bus_key(self):
    assert EsccBus.escc == "escc"

  def test_update_scc12_injects_mirror(self):
    escc = ESCC(ESCC_FLAG)
    escc.cmd_act = 1
    escc.aeb_warning = 2
    escc.aeb_dec_cmd_act = 1
    escc.aeb_dec_cmd = 0.5
    values = {}
    escc.update_scc12(values)
    assert values["AEB_CmdAct"] == 1
    assert values["CF_VSM_Warn"] == 2
    assert values["CF_VSM_DecCmdAct"] == 1
    assert values["CR_VSM_DecCmd"] == 0.5
    assert values["AEB_Status"] == 2  # AEB enabled on dash

  def test_update_states_from_parser(self):
    escc = ESCC(ESCC_FLAG)
    parser = escc.get_parser()
    packer = CANPacker("hyundai_escc")
    msg = packer.make_can_msg("ESCC", 0, {
      "AEB_CmdAct": 1,
      "CF_VSM_Warn_SCC12": 2,
      "CF_VSM_DecCmdAct_SCC12": 1,
      "CR_VSM_DecCmd_SCC12": 0.5,
    })
    parser.update([0, [msg]])
    escc.update_states(parser)
    assert escc.cmd_act == 1
    assert escc.aeb_warning == 2
    assert escc.aeb_dec_cmd_act == 1
    assert abs(escc.aeb_dec_cmd - 0.5) < 0.011  # signal scale is 0.01

  def test_parser_reads_lead_signals(self):
    escc = ESCC(ESCC_FLAG)
    parser = escc.get_parser()
    packer = CANPacker("hyundai_escc")
    msg = packer.make_can_msg("ESCC", 0, {
      "ACC_ObjStatus": 1,
      "ACC_ObjDist": 42.5,
      "ACC_ObjRelSpd": -3.2,
      "ACC_ObjLatPos": 1.5,
    })
    parser.update([0, [msg]])
    vl = parser.vl["ESCC"]
    assert abs(vl["ACC_ObjDist"] - 42.5) < 0.11
    assert abs(vl["ACC_ObjRelSpd"] - (-3.2)) < 0.11
    assert abs(vl["ACC_ObjLatPos"] - 1.5) < 0.11
    assert vl["ACC_ObjStatus"] == 1


from opendbc.car import gen_empty_fingerprint
from opendbc.car.hyundai.interface import CarInterface
from opendbc.car.hyundai.values import CAR, HyundaiFlags, HyundaiSafetyFlags

RADAR_TRACK_ADDR = 0x500  # first Mando radar track message, bus 1


def _get_params(with_escc, with_radar_tracks=False, candidate=CAR.HYUNDAI_SONATA):
  fingerprint = gen_empty_fingerprint()
  if with_escc:
    fingerprint[0][ESCC.MSG_ID] = 8
  if with_radar_tracks:
    fingerprint[1][RADAR_TRACK_ADDR] = 8
  return CarInterface.get_params(candidate, fingerprint, [], alpha_long=True, is_release=False, docs=False)


class TestEsccDetection:
  def test_no_escc_no_flag(self):
    CP = _get_params(with_escc=False)
    assert not (CP.flags & HyundaiFlags.ESCC.value)
    assert not (CP.safetyConfigs[-1].safetyParam & HyundaiSafetyFlags.ESCC.value)

  def test_escc_detected(self):
    CP = _get_params(with_escc=True)
    assert CP.flags & HyundaiFlags.ESCC.value
    assert CP.safetyConfigs[-1].safetyParam & HyundaiSafetyFlags.ESCC.value
    assert not CP.radarUnavailable

  def test_escc_lead_fallback_when_no_tracks(self):
    CP = _get_params(with_escc=True, with_radar_tracks=False)
    assert CP.flags & HyundaiFlags.ESCC_LEAD.value

  def test_escc_tracks_path_when_tracks_fingerprinted(self):
    # HYUNDAI_SONATA is a Mando-radar platform with Bus.radar in its DBC config
    CP = _get_params(with_escc=True, with_radar_tracks=True)
    assert CP.flags & HyundaiFlags.ESCC.value
    assert not (CP.flags & HyundaiFlags.ESCC_LEAD.value)
    assert not CP.radarUnavailable

  def test_canfd_never_detects_escc(self):
    fingerprint = gen_empty_fingerprint()
    fingerprint[0][ESCC.MSG_ID] = 8
    CP = CarInterface.get_params(CAR.HYUNDAI_IONIQ_5, fingerprint, [], alpha_long=True, is_release=False, docs=False)
    assert not (CP.flags & HyundaiFlags.ESCC.value)


from opendbc.car import Bus
from opendbc.car.hyundai.carstate import CarState


def _feed(parser, packer, name, values, bus=0):
  # touch vl[name] once first: this CANParser only starts tracking a message's
  # MessageState the first time it's accessed (or if passed in the constructor's
  # messages list); Bus.pt's parser is built with an empty messages list, so
  # without this a single update() would silently drop the frame
  parser.vl[name]
  msg = packer.make_can_msg(name, bus, values)
  parser.update([0, [msg]])


class TestEsccCarState:
  def _setup(self, with_escc=True, use_fca=False):
    CP = _get_params(with_escc=with_escc)
    if use_fca:
      CP.flags |= HyundaiFlags.USE_FCA.value
    else:
      CP.flags &= ~HyundaiFlags.USE_FCA.value
    cs = CarState(CP)
    parsers = cs.get_can_parsers(CP)
    return CP, cs, parsers

  def test_escc_parser_registered(self):
    _, _, parsers = self._setup(with_escc=True)
    assert EsccBus.escc in parsers

  def test_no_escc_no_parser(self):
    _, _, parsers = self._setup(with_escc=False)
    assert EsccBus.escc not in parsers

  def test_mirror_and_events_non_fca(self):
    _, cs, parsers = self._setup(use_fca=False)
    packer = CANPacker("hyundai_escc")
    # AEB braking: warning + decel command active
    _feed(parsers[EsccBus.escc], packer, "ESCC", {
      "AEB_CmdAct": 1, "CF_VSM_Warn_SCC12": 2, "CF_VSM_DecCmdAct_SCC12": 1, "CR_VSM_DecCmd_SCC12": 0.98,
    })
    ret = cs.update(parsers)
    assert ret.stockAeb
    assert not ret.stockFcw
    assert cs.escc.cmd_act == 1
    assert cs.escc.aeb_warning == 2
    assert cs.escc.aeb_dec_cmd_act == 1
    assert abs(cs.escc.aeb_dec_cmd - 0.98) < 0.011

  def test_fcw_only_non_fca(self):
    _, cs, parsers = self._setup(use_fca=False)
    packer = CANPacker("hyundai_escc")
    _feed(parsers[EsccBus.escc], packer, "ESCC", {"CF_VSM_Warn_SCC12": 2})
    ret = cs.update(parsers)
    assert ret.stockFcw
    assert not ret.stockAeb

  def test_fca_car_reads_fca11_not_mirror(self):
    CP, cs, parsers = self._setup(use_fca=True)
    pt_packer = CANPacker("hyundai_can_generated")
    _feed(parsers[Bus.pt], pt_packer, "FCA11", {"CF_VSM_Warn": 2, "CF_VSM_DecCmdAct": 1, "FCA_CmdAct": 1})
    ret = cs.update(parsers)
    assert ret.stockAeb
    # mirror fields untouched on FCA cars - AEB actuates via pass-through FCA11
    assert cs.escc.cmd_act == 0 and cs.escc.aeb_warning == 0


from types import SimpleNamespace
from opendbc.car.hyundai import hyundaican


def _acc_commands(CP, escc):
  packer = CANPacker("hyundai_can_generated")
  hud_control = SimpleNamespace(leadDistanceBars=2, leadVisible=False)
  return hyundaican.create_acc_commands(packer, True, -1.0, 1.0, 0, hud_control,
                                        50, False, False,
                                        bool(CP.flags & HyundaiFlags.USE_FCA.value), CP, escc=escc)


FCA11_ADDR, FCA12_ADDR, SCC12_ADDR = 0x38D, 0x483, 0x421


class TestEsccTx:
  def test_scc12_carries_mirror(self):
    CP = _get_params(with_escc=True)
    escc = ESCC(CP.flags)
    escc.cmd_act, escc.aeb_warning, escc.aeb_dec_cmd_act, escc.aeb_dec_cmd = 1, 2, 1, 0.98
    cmds = _acc_commands(CP, escc)
    # unpack the SCC12 we would send and check the AEB signals survived
    parser = CANParser("hyundai_can_generated", [("SCC12", 50)], 0)
    scc12 = next(m for m in cmds if m[0] == SCC12_ADDR)
    parser.update([0, [scc12]])
    vl = parser.vl["SCC12"]
    assert vl["AEB_CmdAct"] == 1
    assert vl["CF_VSM_Warn"] == 2
    assert vl["CF_VSM_DecCmdAct"] == 1
    assert abs(vl["CR_VSM_DecCmd"] - 0.98) < 0.011
    assert vl["AEB_Status"] == 2

  def test_scc12_checksum_covers_mirror(self):
    # Pins the ordering that escc.update_scc12() must run BEFORE the SCC12 checksum
    # is computed (hyundaican.py: splice, then pack+sum, then set CR_VSM_ChkSum).
    # CANParser has no checksum profile for "hyundai_can_generated" (see dbc.py
    # get_checksum_state), so it never validates CR_VSM_ChkSum on its own - a
    # regression that spliced the AEB mirror in AFTER the checksum was computed
    # would still decode fine and pass test_scc12_carries_mirror. This test
    # recomputes the checksum independently (mirroring hyundaican.py's algorithm)
    # over the actually-transmitted bytes and checks it matches the transmitted
    # CR_VSM_ChkSum, which only holds if the splice happened before checksumming.
    CP = _get_params(with_escc=True)
    escc = ESCC(CP.flags)
    escc.cmd_act, escc.aeb_warning, escc.aeb_dec_cmd_act, escc.aeb_dec_cmd = 1, 2, 1, 0.98
    cmds = _acc_commands(CP, escc)
    scc12 = next(m for m in cmds if m[0] == SCC12_ADDR)

    parser = CANParser("hyundai_can_generated", [("SCC12", 50)], 0)
    parser.update([0, [scc12]])
    vl = dict(parser.vl["SCC12"])
    transmitted_checksum = int(vl["CR_VSM_ChkSum"])

    # re-pack the decoded signals with CR_VSM_ChkSum absent (defaults to 0), exactly
    # like hyundaican.py's first pass before it knows the checksum, then sum nibbles
    del vl["CR_VSM_ChkSum"]
    recompute_packer = CANPacker("hyundai_can_generated")
    dat = recompute_packer.make_can_msg("SCC12", 0, vl)[1]
    expected_checksum = 0x10 - sum(sum(divmod(i, 16)) for i in dat) % 0x10

    assert transmitted_checksum == expected_checksum

  def test_no_fca11_when_escc(self):
    CP = _get_params(with_escc=True)
    CP.flags |= HyundaiFlags.USE_FCA.value
    cmds = _acc_commands(CP, ESCC(CP.flags))
    assert not any(m[0] == FCA11_ADDR for m in cmds)

  def test_no_fca12_when_escc(self):
    CP = _get_params(with_escc=True)
    packer = CANPacker("hyundai_can_generated")
    cmds = hyundaican.create_acc_opt(packer, CP, escc=ESCC(CP.flags))
    assert not any(m[0] == FCA12_ADDR for m in cmds)

  def test_byte_identical_without_escc(self):
    # regression guard: escc=None and escc-disabled must not change output at all
    CP = _get_params(with_escc=False)
    CP.flags |= HyundaiFlags.USE_FCA.value
    baseline = _acc_commands(CP, None)
    disabled = _acc_commands(CP, ESCC(CP.flags))
    assert baseline == disabled
    assert any(m[0] == FCA11_ADDR for m in baseline)  # FCA11 still sent without ESCC


from unittest import mock


class TestEsccInit:
  def test_radar_not_disabled_with_escc(self):
    CP = _get_params(with_escc=True)
    with mock.patch("opendbc.car.hyundai.interface.disable_ecu") as m_disable, \
         mock.patch("opendbc.car.hyundai.escc.enable_radar_tracks"):
      CarInterface.init(CP, mock.MagicMock(), mock.MagicMock())
      m_disable.assert_not_called()

  def test_radar_disabled_without_escc(self):
    CP = _get_params(with_escc=False)
    with mock.patch("opendbc.car.hyundai.interface.disable_ecu") as m_disable:
      CarInterface.init(CP, mock.MagicMock(), mock.MagicMock())
      m_disable.assert_called_once()

  def test_radar_tracks_enabled_on_mando_escc(self):
    CP = _get_params(with_escc=True)
    assert CP.flags & HyundaiFlags.MANDO_RADAR.value  # SONATA is Mando
    with mock.patch("opendbc.car.hyundai.escc.enable_radar_tracks") as m_tracks:
      CarInterface.init(CP, mock.MagicMock(), mock.MagicMock())
      m_tracks.assert_called_once()

  def test_radar_tracks_not_enabled_on_deinit(self):
    # deinit() calls init() internally with communication_control set; the UDS write
    # must only fire on true startup init, not on every teardown
    CP = _get_params(with_escc=True)
    assert CP.flags & HyundaiFlags.MANDO_RADAR.value  # SONATA is Mando
    with mock.patch("opendbc.car.hyundai.escc.enable_radar_tracks") as m_tracks:
      CarInterface.deinit(CP, mock.MagicMock(), mock.MagicMock())
      m_tracks.assert_not_called()


from opendbc.car.hyundai.radar_interface import RadarInterface


class TestEsccRadarInterface:
  def test_escc_lead_point(self):
    CP = _get_params(with_escc=True, with_radar_tracks=False)
    ri = RadarInterface(CP)
    assert ri.trigger_msg == ESCC.MSG_ID
    packer = CANPacker("hyundai_escc")
    msg = packer.make_can_msg("ESCC", 0, {
      "ACC_ObjStatus": 1, "ACC_ObjDist": 42.5, "ACC_ObjRelSpd": -3.2, "ACC_ObjLatPos": 1.5,
    })
    rr = ri.update([(0, [msg])])
    assert rr is not None
    assert len(rr.points) == 1
    pt = rr.points[0]
    assert abs(pt.dRel - 42.5) < 0.11
    assert abs(pt.vRel - (-3.2)) < 0.11
    assert abs(pt.yRel - (-1.5)) < 0.11

  def test_escc_lead_clears_when_invalid(self):
    CP = _get_params(with_escc=True, with_radar_tracks=False)
    ri = RadarInterface(CP)
    packer = CANPacker("hyundai_escc")
    ri.update([(0, [packer.make_can_msg("ESCC", 0, {"ACC_ObjStatus": 1, "ACC_ObjDist": 10.0})])])
    rr = ri.update([(0, [packer.make_can_msg("ESCC", 0, {"ACC_ObjStatus": 0})])])
    assert len(rr.points) == 0

  def test_tracks_path_untouched(self):
    CP = _get_params(with_escc=True, with_radar_tracks=True)
    ri = RadarInterface(CP)
    # tracks fingerprinted -> upstream tracks parser and trigger message, not ESCC
    assert ri.trigger_msg != ESCC.MSG_ID


class TestEsccReplayScenario:
  """Synthetic-CAN replay: a scripted 3-phase drive fed frame-by-frame through
  CarState + RadarInterface. Phase 1: lead appears. Phase 2: AEB warning (FCW).
  Phase 3: AEB braking. Assert outputs at every frame."""

  def test_scenario(self):
    CP = _get_params(with_escc=True, with_radar_tracks=False)
    cs = CarState(CP)
    parsers = cs.get_can_parsers(CP)
    ri = RadarInterface(CP)
    escc_packer = CANPacker("hyundai_escc")

    def frame(escc_values):
      msg = escc_packer.make_can_msg("ESCC", 0, escc_values)
      parsers[EsccBus.escc].update([0, [msg]])
      ret = cs.update(parsers)
      rr = ri.update([(0, [msg])])
      return ret, rr

    # phase 1: lead at 50m closing at 2 m/s, no AEB
    for i in range(50):
      ret, rr = frame({"ACC_ObjStatus": 1, "ACC_ObjDist": 50.0 - i * 0.4, "ACC_ObjRelSpd": -2.0})
      assert not ret.stockAeb and not ret.stockFcw
      assert rr is not None and len(rr.points) == 1
      assert abs(rr.points[0].dRel - (50.0 - i * 0.4)) < 0.11

    # phase 2: FCW - warning without braking
    for _ in range(10):
      ret, rr = frame({"ACC_ObjStatus": 1, "ACC_ObjDist": 30.0, "ACC_ObjRelSpd": -2.0,
                       "CF_VSM_Warn_SCC12": 2})
      assert ret.stockFcw and not ret.stockAeb

    # phase 3: AEB braking - mirror must carry the decel command into our SCC12
    for _ in range(10):
      ret, rr = frame({"ACC_ObjStatus": 1, "ACC_ObjDist": 10.0, "ACC_ObjRelSpd": -5.0,
                       "CF_VSM_Warn_SCC12": 2, "CF_VSM_DecCmdAct_SCC12": 1,
                       "AEB_CmdAct": 1, "CR_VSM_DecCmd_SCC12": 0.98})
      assert ret.stockAeb and not ret.stockFcw
      scc12 = {}
      cs.escc.update_scc12(scc12)
      assert scc12["AEB_CmdAct"] == 1
      assert abs(scc12["CR_VSM_DecCmd"] - 0.98) < 0.011

    # lead disappears
    ret, rr = frame({"ACC_ObjStatus": 0})
    assert len(rr.points) == 0
