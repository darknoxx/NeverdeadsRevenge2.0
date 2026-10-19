"""The face, drawn by either of the two renderers pygame can give it.

The game ships its own typeface, and which *module* draws it is not a choice this
game gets to make: ``pygame.freetype`` is optional, and the Android build leaves it
out -- pygame-ce's own ``buildconfig/Setup.Android.SDL2.in`` comments the
``_freetype`` line out -- so a handheld has SDL_ttf and nothing else.

The layouts count cells, so the thing both renderers have to agree about is the
*cell*. They do, at the two sizes this game uses, and the tests here say where and
why -- rather than pretending two rasterizers are one.
"""

from __future__ import annotations

import os

FONT = "src/neverdeads_revenge/desktop/fonts/DejaVuSansMono.ttf"


def _sdl():
    """SDL, up and initialised, the way the rest of the suite does it."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    pygame.init()
    return pygame


def test_the_face_can_be_drawn_without_freetype_and_lays_out_the_same():
    """The second renderer, and the invariant that makes it safe to have one.

    ``pygame.freetype`` is an optional module and the Android build leaves it out
    -- pygame-ce's own ``Setup.Android.SDL2.in`` comments the ``_freetype`` line
    out -- so a handheld has ``pygame.font`` (SDL_ttf) and nothing else. Since the
    font module imported freetype at the top of the file, that build did not lose
    the face: it failed to start, which is how this was found.

    The layouts count cells, so the thing that has to hold is the *cell*: both
    renderers measure the same one at the two sizes the game uses -- sixteen for
    the desktop and thirty-four for a handheld -- and no further apart than a row
    anywhere else. The two rasterizers round their vertical metrics differently at
    some sizes (freetype calls a face 31 pixels tall where SDL_ttf calls it 32),
    which is a fact about them and not about this game, and it is why the test
    says "the same" exactly where it matters and "within a row" everywhere.
    """
    _sdl()
    from neverdeads_revenge.sdl_front.font import SdlFont

    for pixel_size in (16, 34):
        a = SdlFont(FONT, pixel_size, renderer="freetype")
        b = SdlFont(FONT, pixel_size, renderer="sdl_ttf")
        assert (a.cell_w, a.cell_h) == (b.cell_w, b.cell_h), (
            f"at {pixel_size}px the two renderers disagree about the cell: "
            f"{a.cell_w}x{a.cell_h} vs {b.cell_w}x{b.cell_h}"
        )

    for pixel_size in range(12, 49):
        a = SdlFont(FONT, pixel_size, renderer="freetype")
        b = SdlFont(FONT, pixel_size, renderer="sdl_ttf")
        assert a.cell_w == b.cell_w, "the advance is the same measurement on both"
        assert abs(a.cell_h - b.cell_h) <= 1, (
            f"at {pixel_size}px the two renderers are more than a row apart: "
            f"{a.cell_h} vs {b.cell_h}"
        )


def test_both_renderers_put_ink_on_the_same_cell():
    """A cell's worth of picture from either renderer, and it is a picture.

    The measure that matters here is not "are the pixels identical" -- two
    rasterizers never are, and they do not have to be -- but that a glyph comes
    out *on the cell*: the right size, transparent where there is no ink, and with
    ink where the letter is. A renderer that returned an empty cell would draw a
    screen of nothing and pass every layout test in this file.
    """
    _sdl()
    from neverdeads_revenge.desktop.theme import parse_style
    from neverdeads_revenge.sdl_front.font import SdlFont

    for name in ("freetype", "sdl_ttf"):
        face = SdlFont(FONT, 34, renderer=name)
        cell = face.glyph("M", parse_style("bone").fg)
        assert cell.get_size() == (face.cell_w, face.cell_h), name
        assert cell.get_at((0, 0))[3] == 0, f"{name} painted the cell's corner"
        ink = sum(
            1
            for x in range(cell.get_width())
            for y in range(cell.get_height())
            if cell.get_at((x, y))[3]
        )
        assert ink > 100, f"{name} drew an M with {ink} pixels of ink"


def test_the_sdl_ttf_renderer_prefers_the_drawn_bold_face():
    """The real Bold when it is beside the Regular, and a flag when it is not.

    SDL_ttf can thicken a font itself and DejaVu ships a drawn Bold; this
    repository carries all four faces, so the file is what a machine with the pack
    gets -- and a machine with one file still gets a bold cell rather than a
    crash, which is the part worth holding still.
    """
    import shutil
    import tempfile
    from pathlib import Path

    _sdl()
    from neverdeads_revenge.desktop.theme import parse_style
    from neverdeads_revenge.sdl_front.font import SdlFont

    ink = parse_style("bone").fg

    # One file and no Bold beside it: SDL_ttf's own flag, and still a cell.
    alone = Path(tempfile.mkdtemp()) / "DejaVuSansMono.ttf"
    shutil.copyfile(FONT, alone)
    face = SdlFont(str(alone), 34, renderer="sdl_ttf")
    bold = face.glyph("M", ink, bold=True)
    assert bold is not None and bold.get_size() == (face.cell_w, face.cell_h)

    # The whole pack: the drawn face, which is a different picture of an M.
    with_pack = SdlFont(FONT, 34, renderer="sdl_ttf")
    plain = with_pack.glyph("M", ink)
    drawn = with_pack.glyph("M", ink, bold=True)
    assert drawn is not plain, "the Bold file was not used"
    assert drawn.get_size() == plain.get_size()


