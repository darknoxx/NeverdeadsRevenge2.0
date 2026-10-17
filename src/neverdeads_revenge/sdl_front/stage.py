"""The arena's pixel layer, for a front end with no QPainter.

The Qt arena paints its room in two passes: one into the grid, where the panels
and the letters live, and one onto the picture, where the *art* lives -- the
flagstones, the sprites that stand on them, the stripe under each monster. The
first pass is already shared between the front ends. This is the second.

It is a smaller job than it looks, for one reason worth writing down: **the art is
PNG files, and both toolkits read the same ones.** Nothing here re-draws a monster
or a flagstone; it loads what the game already ships and puts it where the arena's
own arithmetic says, because the geometry comes from `_field` and `_figures` and
those are the arena's. There is still one room and not two. The only change the Qt
side needed was `_floor_stone` being asked to *name* its stones instead of loading
them, which is the same shape as `_verdict_panel`: the room's rules stay in the
room, and a painter only paints.

What is deliberately *not* here is the motion: no strike poses, no knockbacks, no
damage numbers, no sparks, no colour wash across the room. There is nothing to
drive them either -- a round on this front end is read and not watched, so the
room stands still -- and they are the next pass. The room they will move in is
this one.
"""

from __future__ import annotations

import math

from ..desktop.screens.battle import BOB_HEIGHT, BOB_SPEED, THICKNESS, BattleScreen
from ..desktop.theme import parse_style
from .paint import load

__all__ = ["Stage"]

#: The wash over a row of floor, heavier the further back it is: the same fade the
#: Qt painter lays down, and the reason distance reads at all in a flat grid.
FADE_ALPHA = 140
FADE_COLOUR = (6, 6, 10)


class Stage:
    """The painted room: the floor, the bars, the shadows and the figures.

    Owns its images because a room is painted every frame and a PNG should be read
    once. Nothing here knows about the fight; it is handed the arena's geometry
    and its staging, and it draws.
    """

    def __init__(self) -> None:
        self._washes: dict[tuple[int, int, int], object] = {}
        self._shadow: object | None = None

    # -- the art ------------------------------------------------------------
    def tile(self, name: str):
        """The stone called ``name``, or ``None`` if there is none."""
        return load(f"tiles/{name}.png")

    # -- the floor ----------------------------------------------------------
    def floor(self, surface, field) -> None:
        """The flagstones, laid the way the grid laid them and then painted over.

        Two cells to a stone, half a stone of stagger on every row, the two tones
        alternating where the two grid tones used to, and the taper clipped so
        that a staggered stone never lands outside the floor.
        """
        light, dark = self.tile("floor_a"), self.tile("floor_b")
        if light is None or dark is None:
            return
        tw = light.get_width()
        left, right = int(field["left"]), int(field["right"])
        top, cell_h = int(field["top"]), int(field["cell_h"])
        rows = int(field["cells_h"])
        for row in range(rows):
            depth = row / max(1, rows - 1)
            y = top + row * cell_h
            inset = round((1.0 - depth) * float(field["inset_px"]))
            clip_left, clip_right = left + inset, right - inset
            x = clip_left - (row % 2) * (tw // 2)
            index = 0
            while x < clip_right:
                stone = self.tile(BattleScreen._floor_stone(index, row, index % 2 == 0))
                self._blit_clipped(
                    surface,
                    stone or (light if index % 2 == 0 else dark),
                    x,
                    y,
                    clip_left,
                    clip_right,
                )
                x += tw
                index += 1
            fade = int(FADE_ALPHA * (1.0 - depth))
            if fade:
                surface.blit(self._wash(right - left, cell_h, fade), (left, y))

    @staticmethod
    def _blit_clipped(surface, image, x: int, y: int, left: int, right: int) -> None:
        """One stone, cut to the floor's taper rather than painted outside it."""
        if image is None:
            return
        width = image.get_width()
        src_x = max(0, left - x)
        dst_x = max(x, left)
        span = min(width - src_x, right - dst_x)
        if span <= 0:
            return
        surface.blit(image, (dst_x, y), (src_x, 0, span, image.get_height()))

    def _wash(self, width: int, height: int, alpha: int):
        """A row's fade, kept: it is the same strip every frame at every depth."""
        key = (width, height, alpha)
        strip = self._washes.get(key)
        if strip is None:
            import pygame

            strip = pygame.Surface((width, height), pygame.SRCALPHA)
            strip.fill((*FADE_COLOUR, alpha))
            self._washes[key] = strip
        return strip

    # -- what is standing on it ---------------------------------------------
    def health(self, surface, figures, font, shown, hero, fades) -> None:
        """The stripe under every monster, on the floor it is standing on.

        Painted here and not written into the grid, because the grid's floor is a
        picture now and a bar in the grid would be a bar *under* the picture. The
        same three colours the cell version uses, so the reading does not change
        with the front end.
        """
        import pygame

        for figure in figures:
            if figure.actor is hero:
                continue
            if fades[id(figure.actor)] < 1.0:
                # The bar goes with the monster and not before it: a stripe lying
                # on the floor under nobody is a stripe about nobody.
                continue
            total = max(1, figure.actor.max_hp)
            shown_hp = shown.get(id(figure.actor), figure.actor.stats.hp)
            ratio = max(0.0, min(1.0, shown_hp / total))
            cells = max(8, min(14, figure.cells * 2))
            width = cells * font.cell_w
            height = font.cell_h // 2
            left = round(figure.cx - width / 2.0)
            top = figure.row * font.cell_h + height
            pygame.draw.rect(surface, _rgb("grey19"), (left, top, width, height))
            filled = round(width * ratio)
            if filled:
                pygame.draw.rect(
                    surface, _rgb(_bar_colour(ratio)), (left, top, filled, height)
                )

    def shadow(self, surface, figure, font, fade: float) -> None:
        """A pool of ground under a figure, soft at the rim.

        Drawn rather than written into the grid, because a shadow is the one thing
        here that has to have soft edges: a rectangle of black cells under a
        painted sprite reads as a hole in the floor.
        """
        if fade <= 0.0:
            return
        import pygame

        width = max(20.0, float(figure.cells * font.cell_w) * 1.05)
        height = max(6.0, width * 0.24)
        pool = self._pool()
        scaled = pygame.transform.smoothscale(pool, (round(width), round(height)))
        scaled.set_alpha(round(255 * fade))
        centre_y = figure.row * font.cell_h - 1
        surface.blit(
            scaled,
            (round(figure.cx - width / 2.0), round(centre_y - height / 2.0)),
        )

    def _pool(self):
        """The gradient a shadow is made of, drawn once and stretched per figure.

        Rings of black, each a step darker than the one outside it, so the edge
        goes to nothing instead of stopping.
        """
        if self._shadow is None:
            import pygame

            size = 64
            pool = pygame.Surface((size, size), pygame.SRCALPHA)
            half = size // 2
            for step in range(half, 0, -1):
                alpha = round(120 * (1.0 - step / half) ** 1.4)
                pygame.draw.ellipse(
                    pool,
                    (0, 0, 0, alpha),
                    pygame.Rect(half - step, half - step // 2, step * 2, step),
                )
            self._shadow = pool
        return self._shadow

    def figure(self, surface, figure, font, clock: float, fade: float) -> bool:
        """One figure on the floor: its picture, at its own size, breathing.

        Drawn at its own size and never scaled -- these are painted figures, and a
        painted figure put through a nearest-neighbour resize looks like a mistake.
        Returns whether anything was drawn, which is the arena's cue to leave the
        grid's letter in place when the sheets have no picture for this one.
        """
        if figure.art is None:
            return False
        image = load(figure.art)
        if image is None:
            return False
        raise_px = 0
        if figure.actor.stats.alive:
            # Off its own phase, taken from its place in the row: side by side,
            # rising and falling together, they would read as one wave.
            raise_px = round(math.sin(clock * BOB_SPEED + figure.phase) * BOB_HEIGHT)
        baseline = figure.row * font.cell_h - THICKNESS - raise_px
        if fade < 1.0:
            image = image.copy()
            image.set_alpha(round(255 * fade))
        surface.blit(
            image,
            (round(figure.cx - image.get_width() / 2), baseline - image.get_height()),
        )
        return True


def _bar_colour(ratio: float) -> str:
    """Green over half, yellow over a quarter, red under that: the arena's rule."""
    if ratio > 0.5:
        return "bright_green"
    if ratio > 0.25:
        return "bright_yellow"
    return "bright_red"


def _rgb(name: str) -> tuple[int, int, int]:
    """A style name as a colour: the same palette both front ends read."""
    return tuple(parse_style(name).fg)
