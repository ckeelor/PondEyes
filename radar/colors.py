# radar.colors
# ============
#
# Per-sensor color model.
#
# In the original single-sensor app, every target was colored by SPEED using one global
# green->cyan->yellow->red gradient (constants.GRADIENT). With multiple sensors we want two
# things at once on screen:
#   1. WHICH SENSOR a target came from  (identity)  -> encoded as the HUE
#   2. HOW FAST the target is moving     (velocity)  -> encoded as BRIGHTNESS/SATURATION
#
# So each sensor gets a base color (its hue), and a given target's color is that hue made
# dim/muted when slow and vivid/bright when fast. The marker and field-of-view cone use the
# base color directly; only the moving targets get the speed ramp.
#
# We work in HSV because it separates exactly the axes we care about: H = identity (leave it
# alone), V/S = speed (ramp them). Converting RGB<->HSV is one stdlib call away (colorsys),
# which operates on 0..1 floats — so the helpers below translate to/from 0..255 ints and
# #rrggbb strings, which is what pygame and the config file use.

from __future__ import annotations

import colorsys
from typing import Tuple

RGB = Tuple[int, int, int]


def hex_to_rgb(s: str) -> RGB:
    # "#00ff80" (or "00ff80") -> (0, 255, 128). Tolerant of a missing leading '#'.
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def rgb_to_hex(rgb: RGB) -> str:
    # (0, 255, 128) -> "#00ff80". Values are clamped to the valid 0..255 byte range.
    r, g, b = (max(0, min(255, int(c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def rgb_to_hsv(rgb: RGB) -> Tuple[float, float, float]:
    # 0..255 ints -> (h, s, v) floats in 0..1, via stdlib colorsys.
    r, g, b = (c / 255.0 for c in rgb)
    return colorsys.rgb_to_hsv(r, g, b)


def hsv_to_rgb(h: float, s: float, v: float) -> RGB:
    # (h, s, v) floats in 0..1 -> 0..255 int RGB tuple.
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (round(r * 255), round(g * 255), round(b * 255))


# Tunables for the speed ramp. At speed_norm = 0 (stationary) a target is dim and slightly
# desaturated; at speed_norm = 1 (fast) it is full brightness and saturation. Keeping a
# non-zero floor (V never drops below ~0.45) means even a still target stays visible.
_V_MIN, _V_MAX = 0.45, 1.00
_S_MIN, _S_MAX = 0.65, 1.00


def dim(rgb: RGB, factor: float = 0.35) -> RGB:
    # Darken a color toward black by `factor` (0..1). Used for the muted field-of-view cone
    # lines so they read as "this sensor's coverage" without overpowering the live targets.
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


def target_color(base_hex: str, speed_norm: float) -> RGB:
    # Color one target: keep the SENSOR'S HUE from base_hex, ramp brightness/saturation by
    # speed. speed_norm is expected in 0..1 (caller normalises raw mm/s by a max speed); we
    # clamp defensively so out-of-range inputs can't produce invalid colors.
    #
    #   slow target  -> dim, slightly muted version of the sensor's color
    #   fast target  -> vivid, full-brightness version of the sensor's color
    n = 0.0 if speed_norm < 0 else (1.0 if speed_norm > 1 else speed_norm)
    h, _s_base, _v_base = rgb_to_hsv(hex_to_rgb(base_hex))
    s = _S_MIN + (_S_MAX - _S_MIN) * n
    v = _V_MIN + (_V_MAX - _V_MIN) * n
    return hsv_to_rgb(h, s, v)
