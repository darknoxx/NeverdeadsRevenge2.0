"""The pattern buffer: the grid of characters the game is drawn into.

Everything above this draws characters into cells; everything below it paints
those cells into a bitmap. The split is the whole reason the CRT pass can be a
single shader -- by the time the picture exists it is a flat image at a known,
tiny resolution, and scaling it by a whole number and laying scanlines over it is
arithmetic rather than a redraw.

A cell is a character and a :class:`~neverdeads_revenge.desktop.theme.Style`.
Consecutive cells that share a style are drawn as one run, because Qt draws a
string faster than it draws a string of one character many times, and a sidebar
line is a run.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter

from .font import BitmapFont
from .theme import BACKGROUND, Colour, Style

__all__ = ["Cell", "PatternBuffer", "qcolour"]


def qcolour(colour) -> QColor:
    """A colour as the one thing Qt paints with, whatever kind it arrived as.

    Forgiving on purpose. The theme's own `Colour`, a ``QColor`` a painter made
    for itself, or the hex string a constant was written as all mean the same
    thing to Qt -- and a seam that has to be told which is which is a seam that
    gets told wrong once, in a fight, and crashes. So this takes all three and
    answers the one question the painter asked.
    """
    if isinstance(colour, QColor):
        return colour
    if isinstance(colour, Colour):
        return QColor(colour.r, colour.g, colour.b)
    if isinstance(colour, str):
        parsed = Colour.parse(colour)
        if parsed is not None:
            return QColor(parsed.r, parsed.g, parsed.b)
    return QColor(colour)


@dataclass(slots=True)
class Cell:
    char: str = " "
    style: Style = Style()


class PatternBuffer:
    """A grid of character cells, rendered to a :class:`QImage`."""

    def __init__(self, cols: int, rows: int, font: BitmapFont) -> None:
        self.cols = cols
        self.rows = rows
        self.font = font
        self.cells: list[list[Cell]] = [
            [Cell() for _ in range(cols)] for _ in range(rows)
        ]

    # -- writing ------------------------------------------------------------
    def clear(self, char: str = " ", style: Style | None = None) -> None:
        for row in self.cells:
            for cell in row:
                cell.char = char
                cell.style = style or Style()

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

    # -- rendering ----------------------------------------------------------
    def render(self) -> QImage:
        """Paint the whole grid into an image at one pixel per font pixel."""
        font = self.font
        image = QImage(
            self.cols * font.cell_w,
            self.rows * font.cell_h,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(qcolour(BACKGROUND))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        for y, row in enumerate(self.cells):
            x = 0
            while x < self.cols:
                cell = row[x]
                end = x + 1
                while end < self.cols and row[end].style == cell.style:
                    end += 1
                self._draw_run(painter, x, y, row[x:end])
                x = end
        painter.end()
        return image

    def _draw_run(self, painter: QPainter, x: int, y: int, run: list[Cell]) -> None:
        style = run[0].style
        left = x * self.font.cell_w
        top = y * self.font.cell_h
        width = len(run) * self.font.cell_w

        # A cell's own background, if it has one. This is how a menu panel is
        # opaque: the box fills its inside with a colour before anything is
        # written on it, so the dungeon cannot show through.
        if style.bg is not None:
            painter.fillRect(
                QRect(left, top, width, self.font.cell_h), qcolour(style.bg)
            )

        if style.reverse:
            painter.fillRect(
                QRect(left, top, width, self.font.cell_h), qcolour(style.fg)
            )
            painter.setPen(
                qcolour(style.bg) if style.bg is not None else qcolour(BACKGROUND)
            )
        else:
            painter.setPen(self._ink(style))

        if style.italic:
            painter.setFont(
                self.font.bold_italic if style.bold else self.font.italic
            )
        else:
            painter.setFont(self.font.bold if style.bold else self.font.normal)
        text = "".join(cell.char for cell in run)
        # ``TextDontClip`` off, and a rect one row taller than the cell: a glyph
        # with a descender hangs below the baseline, and clipping it to the cell
        # shaves the tail off a ``g`` on the one line the player is reading.
        painter.drawText(
            QRect(left, top, width, self.font.cell_h + 4),
            0,
            text,
        )

    @staticmethod
    def _ink(style: Style) -> QColor:
        """The colour a glyph is drawn in, with ``dim`` folded in.

        The dimming itself is the colour's own business now (see
        ``Colour.dimmed``), because it is a fact about the style rather than
        about Qt -- and the front end that is not Qt needs it just as much.
        """
        return qcolour(style.fg.dimmed() if style.dim else style.fg)
