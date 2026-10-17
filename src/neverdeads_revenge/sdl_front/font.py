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
"""

from __future__ import annotations

from pygame import freetype
from pygame import SRCALPHA, Surface

from ..desktop.theme import BACKGROUND, Colour

__all__ = ["SdlFont"]


class SdlFont:
    """A monospaced face and the cell it comes to."""

    def __init__(self, path: str, pixel_size: int = 16) -> None:
        self.path = path
        self.pixel_size = pixel_size
        self.faces: dict[tuple[bool, bool], freetype.Font] = {}
        self._atlas: dict[tuple, Surface | None] = {}
        face = self._face(False, False)
        # The widest advance, which is what a monospace face answers for every
        # glyph -- Qt measures it the same way, with ``maxWidth`` rather than the
        # width of an M, because the one that cannot lie about a wide glyph is
        # the one to trust.
        self.cell_w = round(face.get_metrics("M")[0][4])
        # Plus the pixel that keeps a descender from being clipped, exactly as
        # `desktop/font.py` adds it: a `g` that loses its tail on the one line a
        # player is reading is the bug this number exists to prevent.
        self.cell_h = round(face.get_sized_height()) + 1
        self.ascent = round(face.get_sized_ascender())

    def _face(self, bold: bool, italic: bool) -> freetype.Font:
        key = (bold, italic)
        if key not in self.faces:
            face = freetype.Font(self.path, self.pixel_size, resolution=72)
            face.origin = True
            face.antialiased = False
            face.strong = bold
            face.oblique = italic
            self.faces[key] = face
        return self.faces[key]

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

        face = self._face(bold, italic)
        image = Surface((self.cell_w, self.cell_h), SRCALPHA)
        if bg is not None:
            image.fill(bg)
        else:
            image.fill((0, 0, 0, 0))
        # A *transparent* background: `bgcolor=None` fills with the face's own
        # idea of paper, which on this machine is grey, and a grid drawn out of
        # grey squares is not a grid. Four zeroes make the glyph's own pixels the
        # only ones with anything in them, which is what a blit wants.
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
        self._atlas[key] = image
        return image
