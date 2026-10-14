"""Turn the game's SVG mark into the .ico a Windows build needs.

Run it once with the repository's own virtualenv, and commit the result:

    ./.venv/bin/python packaging/windows/make_icon.py

An ``.ico`` is a Windows concern; the rest of the project ships an SVG. Qt draws
the SVG (it is already a dependency) and the container is written here -- an ICO
is a small header and then the images, and Vista and later read PNGs straight out
of it, so no image library is needed.
"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

#: The sizes Windows asks for: the taskbar, the window, the alt-tab, the shell.
SIZES = (16, 24, 32, 48, 64, 128, 256)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SVG = ROOT / "assets" / "neverdeads-revenge-2.svg"
OUT = HERE / "neverdeads_revenge.ico"


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


def pack(images: list[tuple[int, bytes]]) -> bytes:
    """A PNG-in-ICO file: a header, one entry per image, then the PNGs."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    blobs = b""
    for size, png in images:
        dimension = 0 if size >= 256 else size  # 0 means 256 in an ICO
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), offset
        )
        offset += len(png)
        blobs += png
    return header + entries + blobs


def main() -> int:
    svg_bytes = SVG.read_bytes()
    images = [(size, render(svg_bytes, size)) for size in SIZES]
    OUT.write_bytes(pack(images))
    print(f"wrote {OUT.name} ({OUT.stat().st_size} bytes, {len(images)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
