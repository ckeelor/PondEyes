# tests.test_store
# ================
#
# Lifecycle + concurrency tests for radar/store.py (the SQLite TrackStore). We verify the
# open->append->close flow, that the incremental bounding box is correct, that serial
# numbering can resume from the DB, and that two threads appending at once don't corrupt data
# (the multi-sensor concurrency case).

import threading

from radar.store import TrackStore


def _sensor(sid):
    return {"id": sid, "label": sid, "input_mode": "serial", "position": [0, 0], "heading": 0}


def test_v2_snapshot_and_t_rel_s_round_trip(tmp_path):
    import sqlite3
    st = TrackStore(tmp_path / "t.db")
    st.upsert_sensor(_sensor("S1"))
    tid = st.open_track("S1", "T1", (1, 2, 3), "2026-01-01T00:00:00.000000",
                        snapshot={"color": "#abcdef", "min_range_mm": 500, "max_range_mm": 2000,
                                  "trail_on": False, "speed_sensitivity": 0.7})
    st.append_point(tid, "2026-01-01T00:00:00.050000", 10, 20, 22, 1.0, 0.0, "", t_rel_s=0.05)
    st.conn.row_factory = sqlite3.Row
    t = st.conn.execute("SELECT * FROM tracks WHERE id=?", (tid,)).fetchone()
    assert (t["sensor_color"], t["sensor_min_range_mm"], t["sensor_max_range_mm"]) == ("#abcdef", 500, 2000)
    assert t["sensor_trail_on"] == 0 and t["sensor_speed_sensitivity"] == 0.7
    p = st.conn.execute("SELECT t_rel_s FROM track_points WHERE track_id=?", (tid,)).fetchone()
    assert p["t_rel_s"] == 0.05
    st.close()


def test_v1_db_migrates_to_v2(tmp_path):
    import sqlite3
    from radar.store import _SCHEMA_V1
    p = tmp_path / "v1.db"
    c = sqlite3.connect(str(p), isolation_level=None)
    c.executescript("BEGIN;" + _SCHEMA_V1 + "PRAGMA user_version=1; COMMIT;")
    c.close()
    st = TrackStore(p)                                   # opening migrates v1 -> v2
    assert st.conn.execute("PRAGMA user_version").fetchone()[0] == 2
    cols_t = [r[1] for r in st.conn.execute("PRAGMA table_info(tracks)")]
    cols_p = [r[1] for r in st.conn.execute("PRAGMA table_info(track_points)")]
    assert {"sensor_color", "sensor_min_range_mm", "sensor_max_range_mm",
            "sensor_trail_on", "sensor_speed_sensitivity"} <= set(cols_t)
    assert "t_rel_s" in cols_p
    st.close()


def test_track_lifecycle_and_bbox(tmp_path):
    st = TrackStore(tmp_path / "t.db")
    st.upsert_sensor(_sensor("S1"))

    tid = st.open_track("S1", "T1", (10, 20, 0), "2026-01-01T00:00:00.000")
    st.append_point(tid, "2026-01-01T00:00:00.100", 10, 20, 22, 1.0, 0.0, "aa")
    st.append_point(tid, "2026-01-01T00:00:00.200", -5, 30, 30, 2.0, 1.0, "bb")
    st.close_track(tid, "2026-01-01T00:00:00.200", 0.2)

    assert len(st.fetch_points(tid)) == 2
    tracks = st.list_tracks_on_day("2026-01-01")
    assert len(tracks) == 1
    t = tracks[0]
    assert t["point_count"] == 2
    # bounding box across the two points
    assert (t["x_min"], t["x_max"], t["y_min"], t["y_max"]) == (-5, 10, 20, 30)
    # pose snapshot preserved
    assert (t["sensor_x"], t["sensor_y"], t["sensor_heading"]) == (10, 20, 0)
    st.close()


def test_max_serial_resumes(tmp_path):
    st = TrackStore(tmp_path / "t.db")
    st.upsert_sensor(_sensor("S1"))
    assert st.max_serial() == 0
    st.open_track("S1", "T7", (0, 0, 0), "2026-01-01T00:00:00.000")
    st.open_track("S1", "T3", (0, 0, 0), "2026-01-01T00:00:01.000")
    assert st.max_serial() == 7        # highest numeric suffix
    st.close()


def test_upsert_sensor_is_idempotent(tmp_path):
    st = TrackStore(tmp_path / "t.db")
    st.upsert_sensor(_sensor("S1"))
    st.upsert_sensor({**_sensor("S1"), "label": "Renamed", "color": "#ff0000"})
    row = st.conn.execute("SELECT label, color FROM sensors WHERE id='S1'").fetchone()
    assert row == ("Renamed", "#ff0000")
    st.close()


def test_concurrent_appends_from_two_threads(tmp_path):
    # Simulate two sensor reader threads appending to two tracks at once. With the store's
    # write lock + WAL, every insert must land (no lost rows, no corruption).
    st = TrackStore(tmp_path / "t.db")
    st.upsert_sensor(_sensor("S1"))
    st.upsert_sensor(_sensor("S2"))
    t1 = st.open_track("S1", "T1", (0, 0, 0), "2026-01-01T00:00:00.000")
    t2 = st.open_track("S2", "T2", (0, 0, 0), "2026-01-01T00:00:00.000")

    N = 200

    def hammer(track_id):
        for i in range(N):
            st.append_point(track_id, f"2026-01-01T00:00:{i:02d}.000", i, i, i, 1.0, 0.0, "")

    threads = [threading.Thread(target=hammer, args=(t,)) for t in (t1, t2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert len(st.fetch_points(t1)) == N
    assert len(st.fetch_points(t2)) == N
    st.close()
