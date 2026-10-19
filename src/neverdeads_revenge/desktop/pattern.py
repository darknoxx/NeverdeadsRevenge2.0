"""The pattern buffer: the grid of characters the game is drawn into.

Everything above this draws characters into cells; everything below it paints
those cells into a bitmap. The split is the whole reason the CRT pass can be a
single shader -- by the time the picture exists it is a flat image at a known,
tiny resolution, and scaling it by a whole number and laying scanlines over it is
arithmetic rather than a redraw.

A cell is a character and a :class:`~neverdeads_revenge.desktop.theme.Style`.

**Qt-free on purpose.** This is where the game's alphabet actually lives, and the
alphabet is not a GUI toolkit's business: the Qt painter is a *subclass* of this
grid in :mod:`~neverdeads_revenge.desktop.buffer`, a second front end paints the
same cells with its own blitter, and neither of them owns the cells. That is why
the module carries the run-splitting the renderers want: consecutive cells that
share a style are one run, and a run is what every painter in the world draws
faster than a character at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .theme import Style

__all__ = ["Cell", "PatternBuffer"]


@dataclass(slots=True)
class Cell:
    char: str = " "
    style: Style = Style()


class PatternBuffer:
    """A grid of character cells."""

    def __init__(self, cols: int, rows: int, font=None) -> None:
        #: A hash of what has been *written* into the grid since it was cleared.
        #:
        #: The painter wants to know whether this frame's cells are the same as
        #: the last frame's -- a fight's panels and log are still between its
        #: breaths, and repainting them costs a megapixel of blending on a machine
        #: without SIMD blitters. It is kept here, as the writes happen, because a
        #: pass over the grid to find out afterwards is the cost it exists to avoid.
        self.signature = 0
        #: And the same signature per *row*, because a changed frame is almost
        #: always a changed line: a cursor in a menu, a line arriving in the log.
        #: Repainting the row that moved is a hundredth of the cost of repainting
        #: the megapixel around it.
        self.row_signature: list[int] = [0] * rows
        self.cols = cols
        self.rows = rows
        #: Kept rather than used: the grid is measured in cells and does not
        #: care how wide one is, but a painter wants the font and the caller has
        #: already got it in hand.
        self.font = font
        self.cells: list[list[Cell]] = [
            [Cell() for _ in range(cols)] for _ in range(rows)
        ]

    # -- writing ------------------------------------------------------------
    def clear(self, char: str = " ", style: Style | None = None) -> None:
        # One style for the whole grid and not one per cell: a ``Style`` is frozen,
        # so sharing it is safe, and a frame that builds two thousand six hundred
        # of them is a frame spending a millisecond and a half writing the same
        # blank. (Measured: 1.43 ms a frame, and 0.03 ms this way.)
        blank = style or Style()
        self.signature = 0
        self.row_signature = [0] * self.rows
        for row in self.cells:
            for cell in row:
                cell.char = char
                cell.style = blank

    def put(self, x: int, y: int, char: str, style: Style | None = None) -> None:
        if 0 <= x < self.cols and 0 <= y < self.rows:
            cell = self.cells[y][x]
            new = style or Style()
            if new.bg is None and cell.style.bg is not None:
                # The cell already sits on a panel. Writing a *word* onto it does
                # not lift the panel out from under the writing: the text keeps
                # the background the square had, which is why the words in a
                # menu read on the panel and not on a stripe of black.
                new = Style(
                    fg=new.fg, bg=cell.style.bg, bold=new.bold, dim=new.dim,
                    reverse=new.reverse, italic=new.italic,
                )
            cell.char = char
            cell.style = new
            # Order matters and does not have to be stable across frames: the
            # screens draw in the same order every time, so the same content
            # writes the same signature.
            stamp = hash((char, new))
            self.signature = (self.signature * 31 + stamp) & 0xFFFFFFFF
            self.row_signature[y] = (self.row_signature[y] * 31 + stamp) & 0xFFFFFFFF

    def text(self, x: int, y: int, string: str, style: Style | None = None) -> int:
        """Write ``string`` starting at ``x``. Returns the next free column.

        Characters past the right edge are dropped rather than wrapped: every
        line in this game is positioned by hand, and a wrap is a line that lands
        somewhere the screen did not ask for.
        """
        style = style or Style()
        for offset, char in enumerate(string):
            self.put(x + offset, y, char, style)
        return x + len(string)

    def fill_row(self, y: int, char: str, style: Style | None = None) -> None:
        for x in range(self.cols):
            self.put(x, y, char, style)

    # -- reading ------------------------------------------------------------
    def runs(self) -> Iterator[tuple[int, int, list[Cell]]]:
        """Every row as runs of same-styled cells: ``(x, y, the run)``.

        The unit both painters draw in. Qt draws a string faster than a string
        of one character many times, and a blitter draws one strip of a texture
        faster than the same strip in pieces -- so the run is the thing worth
        finding once rather than twice.
        """
        for y, row in enumerate(self.cells):
            x = 0
            while x < self.cols:
                style = row[x].style
                end = x + 1
                while end < self.cols and row[end].style == style:
                    end += 1
                yield x, y, row[x:end]
                x = end
