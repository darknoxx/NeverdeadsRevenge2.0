#!/usr/bin/env python3
"""Draw the arena's backdrop: dark stone, two torches, and a floor line.

Not a painting and not pretending to be one -- this is *drawn*, stone by stone, by
code. It exists because the room needs a floor at a known line and two flames at
known places, and because a picture that is drawn can be re-drawn when a number
moves: the floor line, the torches, the palette and the whole shape of the room are
constants at the top of this file.

The numbers are the game's, not the picture's:

* **1920x1080** -- the canvas at sixteen by nine is 960x540 game pixels, so this is
  exactly twice it and can be shown without resampling.
* **the floor line at 46%** of the height, which is where the wall meets the floor
  and where the far monsters stand.
* **two torches at 13.5% and 86.5%** across, a quarter down -- *outside* the middle
  band, because the monsters stand at about a quarter and three quarters across and
  a column behind a figure is a figure nobody can read.
* **the middle kept empty and dark**, x 15-85%, y 15-70%: that is where the fight
  happens.
* **the middle is also left plain**: no bright masonry, no props, nothing the eye
  will try to read through a monster. A backdrop earns its keep by being unnoticed.

Run it:

    ./.venv/bin/python tools/make_backdrop.py /tmp/backdrop.png

It is deterministic -- the same numbers and the same seed give the same picture --
so the file can be regenerated and compared.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pygame

WIDTH, HEIGHT = 1920, 1080

#: Where the wall meets the floor, as a share of the height.
FLOOR_AT = 0.46

#: The two torches, across and down.
TORCH_X = (0.135, 0.865)
TORCH_Y = 0.27

#: The two doorways, and the columns beside them.
DOORWAY_X = (0.075, 0.925)
COLUMN_X = (0.185, 0.815)

#: The empty middle: nothing bright inside this box.
CLEAR = (0.15, 0.15, 0.85, 0.70)

#: The palette: cold stone, warm fire, and not much in between.
STONE_DARK = (16, 16, 21)
STONE_MID = (36, 36, 44)
JOINT = (9, 9, 13)
FLOOR_DARK = (14, 14, 18)
FLOOR_LIT = (46, 44, 50)
FIRE_CORE = (255, 246, 214)
FIRE_MID = (255, 176, 72)
FIRE_LOW = (196, 78, 22)

SEED = 20261018


def _lerp(a, b, t: float):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _shade(colour, factor: float):
    return tuple(max(0, min(255, round(channel * factor))) for channel in colour)


def back_wall(surface: pygame.Surface, rng: random.Random) -> None:
    """The wall behind everything: courses of blocks, dark, plainer in the middle.

    The centre is left *boring* on purpose -- it is where the fight happens, and the
    best backdrop for a fight is the one nobody notices.
    """
    horizon = int(HEIGHT * FLOOR_AT)
    course = 42
    for index, top in enumerate(range(-course, horizon + course, course)):
        offset = (index % 2) * 66
        for x in range(-160 + offset, WIDTH + 160, 104):
            tone = rng.uniform(-0.16, 0.13)
            depth = min(1.0, max(0.0, (top + course) / max(1, horizon)))
            # Dark at the ceiling, a little life near the floor.
            base = _lerp(STONE_DARK, STONE_MID, 0.20 + depth * 0.85)
            # And flatter in the middle: no course is allowed to be interesting
            # where a monster will stand.
            middle = 1.0 - min(1.0, abs((x + 64) / WIDTH - 0.5) / 0.35)
            base = _shade(base, 1.0 - 0.18 * middle)
            pygame.draw.rect(
                surface, _shade(base, 1.0 + tone), pygame.Rect(x, top, 100, course - 4)
            )
            pygame.draw.line(
                surface, _shade(base, 1.30 + tone), (x, top), (x + 96, top), 2
            )
            pygame.draw.line(
                surface, JOINT, (x, top + course - 4), (x + 96, top + course - 4), 2
            )


def weather(surface: pygame.Surface, rng: random.Random) -> None:
    """A few dark patches and damp streaks, so the wall is not a texture repeat."""
    horizon = HEIGHT * FLOOR_AT
    for _ in range(30):
        cx, cy = rng.uniform(0, WIDTH), rng.uniform(0, horizon)
        size = rng.uniform(50, 220)
        patch = pygame.Surface((int(size * 2), int(size * 2)), pygame.SRCALPHA)
        for step in range(int(size), 0, -5):
            share = 1.0 - step / size
            alpha = round(18 * share)
            if not alpha:
                continue
            pygame.draw.ellipse(
                patch,
                (6, 6, 11, alpha),
                pygame.Rect(
                    int(size - step), int(size - step * 0.7), step * 2, int(step * 1.4)
                ),
            )
        surface.blit(patch, (int(cx - size), int(cy - size)))


def doorway(surface: pygame.Surface, cx: int, width: int, top: int, floor_y: int) -> None:
    """An arched opening in the back wall: dark inside, with a lit rim."""
    radius = width // 2
    pygame.draw.rect(surface, (6, 6, 9), pygame.Rect(cx - radius, top, width, floor_y - top))
    pygame.draw.circle(surface, (6, 6, 9), (cx, top), radius)
    pygame.draw.arc(
        surface,
        _shade(STONE_MID, 1.0),
        pygame.Rect(cx - radius, top - radius, width, width),
        math.pi,
        math.tau,
        5,
    )
    for x in (cx - radius, cx + radius):
        pygame.draw.line(surface, _shade(STONE_MID, 1.0), (x, top), (x, floor_y), 3)
    pygame.draw.rect(surface, (4, 4, 6), pygame.Rect(cx - radius, floor_y - 18, width, 18))


def pilaster(
    surface: pygame.Surface, cx: int, width: int, top: int, floor_y: int, lit: float
) -> None:
    """A flat column against the wall, catching the torchlight on one side."""
    rect = pygame.Rect(cx - width // 2, top, width, floor_y - top)
    pygame.draw.rect(surface, _shade(STONE_DARK, 1.35 + lit * 0.5), rect)
    pygame.draw.rect(
        surface,
        _shade(STONE_DARK, 1.6 + lit * 0.7),
        pygame.Rect(rect.x, rect.y, max(3, width // 3), rect.h),
    )
    pygame.draw.rect(
        surface,
        _shade(STONE_DARK, 0.85),
        pygame.Rect(rect.right - width // 4, rect.y, width // 4, rect.h),
    )
    for y in (rect.y - 18, floor_y - 36):
        pygame.draw.rect(
            surface,
            _shade(STONE_DARK, 1.5 + lit * 0.5),
            pygame.Rect(rect.x - 16, y, width + 32, 22),
        )


def floor(surface: pygame.Surface, rng: random.Random) -> None:
    """Flagstones in perspective: short courses at the back, tall ones up front.

    Staggered, more stones to a course the nearer it is, and darker the further back
    -- so the floor goes somewhere instead of lying flat.
    """
    horizon = HEIGHT * FLOOR_AT
    rows = 18
    edges = [horizon + (HEIGHT - horizon) * ((i / rows) ** 1.55) for i in range(rows + 1)]
    for index in range(rows):
        top, bottom = edges[index], edges[index + 1]
        share = index / rows
        width_share = 0.88 + 0.12 * share
        left = WIDTH * (0.5 - width_share / 2)
        right = WIDTH * (0.5 + width_share / 2)
        stones = max(3, round(3 + index * 0.75))
        offset = 0.5 if index % 2 else 0.0
        for stone in range(stones + 2):
            x0 = left + (right - left) * (stone - offset) / stones
            x1 = left + (right - left) * (stone + 1 - offset) / stones
            if x1 < left or x0 > right:
                continue
            tone = rng.uniform(-0.18, 0.12)
            base = _lerp(FLOOR_DARK, FLOOR_LIT, 0.04 + share * 0.42)
            pygame.draw.polygon(
                surface,
                _shade(base, 1.0 + tone),
                [(x0, top), (x1, top), (x1 - 3, bottom), (x0 + 3, bottom)],
            )
            # The joint down between two stones of a course, and a lit top edge on
            # the stone itself: without these a course is one long strip and the
            # floor reads as a brick wall lying down, which is what it did.
            pygame.draw.line(surface, JOINT, (x0, top), (x0 + 3, bottom), 3)
            pygame.draw.line(
                surface, _shade(base, 1.5 + tone), (x0, top), (x1, top), 2
            )
        pygame.draw.line(surface, _shade(JOINT, 0.7), (left, bottom), (right, bottom), 3)


def flame(surface: pygame.Surface, cx: int, cy: int) -> None:
    """A torch on its bracket: the flame the game will put its own light over."""
    # An iron bracket: up the wall, and an arm out to the bowl.
    pygame.draw.rect(surface, _shade(STONE_DARK, 2.2), pygame.Rect(cx - 4, cy + 26, 8, 44))
    pygame.draw.rect(surface, _shade(STONE_DARK, 2.4), pygame.Rect(cx - 24, cy + 44, 48, 8))
    pygame.draw.rect(surface, _shade(STONE_DARK, 1.8), pygame.Rect(cx - 14, cy + 48, 28, 12))
    for colour, size, lift in ((FIRE_LOW, 26, 0), (FIRE_MID, 17, 10), (FIRE_CORE, 8, 20)):
        height = round(size * 1.7)
        pygame.draw.ellipse(
            surface,
            colour,
            pygame.Rect(cx - round(size * 0.44), cy - height + lift, round(size * 0.88), height * 2),
        )


def light(surface: pygame.Surface) -> None:
    """The torchlight: a warm wash over the wall and a pool on the floor.

    Added rather than painted, the way the game adds its own -- which is what makes
    the two agree: the picture has the light that is *in* the picture, and the game
    puts the light that *moves* over the top of it.
    """
    glow = pygame.Surface((WIDTH, HEIGHT))
    glow.fill((0, 0, 0))
    for fx in TORCH_X:
        cx, cy = int(WIDTH * fx), int(HEIGHT * TORCH_Y)
        for step in range(250, 0, -5):
            share = 1.0 - step / 250.0
            level = share**2.3
            pygame.draw.ellipse(
                glow,
                (round(126 * level), round(78 * level), round(28 * level)),
                pygame.Rect(cx - step, cy - round(step * 0.8), step * 2, round(step * 1.6)),
            )
        for step in range(320, 0, -5):
            share = 1.0 - step / 320.0
            level = share**2.6
            y = HEIGHT * 0.78
            pygame.draw.ellipse(
                glow,
                (round(40 * level), round(26 * level), round(10 * level)),
                pygame.Rect(cx - step, round(y - step * 0.32), step * 2, round(step * 0.64)),
            )
    surface.blit(glow, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def darken_outside(surface: pygame.Surface) -> None:
    """Walk the eye around: darker at the ceiling, at the corners, and -- gently --
    in the middle band where the fight happens."""
    veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for y in range(HEIGHT):
        top = max(0.0, 1.0 - y / (HEIGHT * 0.50))
        value = int(132 * top**1.5)
        if value:
            pygame.draw.line(veil, (6, 6, 10, value), (0, y), (WIDTH, y))
    left, top, right, bottom = CLEAR
    for step in range(40, 0, -2):
        share = 1.0 - step / 40.0
        rect = pygame.Rect(
            round(WIDTH * left - step * 5),
            round(HEIGHT * top - step * 3),
            round(WIDTH * (right - left) + step * 10),
            round(HEIGHT * (bottom - top) + step * 6),
        )
        pygame.draw.rect(veil, (6, 6, 10, round(10 * share)), rect, border_radius=80)
    surface.blit(veil, (0, 0))


def grain(surface: pygame.Surface, rng: random.Random) -> None:
    """A little noise, so the flat areas are stone and not paint."""
    small = pygame.Surface((WIDTH // 8, HEIGHT // 8))
    for x in range(small.get_width()):
        for y in range(small.get_height()):
            value = rng.randint(0, 9)
            small.set_at((x, y), (value, value, value))
    surface.blit(
        pygame.transform.smoothscale(small, (WIDTH, HEIGHT)),
        (0, 0),
        special_flags=pygame.BLEND_RGB_ADD,
    )


def draw(seed: int = SEED) -> pygame.Surface:
    """The room in the order a room is built: wall, what stands against it, floor."""
    rng = random.Random(seed)
    surface = pygame.Surface((WIDTH, HEIGHT))
    surface.fill(STONE_DARK)
    floor_y = int(HEIGHT * FLOOR_AT)
    back_wall(surface, rng)
    weather(surface, rng)
    for doorway_x, column_x in zip(DOORWAY_X, COLUMN_X):
        doorway(surface, int(WIDTH * doorway_x), 132, int(HEIGHT * 0.13), floor_y)
        pilaster(
            surface,
            int(WIDTH * column_x),
            56,
            int(HEIGHT * 0.05),
            floor_y,
            lit=1.0 if column_x < 0.5 else 0.35,
        )
    # The line the room stands on: a shadow at the foot of the wall, so the eye can
    # see where the floor begins -- which is the line the monsters stand on.
    shadow = pygame.Surface((WIDTH, 60), pygame.SRCALPHA)
    for row in range(60):
        alpha = round(96 * max(0.0, 1.0 - row / 28.0))
        pygame.draw.line(shadow, (4, 4, 7, alpha), (0, row), (WIDTH, row))
    surface.blit(shadow, (0, floor_y - 22))
    floor(surface, rng)
    for fx in TORCH_X:
        pilaster(surface, int(WIDTH * fx), 42, int(HEIGHT * 0.09), floor_y, lit=1.0)
        flame(surface, int(WIDTH * fx), int(HEIGHT * TORCH_Y))
    light(surface)
    darken_outside(surface)
    grain(surface, rng)
    return surface


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    target = Path(args[0]) if args else Path("/tmp/opencode/backdrop.png")
    pygame.init()
    pygame.display.set_mode((64, 64))
    surface = draw()
    target.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(target))
    print(f"{target}  {surface.get_width()}x{surface.get_height()}")
    print(
        f"floor line {FLOOR_AT:.3f} = {round(HEIGHT * FLOOR_AT)}px | "
        f"torches at {[round(WIDTH * fx) for fx in TORCH_X]}px, "
        f"{round(HEIGHT * TORCH_Y)}px"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
