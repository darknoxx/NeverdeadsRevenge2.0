"""The fight, on the second front end: the real arena's panels, playback and all.

This is the same seam job the theme and the grid already had, one screen further
along. The arena *says* almost everything it has to say in cells -- the plate with
the purse and the kill count, the log, the four verbs, the order strip, and the
monsters' own health bars -- all of it ``buffer.text(...)`` and ``self._bar(...)``
rather than a painter. Measured, that whole ``draw`` path asks Qt for no typeface,
which is why this screen can hand it a grid and get a real fight back.

The *playback* is shared as well, and that is the new thing here. A round used to
be read at once on this front end -- nothing moved, the log simply had the whole
round in it -- because the animation lived among the painters: a damage number's
placement and a wound's brighter colour were measured in a Qt typeface. Both have
moved to where faces belong (the painter that draws them, and the palette), and
what is left is a sequence of facts about a fight and a clock. So this screen asks
the arena to *play* the round, exactly as the Qt build does, and the panels, the
bars, the log, the badges and the verdict all arrive on the beat they always
arrived on:

    the animation always comes first, and every display and calculation after it.

What is left for this file is the painting: the flagstones, the sprites standing on
them, the shadows, the stripe under each monster, the numbers over their heads, the
colour a blow throws across the room -- and the figures' own movement, which is the
arena's arithmetic asked at this frame's clock. The art is PNG files and both
toolkits read the same ones; the geometry comes from the arena's own ``_field``,
``_figures`` and pose helpers. One room, two painters, one clock.
"""

from __future__ import annotations

import math

from ..desktop.art import size as art_size
from ..desktop.screens.base import Screen
from ..desktop.screens.battle import (
    ARROW,
    BOB_HEIGHT,
    BOB_SPEED,
    FLASH_LIFE,
    JOLT,
    MONSTER_BADGE,
    MONSTER_BADGE_GAP,
    STATUS_BADGE,
    STATUS_GAP,
    STATUS_ICONS,
    STATUS_ROW_DOWN,
    STATUS_ROW_IN,
    STATUS_SLOT,
    THICKNESS,
    BattleScreen,
    Popup,
)
from ..desktop.theme import Colour, parse_style
from .paint import load, paint
from .stage import Stage, bar_box

__all__ = ["SdlArena"]

#: How far above a figure's own line a damage number hangs, in cell rows. The Qt
#: build measures it from the cap height of the face and the height of the aim
#: arrow; here it is the grid's own unit, which is what a number drawn in the
#: grid's face is measured in anyway.
NUMBER_LIFT = 2


class SdlArena(Screen):
    """The arena's own panels, its playback, and the room painted by pygame."""

    def __init__(self, battle, backdrop: bool = True) -> None:
        self.battle = battle
        #: Whether the room is one painting or the game's own flagstones and
        #: walls. On by default where the art is there, and off with --no-backdrop.
        self.backdrop = backdrop
        #: The Qt build's arena, used for everything that is not pixels: its
        #: panels, its verbs, its order strip, its staging, its floor's geometry,
        #: *its playback*, and the whole of the rules behind them. It is never
        #: asked to `paste`, which is the one place its own painting lives.
        self.arena = BattleScreen(battle)
        #: The painted room: the flagstones, the sprites on them, the shadows and
        #: the stripes. Loaded once, because a room is painted every frame.
        self._stage = Stage()
        #: The faces the damage numbers are drawn in, one per size, made when the
        #: first number needs one.
        self._faces: dict[int, object] = {}
        #: The panel band, painted from the cells and laid over the art: the one
        #: part of the grid that lands on top of a sprite. Kept until a row of it
        #: is written, because the panels are still between animations.
        self._band = None
        self._band_rows: tuple[int, ...] | None = None
        self._band_cell = 0
        #: One transparent surface to wash the room with, kept and refilled: a
        #: landed blow throws a colour over everything for a few frames.
        self._overlay = None

    def paper(self, cols: int, rows: int, font):
        """The whole frame's paper, when the room is a painting.

        Fitted to the *frame* and not to the room band: the painting goes behind
        everything -- the sidebar, the log, the panels -- and the cells that have
        nothing to say let it show. Which is the difference between a room with a
        picture in it and a picture of a room that the game is standing in.
        """
        if not self.backdrop:
            return None
        return self._stage.paper(
            cols, rows, font, float(self.arena._floor_row(cols, rows) * font.cell_h)
        )

    # -- the first pass -----------------------------------------------------
    def draw(self, buffer, app) -> None:
        """The panels, and a letter for anything the sheets have no picture of.

        The letters were the whole of the arena for a session and are the fallback
        now -- exactly the promise the art was added on top of. A figure the
        sheets *do* have a picture for is left to the second pass, because a letter
        written here would stand through the sprite pasted over it.
        """
        # Where the painting's floor is, told to the screen that stages the fight:
        # the room's own rules stay in the room, and the artwork's answer to "where
        # is the floor" is the one thing only the artwork knows. None for a room of
        # cells, where the grid's own band *is* the floor.
        frame_w = buffer.cols * buffer.font.cell_w
        frame_h = buffer.rows * buffer.font.cell_h
        # Where the *room* says its floor is: the foot of the ground band, in
        # pixels. The painting is fitted to this line rather than the staging being
        # fitted to the painting -- so the monsters stand on the row the game's own
        # layout puts them on, and the artwork is placed to agree.
        floor_px = float(self.arena._floor_row(buffer.cols, buffer.rows) * buffer.font.cell_h)
        #: The wall, as the *placed* painting draws it: the one line the staging has
        #: to be told, because only the front end knows where the artwork ended up.
        self.arena.stage_horizon = (
            self._stage.horizon_line(frame_w, frame_h, floor_px) if self.backdrop else None
        )
        self.arena.draw(buffer, app, ground=not self.backdrop)
        if self.backdrop:
            # The painting *is* the room, so the grid's room is not drawn: the
            # arena's cell floor is a checker of opaque cells, and leaving it in
            # would be a grey patch in the middle of the picture. The wall band
            # is left alone -- it is glyphs, and they are ink either way.
            # The ground is already skipped by the line above; this stays as the
            # belt to that pair of braces, and it is cheap.
            self._bare_ground(buffer)
        cell_w = max(1, buffer.font.cell_w)
        for figure in self.arena._figures(buffer.cols, buffer.rows, buffer.font):
            if figure.art is not None:
                continue
            x = int(figure.cx) // cell_w
            row = int(figure.row)
            if 0 <= x < buffer.cols and 0 <= row < buffer.rows:
                buffer.put(x, row, figure.glyph, parse_style(figure.colour))

    # -- the second pass ----------------------------------------------------
    def paint_over(self, surface, app) -> None:
        """The room, painted, in the arena's own order.

        Floor, the stripe under each monster, the shadows, the figures -- the ones
        mid-blow in front of and behind the rest, because a striker lands *over*
        what it is hitting -- then the numbers, the verdict, and the colour a blow
        throws across the whole room. Missing still are the walls (the grid's own
        band stands in), the wound rows and the aim arrow.

        Called `paint_over` rather than `paste` because the Qt screens this app
        reuses have a `paste` of their own, and it takes a QImage.
        """
        cols, rows = self.arena._dims(app)
        font = app.font
        figures = self.arena._figures(cols, rows, font)
        field = self.arena._field(cols, rows, font.cell_w, font.cell_h)
        areas = self.arena._areas(cols, rows)
        fades = {id(one.actor): self.arena._fade(id(one.actor)) for one in figures}
        if not self.backdrop:
            # No painting: the room this game ships -- the flagstones and the
            # three planes of wall. With one, the room is already on the frame:
            # it is the paper the cells were drawn on.
            self._stage.floor(surface, field)
            if not self._stage.wall(surface, field):
                self._hash_walls(surface, app, field)
        # The light on the painting's torches, over the room and under the fight.
        # Only with a painting: the torches are the painting's, and a room made of
        # the game's own stones has no flames to be lit by.
        if self.backdrop:
            self._stage.glow(
                surface,
                surface.get_width(),
                surface.get_height(),
                self.arena._clock,
                float(self.arena._floor_row(cols, rows) * app.font.cell_h),
            )
        self._stage.health(
            surface, figures, font, self.arena._shown, self.battle.hero, fades
        )
        self._wounds(surface, app, figures, fades)
        # The shadows first: they live on the floor, so a figure standing on one
        # stands on it rather than carrying it around.
        for figure in figures:
            self._stage.shadow(surface, figure, font, fades[id(figure.actor)])
        for figure in self._ordered(figures):
            self._figure(surface, app, figure, figures, fades[id(figure.actor)])
        # The panels again, over whoever is standing in front of them: the plate
        # the hero's feet are in, and the list of the five when it is open. Painted
        # from the grid -- which is under the art and has to be, or the room would
        # not be a room -- so this is the one part of the cells that lands on top
        # of a sprite. The numbers come after it, because a hit that says "8" over
        # the plate is still a hit and the number has to be read.
        first, last = self.arena.panel_band(cols, rows)
        # No paper under the band: a band is *cells*. The boxes fill their own
        # squares, the frame and the letters are glyphs, and every other cell in
        # these rows stays clear -- so the hero is covered by the menu where the
        # menu is, and stands in front of the panel's empty room where it is not.
        # ``band_rows`` and not ``rows``: the arena's own row count is still
        # needed below, and this shadowed it -- which the wound row found out.
        band_rows = tuple(app.grid.row_signature[first:last])
        if (
            self._band is None
            or band_rows != self._band_rows
            or self._band_cell != app.font.cell_w
        ):
            self._band = paint(app.grid, app.font, None, (first, last))
            self._band_rows = band_rows
            self._band_cell = app.font.cell_w
        surface.blit(self._band, (0, first * app.font.cell_h))
        # The hero's own row of wounds, and only now: it is painted on the plate,
        # and the plate is the panel this band has just put down. Drawn before the
        # band, it was a row of symbols painted over and hidden by the panel it
        # belongs to.
        self._hero_wounds(surface, app, cols, rows)
        for figure in figures:
            if figure.chosen:
                self._arrow(surface, app, figure)
        for popup in self.arena._popups:
            self._number(surface, font, popup)
        if self.arena.verdict is not None:
            self._verdict(surface, font, cols, rows)
        self._wash(surface)

    def _ordered(self, figures) -> list:
        """Who is drawn in which order: a striker over what it is hitting.

        A monster that came for the hero lands *behind* him and is covered by him,
        which is where it came from; the hero lands over whatever he is hitting.
        Everybody else is standing still and goes in the middle.
        """
        hero = self.battle.hero
        strikes = self.arena._strikes
        behind = [f for f in figures if id(f.actor) in strikes and f.actor is not hero]
        front = [f for f in figures if id(f.actor) in strikes and f.actor is hero]
        middle = [f for f in figures if f not in behind and f not in front]
        return [*behind, *middle, *front]

    def _figure(self, surface, app, figure, figures, fade: float) -> None:
        """One figure: where its strike put it, and how solid it is right now."""
        if fade <= 0.0 or figure.art is None:
            return
        import pygame

        image = self._stage.figure(figure, app.font)
        if image is None:
            return
        cx, baseline, opacity = self._pose(
            figure, figures, fade, app.font.cell_w, app.font.cell_h
        )
        opacity = max(0.0, min(1.0, opacity))
        if opacity < 1.0:
            image = image.copy()
            image.set_alpha(round(255 * opacity))
        where = (round(cx - image.get_width() / 2), baseline - image.get_height())
        surface.blit(image, where)
        # And the flash of a blow that has just landed: the same figure, in the
        # trick's own colour, for the fifth of a second the jolt lasts.
        hurt = self.arena._hurts.get(id(figure.actor))
        if hurt is None:
            return
        age = self.arena._clock - hurt[0]
        if not (0.0 <= age <= JOLT):
            return
        flash = image.copy()
        flash.fill(
            (*tuple(parse_style(hurt[1]).fg), 255), special_flags=pygame.BLEND_RGBA_MULT
        )
        flash.set_alpha(round(255 * opacity * (1.0 - age / JOLT) * 0.85))
        surface.blit(flash, where)

    def _pose(
        self, figure, figures, fade: float, cell_w: int, cell_h: int
    ) -> tuple[int, int, float]:
        """Where a figure is and how solid, this frame.

        The port of the Qt build's own geometry, asked of the same helpers: the
        breath comes off the figure's own phase, a shove moves it up the room, a
        mid-blow figure is *somewhere else and see-through*, and a struck one is
        shaking where it stands.
        """
        raise_px = 0
        if figure.actor.stats.alive:
            raise_px = round(
                math.sin(self.arena._clock * BOB_SPEED + figure.phase) * BOB_HEIGHT
            )
        home = round(figure.row * cell_h - THICKNESS)
        home -= self.arena._knockback(figure, cell_h)
        cx, baseline, opacity = figure.cx, home - raise_px, 1.0
        pose = self.arena._strike_pose(figure, figures, home, cell_w, cell_h)
        if pose is not None:
            cx, baseline, opacity = pose
        else:
            cx += self.arena._jolt(figure)
        return cx, baseline, opacity * fade

    def _arrow(self, surface, app, figure) -> None:
        """The blade over the chosen one -- the menus' marker, standing up.

        It hangs above the figure rather than beside it, because beside a figure
        is where the next monster is: an arrow that means "this one" has to point
        at the one it means. It only exists while something is being aimed -- it
        marks the *question*, and there is no question on the floor until a trick
        has asked one -- and it breathes, one pixel either way, because a marker
        that stands as still as everything under it is a marker to hunt for.
        """
        face = self._face(app.font.path, max(16, figure.size // 2))
        # Above the *bar* and not merely above the figure: the stripe and the arrow
        # are both facts about this monster and cannot share a line.
        _left, bar_top, _width, _height = bar_box(figure, app.font)
        bob = round(math.sin(self.arena._clock * 5.0) * 2) - 1
        centre = round(figure.cx - len(ARROW) * face.cell_w / 2)
        above = bar_top - face.cell_h - bob
        # A dark copy under a bright one, the same two passes every letter in this
        # game gets: the edge is the game's own edge and not a drop shadow.
        for offset, colour in ((THICKNESS, Colour(0, 0, 0)), (0, parse_style(figure.colour).fg)):
            glyph = face.glyph(ARROW, colour)
            if glyph is not None:
                surface.blit(glyph, (centre, above + offset))

    def _hash_walls(self, surface, app, field) -> None:
        """The room without the art: the dungeon's own ``#``, drawn big.

        The Qt build has the same fallback for the same reason -- the alphabet is
        underneath every picture in this game, so a machine with no wall art gets
        the room it always had. Here it is a row of glyphs in the wall's own grey,
        which is what the grid drew before there were pictures at all.
        """
        art = app.font
        face = self._face(art.path, max(16, art.cell_h * 2))
        top = int(field.get("wall_top", field["top"] - 60.0))
        colour = parse_style(WALL_NEAR).fg
        y = max(0, top)
        stride = face.cell_w * 2
        step = 0
        while y < field["top"] and step < 3:
            for x in range(0, surface.get_width(), stride):
                for index in range(2):
                    glyph = face.glyph("#", colour if index == 0 else parse_style(WALL_FAR).fg)
                    if glyph is not None:
                        surface.blit(glyph, (x + index * face.cell_w, y))
            y += face.cell_h
            step += 1

    def _bare_ground(self, buffer) -> None:
        """Take the arena's own floor back out of the grid: the painting has one.

        Written straight into the cells and *not* through ``put``, which keeps the
        background a cell already has -- a word written on a panel must not lift
        the panel out from under it, and that rule is right. It is also why the
        first version of this did nothing at all: five hundred and ninety-two
        cells still had their floor. Clearing is not writing a word, so it is the
        one place that writes a cell outright.
        """
        from ..desktop.pattern import Cell

        x0, y0, width, height = self.arena._areas(buffer.cols, buffer.rows)["ground"]
        for row in range(y0, y0 + height):
            for column in range(x0, x0 + width):
                buffer.cells[row][column] = Cell()

    def _wounds(self, surface, app, figures, fades) -> None:
        """What is eating each monster, at the end of its bar.

        The room used to say this with a light around the figure, and a light
        could not say *which* wound. A monster whose bar already says how much of
        it is left is the one place that can also say what is still taking it.
        """
        font = app.font
        for figure in figures:
            if figure.actor is self.battle.hero or fades[id(figure.actor)] < 1.0:
                continue
            left, top, width, height = bar_box(figure, font)
            self._wound_row(
                surface,
                app,
                figure.actor,
                left + width + MONSTER_BADGE_GAP,
                top + height / 2.0,
                MONSTER_BADGE,
            )

    def _hero_wounds(self, surface, app, cols: int, rows: int) -> None:
        """The hero's own wounds, beside his life bar on the plate.

        A wound used to be a *light*: the figure stood in a pool of the colour of
        whatever was eating it until it stopped. This says the same thing more
        exactly -- which wound, and all of them side by side -- and it says it on
        the plate, which is the one place in the arena that owns the hero's own
        numbers.
        """
        if self.arena.picking:
            # The list of tricks covers the whole strip, plate and all, and this
            # row is *pixels*: it would hang over a panel that is no longer there.
            return
        worn = self.arena._worn(self.battle.hero)
        if not worn:
            return
        x, y, width, height = self.arena._areas(cols, rows)["plate"]
        if height < 4 or width < 12:
            return
        font = app.font
        left = (x + min(STATUS_ROW_IN, max(2, width - 6))) * font.cell_w
        right = (x + width - 1) * font.cell_w
        room = max(0, right - left)
        # Sized to fit and not left to run off the plate: five wounds share the
        # room the row has, because a row that fell off the end would tell the
        # player about four of their five problems.
        size = max(
            10,
            min(
                STATUS_BADGE,
                3 * font.cell_h,
                (room - (len(worn) - 1) * STATUS_GAP)
                // max(1, round(len(worn) * STATUS_SLOT)),
            ),
        )
        top = (y + STATUS_ROW_DOWN) * font.cell_h
        self._wound_row(surface, app, self.battle.hero, left, top + size / 2.0, size)

    def _wound_row(self, surface, app, actor, start: float, middle: float, size: int) -> None:
        """One row of wound symbols, from ``start`` and centred on ``middle``.

        The same symbols the plate wears, in the same order and with the same
        spacing: a player who has learned one of them in one place should find it
        drawn the same way in the other.
        """
        import pygame

        pairs = [
            (key, load(f"sprites/status/{STATUS_ICONS[key]}.png"))
            for key in self.arena._worn(actor)
            if key in STATUS_ICONS
        ]
        pairs = [(key, art) for key, art in pairs if art is not None]
        if not pairs:
            return
        slot = max(6, round(size * STATUS_SLOT))
        step = slot + STATUS_GAP
        for index, (key, art) in enumerate(pairs):
            # Fitted, not stretched: the largest box of its own shape that fits in
            # the slot, so the spacing is even and every symbol keeps its shape.
            scale = min(slot / art.get_width(), size / art.get_height())
            width = max(1, round(art.get_width() * scale))
            height = max(1, round(art.get_height() * scale))
            x = round(start + index * step + (slot - width) / 2.0)
            y = round(middle - height / 2.0)
            if width != art.get_width() or height != art.get_height():
                surface.blit(pygame.transform.smoothscale(art, (width, height)), (x, y))
            else:
                surface.blit(art, (x, y))
            depth = self.arena._depths.get(id(actor), {}).get(key, 1)
            if depth >= 2:
                self._stamp(surface, app, str(depth), x + width, y + height, size)

    def _stamp(self, surface, app, text_: str, right: float, bottom: float, size: int) -> None:
        """How deep a wound is, stamped on its own badge.

        Bottom right and a hair inside the symbol -- in front of it, which is what
        a stamp on a seal is -- and only once there is more than one stack: a wound
        that says "1" on every monster is a number nobody reads.
        """
        face = self._face(app.font.path, max(10, round(size * 0.42)))
        width = len(text_) * face.cell_w
        x = round(right - width - max(1.0, size * 0.04))
        y = round(bottom - max(1.0, size * 0.06) - face.cell_h)
        for offset, colour in ((1, Colour(0, 0, 0)), (0, parse_style("bold white").fg)):
            glyph = face.glyph(text_, colour)
            if glyph is not None:
                surface.blit(glyph, (x + offset, y + offset))

    def _number(self, surface, font, popup: Popup) -> None:
        """A damage number, on its way up: the only thing here that moves.

        Both halves of the rule are the arena's and not this file's -- a number is
        written down at the *swing* and read at the *impact*, and its bar drops
        with it -- which is why there is no timing in here at all. This only
        draws what the fight already decided when the player is allowed to see it.
        """
        if popup.age < 0:
            return
        face = self._face(font.path, 34 if popup.crit else 26)
        rise = int(popup.age / Popup.LIFE * 26)
        fade = max(0.25, 1.0 - popup.age / Popup.LIFE)
        ink = parse_style(popup.colour).fg
        shown = Colour(round(ink.r * fade), round(ink.g * fade), round(ink.b * fade))
        left = round(popup.x - len(popup.text) * face.cell_w / 2)
        top = popup.y - font.cell_h * NUMBER_LIFT - rise
        # A dark copy under a bright one, the way the Qt build draws it: the slab
        # is what makes a number legible over a monster rather than on it.
        for index, char in enumerate(popup.text):
            dark = face.glyph(char, Colour(0, 0, 0), bold=True)
            if dark is not None:
                surface.blit(dark, (left + index * face.cell_w, top + 3))
        for index, char in enumerate(popup.text):
            glyph = face.glyph(char, shown, bold=True)
            if glyph is not None:
                surface.blit(glyph, (left + index * face.cell_w, top))

    def _face(self, path: str, size: int):
        """The face a number is drawn in, at its own size, made once."""
        face = self._faces.get(size)
        if face is None:
            from .font import SdlFont

            face = SdlFont(path, size)
            self._faces[size] = face
        return face

    def _wash(self, surface) -> None:
        """The colour a landed blow throws across the room, fading.

        The Qt build draws it in its paste and clears it there; on this front end
        the paint is where it has to be cleared, because there is no other pass
        over the frame.
        """
        import pygame

        wash = self.arena._wash
        if wash is None:
            return
        age = self.arena._clock - wash.when
        if age < 0:
            return
        if age > FLASH_LIFE:
            self.arena._wash = None
            return
        if self._overlay is None or self._overlay.get_size() != surface.get_size():
            self._overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        alpha = round(255 * wash.strength * (1.0 - age / FLASH_LIFE))
        self._overlay.fill((*tuple(parse_style(wash.colour).fg), max(0, min(255, alpha))))
        surface.blit(self._overlay, (0, 0))

    def _verdict(self, surface, font, cols: int, rows: int) -> None:
        """What the fight came to, over the stage the way Qt blits it.

        The panel is the arena's own -- the same box, the same rule, the same
        hint -- asked for as cells, painted by the grid painter, and laid on top.
        """
        panel, x, y = self.arena._verdict_panel(cols, rows, font)
        surface.blit(paint(panel, font), (x * font.cell_w, y * font.cell_h))

    # -- the fight ----------------------------------------------------------
    def key(self, name, event, app) -> bool:
        """A key, and then whatever round it set off -- played, not snapped.

        The arena takes the choice and queues the round the instant the player
        commits, which is what makes a fight *decidable*; the frames that follow
        are this screen being asked to play it, one beat at a time.
        """
        return self.arena.key(name, event, app)

    def step(self, dt: float, app) -> None:
        """A frame went by: the fight's own clock, which everything reads."""
        self.arena.step(dt, app)

    @property
    def busy(self) -> bool:
        """Whether the fight is still talking -- a round half played."""
        return self.arena.busy

    @property
    def animating(self) -> bool:
        """Always: a fight breathes while the player is deciding, too."""
        return True

