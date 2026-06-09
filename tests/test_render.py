# tests.test_render
# =================
#
# The shared renderer that both the live view and playback use. geometry.* is pure math (the
# de-duplicated projection / arc geometry); render.* are the pygame draw primitives. We verify
# the math exactly and that the draw helpers run headless without raising.

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import math

import pygame
import pytest

from radar import geometry, render


def test_projector_round_trip():
    p = geometry.Projector(off_x=100, off_y=50, ppm=0.5, svg_h=800)
    px, py = p.mm_to_px(1000, 2000)
    mx, my = p.px_to_mm(px, py)
    assert mx == pytest.approx(1000, abs=2)
    assert my == pytest.approx(2000, abs=2)


def test_local_to_world_matches_rotation():
    # heading 90: straight-ahead (0,1000) -> +x ; right (1000,0) -> -y. Same result the old
    # Sensor.local_to_world produced (it now delegates here).
    assert geometry.local_to_world(0, 1000, (0, 0, 90)) == pytest.approx((1000, 0))
    assert geometry.local_to_world(1000, 0, (0, 0, 90)) == pytest.approx((0, -1000))
    assert geometry.local_to_world(0, 1000, (500, 700, 0)) == pytest.approx((500, 1700))


def test_fov_arc_endpoints_and_midpoint():
    pts = geometry.fov_arc_pts(0, 0, 0, 100, fov_deg=120, steps=24)
    assert len(pts) == 25
    # heading 0 -> "ahead" is screen-up (0, -R); the arc midpoint sits there.
    assert pts[12] == pytest.approx((0, -100), abs=1)
    # endpoints land at ±60° (±FOV/2) from ahead.
    assert pts[0] == pytest.approx((100 * math.sin(math.radians(-60)),
                                    -100 * math.cos(math.radians(-60))), abs=1)
    assert pts[-1] == pytest.approx((100 * math.sin(math.radians(60)),
                                     -100 * math.cos(math.radians(60))), abs=1)


def test_sensor_fill_pts_pie_vs_annulus():
    # No near gate -> pie slice (apex at the sensor). With a near gate -> annulus (no apex).
    pie = geometry.sensor_fill_pts(0, 0, 0, 100.0, 0.0)
    ann = geometry.sensor_fill_pts(0, 0, 0, 100.0, 40.0)
    assert pie is not None and (0, 0) in pie
    assert ann is not None and (0, 0) not in ann
    assert geometry.sensor_fill_pts(0, 0, 0, 50.0, 80.0) is None      # degenerate (in > out)


def test_draw_helpers_headless():
    pygame.init()
    surf = pygame.Surface((400, 400))
    proj = geometry.Projector(0, 0, 0.1, 400)
    # marker + cone + min/max gate arcs + fill, all without raising
    sx, sy = render.draw_sensor(surf, proj, (1000, 1000, 30), (0, 255, 0),
                                min_range_mm=500, max_range_mm=2000)
    assert isinstance(sx, int) and isinstance(sy, int)
    render.draw_trail(surf, [(10, 10, 0.0, (0, 255, 0))], now=1.0, duration=5.0)
    render.draw_target(surf, 50, 50, (0, 255, 0), pulse=0.5, speed_norm=0.3, label="T1",
                       font=pygame.font.SysFont(None, 16))
    render.draw_target(surf, 80, 80, (0, 255, 0), pulse=0.5, speed_norm=0.3, label="T2",
                       font=pygame.font.SysFont(None, 16), ghost=True)   # greyed/translucent path
