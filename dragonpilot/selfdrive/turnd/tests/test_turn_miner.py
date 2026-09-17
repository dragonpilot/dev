import csv
import glob
import os

import pytest

from dragonpilot.selfdrive.turnd import turn_miner as tm
from dragonpilot.selfdrive.turnd.turn_miner import Sample, extract_turns, MINE_COLUMNS, read_segment, mine_segment
from dragonpilot.selfdrive.turnd.turn_report import report

_LOCAL_REALDATA = "/home/ricklan/cifs/realdata"


def _stream(segs):
  """segs: list of (duration_s, yaw_rate, v_ego, blinker) -> 20 Hz Sample list."""
  dt, t, out = 0.05, 0.0, []
  for dur, yr, v, bl in segs:
    for _ in range(int(round(dur / dt))):
      out.append(Sample(t=t, v_ego=v, left_blinker=(bl == "L"), right_blinker=(bl == "R"),
                        yaw_rate=yr, model_curv=yr / max(v, 0.1),
                        desire_turn_l=0.5 if yr < 0 else 0.1, desire_turn_r=0.5 if yr > 0 else 0.1,
                        ll_prob_l=0.02, ll_prob_r=0.02, lat=25.0, lon=121.0))
      t += dt
  return out


def test_extract_signaled_right_turn():
  s = _stream([(6.0, 0.0, 8.0, "."), (3.14, 0.5, 4.0, "R"), (6.0, 0.0, 8.0, ".")])
  rows = extract_turns(s, "segX")
  assert rows
  assert sorted(set(r["maneuver_id"] for r in rows)) == [0]
  assert rows[0]["outcome"] == "right" and rows[0]["heading_change"] > 45.0
  assert set(rows[0].keys()) == set(MINE_COLUMNS)
  assert [r["seq"] for r in rows] == list(range(len(rows)))
  assert rows[0]["t_rel"] == 0.0
  assert any(r["blinker"] == "R" for r in rows)          # blinker recorded


def test_extract_skips_unsignaled_turn():
  # a real yaw turn but blinker OFF the whole time -> deliberately NOT captured
  s = _stream([(6.0, 0.0, 8.0, "."), (3.14, 0.5, 4.0, "."), (6.0, 0.0, 8.0, ".")])
  assert extract_turns(s, "segX") == []


def test_extract_skips_maneuver_active_at_start():
  # stream begins mid-turn (blinker already on) -> skip it; then a clean signaled LEFT
  s = _stream([(2.0, 0.5, 4.0, "R"), (4.0, 0.0, 8.0, "."),
               (3.14, -0.5, 4.0, "L"), (6.0, 0.0, 8.0, ".")])
  rows = extract_turns(s, "segX")
  assert sorted(set(r["maneuver_id"] for r in rows)) == [0]
  assert rows[0]["outcome"] == "left"


def test_extract_skips_maneuver_active_at_end():
  # clean RIGHT, then a turn whose blinker is still on when the stream ends -> skip the second
  s = _stream([(4.0, 0.0, 8.0, "."), (3.14, 0.5, 4.0, "R"), (2.0, 0.0, 8.0, "."),
               (3.0, -0.5, 4.0, "L")])
  rows = extract_turns(s, "segX")
  assert sorted(set(r["maneuver_id"] for r in rows)) == [0]
  assert rows[0]["outcome"] == "right"


def test_extract_ignores_short_blinker_tap():
  s = _stream([(4.0, 0.0, 8.0, "."), (0.4, 0.5, 4.0, "R"), (4.0, 0.0, 8.0, ".")])  # 0.4s < MIN_TURN_DUR
  assert extract_turns(s, "segX") == []


@pytest.mark.skipif(not os.path.isdir(_LOCAL_REALDATA), reason="no local realdata mount")
def test_read_segment_returns_samples():
  seg = next((d for d in sorted(glob.glob(os.path.join(_LOCAL_REALDATA, "*")))
              if os.path.isfile(os.path.join(d, "rlog.zst"))), None)
  assert seg is not None
  samples = read_segment(os.path.join(seg, "rlog.zst"))
  assert isinstance(samples, list)
  if samples:
    assert isinstance(samples[0].v_ego, float) and isinstance(samples[0].yaw_rate, float)


@pytest.mark.skipif(not os.path.isdir(_LOCAL_REALDATA), reason="no local realdata mount")
def test_mine_segment_writes_rows_if_any_signaled_turn(tmp_path):
  # mine an entire route; at least one signaled turn is expected across it
  segs = sorted(glob.glob(os.path.join(_LOCAL_REALDATA, "0000000b--3555dbc7d6--*")))
  segs = [s for s in segs if os.path.isfile(os.path.join(s, "rlog.zst"))]
  if not segs:
    pytest.skip("route not present")
  out = tmp_path / "turn_mined.csv"
  total = 0
  with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=tm.MINE_COLUMNS)
    w.writeheader()
    for s in segs:
      total += mine_segment(s, w)
  assert total > 0
  with open(out) as f:
    rows = list(csv.DictReader(f))
  assert any(r["outcome"] in ("left", "right") for r in rows)
  # every emitted maneuver must be a complete signaled turn: it has a real blinker somewhere
  by_man = {}
  for r in rows:
    by_man.setdefault((r["segment"], r["maneuver_id"]), []).append(r)
  assert all(any(rr["blinker"] in ("L", "R") for rr in man) for man in by_man.values())


def test_read_segment_missing_file_returns_empty():
  assert read_segment("/no/such/rlog.zst") == []


def test_report_computes_lead_times(tmp_path):
  import csv as _csv
  p = tmp_path / "turn_mined.csv"
  with open(p, "w", newline="") as f:
    w = _csv.DictWriter(f, fieldnames=tm.MINE_COLUMNS)
    w.writeheader()
    yaws = [0.0, 0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.6, 0.4, 0.1]
    dtr  = [0.1, 0.1, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.5, 0.3]
    for i, (y, d) in enumerate(zip(yaws, dtr)):
      w.writerow({"segment": "s", "maneuver_id": 0, "seq": i, "t_rel": round(i * 0.2, 3),
                  "v_ego": 5.0, "blinker": "R", "yaw_rate": y, "heading_change": 80.0,
                  "outcome": "right", "model_curv": y / 5.0, "desire_turn_l": 0.1,
                  "desire_turn_r": d, "ll_prob_l": 0.02, "ll_prob_r": 0.02,
                  "lat": 0.0, "lon": 0.0})
  r = report(str(p))
  assert r["n_turns"] == 1
  assert r["signals"]["desire_turn_r"]["hit_rate"] == 1.0
  assert r["signals"]["desire_turn_r"]["median_lead_s"] >= 0.8   # crossed 0.5 at t=0.4, apex t=1.4
