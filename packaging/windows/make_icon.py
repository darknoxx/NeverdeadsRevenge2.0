"""Turn the game's SVG mark into the .ico a Windows build needs.

Run it once with the repository's own virtualenv, and commit the result:

    ./.venv/bin/python packaging/windows/make_icon.py

An ``.ico`` is a Windows concern; the rest of the project ships an SVG. The
drawing lives in ``packaging/mark.py`` and the container is written here -- an
ICO is a small header and then the images, and Vista and later read PNGs
straight out of it, so no image library is needed.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from mark import SVG, render  # noqa: E402 - the path above has to be set first

#: The sizes Windows asks for: the taskbar, the window, the alt-tab, the shell.
SIZES = (16, 24, 32, 48, 64, 128, 256)

OUT = HERE / "neverdeads_revenge.ico"


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
