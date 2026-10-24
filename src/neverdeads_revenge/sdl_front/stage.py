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
    THICKNESS,
    BattleScreen,
)
from ..desktop.theme import parse_style
from .paint import load

__all__ = ["Stage"]

#: The wash over a row of floor, heavier the further back it is: the same fade the
#: Qt painter lays down, and the reason distance reads at all in a flat grid.
FADE_ALPHA = 140
FADE_COLOUR = (6, 6, 10)

#: Where the front edge of the painting's floor is, as a share of the painting's
#: own height: the line the nearest monsters stand on.
#:
#: It is a property of the *painting* and not of the window, and that is the whole
#: point of it. The staging used to be measured in the grid's rows -- from the foot
#: of the room's ground band -- which agrees with the painting exactly at sixteen
#: by nine and drifts away from it at any other shape, because the grid is derived
#: from the window and grows by *cells* while the painting grows by *pixels*. On a
#: taller or shorter monitor the monsters ended up standing on the flagstones'
#: horizon line, in the wall, at whatever distance the arithmetic happened to put
#: them. Anchored here they stand on the floor the artist drew, at every size.
#:
#: The number is where a sixteen-by-nine frame puts it, which is the shape the
#: staging was tuned at -- so nothing moves there, and everything else is measured
#: from the painting instead of from the grid.
FLOOR_AT = 0.5556

#: And where the floor *ends*, at the back: the line the wall stands on.
#:
#: A monster behind it is a monster in the masonry. That is not a mistake the
#: staging makes by design -- every lane has a depth and every depth is a place --
#: but a lane that stands 1.5 rows higher than its depth asks for, on a frame that
#: draws the room's rows in a different size than the painting draws its floor, can
#: cross the line, and the one that crosses it is always the middle of three: the
#: only lane with a nudge of its own.
#:
#: 0.472 is the value the staging was tuned against -- the monsters' feet were
#: measured at 255, 275 and 295 pixels of 540 and 255 was taken for the horizon --
#: and it is used as a *clamp* rather than as a placement, so it is deliberately a
#: few pixels in front of the line: measured off the painting itself, the wall
#: meets the floor at 0.463, and a clamp set exactly there would leave a monster
#: standing in the last row of masonry.
HORIZON_AT = 0.472

#: Where the painting's two torches are, as shares of the painting itself.
#: Measured off the picture: the bright pixels of the flames, left and right.
TORCHES = ((0.112, 0.264), (0.889, 0.268))


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
        #: The pictures at the sizes a *pose* asks for: the room has two depths,
        #: so there are two of these per figure and they are made once.
        #: Keyed by (art, scale) and, for the echo, which tint of it.
        self._scaled: dict[tuple, object] = {}

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
    # -- what is standing on it ---------------------------------------------
    def health(
        self, surface, figures, font, shown, hero, fades, scales=None, poses=None
    ) -> None:
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
            left, top, width, height = bar_box(
                figure,
                font,
                (scales or {}).get(id(figure.actor), 1.0),
                (poses or {}).get(id(figure.actor)),
            )
            pygame.draw.rect(surface, _rgb("grey19"), (left, top, width, height))
            filled = round(width * ratio)
            if filled:
                pygame.draw.rect(
                    surface, _rgb(_bar_colour(ratio)), (left, top, filled, height)
                )

    def shadow(self, surface, figure, font, fade: float, pose=None) -> None:
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
        # A shadow under the *drawn* figure: a monster that has lunged at the hero
        # leaves no pool behind it on the floor it came from.
        centre_y = round((pose[1] if pose is not None else figure.row * font.cell_h) - 1)
        centre_x = pose[0] if pose is not None else figure.cx
        surface.blit(
            scaled,
            (round(centre_x - width / 2.0), round(centre_y - height / 2.0)),
        )

    def placement(self, width: int, height: int, floor_px: float):
        """The painting on this frame: scaled and *placed* so its floor is the room's.

        This is the whole of how the artwork and the cells agree. The room's floor
        line is a row of the grid -- the foot of the ground band, which is a fixed
        number of rows above the panels whatever the window did -- and the painting
        is scaled until its painted floor edge can be laid exactly on that line and
        still cover the frame. So the monsters stand on the floor the artist drew
        *and* on the row the room says, and neither of them is a compromise.

        Returns ``(factor, off_x, off_y)``: the scale, and where the scaled painting
        is put, both in frame pixels. ``off_y`` may be negative -- the painting
        hanging over the top of the frame is a crop, and it is meant.
        """
        image = load("backdrops/arena.png")
        if image is None:
            return 1.0, 0.0, 0.0
        own_w, own_h = image.get_size()
        # Big enough to cover sideways, big enough that the floor edge can reach
        # `floor_px` from above it, and big enough that what is below that edge
        # still reaches the bottom of the frame.
        above = max(1.0, floor_px) / (own_h * FLOOR_AT)
        below = max(1.0, height - floor_px) / (own_h * (1.0 - FLOOR_AT))
        factor = max(width / own_w, above, below)
        span_w, span_h = own_w * factor, own_h * factor
        # Centred: half of what hangs over goes off each side. This was the wrong
        # way round for one release -- a positive offset here puts the painting to
        # the *right* of the frame's left edge, which is a black bar down the left
        # and the room sliding sideways, and it only showed on shapes wide enough
        # for the painting to be wider than the frame (2560x1440 fullscreen).
        return factor, (width - span_w) / 2.0, floor_px - FLOOR_AT * span_h

    def _own_size(self, height: int) -> tuple[int, int]:
        """The painting's own pixels, or the frame's shape when there is none."""
        image = load("backdrops/arena.png")
        if image is None:
            return max(1, height), max(1, height)
        return image.get_size()

    def line_at(self, share: float, width: int, height: int, floor_px: float) -> float:
        """Where a share of the painting's height lands, in frame pixels.

        The placement's offset is where the painting's *top* is put, so a line on
        the painting is that offset plus the share of its height -- and the floor
        edge is the line the whole placement exists to land on the room's own row.
        """
        factor, _off_x, off_y = self.placement(width, height, floor_px)
        return off_y + share * self._own_size(height)[1] * factor

    def horizon_line(self, width: int, height: int, floor_px: float) -> float:
        """The far edge: beyond it there is wall, and nothing stands there."""
        return self.line_at(HORIZON_AT, width, height, floor_px)

    def paper(self, cols: int, rows: int, font, floor_px: float):
        """The painting, placed on this frame, at the room's own floor line."""
        image = load("backdrops/arena.png")
        if image is None:
            return None
        import pygame

        width, height = cols * font.cell_w, rows * font.cell_h
        key = (int(width), int(height), int(floor_px))
        if key not in self._fitted:
            factor, off_x, off_y = self.placement(width, height, floor_px)
            own_w, own_h = image.get_size()
            # Rounded *up* and placed *down*: a covering fit that rounds the wrong
            # way leaves a one-pixel sliver of nothing along an edge, and a sliver
            # of nothing is a black line on a player's screen.
            scaled = pygame.transform.smoothscale(
                image,
                (
                    max(1, math.ceil(own_w * factor)),
                    max(1, math.ceil(own_h * factor)),
                ),
            )
            frame = pygame.Surface((width, height))
            frame.fill((0, 0, 0))
            frame.blit(scaled, (math.floor(off_x), math.floor(off_y)))
            self._fitted[key] = frame
        return self._fitted[key]

    def glow(self, surface, width: int, height: int, clock: float, floor_px: float) -> None:
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

        # The same placement the paper uses, or the light drifts off the torch it
        # belongs to -- which is exactly what happened: the paper was placed by the
        # room's floor line and the light by the old centred fit, and on a screen
        # wide enough to tell them apart the flame was in one place and its glow in
        # another.
        factor, off_x, off_y = self.placement(width, height, floor_px)
        own_h = image.get_size()[1]
        span_w, span_h = image.get_size()[0] * factor, own_h * factor
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
                    round(off_x + fx * span_w - side / 2),
                    round(off_y + fy * span_h - side / 2),
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

    def figure(self, figure, scale: float = 1.0):
        """A figure's picture, loaded -- and, when a pose asks, resized.

        Deliberately dumb about *where*: a figure stands in the arena's arithmetic
        and moves every frame (it breathes, it is shoved, it lunges), so this hands
        back the picture and lets the screen put it down.

        ``scale`` is the pose's, and it is the room's *depth*: a hero crossing the
        room to strike is drawn at half, because he is further away, and a monster
        that has come to the hero at the size it was exported at. One ratio, used
        in both directions -- a half and a double, and never a fraction in between,
        because a painter's figure through a fractional resize looks like a
        mistake. Both are made once and kept, so the blink a blow is made of costs
        a cached blit.

        ``None`` means the sheets have nothing, which is the arena's cue to leave
        the grid's own letter standing.
        """
        import pygame

        if figure.art is None:
            return None
        image = load(figure.art)
        if image is None:
            return None
        if scale == 1.0:
            return image
        key = (figure.art, round(scale, 3))
        if key not in self._scaled:
            size = (
                max(1, round(image.get_width() * scale)),
                max(1, round(image.get_height() * scale)),
            )
            if scale < 1.0:
                # A box of four pixels into one keeps more of the drawing than a
                # pick of one in four; an upscale is the other way round.
                self._scaled[key] = pygame.transform.smoothscale(image, size)
            else:
                self._scaled[key] = pygame.transform.scale(image, size)
        return self._scaled[key]

    #: The echo is a hero's *front* multiplied down to a shadow. Dark, and still
    #: holding the shape of whoever the run was -- which is the whole of what it
    #: is: the thing that came back wearing your face.
    SHADOW = (46, 50, 70, 255)

    #: And the ripple around it: the same picture in a cold pale colour, so what
    #: drifts beside the silhouette reads as *that* figure and not a smear.
    RIPPLE = (138, 166, 214, 255)

    def silhouette(self, figure, scale: float = 1.0):
        """The figure as a shadow -- the echo's own version of the picture."""
        return self._tinted(figure, scale, self.SHADOW, "shadow")

    def ripple(self, figure, scale: float = 1.0):
        """The pale copy the arena drifts beside it, a few pixels either way."""
        return self._tinted(figure, scale, self.RIPPLE, "ripple")

    def _tinted(self, figure, scale: float, colour: tuple, label: str):
        """One picture, one colour multiplied into it, made once and kept.

        ``BLEND_RGBA_MULT`` rather than a plain fill: what comes out is the
        drawing *in* that colour, edges and all, and not a coloured rectangle
        where a figure used to be. The alpha is the sheet's own either way.
        """
        import pygame

        image = self.figure(figure, scale)
        if image is None:
            return None
        key = (figure.art, round(scale, 3), label)
        if key not in self._scaled:
            tinted = image.copy()
            tinted.fill(colour, special_flags=pygame.BLEND_RGBA_MULT)
            self._scaled[key] = tinted
        return self._scaled[key]


def bar_box(figure, font, scale: float = 1.0, pose=None) -> tuple[int, int, int, int]:
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
    # Measured as it is *drawn*: a monster that has come close is twice as tall,
    # and a bar placed over the size it has at home would be a bar through its
    # chest.
    sprite_h = (
        measured[1] * scale if measured is not None else font.cell_h * 3
    )
    if pose is not None:
        # Where it is *drawn* this frame: a monster that has come close has its
        # bar over its head at the hero's end of the room, not over the spot it
        # left.
        cx, baseline = pose[0], pose[1]
    else:
        cx, baseline = figure.cx, figure.row * font.cell_h - THICKNESS
    left = round(cx - width / 2.0)
    top = round(baseline - sprite_h - height - 8)
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

