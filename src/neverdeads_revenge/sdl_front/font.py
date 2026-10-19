"""The same face, measured the same way, drawn by SDL.

The game ships its own typeface, so this is a *measurement* rather than a
choice: the same ``DejaVuSansMono.ttf`` at the same pixel size has to come out
as the same cell the Qt build has, or every layout in the game -- all of which
counts in cells -- lands somewhere else.

It does. Measured: Qt's ``QFontMetrics`` gives a 10x20 cell at pixel size 16, and
``SDL_ttf`` gives an advance of 10.0 and a line height of 19 at 16 points and 72
dpi, which is 10x20 once the extra pixel that keeps a descender inside the cell
is added. The numbers are written down here rather than discovered at runtime,
and a test holds them against Qt's.

Everything it draws is *cached by what it is drawing* -- character, colour, the
four flags -- which is the glyph atlas every 2D toolkit ends up building, done
the small way: one surface per distinct thing on the screen, then a blit.

**Two renderers, one face.** ``pygame.freetype`` is the one this was written
against, and it is the one a desktop gets -- but it is an *optional module* in
pygame, and the Android build leaves it out: pygame-ce's own
``buildconfig/Setup.Android.SDL2.in`` has the ``_freetype`` line commented out, so
a handheld has ``pygame.font`` (SDL_ttf) and nothing else. Since the module
imports it at the top of the file, a build without it does not lose the face --
it fails to start at all, which is how this was found out.

So there are two ways to draw the same thing, and the pair of them is held
together by a test rather than by hope: **both renderers have to measure the same
cell for the same face at the same size.** The layouts count cells, so a renderer
that measured differently would move every panel in the game, and that is a thing
to notice on a laptop rather than on a handheld.
"""

from __future__ import annotations

import os

from pygame import SRCALPHA, Surface

from ..desktop.theme import BACKGROUND, Colour

__all__ = ["SdlFont", "RENDERERS", "choose_renderer"]

#: The two ways in. ``freetype`` is preferred -- it is what the numbers above were
#: measured with -- and ``sdl_ttf`` is what a build without it falls back to.
RENDERERS = ("freetype", "sdl_ttf")

#: The real faces beside the regular one, for the renderer that cannot embolden a
#: font itself. Named the way DejaVu names them, and used when they are there: a
#: drawn Bold is a better Bold than a thickened Regular.
_STYLES: dict[tuple[bool, bool], str] = {
    (True, False): "-Bold",
    (False, True): "-Oblique",
    (True, True): "-BoldOblique",
}


def choose_renderer(name: str | None = None) -> str:
    """Which renderer to use: asked for, or the best this pygame has.

    ``pygame.freetype`` is imported *here* and not at the top of the module,
    because the import failing is the thing being guarded against: on a build
    without it, the module still imports and the game still has a face.
    """
    if name is not None:
        return name
    try:
        from pygame import freetype  # noqa: F401
    except ImportError:
        return "sdl_ttf"
    return "freetype"


class SdlFont:
    """A monospaced face and the cell it comes to."""

    def __init__(
        self, path: str, pixel_size: int = 16, *, renderer: str | None = None
    ) -> None:
        self.path = path
        self.pixel_size = pixel_size
        #: Which of the two drew this face. Read by the report and by tests;
        #: nothing else in the game asks, because both draw the same cells.
        self.renderer = choose_renderer(renderer)
        self.faces: dict[tuple[bool, bool], object] = {}
        self._atlas: dict[tuple, Surface | None] = {}
        face = self._face(False, False)
        if self.renderer == "freetype":
            # The widest advance, which is what a monospace face answers for every
            # glyph -- Qt measures it the same way, with ``maxWidth`` rather than
            # the width of an M, because the one that cannot lie about a wide glyph
            # is the one to trust.
            self.cell_w = round(face.get_metrics("M")[0][4])
            # Plus the pixel that keeps a descender from being clipped, exactly as
            # `desktop/font.py` adds it: a `g` that loses its tail on the one line
            # a player is reading is the bug this number exists to prevent.
            self.cell_h = round(face.get_sized_height()) + 1
            self.ascent = round(face.get_sized_ascender())
        else:
            # The same two questions asked of SDL_ttf: the advance of a capital M
            # out of its own metrics, and the height it gives a line, plus the
            # pixel that keeps a descender inside the cell.
            #
            # The two rasterizers round their vertical metrics differently at some
            # sizes -- freetype says 31 for a face SDL_ttf calls 32 at twenty-seven
            # pixels -- so the cells can differ by a row *there*, and a test says
            # so rather than pretending otherwise. At the two sizes this game
            # actually uses, sixteen and thirty-two, they agree exactly.
            self.cell_w = round(face.metrics("M")[0][4])
            self.cell_h = round(face.get_linesize()) + 1
            self.ascent = round(face.get_ascent())

    # -- the faces -----------------------------------------------------------
    def _face(self, bold: bool, italic: bool):
        key = (bold, italic)
        if key not in self.faces:
            self.faces[key] = (
                self._face_freetype(bold, italic)
                if self.renderer == "freetype"
                else self._face_sdl_ttf(bold, italic)
            )
        return self.faces[key]

    def _face_freetype(self, bold: bool, italic: bool):
        from pygame import freetype

        face = freetype.Font(self.path, self.pixel_size, resolution=72)
        face.origin = True
        face.antialiased = False
        face.strong = bold
        face.oblique = italic
        return face

    def _face_sdl_ttf(self, bold: bool, italic: bool):
        """The real Bold/Oblique face when it is beside the regular one.

        SDL_ttf can thicken and lean a font itself, and that is the fallback --
        but DejaVu ships the drawn ones, this repository carries all four, and a
        drawn Bold is a better Bold than a thickened Regular. So the file is
        preferred and the flag is only what a machine with one file gets.
        """
        from pygame import font as sdl_ttf

        if not sdl_ttf.get_init():
            sdl_ttf.init()
        stem, ext = os.path.splitext(self.path)
        styled = f"{stem}{_STYLES[(bold, italic)]}{ext}" if (bold or italic) else ""
        if styled and os.path.exists(styled):
            return sdl_ttf.Font(styled, self.pixel_size)
        face = sdl_ttf.Font(self.path, self.pixel_size)
        face.set_bold(bold)
        face.set_italic(italic)
        return face

    # -- the glyphs ----------------------------------------------------------
    def glyph(
        self,
        char: str,
        fg: Colour,
        bg: Colour | None = None,
        *,
        bold: bool = False,
        dim: bool = False,
        reverse: bool = False,
        italic: bool = False,
    ) -> Surface | None:
        """One cell's worth of picture, made once and remembered.

        The ink is the *style's* own colour with dim folded in, which is the
        theme's business and not a renderer's -- see ``Colour.dimmed``. Reverse
        is the two colours swapped, and the background is painted here rather
        than by the caller so that a panel's letters and a panel's fill cannot
        be told apart from the outside.
        """
        ink = fg.dimmed() if dim else fg
        if reverse:
            ink, bg = (bg if bg is not None else BACKGROUND), fg
        key = (char, ink, bg, bold, italic)
        if key in self._atlas:
            return self._atlas[key]

        image = Surface((self.cell_w, self.cell_h), SRCALPHA)
        # A *transparent* background: a grid drawn out of grey squares is not a
        # grid. Four zeroes make the glyph's own pixels the only ones with
        # anything in them, which is what a blit wants.
        image.fill(bg if bg is not None else (0, 0, 0, 0))
        if self.renderer == "freetype":
            self._blit_freetype(image, char, ink, bold, italic)
        else:
            self._blit_sdl_ttf(image, char, ink, bg, bold, italic)
        self._atlas[key] = image
        return image

    def _blit_freetype(self, image, char, ink, bold, italic) -> None:
        face = self._face(bold, italic)
        # ``bgcolor=None`` would fill with the face's own idea of paper, so the
        # glyph is asked for with four zeroes as its background -- the same
        # transparent cell the image was filled with.
        glyph, rect = face.render(char, ink, (0, 0, 0, 0))
        # The pen sits on the baseline and the cell starts at its top, so the
        # glyph's own box goes where the face says it goes *relative to that
        # pen* -- which is what the rect is for, and why the face was opened
        # with ``origin = True``: the descender of a ``g`` then hangs below the
        # baseline exactly as far as it should, inside the cell that was made a
        # pixel taller to keep it.
        # And the rect runs *upward* from the pen while the cell runs downward
        # from its top, so the offset is the ascender minus it. Measured: a
        # capital M at this size lands on rows 3 to 14 of the twenty, which is
        # exactly where the Qt build puts it.
        image.blit(glyph, (rect.x, self.ascent - rect.y))

    def _blit_sdl_ttf(self, image, char, ink, bg, bold, italic) -> None:
        face = self._face(bold, italic)
        # No antialiasing, for the same reason the freetype face has none: this
        # game's letters are a grid's letters, and a smeared edge is a pixel that
        # belongs to no cell.
        glyph = face.render(char, False, ink, bg if bg is not None else None)
        # SDL_ttf lays a glyph out from the pen itself -- the advance starts at
        # zero and the baseline is the face's own ascent -- so the surface goes
        # down at the cell's top left, which is where the freetype path's
        # arithmetic lands too.
        image.blit(glyph, (0, 0))
