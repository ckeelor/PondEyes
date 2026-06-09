# radar.render
# ============
#
# The shared pygame drawing for sensors and targets, used by BOTH the live view (radar.gui) and
# the playback window (radar.playback_gui) so they render identically — same marker, FOV cone,
# distance-gate arcs + fill, pulse ring, and fading trail — with no duplicated draw code. The
# projection/geometry it sits on lives in radar.geometry (pygame-free).
#
# These are stateless primitives: callers own the per-sensor / per-track state (trail deques,
# pulse phase, smoothing) and pass in what to draw. That keeps live-vs-playback differences (the
# live view has smoothing + per-serial pulse state; playback scrubs recorded points) in the
# callers while the pixels come from one place.

from __future__ import annotations

import math

import pygame

from radar import geometry
from radar import colors

FILL_ALPHA = 60          # opacity of the active-area wedge (0..255)
MARKER_R = 6             # sensor marker radius (px)
RING_STEP_MM = 500       # range-reference rings every 0.5 m within the active band


def draw_sensor(screen, proj: geometry.Projector, pose, color, *,
                min_range_mm: float = 0.0, max_range_mm: float = 0.0,
                fov_deg: float = geometry.FOV_DEG, draw_cone: bool = True,
                draw_fill: bool = True, range_rings: bool = True,
                label: str = None, label_font=None):
    # Draw one sensor at `pose` (world x, y, heading_deg) in `color` (rgb tuple): faint active-area
    # fill (only when a far gate bounds it), FOV cone edges, faint range-reference rings every 0.5 m
    # inside the active band, min/max gate arcs (full colour, on top), and the marker. `draw_fill=
    # False` lets the live view batch all fills onto one shared overlay itself (see
    # geometry.sensor_fill_pts); playback uses the default and gets a self-contained fill. Returns
    # the sensor's screen (sx, sy) so callers can add editing affordances on top.
    sx, sy = proj.mm_to_px(pose[0], pose[1])
    heading = pose[2]
    ppm = proj.ppm

    if draw_fill and max_range_mm > 0:
        pts = geometry.sensor_fill_pts(sx, sy, heading, max_range_mm * ppm,
                                       min_range_mm * ppm if min_range_mm > 0 else 0.0, fov_deg)
        if pts:
            ov = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            pygame.draw.polygon(ov, tuple(color) + (FILL_ALPHA,), pts)
            screen.blit(ov, (0, 0))

    if draw_cone:
        for ang in (-fov_deg / 2, fov_deg / 2):                     # cone edges (same stroke as arcs)
            th = math.radians(heading + ang)
            pygame.draw.line(screen, color, (sx, sy),
                             (int(sx + math.sin(th) * 5000 / ppm),
                              int(sy - math.cos(th) * 5000 / ppm)), 1)
        # Range-reference rings every 0.5 m within the active band (faint; whole metres labelled
        # on the cone centre-line), so the user can read distance inside the shaded gate area.
        if range_rings and max_range_mm > 0:
            ring = colors.dim(color, 0.40)
            r_mm = RING_STEP_MM
            while r_mm <= max_range_mm + 1:
                if r_mm > min_range_mm:                             # only inside the active band
                    pygame.draw.lines(screen, ring, False,
                                      geometry.fov_arc_pts(sx, sy, heading, r_mm * ppm, fov_deg), 1)
                    if label_font and r_mm % 1000 == 0:            # label whole metres
                        th = math.radians(heading)
                        lx = sx + math.sin(th) * r_mm * ppm
                        ly = sy - math.cos(th) * r_mm * ppm
                        screen.blit(label_font.render(f"{r_mm // 1000}m", True, ring),
                                    (int(lx) + 3, int(ly) - 7))
                r_mm += RING_STEP_MM
        for rng in (max_range_mm, min_range_mm):                    # far + near gate arcs (on top)
            if rng > 0:
                pygame.draw.lines(screen, color, False,
                                  geometry.fov_arc_pts(sx, sy, heading, rng * ppm, fov_deg), 1)

    pygame.draw.circle(screen, color, (sx, sy), MARKER_R)
    if label and label_font:
        screen.blit(label_font.render(label, True, color), (sx + 8, sy + 6))
    return sx, sy


def draw_trail(screen, trail, now: float, duration: float, skip_pos=None):
    # Fading dots for a target's trail. `trail` is an iterable of (px, py, t, color_rgb); each dot
    # fades to nothing over `duration` seconds. `skip_pos` omits the dot at the live position.
    for tx, ty, tt, tc in trail:
        alpha = int(255 * (1 - (now - tt) / duration))
        if alpha <= 0 or (skip_pos is not None and (tx, ty) == skip_pos):
            continue
        dot = pygame.Surface((10, 10), pygame.SRCALPHA)
        pygame.draw.circle(dot, tuple(tc) + (alpha,), (5, 5), 5)
        screen.blit(dot, (tx - 5, ty - 5))


def draw_target(screen, px: int, py: int, color, *,
                pulse: float = 0.0, speed_norm: float = 0.0, label: str = None, font=None,
                ghost: bool = False):
    # A target: an expanding pulse RING (size grows with the 0..1 pulse phase, scaled by speed),
    # a solid dot, and an optional serial label. When `ghost`, the marker + ring + label are drawn
    # greyed and translucent (a "false reading" the user flagged) instead of full colour.
    ring_r = int(10 + pulse * (20 + 60 * speed_norm))
    if ghost:
        gc = tuple(colors.dim(color, 0.6)) + (90,)              # greyed + translucent
        R = max(ring_r, 8) + 2
        surf = pygame.Surface((2 * R, 2 * R), pygame.SRCALPHA)
        pygame.draw.circle(surf, gc, (R, R), ring_r, 1)
        pygame.draw.circle(surf, gc, (R, R), 5)
        screen.blit(surf, (px - R, py - R))
        if label and font:
            lab = font.render(label, True, colors.dim(color, 0.6)); lab.set_alpha(110)
            screen.blit(lab, (px + 8, py - 8))
        return
    pygame.draw.circle(screen, color, (px, py), ring_r, 1)
    pygame.draw.circle(screen, color, (px, py), 5)
    if label and font:
        screen.blit(font.render(label, True, color), (px + 8, py - 8))
