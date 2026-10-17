"""The SDL front end: the same cells, the same face, a different blitter.

The question these hold down is the one the whole port turns on -- *does the game
really come apart from Qt?* -- and it comes in two halves. The first is
measurement: the same typeface at the same size has to give the same cell, or
every layout in the game (all of which counts in cells) lands somewhere else. The
second is that painting needs nothing from the game but cells.

The numbers are the contrast here rather than a comparison in-process, and the
reason is worth writing down because it was chased: pygame and Qt live together
perfectly well -- both orders, in this suite, on this machine. What does not
survive is Qt's *font database* being asked to load a face before a
``QGuiApplication`` exists, which is a mistake in the caller and not a war
between toolkits.

The comparison still belongs in two processes (see ``tools/sdl_probe.py`` and the
Qt half beside it) for a duller reason: each wants its own toolkit's idea of a
cell, and a test that imports both to check one number has to keep both alive to
say one sentence.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.desktop.pattern import PatternBuffer
from neverdeads_revenge.desktop.theme import BACKGROUND, Style, parse_style

FONT = "src/neverdeads_revenge/desktop/fonts/DejaVuSansMono.ttf"


def _sdl():
    """The SDL pieces, imported and initialised only when a test wants them."""
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    # The full init, because a Surface needs more of SDL than freetype alone
    # brings up. It is also the thing that fights with Qt's font database when
    # SDL gets there first -- see the note at the top of this file.
    pygame.init()
    from neverdeads_revenge.sdl_front.font import SdlFont
    from neverdeads_revenge.sdl_front.paint import paint

    return SdlFont(FONT), paint


def test_the_sdl_cell_is_the_cell_the_qt_build_has():
    """Ten by twenty, and the number is the whole port.

    The game lays every panel out in cells and never in pixels, which is what
    makes a second front end possible at all -- and it is only true while the
    face measures the same on both sides. Measured against the Qt build:
    ``QFontMetrics`` gives 10x20 at pixel size 16, and SDL_ttf gives an advance
    of 10.0 and a line height of 19 at 16 points and 72 dpi, which is 10x20 once
    the extra pixel that keeps a descender inside the cell is added.

    If this fails, the layout has moved and *every* screen needs to be looked at.
    """
    font, _ = _sdl()
    assert (font.cell_w, font.cell_h) == (10, 20), (
        "the SDL face does not measure what the Qt build measures"
    )
    assert font.ascent == 15, "the baseline moved, and everything sits on it"


def test_a_grid_of_cells_paints_where_the_cells_are():
    """Painting needs a buffer and a font, and nothing else from the game.

    Checked as *facts about the picture* rather than against the Qt one: pygame
    and Qt cannot both be initialised in one process, and a test that needs them
    to be is a test that cannot run. The colour of a pixel where a panel was
    drawn and the colour of one where a letter was is what the painter promised,
    and that is what is asked.
    """
    font, paint = _sdl()
    pygame = __import__("pygame")

    grid = PatternBuffer(8, 3)
    grid.put(0, 0, "#", parse_style("red"))
    panel = Style(fg=parse_style("green").fg, bg=parse_style("#123456").fg)
    grid.fill_row(1, " ", panel)
    grid.text(0, 2, "ab", parse_style("bold white"))

    surface = paint(grid, font)

    assert surface.get_size() == (80, 60), "the picture is not cells times pixels"

    # The wall is *in* its cell and not on its corner: a glyph is drawn inside
    # the ten by twenty square, and a test that read the square's own top-left
    # pixel would be reading the dungeon behind it.
    wall = [
        surface.get_at((x, y))
        for y in range(0, font.cell_h)
        for x in range(0, font.cell_w)
    ]
    assert any((one.r, one.g, one.b) == (170, 0, 0) for one in wall), (
        "the wall was not drawn in its own colour"
    )

    # A panel is opaque, and it is opaque *behind* the letters on it: that is the
    # rule the whole menu system is built on, and it is the painter's to keep.
    inside = surface.get_at((40, 25))
    assert (inside.r, inside.g, inside.b) == (0x12, 0x34, 0x56), (
        f"the panel did not fill its row: {inside}"
    )

    # And a space writes nothing, which is what two thousand of them a frame
    # depend on.
    empty = surface.get_at((70, 25))
    assert (empty.r, empty.g, empty.b) == (0x12, 0x34, 0x56), (
        "an empty cell wrote over the panel it was standing on"
    )
    # And the row of text drew its own letters, in the colour they were given.
    text_row = [
        surface.get_at((x, y))
        for y in range(40, 60)
        for x in range(0, 20)
    ]
    white = parse_style("bold white").fg
    assert any((one.r, one.g, one.b) == tuple(white) for one in text_row), (
        f"the bold white letters were not drawn: {white}"
    )


def test_the_same_screen_renders_without_qt_in_the_room():
    """The title screen, drawn with a stub app and nothing else.

    The screen reads exactly two things off the application -- whether there is a
    run to continue, and the best score -- and everything else it wants is the
    buffer in its hand. That is the measurement worth having: a screen whose
    whole interface is a buffer and a key name is a screen that can be shown by
    anything, which is what the probe in ``tools/sdl_probe.py`` writes out.
    """
    from neverdeads_revenge.desktop.screens.title import TitleScreen

    font, paint = _sdl()

    class Stub:
        class Progress:
            best_score = 1234

        progress = Progress()

        def has_saved_run(self) -> bool:
            return True

    grid = PatternBuffer(96, 27)
    TitleScreen().draw(grid, Stub())
    surface = paint(grid, font)

    inked = sum(
        1
        for y in range(0, surface.get_height(), 4)
        for x in range(0, surface.get_width(), 4)
        if surface.get_at((x, y))[:3] != tuple(BACKGROUND)
    )
    assert inked > 200, f"the title screen came out nearly empty: {inked} cells of ink"
