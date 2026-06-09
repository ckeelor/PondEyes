# radar.widgets
# =============
#
# Small reusable pygame UI widgets. Right now: ColorPicker (used in the CONFIG dialog).
#
# Colour-picking is a MINOR feature, so the picker is deliberately tiny: a single colour box
# that, when clicked, expands a small row of preset swatches. Picking a swatch sets the colour
# and collapses again. No hex readout, no RGB sliders — just "click box, pick a colour".
#
# The pure helper (swatch hit-test) is split out so it can be unit tested without a display.

from __future__ import annotations

from typing import List, Optional

import pygame

from radar import colors

RGB = tuple

# Preset palette offered when the picker is expanded (matches sensors.DEFAULT_PALETTE).
SWATCHES: List[str] = [
    "#00ff80", "#ff8800", "#00bfff", "#ff00aa",
    "#ffff00", "#00ffff", "#ff5555", "#aa55ff",
]


def swatch_index_at(pos, rects) -> Optional[int]:
    # Index of the swatch rect containing `pos`, or None. Pure -> unit-testable headless.
    for i, r in enumerate(rects):
        if r.collidepoint(pos):
            return i
    return None


class ColorPicker:
    # Collapsed by default: just a colour box. Clicking the box toggles a swatch row open;
    # clicking a swatch sets the colour and collapses. The owner reads `.hex` after events.
    def __init__(self, hex_color: str = "#00ff80"):
        self.rgb = colors.hex_to_rgb(hex_color)
        self.expanded = False
        self._box_rect: Optional[pygame.Rect] = None
        self._swatch_rects: List[pygame.Rect] = []

    @property
    def hex(self) -> str:
        return colors.rgb_to_hex(self.rgb)

    def set_hex(self, hex_color: str):
        try:
            self.rgb = colors.hex_to_rgb(hex_color)
        except (ValueError, IndexError):
            pass  # ignore malformed hex; keep current colour

    # ── drawing ──────────────────────────────────────────────────────────────────────────
    def draw(self, screen, x: int, y: int, width: int, font) -> int:
        # Draw the colour box (+ label), and the swatch row when expanded. Returns the height
        # consumed so the caller can lay out following content.
        from radar import constants as C

        self._box_rect = pygame.Rect(x, y, 24, 24)
        pygame.draw.rect(screen, self.rgb, self._box_rect)
        pygame.draw.rect(screen, C.GREEN, self._box_rect, 2)
        screen.blit(font.render("Marker color", True, C.GREEN), (x + 34, y + 4))
        height = 28

        self._swatch_rects = []
        if self.expanded:
            sy = y + 30
            for i, hx in enumerate(SWATCHES):
                r = pygame.Rect(x + i * 30, sy, 24, 20)
                pygame.draw.rect(screen, colors.hex_to_rgb(hx), r)
                pygame.draw.rect(screen, C.GREEN, r, 1)
                self._swatch_rects.append(r)
            height = 30 + 20 + 6

        return height

    # ── event handling ───────────────────────────────────────────────────────────────────
    def handle_mousedown(self, pos) -> bool:
        # Click the box -> toggle the swatch row. Click a swatch (while open) -> set + collapse.
        # Returns True if the picker consumed the click.
        if self._box_rect and self._box_rect.collidepoint(pos):
            self.expanded = not self.expanded
            return True
        if self.expanded:
            i = swatch_index_at(pos, self._swatch_rects)
            if i is not None:
                self.rgb = colors.hex_to_rgb(SWATCHES[i])
                self.expanded = False
                return True
            self.expanded = False   # clicking elsewhere closes the palette (but doesn't consume)
        return False

    # No-op hooks kept so the dialog's generic mouse handling can call them uniformly.
    def handle_mousemotion(self, pos) -> bool:
        return False

    def handle_mouseup(self):
        pass
