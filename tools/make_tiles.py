#!/usr/bin/env python3
"""Paint the arena's own stone.

The dungeon is an alphabet: a wall is ``#``, a floor is a coloured square, and up
on the map that is the whole look and it works. Down in the arena it stopped
being enough the moment the monsters arrived as *paintings* -- a painted ghoul in
a room made of hashes is a sprite standing in a spreadsheet -- so the room is
painted too, by this file.

Nothing else changed. The walls are still the floor's own edges projected, the
floor is still laid out in the game's cells with a half-tile stagger per row, and
a machine with no art still gets the alphabet underneath: the grid floor and the
``#`` are the fallback, exactly as the *letter* is the fallback for a monster.

    python3 tools/make_tiles.py                   # into the package
    python3 tools/make_tiles.py --out /tmp/x      # somewhere else
    python3 tools/make_tiles.py --zoom 6          # a readable preview, to look at

Everything is generated rather than drawn by hand, and the noise is *seeded*, so
the same code always makes the same bytes -- which is what lets the test suite
regenerate the tiles and fail if the committed ones disagree, the same way it
does for the sounds and the icon.
"""

from __future__ import annotations

import argparse
import random
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Where the stone ships from. Inside the package and not in ``assets/``, for the
#: reason the sounds are: these are read at runtime, so they have to travel with
#: the code.
DEFAULT_OUT = ROOT / "src" / "neverdeads_revenge" / "desktop" / "tiles"

#: The stone, in five shades. Blue-grey, because the floor has always been
#: blue-grey at the hero's feet (``#2c2c36``): the room has to look like the room
#: the sprites were painted for, and every sprite in the game is dark and cold.
DEEP = (0x12, 0x12, 0x1A)  # mortar, joints, the dark between stones
DARK = (0x1E, 0x1E, 0x28)
MID = (0x2A, 0x2A, 0x36)
LIGHT = (0x38, 0x38, 0x48)
EDGE = (0x4A, 0x4A, 0x5C)  # the lit top of a course, where the light falls
#: And the two things that grow on it. Bone is the game's own bone, gone to
#: weather; the moss is the only green in the room, which is why there is not
#: much of it -- a green wall would be a different dungeon.
BONE = (0x9A, 0x94, 0x88)
MOSS = (0x2C, 0x48, 0x33)
LEAF = (0x40, 0x62, 0x45)

#: One cell of the game's font. The floor is laid out in these, so the art is
#: too, and the two agree by construction rather than by a number copied twice.
CELL_W, CELL_H = 10, 20
#: A flagstone: two cells wide and one tall, which is the tile the *grid* floor
#: has always drawn -- two cells, with a half-tile stagger on every row. The art
#: is the same tile with a picture on it.
TILE_W, TILE_H = CELL_W * 2, CELL_H
#: A course of masonry: one cell tall, two flagstones wide.
WALL_W, WALL_H = TILE_W * 2, TILE_H * 2

#: The seed for the speckles. Fixed, because a wall that is a different wall every
#: time it is generated is a wall the test suite cannot check.
NOISE = 7


class Stone:
    """A small square of pixels to paint on and hand back as a PNG."""

    def __init__(self, width: int, height: int, colour: tuple[int, int, int] = DEEP):
        self.width, self.height = width, height
        # Four bytes a pixel and the fourth is opaque: the arena pastes this over
        # the frame it has already drawn, so nothing here is ever see-through.
        self.pixels = bytearray(bytes((*colour, 255)) * (width * height))

    def put(self, x: int, y: int, colour: tuple[int, int, int]) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        at = (y * self.width + x) * 4
        self.pixels[at : at + 3] = bytes(colour)
        self.pixels[at + 3] = 255

    def png(self) -> bytes:
        """PNG bytes, with a row filter of none. No dependencies."""
        stride = self.width * 4
        raw = b"".join(
            b"\x00" + bytes(self.pixels[y * stride : (y + 1) * stride])
            for y in range(self.height)
        )

        def chunk(tag: bytes, data: bytes) -> bytes:
            body = tag + data
            return (
                struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
            )

        header = struct.pack(">IIBBBBB", self.width, self.height, 8, 6, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b"")
        )

    def zoomed(self, factor: int) -> "Stone":
        """The same picture, every pixel a square. For looking at, not for shipping."""
        bigger = Stone(self.width * factor, self.height * factor)
        for y in range(self.height):
            for x in range(self.width):
                at = (y * self.width + x) * 4
                colour = tuple(self.pixels[at : at + 3])
                for dy in range(factor):
                    for dx in range(factor):
                        bigger.put(x * factor + dx, y * factor + dy, colour)
        return bigger


def paint_wall(decor: str = "") -> Stone:
    """Two courses of running bond: bricks with a lit top and mortar under them.

    A *running bond* and not a stack of bricks on top of each other, because
    stacked joints are the one thing that reads as wallpaper instead of
    masonry: every course is laid half a brick along from the one below it.

    ``decor`` is what has grown on this stone since it was laid: ``"bones"`` for
    something that died against it and ``"vines"`` for something that did not.
    Decorated stones are scattered through the wall by the arena rather than
    tiled, because a skull every forty pixels is not a dungeon, it is wallpaper
    with a motif.
    """
    wall = Stone(WALL_W, WALL_H)
    noise = random.Random(NOISE)
    faces = (DARK, MID, LIGHT)
    for course in (0, 1):
        top = course * TILE_H
        # The light falls from above: the top of every course is the brightest
        # line in the picture, and the mortar under it is the darkest.
        for x in range(WALL_W):
            wall.put(x, top, EDGE)
        offset = course * CELL_W
        for brick in range(2):
            start = (brick * TILE_W + offset) % WALL_W
            face = faces[(course + brick) % len(faces)]
            for step in range(TILE_W):
                x = (start + step) % WALL_W
                for y in range(top + 1, top + TILE_H):
                    if y >= top + TILE_H - 4:
                        wall.put(x, y, DEEP)  # the mortar course
                        continue
                    # A brick is not one flat colour: one shade per stone, and a
                    # little grit in it, or a wall of 200 identical bricks reads
                    # as a repeating texture instead of a wall.
                    shade = face
                    if y == top + 1:
                        shade = LIGHT
                    elif noise.random() < 0.12:
                        shade = MID if face is DARK else DARK
                    wall.put(x, y, shade)
            # The joint between two bricks, on the brick's *left* edge.
            for y in range(top + 1, top + TILE_H - 4):
                wall.put(start, y, DEEP)
                wall.put((start + 1) % WALL_W, y, DARK)
    for _ in range(60):
        wall.put(noise.randrange(WALL_W), noise.randrange(WALL_H), DEEP)
    if decor == "bones":
        # High in the bottom course, at the foot of the wall: things die where
        # they are cornered, and they are cornered against the floor.
        _stamp(wall, SKULL, 7, TILE_H + 6)
        for bone in range(2):
            y = TILE_H + 15 + bone * 3
            x0 = 20 + bone * 9
            for step in range(6):
                wall.put(x0 + step, y, BONE)
            wall.put(x0 - 1, y - 1, BONE)
            wall.put(x0 - 1, y, BONE)
            wall.put(x0 + 6, y, BONE)
            wall.put(x0 + 6, y + 1, BONE)
    elif decor == "vines":
        _grow_vine(wall, noise, 6)
        _grow_vine(wall, noise, WALL_W - 9)
    return wall


#: A skull, stamped into the stone. ``#`` bone, ``o`` the dark in the sockets.
#:
#: Drawn on a grid, like everything else in this game: a smooth skull would be
#: the only curve in a project made of blocks.
SKULL = (
    "..####..",
    ".######.",
    "##o##o##",
    "########",
    ".######.",
    "..####..",
    "...##...",
)


def _stamp(wall: Stone, art, x0: int, y0: int) -> None:
    """Put a letter-art picture on the wall, bone for ``#`` and mortar for ``o``."""
    for y, row in enumerate(art):
        for x, glyph in enumerate(row):
            if glyph == "#":
                wall.put(x0 + x, y0 + y, BONE)
            elif glyph == "o":
                wall.put(x0 + x, y0 + y, DEEP)


def _grow_vine(wall: Stone, noise: random.Random, x0: int) -> None:
    """A vine up the wall: two pixels of it, wobbling, with leaves on alternate sides.

    Wobbling and not straight, and thicker at the bottom than the top, because a
    vine is a plant and a plant that grew in a straight line was drawn by a
    computer -- which is exactly what this is, so the wobble has to be *asked*
    for: one step sideways every so often, from a seeded wander.
    """
    x = x0
    for step, y in enumerate(range(WALL_H - 1, 4, -1)):
        drift = noise.choice((-1, 0, 0, 0, 1))
        x = max(2, min(WALL_W - 3, x + drift))
        wall.put(x, y, MOSS)
        if step < (WALL_H - 5) * 0.6:
            wall.put(x + 1, y, MOSS)
        if step and step % 4 == 0:
            side = 2 if (step // 4) % 2 else -2
            wall.put(x + side, y, LEAF)
            wall.put(x + side, y - 1, LEAF)
    for plant in range(3):
        wall.put(x0 + noise.randrange(-1, 2), WALL_H - 1 - plant, MOSS)


def paint_floor(variant: int) -> Stone:
    """One flagstone: a joint along its top and left, a lit bevel, a face.

    Two variants, because the grid floor has always drawn two tones in a checker
    and the arena should not suddenly be a chessboard: the *second* one is the
    darker of the two, and the floor's own fade does the rest.
    """
    floor = Stone(TILE_W, TILE_H)
    noise = random.Random(NOISE + variant)
    face = (MID, DARK)[variant]
    for y in range(TILE_H):
        for x in range(TILE_W):
            if y == 0 or x == 0:
                colour = DEEP
            elif y == 1 or x == 1:
                colour = LIGHT
            elif y >= TILE_H - 2 or x >= TILE_W - 2:
                colour = DARK
            else:
                colour = face
                if noise.random() < 0.10:
                    colour = MID if face is DARK else DARK
            floor.put(x, y, colour)
    return floor


#: What gets written, and what it is called. The list *is* the tile set.
TILES: dict[str, callable] = {
    "wall": paint_wall,
    "wall_bones": lambda: paint_wall("bones"),
    "wall_vines": lambda: paint_wall("vines"),
    "floor_a": lambda: paint_floor(0),
    "floor_b": lambda: paint_floor(1),
}


def write_all(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, paint in TILES.items():
        path = out / f"{name}.png"
        path.write_bytes(paint().png())
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--zoom", type=int, default=0, help="also write a 6x preview, for looking at"
    )
    args = parser.parse_args(argv)

    written = write_all(args.out)
    total = sum(path.stat().st_size for path in written)
    print(f"wrote {len(written)} tiles to {args.out} ({total / 1024:.0f} kB)")
    if args.zoom:
        for name, paint in TILES.items():
            preview = args.out / f"{name}_x{args.zoom}.png"
            preview.write_bytes(paint().zoomed(args.zoom).png())
            print(f"  {preview.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
