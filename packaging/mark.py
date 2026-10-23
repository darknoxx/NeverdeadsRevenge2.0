"""The game's SVG mark, drawn at a size, for the icons the builds carry.

Qt is not a runtime dependency any more, and this is not part of the game: it is
a one-off development tool, run from the repository's own virtualenv, and the
images it draws are committed beside the builds that need them. Windows reads an
``.ico`` and Linux wants a ``.png``, so the drawing is here once and the two
scripts differ only in the container they write.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

#: The mark itself, at the top of the repository.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SVG = ROOT / "assets" / "neverdeads-revenge-2.svg"


def render(svg_bytes: bytes, size: int) -> bytes:
    """One size of the mark, as PNG bytes."""
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)  # transparent black
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())
