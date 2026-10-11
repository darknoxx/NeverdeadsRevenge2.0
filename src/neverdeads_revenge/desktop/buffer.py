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
from .theme import BACKGROUND, Style

__all__ = ["Cell", "PatternBuffer"]


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
            cell.char = char
            cell.style = style or Style()

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
        image.fill(BACKGROUND)

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
            painter.fillRect(QRect(left, top, width, self.font.cell_h), style.bg)

        if style.reverse:
            painter.fillRect(QRect(left, top, width, self.font.cell_h), style.fg)
            painter.setPen(style.bg if style.bg is not None else BACKGROUND)
        else:
            painter.setPen(self._ink(style))

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
        """The colour a glyph is drawn in, with ``dim`` folded in."""
        if not style.dim:
            return style.fg
        # Dim toward the background rather than toward black: the phosphor fades,
        # it does not switch off, and a remembered wall has to stay a wall.
        ink = QColor(style.fg)
        ink.setRed((ink.red() + BACKGROUND.red()) // 2)
        ink.setGreen((ink.green() + BACKGROUND.green()) // 2)
        ink.setBlue((ink.blue() + BACKGROUND.blue()) // 2)
        return ink
