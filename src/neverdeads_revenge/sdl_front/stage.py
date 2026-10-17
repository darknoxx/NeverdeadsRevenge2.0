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

from ..desktop.art import size as art_size
from ..desktop.screens.battle import (
    FAR_LIGHT,
    MONSTER_BADGE,
    THICKNESS,
    WALL_FAR,
    WALL_NEAR,
    BattleScreen,
)
from ..desktop.theme import parse_style
from .paint import load

__all__ = ["Stage"]

#: The wash over a row of floor, heavier the further back it is: the same fade the
#: Qt painter lays down, and the reason distance reads at all in a flat grid.
FADE_ALPHA = 140
FADE_COLOUR = (6, 6, 10)

#: Where the painting's two torches are, as shares of the painting itself.
#: Measured off the picture: the bright pixels of the flames, left and right.
TORCHES = ((0.110, 0.250), (0.890, 0.267))


class Stage:
    """The painted room: the floor, the bars, the shadows and the figures.

    Owns its images because a room is painted every frame and a PNG should be read
    once. Nothing here knows about the fight; it is handed the arena's geometry
    and its staging, and it draws.
    """

    def __init__(self) -> None:
        self._washes: dict[tuple[int, int, int], object] = {}
        self._shadow: object | None = None
        #: The stones, shaded, and the whole wall built out of them -- both kept,
        #: because masonry does not change and a shear is not something to do
        #: every frame. Keyed by what they were asked for.
        self._stones: dict[tuple[str, int], object] = {}
        self._walls: dict[tuple, object] = {}
        #: The backdrop, fitted to the room once and blitted after: the painting
        #: is four megapixels and scaling that per frame is a crawl.
        self._fitted: dict[tuple[int, int], object] = {}
        self._lamp: object | None = None

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

    # -- the room around it -------------------------------------------------
    def wall(self, surface, field) -> bool:
        """The room: three planes of the same stone, built once and blitted.

        The far wall faces the viewer and needs no shear; the two at the sides
        are the floor's own edges standing up, so each is the *same* transform of
        the same tile. A shear is a column of one-pixel strips at a walking
        offset -- far too much to do every frame and nothing at all to do once --
        so the whole thing is built on the first frame of a window size and
        blitted after that. Returns whether there was any wall art to build from.
        """
        key = tuple(sorted(field.items()))
        if key not in self._walls:
            self._walls[key] = self._build_wall(field, surface.get_size())
        built = self._walls[key]
        if built is None:
            return False
        surface.blit(built, (0, 0))
        return True

    def _build_wall(self, field, size):
        """The three planes, on their own surface, with the shade baked in."""
        import pygame

        art = self.tile("wall")
        if art is None:
            return None
        wall = _blank(size)
        tw, th = art.get_width(), art.get_height()
        left = float(field["left"])
        inset = float(field["inset_px"])
        ground_top = float(field["top"])
        wall_top = float(field.get("wall_top", ground_top - 60.0))
        bottom = float(field["bottom"])
        down = max(1, math.ceil((ground_top - wall_top) / th))

        # The far wall: laid *up* from the floor's own edge, because a wall that
        # grew downwards would be standing on the floor.
        across = max(1, math.ceil((float(field["width_px"]) - inset * 2) / tw))
        for index in range(across):
            x = round(left + inset + index * tw)
            for course in range(down):
                stone = self._stone(BattleScreen._stone(index, course), FAR_LIGHT)
                if stone is not None:
                    wall.blit(stone, (x, round(ground_top - (course + 1) * th)))

        # And the two sides, sheared along the floor's own edge -- the light
        # coming from the hero's end, so the far corner is the darkest thing.
        edge_x, edge_y = float(field["edge_x"]), float(field["edge_y"])
        steps = max(1, round(float(field["edge_len"]) / tw))
        for side in (0, 1):
            ux = edge_x if side == 0 else -edge_x
            if side:
                ax0 = float(field["right"]) - inset
                ax1 = float(field["right"])
            else:
                ax0, ax1 = left + inset, left
            ay0, ay1 = ground_top, bottom
            for step in range(steps):
                along = (step + 0.5) / steps
                ax = ax0 + (ax1 - ax0) * along
                ay = ay0 + (ay1 - ay0) * along
                for course in range(down):
                    stone = self._stone(
                        BattleScreen._stone(step, course), FAR_LIGHT - along * 0.75
                    )
                    if stone is not None:
                        _shear_into(
                            wall,
                            stone,
                            ux,
                            edge_y,
                            ax,
                            ay,
                            float(-(course + 1) * th),
                        )

        # The clip: courses climb, and a wall does not have to cover the sky.
        if wall_top > 0:
            wall.fill((0, 0, 0, 0), pygame.Rect(0, 0, size[0], round(wall_top)))
        return wall

    def _stone(self, name: str, how_much: float):
        """One stone, with the room's own dark laid over it, made once.

        The hashes were *drawn* in three greys; a picture cannot be, so the
        difference between the far wall and the near corner is a wash of the
        darkness over the top of it -- the same idea, one layer up.
        """
        alpha = max(0, min(255, int(150 * how_much)))
        key = (name, alpha)
        if key not in self._stones:
            art = self.tile(name)
            if art is None:
                self._stones[key] = None
            else:
                art = art.copy()
                if alpha:
                    wash = _blank(art.get_size())
                    wash.fill((6, 6, 10, alpha))
                    art.blit(wash, (0, 0))
                self._stones[key] = art
        return self._stones[key]

    # -- and the room in one picture ----------------------------------------
    def paper(self, cols: int, rows: int, font):
        """The painting, fitted to the whole frame, or ``None`` if there is none.

        Covered and not stretched: the painting is three by two and a frame is
        sixteen by nine, so it is scaled until it fills and centred -- crops,
        rather than squashes. One dial for the eye, and this is the neutral
        setting.
        """
        image = load("backdrops/arena.png")
        if image is None:
            return None
        return self._backdrop_for(
            image, (cols * font.cell_w, rows * font.cell_h)
        )

    def _backdrop_for(self, image, size):
        """The painting, fitted to that rectangle, once per size."""
        import pygame

        key = (int(size[0]), int(size[1]))
        if key not in self._fitted:
            width, height = key
            factor = max(width / image.get_width(), height / image.get_height())
            scaled = pygame.transform.smoothscale(
                image,
                (
                    max(1, round(image.get_width() * factor)),
                    max(1, round(image.get_height() * factor)),
                ),
            )
            self._fitted[key] = scaled.subsurface(
                pygame.Rect(
                    (scaled.get_width() - width) // 2,
                    (scaled.get_height() - height) // 2,
                    width,
                    height,
                )
            )
        return self._fitted[key]

    def _cell(self, field) -> tuple[int, int]:
        """The cell the room is measured in, off the field it was built from."""
        return (int(field["cell_w"]), int(field["cell_h"]))

    # -- what is standing on it ---------------------------------------------
    def health(self, surface, figures, font, shown, hero, fades) -> None:
        """The stripe over every monster's head, where its wounds are worn too.

        It was under the feet, on the floor -- and on a floor made of a *painting*
        a stripe lying across the flagstones reads as part of the room rather than
        as a fact about the monster standing in it. Over the head it is at the
        figure's own outline, which is where a player looks to see what is left of
        something.

        Same three colours, same length, same end for the wound symbols: one place
        decides the box, and the icons follow it.
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
            left, top, width, height = bar_box(figure, font)
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

        It was always here and always under the sprite -- and nobody could see it:
        black at three quarters of nothing over a floor that is already dark stone
        is a shadow in the arithmetic and not on the screen. Deeper, and wider at
        the rim, so that the pool *reads* as ground under a figure.
        """
        if fade <= 0.0:
            return
        import pygame

        width = max(24.0, float(figure.cells * font.cell_w) * 1.25)
        height = max(6.0, width * 0.24)
        pool = self._pool()
        scaled = pygame.transform.smoothscale(pool, (round(width), round(height)))
        scaled.set_alpha(round(255 * fade))
        centre_y = figure.row * font.cell_h - 1
        surface.blit(
            scaled,
            (round(figure.cx - width / 2.0), round(centre_y - height / 2.0)),
        )

    def glow(self, surface, width: int, height: int, clock: float) -> None:
        """Light on the two torches in the painting, breathing.

        The painting brought its own flames and they are, of course, painted: they
        do not move. A light that grows and shrinks over each of them is the whole
        difference between a *picture* of a lit room and a room that is lit -- and
        it costs two additive blits a frame.

        A radial ramp in *colour* and not in alpha, because the blend is additive:
        what it adds is the light, and adding nothing is what the rim does.

        The torches' places are *the painting's*, so they are mapped the way the
        painting was fitted and not as shares of the frame: the two agree at
        sixteen by nine, where the fit crops nothing, and stop agreeing in a
        fullscreen of another shape, where the fit does.
        """
        if not TORCHES:
            return
        image = load("backdrops/arena.png")
        if image is None:
            return
        import pygame

        own_w, own_h = image.get_size()
        factor = max(width / own_w, height / own_h)
        span_w, span_h = own_w * factor, own_h * factor
        off_x, off_y = (span_w - width) / 2.0, (span_h - height) / 2.0
        pool = self._light()
        breath = 0.5 + 0.5 * math.sin(clock * 2.1)
        wobble = 0.5 + 0.5 * math.sin(clock * 3.7 + 1.0)
        for fx, fy in TORCHES:
            scale = 0.86 + 0.24 * breath + 0.06 * wobble
            side = max(8, round(220 * scale))
            lit = pygame.transform.smoothscale(pool, (side, side))
            surface.blit(
                lit,
                (
                    round(fx * span_w - off_x - side / 2),
                    round(fy * span_h - off_y - side / 2),
                ),
                special_flags=pygame.BLEND_RGB_ADD,
            )

    def _light(self):
        """The ramp a torch's light is made of, drawn once: warm, and to nothing."""
        if self._lamp is None:
            import pygame

            size = 220
            lamp = pygame.Surface((size, size))
            half = size // 2
            for step in range(half, 0, -1):
                share = 1.0 - step / half
                level = share**2.2
                pygame.draw.ellipse(
                    lamp,
                    (
                        round(150 * level),
                        round(96 * level),
                        round(44 * level),
                    ),
                    pygame.Rect(half - step, half - step, step * 2, step * 2),
                )
            self._lamp = lamp
        return self._lamp

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
                alpha = round(190 * (1.0 - step / half) ** 1.2)
                pygame.draw.ellipse(
                    pool,
                    (0, 0, 0, alpha),
                    pygame.Rect(half - step, half - step // 2, step * 2, step),
                )
            self._shadow = pool
        return self._shadow

    def figure(self, figure):
        """A figure's picture, loaded -- and nothing else.

        Deliberately dumb: *where* a figure stands is the arena's arithmetic and
        moves every frame (it breathes, it is shoved, it lunges), so this hands
        back the picture and lets the screen put it down. A painted figure is
        never scaled -- a painter's figure through a nearest-neighbour resize looks
        like a mistake -- and ``None`` means the sheets have nothing, which is the
        arena's cue to leave the grid's own letter standing.
        """
        if figure.art is None:
            return None
        return load(figure.art)


def bar_box(figure, font) -> tuple[int, int, int, int]:
    """Where a monster's bar goes: over its head, as wide as its own footprint.

    Measured off the *picture's* height and not the figure's nominal size, because
    the sprites are drawn at their own size: a bar placed from a number the art
    does not have would end up in the middle of somebody's skull.

    One function for the bar and for the wound symbols, because the symbols live at
    the end of the bar and two calculations of one place is two places.
    """
    cells = max(8, min(14, figure.cells * 2))
    width = cells * font.cell_w
    height = font.cell_h // 2
    measured = art_size(figure.art) if figure.art is not None else None
    sprite_h = measured[1] if measured is not None else font.cell_h * 3
    left = round(figure.cx - width / 2.0)
    top = figure.row * font.cell_h - THICKNESS - sprite_h - height - 8
    return left, top, width, height


def _blank(size):
    """A transparent surface, made the one way: SDL needs the import, too."""
    import pygame

    return pygame.Surface(size, pygame.SRCALPHA)


def _shear_into(target, stone, ux: float, uy: float, ax: float, ay: float, top: float) -> None:
    """Blit a tile as its *plane*: every column shifted up and along.

    Which is what a shear is, done the only way a blitter can do it without a
    matrix: one column at a time, at a walking offset. ``(ax, ay)`` is the point
    on the wall's own edge that the tile is *centred* on and ``top`` where the
    tile sits above it -- both in tile space, which is the whole subtlety: a
    column's offset is measured from the tile's middle and not from its left
    edge, and a wall drawn from its left edge is a wall shifted half a stone
    along its own plane. (It was, for a while: half a tile left and the same up,
    which is exactly the gap that showed against the far wall.)
    """
    import pygame

    width, height = stone.get_size()
    for column in range(width):
        along = column - width / 2.0
        strip = stone.subsurface(pygame.Rect(column, 0, 1, height))
        target.blit(strip, (round(ax + ux * along), round(ay + uy * along + top)))


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

