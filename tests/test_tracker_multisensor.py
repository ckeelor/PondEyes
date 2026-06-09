# tests.test_tracker_multisensor
# ==============================
#
# The headline multi-sensor correctness test: two sensors each reporting a target in slot 1
# must produce TWO independent tracks (not collide into one). Also exercises the full
# FakeReader -> Tracker -> TrackStore pipeline deterministically via manual-clock.

import datetime as dt

from radar.store import TrackStore
from radar.tracking import (Tracker, split_speed_for,
                            SPLIT_SPEED_STRICT_MM_S, SPLIT_SPEED_PERMISSIVE_MM_S)
from radar.reader_base import FakeReader
from radar import trajectories


def _sensor(sid):
    return {"id": sid, "label": sid, "input_mode": "serial", "position": [0, 0], "heading": 0}


def test_two_sensors_slot1_are_independent(tmp_path):
    st = TrackStore(tmp_path / "t.db")
    st.upsert_sensor(_sensor("S1"))
    st.upsert_sensor(_sensor("S2"))
    tr = Tracker(st)

    # Both sensors report a target in slot 1, at different positions.
    tr.update("S1", (0, 0, 0), [(1, 100, 200, "")])
    tr.update("S2", (0, 0, 0), [(1, 300, 400, "")])

    s1 = tr.serial_for("S1", 1)
    s2 = tr.serial_for("S2", 1)
    assert s1 is not None and s2 is not None
    assert s1 != s2                      # distinct serials -> distinct people
    assert len(tr.active) == 2           # two live tracks
    st.close()


def test_pipeline_fakereader_to_store(tmp_path):
    # Drive a stationary target through FakeReader (manual-clock) into the Tracker, and assert
    # the SQLite store ends up with one track holding the expected number of points.
    st = TrackStore(tmp_path / "t.db")
    st.upsert_sensor(_sensor("S1"))
    tr = Tracker(st)

    # The GUI normally wraps tracker.update with the sensor id + pose; emulate that closure.
    fr = FakeReader(lambda lst, t: tr.update("S1", (0.0, 0.0, 0.0), lst, frame_mono=t),
                    trajectories.static(x=100, y=200), manual=True)
    for i in range(5):
        fr.tick(i * 0.1)

    today = dt.date.today().isoformat()
    tracks = st.list_tracks_on_day(today)
    assert len(tracks) == 1
    assert tracks[0]["point_count"] == 5
    assert tracks[0]["sensor_id"] == "S1"
    st.close()


def test_split_speed_for_mapping():
    assert split_speed_for(0) is None                  # off
    assert split_speed_for(-1) is None
    assert split_speed_for(1.0) == SPLIT_SPEED_STRICT_MM_S
    assert split_speed_for(0.5) == (SPLIT_SPEED_PERMISSIVE_MM_S + SPLIT_SPEED_STRICT_MM_S) / 2


# Speed sensitivity / slot-reuse split. update() calls are back-to-back so dt ~ 1ms, making the
# gate ~ SPLIT_JITTER_MM (350mm); a >1m jump is far above it, a normal step far below.
SPLIT = 8000.0
A = (1, 100, 100, "")
B = (1, 4000, 4000, "")            # ~5.5m teleport from A


def _tracker(tmp_path):
    st = TrackStore(tmp_path / "t.db"); st.upsert_sensor(_sensor("S1"))
    return st, Tracker(st)


def test_teleport_confirmed_splits_into_two_tracks(tmp_path):
    st, tr = _tracker(tmp_path)
    tr.update("S1", (0, 0, 0), [A], SPLIT)             # establish a track at A
    old = tr.serial_for("S1", 1)
    tr.update("S1", (0, 0, 0), [B], SPLIT)             # jump -> PENDING (not yet split)
    assert ("S1", 1) in tr.pending                     # suppressed mid-jump
    tr.update("S1", (0, 0, 0), [B], SPLIT)             # persisted at B -> CONFIRM split
    new = tr.serial_for("S1", 1)
    assert new != old                                  # a NEW serial owns the slot
    assert old not in tr.active                         # old track was closed
    assert any(r["serial"] == old for r in tr.recent)
    st.close()


def test_single_frame_outlier_is_cancelled(tmp_path):
    st, tr = _tracker(tmp_path)
    tr.update("S1", (0, 0, 0), [A], SPLIT)
    old = tr.serial_for("S1", 1)
    tr.update("S1", (0, 0, 0), [B], SPLIT)             # jump -> pending
    tr.update("S1", (0, 0, 0), [A], SPLIT)             # came BACK to A -> cancel, resume old
    assert tr.serial_for("S1", 1) == old               # same track, no split
    assert ("S1", 1) not in tr.pending
    assert len(tr.active) == 1
    st.close()


def test_plausible_motion_never_splits(tmp_path):
    st, tr = _tracker(tmp_path)
    serials = set()
    for i in range(6):                                 # 120mm steps -> well under the gate
        tr.update("S1", (0, 0, 0), [(1, 100 + i*120, 100, "")], SPLIT)
        serials.add(tr.serial_for("S1", 1))
    assert len(serials) == 1                            # one continuous track
    st.close()


def test_split_off_keeps_legacy_teleport(tmp_path):
    st, tr = _tracker(tmp_path)
    tr.update("S1", (0, 0, 0), [A], None)              # splitting OFF
    old = tr.serial_for("S1", 1)
    tr.update("S1", (0, 0, 0), [B], None)              # teleport recorded onto the SAME serial
    assert tr.serial_for("S1", 1) == old
    assert not tr.pending
    st.close()


def test_snapshot_and_timing_persist(tmp_path):
    import sqlite3
    st, tr = _tracker(tmp_path)
    tr.update("S1", (0, 0, 0), [(1, 100, 100, "")], frame_mono=10.0,
              sensor_snapshot={"color": "#112233", "min_range_mm": 300, "max_range_mm": 1500,
                               "trail_on": False, "speed_sensitivity": 0.6})
    tr.update("S1", (0, 0, 0), [(1, 110, 110, "")], frame_mono=10.05)   # +50ms
    st.conn.row_factory = sqlite3.Row
    t = st.conn.execute("SELECT * FROM tracks ORDER BY id DESC LIMIT 1").fetchone()
    assert t["sensor_color"] == "#112233" and t["sensor_max_range_mm"] == 1500
    assert t["sensor_min_range_mm"] == 300 and t["sensor_trail_on"] == 0
    rels = [r["t_rel_s"] for r in st.conn.execute(
        "SELECT t_rel_s FROM track_points WHERE track_id=? ORDER BY rowid", (t["id"],))]
    assert rels[0] == 0.0 and abs(rels[1] - 0.05) < 1e-6     # frame_mono drives accurate t_rel_s
    st.close()


def test_serial_resumes_from_existing_db(tmp_path):
    # A Tracker built on a store that already has T4 should issue T5 next.
    st = TrackStore(tmp_path / "t.db")
    st.upsert_sensor(_sensor("S1"))
    st.open_track("S1", "T4", (0, 0, 0), "2026-01-01T00:00:00.000")
    tr = Tracker(st)
    tr.update("S1", (0, 0, 0), [(1, 10, 10, "")])
    assert tr.serial_for("S1", 1) == "T5"
    st.close()
