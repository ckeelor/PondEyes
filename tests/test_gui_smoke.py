# tests.test_gui_smoke
# ====================
#
# Headless smoke test for the GUI. Because we can't eyeball pixels in CI, this boots the real
# RadarGUI under SDL's dummy video/audio drivers with TWO simulated sensors, runs the actual
# event+render loop for a fraction of a second, then quits. It asserts:
#   - the loop runs and exits with NO exceptions (catches render-time mistakes), and
#   - both sensors' frames flowed all the way into the SQLite store as tracks.
#
# This is what guards the large, blind gui.py edits in the multi-sensor refactor.

import os
import time
import threading
from pathlib import Path

# SDL must be told to use non-graphical drivers BEFORE the display/mixer are created.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

REPO = Path(__file__).resolve().parent.parent
MAP = str(REPO / "map.svg")


def _sim_sensor(sid, color):
    # A self-contained sensor that needs no hardware: input_mode "sim" -> FakeReader.
    return {
        "id": sid, "label": sid, "color": color, "enabled": True,
        "input_mode": "sim", "sim_pattern": "circle", "sim_hz": 30.0,
        "position": [2000.0, 2000.0], "heading": 0.0,
    }


def test_gui_runs_headless_with_two_sim_sensors(tmp_path, monkeypatch):
    pygame.init()
    # The dummy video driver has no cursor support; neutralise the call.
    monkeypatch.setattr(pygame.mouse, "set_cursor", lambda *a, **k: None)
    # run() ends with pygame.quit() (production shutdown). In a shared test process that
    # uninitialises pygame for sibling tests and can segfault the next set_mode under the
    # dummy driver, so neutralise it here — real runs are unaffected.
    monkeypatch.setattr(pygame, "quit", lambda: None)

    # Send the SQLite DB (and any migration .bak) to a temp dir, not the repo.
    from radar import constants as C
    monkeypatch.setattr(C, "ROOT", tmp_path)

    cfg = {
        "schema_version": 2,
        "sensors": [_sim_sensor("S1", "#00ff80"), _sim_sensor("S2", "#ff8800")],
        "map": MAP, "sound": False, "night": False,
        "trail_duration": 5.0, "trail_on": True,
        "smoothing_on": True, "smooth_level": 0, "debug": True,
    }

    from radar.gui import RadarGUI
    app = RadarGUI(cfg)

    # Run the real loop briefly, then post QUIT from a helper thread so run() exits cleanly.
    def stopper():
        time.sleep(0.4)
        pygame.event.post(pygame.event.Event(pygame.QUIT))
    threading.Thread(target=stopper, daemon=True).start()

    app.run()      # exercises events + the full draw path; any exception fails the test

    # Both sim sensors should have produced tracks in the DB.
    from radar.store import TrackStore
    import datetime as dt
    store = TrackStore(tmp_path / "pondeyes.db")
    tracks = store.list_tracks_on_day(dt.date.today().isoformat())
    sensor_ids = {t["sensor_id"] for t in tracks}
    store.close()
    assert "S1" in sensor_ids and "S2" in sensor_ids, f"got tracks for {sensor_ids}"
