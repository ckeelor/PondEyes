# tests.test_widgets
# ==================
#
# Unit tests for radar/widgets.py — the (reduced) ColorPicker. Click/drag in the live dialog
# still needs a human, but the collapse/expand state machine and swatch hit-test are pinned.

import pygame

from radar import widgets
from radar.widgets import ColorPicker


def test_swatch_index_at():
    rects = [pygame.Rect(0, 0, 10, 10), pygame.Rect(20, 0, 10, 10)]
    assert widgets.swatch_index_at((5, 5), rects) == 0
    assert widgets.swatch_index_at((25, 5), rects) == 1
    assert widgets.swatch_index_at((100, 100), rects) is None


def test_colorpicker_hex_round_trip():
    cp = ColorPicker("#ff8800")
    assert cp.hex == "#ff8800"
    cp.set_hex("#00bfff")
    assert cp.rgb == (0, 191, 255)
    cp.set_hex("not-a-color")           # malformed -> unchanged
    assert cp.rgb == (0, 191, 255)


def test_clicking_box_toggles_expanded():
    cp = ColorPicker("#000000")
    cp._box_rect = pygame.Rect(0, 0, 24, 24)
    assert cp.expanded is False
    assert cp.handle_mousedown((10, 10)) is True
    assert cp.expanded is True            # opened
    assert cp.handle_mousedown((10, 10)) is True
    assert cp.expanded is False           # toggled closed


def test_clicking_swatch_sets_colour_and_collapses():
    cp = ColorPicker("#000000")
    cp._box_rect = pygame.Rect(0, 0, 24, 24)
    cp.expanded = True
    cp._swatch_rects = [pygame.Rect(i * 30, 30, 24, 20) for i in range(len(widgets.SWATCHES))]
    assert cp.handle_mousedown((30 + 5, 35)) is True   # click 2nd swatch
    assert cp.hex == widgets.SWATCHES[1]
    assert cp.expanded is False                        # collapsed after picking


def test_clicking_elsewhere_while_open_collapses_without_consuming():
    cp = ColorPicker("#000000")
    cp._box_rect = pygame.Rect(0, 0, 24, 24)
    cp.expanded = True
    cp._swatch_rects = [pygame.Rect(0, 30, 24, 20)]
    # a click far away: not the box, not a swatch -> collapses, returns False (dialog acts)
    assert cp.handle_mousedown((500, 500)) is False
    assert cp.expanded is False
