"""The pattern buffer, painted by Qt.

The cells themselves are in :mod:`~neverdeads_revenge.desktop.pattern` -- they
are the game's alphabet and they do not belong to a GUI toolkit. This is the
*other* half: the painter that turns them into a ``QImage``, which is what the
CRT shader is then handed.

It is a subclass rather than a second class, so every screen that already holds a
``PatternBuffer`` keeps working and a front end that is not Qt can hold the grid
without dragging this in behind it.
"""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter

from .font import BitmapFont
from .pattern import Cell, PatternBuffer as Grid
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


class PatternBuffer(Grid):
    """The grid, and the Qt painter that turns it into a :class:`QImage`."""

    def render(self) -> QImage:
        """Paint the whole grid into an image at one pixel per font pixel."""
        font = self.font or BitmapFont()
        image = QImage(
            self.cols * font.cell_w,
            self.rows * font.cell_h,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(qcolour(BACKGROUND))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        for x, y, run in self.runs():
            self._draw_run(painter, x, y, run)
        painter.end()
        return image

    def _draw_run(self, painter: QPainter, x: int, y: int, run: list[Cell]) -> None:
        font = self.font or BitmapFont()
        style = run[0].style
        left = x * font.cell_w
        top = y * font.cell_h
        width = len(run) * font.cell_w

        # A cell's own background, if it has one. This is how a menu panel is
        # opaque: the box fills its inside with a colour before anything is
        # written on it, so the dungeon cannot show through.
        if style.bg is not None:
            painter.fillRect(QRect(left, top, width, font.cell_h), qcolour(style.bg))

        if style.reverse:
            painter.fillRect(QRect(left, top, width, font.cell_h), qcolour(style.fg))
            painter.setPen(
                qcolour(style.bg) if style.bg is not None else qcolour(BACKGROUND)
            )
        else:
            painter.setPen(self._ink(style))

        if style.italic:
            painter.setFont(font.bold_italic if style.bold else font.italic)
        else:
            painter.setFont(font.bold if style.bold else font.normal)
        text = "".join(cell.char for cell in run)
        # ``TextDontClip`` off, and a rect one row taller than the cell: a glyph
        # with a descender hangs below the baseline, and clipping it to the cell
        # shaves the tail off a ``g`` on the one line the player is reading.
        painter.drawText(QRect(left, top, width, font.cell_h + 4), 0, text)

    @staticmethod
    def _ink(style: Style) -> QColor:
        """The colour a glyph is drawn in, with ``dim`` folded in.

        The dimming itself is the colour's own business now (see
        ``Colour.dimmed``), because it is a fact about the style rather than
        about Qt -- and the front end that is not Qt needs it just as much.
        """
        return qcolour(style.fg.dimmed() if style.dim else style.fg)
