# tests.test_gui_config
# =====================
#
# Headless tests for the Phase 3 sensor-management logic and the CONFIG dialog draw. The
# mouse-driven flows (clicking rows/buttons/sliders) still need a human, but the data
# operations behind them (_add/_remove/_duplicate/_select_sensor) and the dialog's ability to
# render without crashing ARE verifiable here.

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

REPO = Path(__file__).resolve().parent.parent
MAP = str(REPO / "map.svg")


def _sim_sensor(sid, color):
    return {"id": sid, "label": sid, "color": color, "enabled": True,
            "input_mode": "sim", "sim_pattern": "circle", "sim_hz": 30.0,
            "position": [2000.0, 2000.0], "heading": 0.0}


@pytest.fixture
def gui(tmp_path, monkeypatch):
    pygame.init()
    monkeypatch.setattr(pygame.mouse, "set_cursor", lambda *a, **k: None)
    from radar import constants as C
    monkeypatch.setattr(C, "ROOT", tmp_path)
    cfg = {
        "schema_version": 2,
        "sensors": [_sim_sensor("S1", "#00ff80")],
        "map": MAP, "sound": False, "night": False,
        "trail_duration": 5.0, "trail_on": True,
        "smoothing_on": True, "smooth_level": 0, "debug": False,
    }
    from radar.gui import RadarGUI
    app = RadarGUI(cfg)
    yield app
    app._close_inputs()
    app.store.close()


def test_add_sensor(gui):
    n = len(gui.sensors)
    gui._add_sensor()
    assert len(gui.sensors) == n + 1
    assert gui.selected_idx == n                       # newly added is selected
    assert gui.sensors[-1].id == "S2"
    # latest/stats dicts grew to include the new sensor
    assert "S2" in gui.latest_by_sensor and "S2" in gui.stats_by_sid


def test_duplicate_sensor(gui):
    gui.sensors[0].color = "#123456"
    gui._duplicate_sensor()
    assert len(gui.sensors) == 2
    assert gui.sensors[1].id != gui.sensors[0].id      # fresh unique id
    assert gui.sensors[1].color == "#123456"           # copied attributes


def test_remove_all_sensors_allowed(gui):
    gui._add_sensor()                                  # now 2
    gui._remove_sensor()                               # back to 1
    assert len(gui.sensors) == 1
    gui._remove_sensor()                               # remove the LAST one — now allowed
    assert len(gui.sensors) == 0
    assert gui.selected_sensor is None
    # the dialog must still render with zero sensors (and keep ADD available to recover)
    gui.show_cfg = True
    gui._draw_cfg_popup()
    assert "add" in gui.cfg_buttons


def test_inline_rename_and_set_wizard(gui):
    # rename the selected sensor inline
    gui.editing_label = True
    s = gui.selected_sensor
    s.label = ""
    for ch in "Front":
        s.label += ch
    assert gui.sensors[gui.selected_idx].label == "Front"
    # per-row SET launches the wizard for that sensor and closes the dialog
    gui.show_cfg = True
    gui._set_sensor_wizard(0)
    assert gui.sensor_stage == "intro" and gui.show_cfg is False


def test_ghost_marker_cull(gui):
    # A sensor that goes quiet must have its markers cleared even while another stays live —
    # the multi-sensor ghost-marker bug.
    import time
    import collections
    gui._add_sensor()                                  # S2 alongside S1
    s1, s2 = gui.sensors[0].id, gui.sensors[1].id
    now = time.monotonic()
    gui.latest_by_sensor[s1] = [(1, 100, 200)]
    gui.latest_by_sensor[s2] = [(1, 300, 400)]
    for sid in (s1, s2):
        gui.stats_by_sid[sid] = {"count": 5, "times": collections.deque([now]),
                                 "last_hex": "", "t_last": now}
    gui.stats_by_sid[s1]["t_last"] = now - 2.0         # S1 quiet > MARKER_STALE_SEC; S2 fresh
    gui._cull_stale_markers(now)
    assert gui.latest_by_sensor[s1] == []              # ghost cleared
    assert gui.latest_by_sensor[s2] == [(1, 300, 400)]  # live sensor untouched


def test_in_range_filter(gui):
    s = gui.sensors[0]
    s.max_range_mm = 0; s.min_range_mm = 0              # unlimited
    assert gui._in_range(s, 5000, 5000) is True
    s.max_range_mm = 1000                               # far gate at 1 m
    assert gui._in_range(s, 600, 800) is True           # hypot == 1000 (boundary) -> in
    assert gui._in_range(s, 800, 800) is False          # hypot ~1131 > 1000 -> out (too far)
    s.min_range_mm = 500                                # near gate at 0.5 m
    assert gui._in_range(s, 200, 200) is False          # hypot ~283 < 500 -> out (too near)
    assert gui._in_range(s, 600, 600) is True           # ~849 within [500, 1000]


def test_field_drives_sensor_gates(gui):
    gui.cfg_input[gui.MAXRANGE_FIELD] = "2.5"
    gui.cfg_input[gui.MINRANGE_FIELD] = "0.5"
    gui._sync_cfg()
    assert gui.sensors[gui.selected_idx].max_range_mm == 2500.0
    assert gui.sensors[gui.selected_idx].min_range_mm == 500.0


def test_wizard_range_slider_maps_to_field(gui):
    gui._draw_wizard_range_slider(gui.MAXRANGE_FIELD, "Max range", 400)   # registers range_rects
    rr = gui.range_rects[gui.MAXRANGE_FIELD]
    gui._set_range_from_x(gui.MAXRANGE_FIELD, rr.right)
    assert float(gui.cfg_input[gui.MAXRANGE_FIELD]) == gui.RANGE_MAX_M
    gui._set_range_from_x(gui.MAXRANGE_FIELD, rr.left)
    assert float(gui.cfg_input[gui.MAXRANGE_FIELD]) == 0.0


def test_live_arc_grab_and_drag(gui):
    s = gui.sensors[0]
    s.position = (3000, 3000); s.heading = 0.0; s.max_range_mm = 1500.0
    sx, sy = gui.mm_to_px(*s.position)
    R = s.max_range_mm * gui.ppm
    on_arc = (sx, sy - R)                               # straight ahead (heading 0) at the arc
    assert gui._arc_grab_at(on_arc) == (0, gui.MAXRANGE_FIELD)
    assert gui._arc_grab_at((sx, sy - R * 0.3)) is None  # well inside the arc -> no grab
    # drag the grabbed arc inward to half radius -> field roughly halves
    gui._select_sensor(0)
    gui._set_range_field_from_point(gui.MAXRANGE_FIELD, (sx, sy - R / 2))
    assert abs(float(gui.cfg_input[gui.MAXRANGE_FIELD]) - 0.75) < 0.2


def test_serial_baud_field_editable_and_validated(gui, monkeypatch):
    monkeypatch.setattr(gui, "_open_inputs", lambda: None)   # don't spawn a real serial reader
    gui.input_mode = "serial"; gui.sensors[0].input_mode = "serial"; gui._update_visible()
    assert gui.SERIALBAUD_FIELD in gui.visible_idx           # baud reachable in serial mode now
    assert gui.fields[gui.SERIALBAUD_FIELD] == "Serial Baud"
    gui.cfg_input[gui.SERIALBAUD_FIELD] = "921600"; gui._cfg_save()
    assert gui.sensors[gui.selected_idx].serial_baud == 921600 and gui.cfg_error == ""
    gui.cfg_input[gui.SERIALBAUD_FIELD] = "nope"; gui._cfg_save()
    assert gui.sensors[gui.selected_idx].serial_baud == 921600          # unchanged on bad input
    assert "baud" in gui.cfg_error.lower()


def test_auto_baud_button_present_in_serial_mode(gui):
    gui.input_mode = "serial"; gui.sensors[0].input_mode = "serial"; gui._update_visible()
    gui.show_cfg = True; gui._draw_cfg_popup()
    assert gui.cfg_buttons["auto_baud"].width > 0       # AUTO button drawn (not the _zero rect)


def test_auto_baud_applies_or_reports(gui, monkeypatch):
    import radar.gui as G
    monkeypatch.setattr(gui, "_open_inputs", lambda: None)
    monkeypatch.setattr(gui, "_close_inputs", lambda: None)
    gui.input_mode = "serial"; gui.sensors[0].input_mode = "serial"
    # detected -> applies to sensor + field, success message
    monkeypatch.setattr(G, "probe_baud", lambda port, *a, **k: 921600)
    gui._auto_baud()
    assert gui.sensors[gui.selected_idx].serial_baud == 921600
    assert gui.cfg_input[gui.SERIALBAUD_FIELD] == "921600"
    assert "detected" in gui.cfg_error.lower() and "921600" in gui.cfg_error
    # nothing found -> baud untouched, informative error
    monkeypatch.setattr(G, "probe_baud", lambda port, *a, **k: None)
    gui._auto_baud()
    assert gui.sensors[gui.selected_idx].serial_baud == 921600   # unchanged
    assert "no ld2450 frames" in gui.cfg_error.lower()


def test_zoom_to_cursor_and_reset(gui):
    focus = (gui.map_rect.centerx - 60, gui.map_rect.centery + 30)
    w0 = gui.px_to_mm(*focus)
    gui._apply_zoom(4.0, focus)
    assert gui.zoom == 4.0 and abs(gui.ppm - gui.base_ppm * 4.0) < 1e-6
    w1 = gui.px_to_mm(*focus)                                 # world point under cursor is fixed
    assert abs(w1[0] - w0[0]) < 5 and abs(w1[1] - w0[1]) < 5
    gui._apply_zoom(99.0, focus); assert gui.zoom == gui.MAX_ZOOM      # clamp up
    gui._apply_zoom(0.1, focus); assert gui.zoom == 1.0               # can't go below fit
    gui._apply_zoom(3.0, focus)
    bx, by = gui.off_x, gui.off_y                            # pan shifts the view offset
    gui._pan(50, -20)
    assert (gui.off_x, gui.off_y) == (bx + 50, by - 20)
    gui._reset_zoom()                                        # reset restores zoom AND offset
    assert (gui.zoom, gui.ppm) == (1.0, gui.base_ppm)
    assert (gui.off_x, gui.off_y) == (gui.base_off_x, gui.base_off_y)
    assert gui._view_surf is None


def test_target_menu_silence_and_ghost(gui):
    gui.target_hits = [(400, 300, "T7")]
    assert gui._target_at((402, 301)) == "T7"           # hit-test the rendered target
    gui.target_menu = {"serial": "T7", "pos": [402, 301], "rects": {}}
    gui.show_cfg = False
    gui._draw_target_menu()                             # lays out the item rects
    assert set(gui.target_menu["rects"]) == {"silence", "ghost"}
    gui._target_menu_click(gui.target_menu["rects"]["ghost"].center)
    assert "T7" in gui.ghosted and "T7" not in gui.silenced     # independent toggles
    gui._target_menu_click(gui.target_menu["rects"]["silence"].center)
    assert "T7" in gui.silenced
    gui._target_menu_click(gui.target_menu["rects"]["ghost"].center)
    assert "T7" not in gui.ghosted                      # ghost toggles back off


def test_speed_sensitivity_slider_maps_to_sensor(gui):
    gui.show_cfg = True
    gui._draw_cfg_popup()                               # lays out sens_rect for the selected sensor
    gui._set_sens_from_x(gui.sens_rect.right)
    assert gui.sensors[gui.selected_idx].speed_sensitivity == 1.0
    gui._set_sens_from_x(gui.sens_rect.left)
    assert gui.sensors[gui.selected_idx].speed_sensitivity == 0.0


def test_master_trail_override(gui):
    gui._add_sensor()                                  # 2 sensors, each trail_on=True
    gui.trail_on = True
    gui._toggle_all_trails()                           # master OFF (overrides), per-sensor intact
    assert gui.trail_on is False
    assert all(s.trail_on for s in gui.sensors)        # per-sensor settings NOT destroyed
    gui._toggle_all_trails()                           # master ON again
    assert gui.trail_on is True


def test_select_sensor_reloads_mirrors(gui):
    gui._add_sensor()                                  # S2 selected, sim
    gui.sensors[1].position = (4321.0, 8765.0)
    gui.sensors[1].heading = 33.0
    gui.sensors[1].color = "#ff00aa"
    gui._select_sensor(1)
    assert gui.sensor_mm == [4321.0, 8765.0]
    assert gui.sensor_hd == 33.0
    assert gui.color_picker.hex == "#ff00aa"


def test_config_dialog_draws_without_error(gui):
    # Two sensors so the list, picker, and buttons all render; just assert no exception.
    gui._add_sensor()
    gui.show_cfg = True
    gui._draw_cfg_popup()
    # The dialog must have registered its interactive rects for the event handler.
    for key in ("save", "cancel", "add", "remove", "dup", "sensor_rows",
                "mode_mqtt", "mode_serial", "mode_sim"):
        assert key in gui.cfg_buttons


def test_color_picker_change_propagates_to_selected_sensor(gui):
    from radar import widgets
    gui.show_cfg = True
    gui._draw_cfg_popup()                              # draw -> box rect exists, collapsed
    # Expand by clicking the colour box, redraw to lay out swatches, then pick the 2nd swatch.
    gui.color_picker.handle_mousedown(gui.color_picker._box_rect.center)
    assert gui.color_picker.expanded is True
    gui._draw_cfg_popup()
    gui.color_picker.handle_mousedown(gui.color_picker._swatch_rects[1].center)
    gui._sync_cfg()
    assert gui.sensors[gui.selected_idx].color == widgets.SWATCHES[1]
    assert gui.color_picker.expanded is False          # collapses after picking
