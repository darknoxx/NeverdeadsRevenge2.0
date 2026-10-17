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

from pygame import SRCALPHA, Rect, Surface

from ..desktop import art
from ..desktop.pattern import PatternBuffer
from ..desktop.theme import BACKGROUND, Colour
from .font import SdlFont

__all__ = ["load", "paint"]

_LOADED: dict[str, Surface | None] = {}


def load(name: str):
    """A piece of art by its path inside the art, read once.

    ``None`` when the sheets have nothing there, and never a crash: the alphabet
    is underneath every picture in this game, so the worst a missing file can do
    is leave a letter standing. (A video mode that is not there is the same kind
    of nothing: a headless run has no display to optimise for, and the picture is
    still right.)
    """
    if name in _LOADED:
        return _LOADED[name]
    import pygame

    path = art.path(name)
    image = None
    if path.exists():
        try:
            image = pygame.image.load(str(path))
            try:
                image = image.convert_alpha()
            except pygame.error:
                pass
        except pygame.error:
            image = None
    _LOADED[name] = image
    return image


def clear() -> None:
    """Forget what has been loaded. For tests, and for nothing else."""
    _LOADED.clear()


def paint(grid: PatternBuffer, font: SdlFont, background=BACKGROUND, rows=None) -> Surface:
    """The whole grid, as a surface at one pixel per font pixel.

    ``background`` is a colour or a *picture*: hand it a surface and the frame is
    drawn on that instead of on flat paper, and every cell that has nothing to say
    lets it show through. That is how a painted room gets behind the panels and
    the log, and it is the same one line either way -- empty cells write nothing,
    which they had to do anyway.

    ``rows`` is ``(first, last)`` in cells and paints *that band only*, as tall as
    the band, for a painter that already has the grid down and needs one part of it
    again on top of the art drawn there since. That is how a fight's menu ends up
    over the figure standing in front of it, and it is why a band can be told to
    have no paper at all: ``background=None`` leaves the cells to speak for
    themselves. A panel's box fills its cells, and a cell a panel does not want
    stays *transparent* -- the room between the boxes is still the room, and the
    hero behind it is still the hero. Given a colour or a picture the band carries
    it like the frame does, shifted by the same amount, so the band is the band.
    """
    first, last = rows if rows is not None else (0, grid.rows)
    surface = Surface(
        (grid.cols * font.cell_w, (last - first) * font.cell_h),
        SRCALPHA if background is None else 0,
    )
    if isinstance(background, Surface):
        surface.blit(background, (0, -first * font.cell_h))
    elif background is not None:
        surface.fill(background)

    for x, y, run in grid.runs():
        if not first <= y < last:
            continue
        style = run[0].style
        left = x * font.cell_w
        top = (y - first) * font.cell_h
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
