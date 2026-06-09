# tests.test_playback
# ===================
#
# Headless test for the SQLite-backed playback. Seeds a store with one track, then drives the
# RadarPlaybackGUI's data path (load by id, project, draw) without a display server. The
# click/drag HUD still needs a human, but the load + projection + draw are verified here.

import os
import datetime as dt
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

REPO = Path(__file__).resolve().parent.parent
MAP = str(REPO / "map.svg")


def _seed_store(db_path):
    from radar.store import TrackStore
    st = TrackStore(db_path)
    st.upsert_sensor({"id": "S2", "label": "Rear", "color": "#ff8800",
                      "input_mode": "serial", "position": [1000, 2000], "heading": 90})
    tid = st.open_track("S2", "T1", (1000.0, 2000.0, 90.0), "2026-06-08T10:00:00.000")
    for i in range(4):
        st.append_point(tid, f"2026-06-08T10:00:0{i}.000", i * 100, 500 + i * 50,
                        500, 1.0 * i, 0.0, "")
    st.close_track(tid, "2026-06-08T10:00:03.000", 3.0)
    st.close()
    return tid


def test_playback_loads_track_and_draws(tmp_path, monkeypatch):
    pygame.init()
    from radar import constants as C
    monkeypatch.setattr(C, "ROOT", tmp_path)

    tid = _seed_store(tmp_path / "pondeyes.db")

    from radar.playback_gui import RadarPlaybackGUI
    pb = RadarPlaybackGUI({"map": MAP})
    try:
        assert len(pb.tracks) == 1                        # selection list sees the seeded track

        pb._begin_playback_id(tid)
        assert pb.selection_mode is False
        assert len(pb.data) == 4                          # four points loaded
        assert pb.pose == (1000.0, 2000.0, 90.0)          # recorded pose, not live config
        assert pb.track_color == (255, 136, 0)            # S2's colour (#ff8800)

        # Both screens must render without raising.
        pb.selection_mode = True
        pb._draw_selection()
        pb.selection_mode = False
        pb._draw_playback()
    finally:
        pb.worker_alive = False
        pb.store.close()


def test_playback_v2_snapshot_and_timeline(tmp_path, monkeypatch):
    # A v2-recorded track carries gates + colour + trail + high-res t_rel_s; playback must
    # reconstruct them (faithful, "like the live view") and time the replay from t_rel_s.
    pygame.init()
    from radar import constants as C
    monkeypatch.setattr(C, "ROOT", tmp_path)

    from radar.store import TrackStore
    st = TrackStore(tmp_path / "pondeyes.db")
    st.upsert_sensor({"id": "S1", "label": "S1", "color": "#00ddff",
                      "input_mode": "serial", "position": [2000, 2000], "heading": 30})
    tid = st.open_track("S1", "T9", (2000.0, 2000.0, 30.0), "2026-06-08T10:00:00.000000",
                        snapshot={"color": "#00ddff", "min_range_mm": 700, "max_range_mm": 2500,
                                  "trail_on": False, "speed_sensitivity": 0.5})
    for i in range(5):
        st.append_point(tid, f"2026-06-08T10:00:0{i}.000000", i * 120, 600 + i * 40,
                        600, 1.0 * i, 0.0, "", t_rel_s=i * 0.05)
    st.close_track(tid, "2026-06-08T10:00:04.000000", 4.0)
    st.close()

    from radar.playback_gui import RadarPlaybackGUI
    pb = RadarPlaybackGUI({"map": MAP})
    try:
        pb._begin_playback_id(tid)
        assert pb.sensor_min_range_mm == 700 and pb.sensor_max_range_mm == 2500
        assert pb.track_color == (0, 221, 255)              # snapshot colour (#00ddff)
        assert pb.trail_on is False                         # Trail defaulted to as-recorded
        assert pb.capture_start is not None                 # real capture time-of-day available
        assert pb.capture_start.year == 2026
        assert [round(d[0], 3) for d in pb.data] == [0.0, 0.05, 0.1, 0.15, 0.2]  # t_rel_s timeline
        pb.selection_mode = False
        pb._draw_playback()                                 # renders sensor + gate arcs/fill
    finally:
        pb.worker_alive = False
        pb.store.close()
