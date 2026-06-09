# tests.test_colors
# =================
#
# Unit tests for radar/colors.py — the per-sensor color model. The two properties that make
# the model "readable on screen" are what we assert:
#   1. HUE is preserved across speed (so a sensor's targets always look like that sensor).
#   2. BRIGHTNESS increases monotonically with speed (so faster reads as more vivid).

import colorsys

from radar import colors


def test_hex_rgb_round_trip():
    for hx in ("#00ff80", "#ff8800", "#000000", "#ffffff"):
        assert colors.rgb_to_hex(colors.hex_to_rgb(hx)) == hx


def test_hex_tolerates_missing_hash():
    assert colors.hex_to_rgb("00ff80") == (0, 255, 128)


def test_target_color_preserves_hue():
    # The hue of the produced color must match the base color's hue at every speed.
    base = "#00ff80"
    base_h = colorsys.rgb_to_hsv(*[c / 255 for c in colors.hex_to_rgb(base)])[0]
    for speed in (0.0, 0.25, 0.5, 0.75, 1.0):
        r, g, b = colors.target_color(base, speed)
        h = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0]
        assert abs(h - base_h) < 0.02, f"hue drifted at speed={speed}"


def test_target_color_brightness_monotonic_in_speed():
    # Summed RGB is a fine proxy for "brightness here"; it must not decrease as speed rises.
    base = "#00bfff"
    brightness = [sum(colors.target_color(base, s)) for s in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)]
    assert brightness == sorted(brightness)
    assert brightness[-1] > brightness[0]      # fast is strictly brighter than slow


def test_target_color_clamps_out_of_range_speed():
    # Defensive: speeds outside 0..1 must not raise or produce invalid (out-of-byte) colors.
    for s in (-5.0, 2.0):
        r, g, b = colors.target_color("#ff00aa", s)
        assert all(0 <= c <= 255 for c in (r, g, b))
