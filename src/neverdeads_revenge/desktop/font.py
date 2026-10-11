"""The character cell.

The whole look of the game is one grid of fixed cells, so the first thing the
desktop build needs is a font that has a cell: a fixed advance width and a fixed
line height. A monospaced face gives the width for free; the height comes from
its metrics.

Antialiasing is off. That is not nostalgia for its own sake -- a CRT phosphor has
no grey, it is lit or it is not -- and it is also what keeps the pixels honest
once the CRT pass scales them by a whole number. A glyph drawn with soft edges
and then blown up by four is a blur; a glyph drawn as hard pixels and blown up by
four is a character, which is the entire effect.
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontMetrics

__all__ = ["BitmapFont"]

#: Faces tried in order. Every one is monospaced and present on the common
#: desktops; Qt substitutes if none is there, and a substitute monospace still
#: gives the cell the layout needs.
FAMILIES = (
    "DejaVu Sans Mono",
    "Liberation Mono",
    "Noto Sans Mono",
    "Ubuntu Mono",
    "Consolas",
    "Menlo",
    "Courier New",
    "monospace",
)


class BitmapFont:
    """A monospaced font with a measured cell, drawn without antialiasing."""

    def __init__(self, pixel_size: int = 16, family: str | None = None) -> None:
        self.pixel_size = pixel_size
        self.family = family or self._first_available()
        self.normal = self._make(bold=False)
        self.bold = self._make(bold=True)
        self.italic = self._make(bold=False, italic=True)
        self.bold_italic = self._make(bold=True, italic=True)
        metrics = QFontMetrics(self.normal)
        #: Width of one cell. ``maxWidth`` rather than the width of "M": a
        #: monospace face answers the same number for both, and the one that
        #: cannot lie about a wide glyph is the one to trust.
        self.cell_w = max(1, metrics.maxWidth())
        #: Height of one cell, plus a pixel so a descender is not clipped.
        self.cell_h = metrics.height() + 1

    @staticmethod
    def _first_available() -> str:
        from PySide6.QtGui import QFontDatabase

        families = set(QFontDatabase.families())
        for name in FAMILIES:
            if name in families:
                return name
        return FAMILIES[-1]

    def _make(self, bold: bool, italic: bool = False) -> QFont:
        font = QFont(self.family)
        font.setPixelSize(self.pixel_size)
        font.setBold(bold)
        font.setItalic(italic)
        font.setFixedPitch(True)
        font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        return font
