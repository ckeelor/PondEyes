# radar.geometry
# ==============
#
# Pure-math projection + radar geometry shared by the live view (radar.gui) and the playback
# window (radar.playback_gui). No pygame here on purpose: keeping the math pygame-free means
# radar.sensors (and unit tests) can use local_to_world() without dragging in a display.
#
# Before this module the projection was copy-pasted in three places — gui.mm_to_px,
# playback_gui._mm_to_px, and Sensor.local_to_world — which is exactly the kind of drift this
# centralises. radar.render does the pygame drawing on top of these helpers.

from __future__ import annotations

import math
from typing import List, Tuple

FOV_DEG = 120          # LD2450 field-of-view (degrees); the cone + gate arcs span ±FOV_DEG/2.


class Projector:
    # World-millimetres <-> screen-pixels for one fitted map. `svg_h` is the rendered map height;
    # world +y is "up", so it maps to DECREASING screen y. Holds the fit so callers don't repeat
    # the arithmetic. Rebuild it whenever the map is refit (new size / map / mode).
    def __init__(self, off_x: float, off_y: float, ppm: float, svg_h: float):
        self.off_x, self.off_y, self.ppm, self.svg_h = off_x, off_y, ppm, svg_h

    def mm_to_px(self, mx: float, my: float) -> Tuple[int, int]:
        return (self.off_x + int(mx * self.ppm),
                self.off_y + int(self.svg_h - my * self.ppm))

    def px_to_mm(self, px: float, py: float) -> Tuple[float, float]:
        return ((px - self.off_x) / self.ppm,
                (self.svg_h - (py - self.off_y)) / self.ppm)


def local_to_world(xl: float, yl: float, pose: Tuple[float, float, float]) -> Tuple[float, float]:
    # Project a sensor-local point (x-right, y-ahead, mm) into WORLD mm given the sensor's
    # pose = (x, y, heading_deg). Rotate by heading, then translate by position. The minus on
    # the world-y term matches screen/world y growing opposite to a textbook rotation (keeps
    # existing calibrations valid).
    sx, sy, hd = pose
    c, s = math.cos(math.radians(hd)), math.sin(math.radians(hd))
    return sx + xl * c + yl * s, sy - xl * s + yl * c


def fov_arc_pts(sx: float, sy: float, heading: float, R_px: float,
                fov_deg: float = FOV_DEG, steps: int = 24) -> List[Tuple[float, float]]:
    # Points along the FOV arc (−fov/2..+fov/2 around heading) at radius R_px in SCREEN space,
    # using the same sin/−cos convention as the cone edges so the arc ends land on those edges.
    pts = []
    for k in range(steps + 1):
        th = math.radians(heading + (-fov_deg / 2 + fov_deg * k / steps))
        pts.append((sx + math.sin(th) * R_px, sy - math.cos(th) * R_px))
    return pts


def sensor_fill_pts(sx: float, sy: float, heading: float, R_out_px: float,
                    R_in_px: float = 0.0, fov_deg: float = FOV_DEG):
    # Polygon points for the translucent "active area" wedge between the FOV edges, from R_in_px
    # (near gate; 0 = apex/pie-slice) to R_out_px (far gate). Returns None if degenerate.
    if R_out_px <= R_in_px:
        return None
    pts = fov_arc_pts(sx, sy, heading, R_out_px, fov_deg)            # outer arc L->R
    if R_in_px > 0:
        pts += list(reversed(fov_arc_pts(sx, sy, heading, R_in_px, fov_deg)))  # inner R->L
    else:
        pts.append((sx, sy))                                        # apex
    return pts if len(pts) >= 3 else None
