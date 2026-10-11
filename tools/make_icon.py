#!/usr/bin/env python3
"""Draw the application icon.

The N is taken from the game's own block font in ``ui/screens/title.py``, so the
icon cannot drift from the title screen: change the letterform once and both
follow. Everything else here is geometry.

    python3 tools/make_icon.py                  # the skull (default)
    python3 tools/make_icon.py --motive a       # the block N instead
    python3 tools/make_icon.py --png 256 48     # also rasterise, for previews

The rasteriser is here because an icon is judged by eye and this repository has
no SVG renderer to lean on. It is thirty lines of stdlib zlib and it is only
used by ``--png``.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from neverdeads_revenge.ui.blocks import BLOCK  # noqa: E402

#: The icon is authored in a 256-unit square and scaled by the consumer.
SIZE = 256

BACKGROUND = "#121212"
RIM = "#2a2a2a"
PURPLE = "#a855f7"
CYAN = "#00e5ff"
BONE = "#e8e4dc"

#: A 16x16 skull. ``#`` bone, ``o`` a glowing socket, ``.`` nothing.
#:
#: Drawn on a grid rather than as curves because the whole game is blocks: the
#: title screen is a five-by-five block font and the map is one character per
#: cell. A smooth vector skull would be the only soft edge in the project.
SKULL = (
    "....########....",
    "..############..",
    ".##############.",
    "################",
    "################",
    "##ooo######ooo##",
    "##ooo######ooo##",
    "##ooo######ooo##",
    "################",
    "#######..#######",
    "#######..#######",
    ".##############.",
    "..############..",
    "..############..",
    "..##.#.##.#.##..",
    "..##.#.##.#.##..",
)

#: Width of the skull grid, in pixels of sprite.
SKULL_CELLS = 16

MOTIVES = ("skull", "a", "b", "c")


def sprite_rects(
    sprite: tuple[str, ...], char: str, cell: float, ox: float, oy: float
) -> list[tuple[float, float, float, float]]:
    """Filled rectangles for one sprite character, merging runs along each row.

    Merging matters: a rectangle per pixel would be a two-hundred-line SVG for a
    sixteen-by-sixteen drawing, and the whole point of shipping the generator
    rather than the drawing is that the file stays readable.
    """
    rects = []
    for row, line in enumerate(sprite):
        col = 0
        while col < len(line):
            if line[col] != char:
                col += 1
                continue
            start = col
            while col < len(line) and line[col] == char:
                col += 1
            rects.append(
                (ox + start * cell, oy + row * cell, (col - start) * cell, cell)
            )
    return rects


def blocks_n(cell: float, ox: float, oy: float) -> list[tuple[float, float, float, float]]:
    """The letter N as filled rectangles, one per ``█`` in the block font."""
    rects = []
    for row, line in enumerate(BLOCK["N"]):
        for col, char in enumerate(line):
            if char == "█":
                rects.append((ox + col * cell, oy + row * cell, cell, cell))
    return rects


def geometry(motive: str) -> tuple[list[tuple[str, list]], list[tuple]]:
    """``(fills, shapes)`` for one motive, in the 256-unit square.

    ``fills`` are painted in order, so a later one covers an earlier one.
    """
    fills: list[tuple[str, list]] = []
    shapes: list[tuple] = []

    if motive == "skull":
        cell = 13
        span = cell * SKULL_CELLS
        offset = (SIZE - span) / 2
        fills.append((BONE, sprite_rects(SKULL, "#", cell, offset, offset)))
        fills.append((PURPLE, sprite_rects(SKULL, "o", cell, offset, offset)))

    if motive in ("a", "b"):
        cell = 30 if motive == "a" else 26
        span = cell * 5
        offset = (SIZE - span) / 2
        fills.append((PURPLE, blocks_n(cell, offset, offset)))
        if motive == "b":
            shapes.append(("line", 150, 232, 236, 150, 14))

    if motive == "c":
        shapes.append(("ring", 88, 88, 30, 26))
        shapes.append(("ring", 168, 168, 30, 26))
        shapes.append(("line", 58, 198, 198, 58, 26))

    return fills, shapes


def to_svg(motive: str) -> str:
    fills, shapes = geometry(motive)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}"'
        f' width="{SIZE}" height="{SIZE}">',
        "  <title>Neverdead's Revenge</title>",
        f'  <rect x="8" y="8" width="240" height="240" rx="52" fill="{BACKGROUND}"/>',
        f'  <rect x="9.5" y="9.5" width="237" height="237" rx="50.5"'
        f' fill="none" stroke="{RIM}" stroke-width="3"/>',
    ]
    for colour, rects in fills:
        for x, y, w, h in rects:
            parts.append(
                f'  <rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" fill="{colour}"/>'
            )
    for shape in shapes:
        if shape[0] == "line":
            _, ax, ay, bx, by, width = shape
            parts.append(
                f'  <line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}"'
                f' stroke="{CYAN}" stroke-width="{width}" stroke-linecap="round"/>'
            )
        else:
            _, cx, cy, radius, width = shape
            parts.append(
                f'  <circle cx="{cx}" cy="{cy}" r="{radius}"'
                f' fill="none" stroke="{CYAN}" stroke-width="{width}"/>'
            )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# -- optional rasteriser, for looking at the result -------------------------


def _rounded_rect(x, y, x0, y0, x1, y1, r) -> bool:
    if not (x0 <= x < x1 and y0 <= y < y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _segment(x, y, ax, ay, bx, by, half) -> bool:
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length))
    return (x - (ax + t * dx)) ** 2 + (y - (ay + t * dy)) ** 2 <= half * half


def _ring(x, y, cx, cy, radius, half) -> bool:
    d2 = (x - cx) ** 2 + (y - cy) ** 2
    return (radius - half) ** 2 <= d2 <= (radius + half) ** 2


def rasterise(motive: str, size: int, supersample: int = 4) -> bytearray:
    hi = size * supersample
    k = hi / SIZE
    fills, shapes = geometry(motive)
    palette = {
        BONE: (232, 228, 220, 255),
        PURPLE: (168, 85, 247, 255),
        CYAN: (0, 229, 255, 255),
    }

    buf = bytearray(hi * hi * 4)
    for y in range(hi):
        for x in range(hi):
            colour = (0, 0, 0, 0)
            if _rounded_rect(x, y, 8 * k, 8 * k, 248 * k, 248 * k, 52 * k):
                colour = (18, 18, 18, 255)
                if not _rounded_rect(x, y, 11 * k, 11 * k, 245 * k, 245 * k, 49 * k):
                    colour = (42, 42, 42, 255)
            for fill_colour, rects in fills:
                for rx, ry, rw, rh in rects:
                    if rx * k <= x < (rx + rw) * k and ry * k <= y < (ry + rh) * k:
                        colour = palette[fill_colour]
            for shape in shapes:
                hit = False
                if shape[0] == "line":
                    _, ax, ay, bx, by, width = shape
                    hit = _segment(x, y, ax * k, ay * k, bx * k, by * k, width * k / 2)
                else:
                    _, cx, cy, radius, width = shape
                    hit = _ring(x, y, cx * k, cy * k, radius * k, width * k / 2)
                if hit:
                    colour = (0, 229, 255, 255)
            off = (y * hi + x) * 4
            buf[off : off + 4] = bytes(colour)

    out = bytearray(size * size * 4)
    n = supersample * supersample
    for y in range(size):
        for x in range(size):
            r = g = b = a = 0
            for dy in range(supersample):
                for dx in range(supersample):
                    off = ((y * supersample + dy) * hi + (x * supersample + dx)) * 4
                    r += buf[off]
                    g += buf[off + 1]
                    b += buf[off + 2]
                    a += buf[off + 3]
            off = (y * size + x) * 4
            out[off : off + 4] = bytes((r // n, g // n, b // n, a // n))
    return out


def write_png(path: Path, size: int, rgba: bytearray) -> None:
    raw = b"".join(
        b"\x00" + bytes(rgba[y * size * 4 : (y + 1) * size * 4]) for y in range(size)
    )

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--motive", choices=MOTIVES, default="skull")
    parser.add_argument("--out", type=Path, default=ROOT / "assets")
    parser.add_argument(
        "--png", type=int, nargs="*", default=None, metavar="SIZE",
        help="also write PNGs at these sizes, for looking at",
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    svg_path = args.out / "neverdeads-revenge.svg"
    svg_path.write_text(to_svg(args.motive))
    print(f"wrote {svg_path}")

    if args.png is not None:
        for size in args.png or [256, 48]:
            png_path = args.out / f"neverdeads-revenge-{size}.png"
            write_png(png_path, size, rasterise(args.motive, size))
            print(f"wrote {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
