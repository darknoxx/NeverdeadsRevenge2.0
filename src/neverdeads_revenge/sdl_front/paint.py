"""The grid, as a picture, drawn by SDL.

The other half of what ``desktop/buffer.py`` does: same cells, same runs, same
style semantics -- and a picture at the end of it. Nothing here knows about Qt
and nothing in the cells knows about SDL, which is the whole point of the split:
the game's alphabet is one thing and the blitter is another.

The run is the unit, because it is the unit that pays: a run's background is one
``fill``, and a *cell* is one blit of a surface the font made once. There is no
per-character work in this file beyond the loop the grid already needed.
"""

from __future__ import annotations

from pygame import Rect, Surface

from ..desktop.pattern import PatternBuffer
from ..desktop.theme import BACKGROUND, Colour
from .font import SdlFont

__all__ = ["paint"]


def paint(
    grid: PatternBuffer, font: SdlFont, background: Colour = BACKGROUND
) -> Surface:
    """The whole grid, as a surface at one pixel per font pixel."""
    surface = Surface((grid.cols * font.cell_w, grid.rows * font.cell_h))
    surface.fill(background)

    for x, y, run in grid.runs():
        style = run[0].style
        left = x * font.cell_w
        top = y * font.cell_h
        width = len(run) * font.cell_w
        if style.bg is not None:
            # A panel is opaque the same way it is in the Qt build: the box
            # fills its own cells before anything is written on them, so the
            # dungeon cannot show through the menu standing on it.
            surface.fill(style.bg, Rect(left, top, width, font.cell_h))
        for index, cell in enumerate(run):
            if cell.char == " ":
                # Nothing to draw, and a space is the most common character in
                # the game by a wide margin: the atlas would hold a blank
                # surface for it and the blit would write transparent over
                # transparent, for every one of a few thousand cells a frame.
                continue
            glyph = font.glyph(
                cell.char,
                style.fg,
                style.bg,
                bold=style.bold,
                dim=style.dim,
                reverse=style.reverse,
                italic=style.italic,
            )
            if glyph is not None:
                surface.blit(glyph, (left + index * font.cell_w, top))
    return surface
