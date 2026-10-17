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

from ..desktop.screens.base import Screen
from ..desktop.screens.battle import (
    BOB_HEIGHT,
    BOB_SPEED,
    FLASH_LIFE,
    JOLT,
    THICKNESS,
    BattleScreen,
    Popup,
)
from ..desktop.theme import Colour, parse_style
from .paint import paint
from .stage import Stage

__all__ = ["SdlArena"]

#: How far above a figure's own line a damage number hangs, in cell rows. The Qt
#: build measures it from the cap height of the face and the height of the aim
#: arrow; here it is the grid's own unit, which is what a number drawn in the
#: grid's face is measured in anyway.
NUMBER_LIFT = 2


class SdlArena(Screen):
    """The arena's own panels, its playback, and the room painted by pygame."""

    def __init__(self, battle) -> None:
        self.battle = battle
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
        #: One transparent surface to wash the room with, kept and refilled: a
        #: landed blow throws a colour over everything for a few frames.
        self._overlay = None

    # -- the first pass -----------------------------------------------------
    def draw(self, buffer, app) -> None:
        """The panels, and a letter for anything the sheets have no picture of.

        The letters were the whole of the arena for a session and are the fallback
        now -- exactly the promise the art was added on top of. A figure the
        sheets *do* have a picture for is left to the second pass, because a letter
        written here would stand through the sprite pasted over it.
        """
        self.arena.draw(buffer, app)
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
        fades = {id(one.actor): self.arena._fade(id(one.actor)) for one in figures}
        self._stage.floor(surface, field)
        self._stage.health(
            surface, figures, font, self.arena._shown, self.battle.hero, fades
        )
        # The shadows first: they live on the floor, so a figure standing on one
        # stands on it rather than carrying it around.
        for figure in figures:
            self._stage.shadow(surface, figure, font, fades[id(figure.actor)])
        for figure in self._ordered(figures):
            self._figure(surface, app, figure, figures, fades[id(figure.actor)])
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

        image = self._stage.figure(figure)
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
        home = figure.row * cell_h - THICKNESS
        home -= self.arena._knockback(figure, cell_h)
        cx, baseline, opacity = figure.cx, home - raise_px, 1.0
        pose = self.arena._strike_pose(figure, figures, home, cell_w, cell_h)
        if pose is not None:
            cx, baseline, opacity = pose
        else:
            cx += self.arena._jolt(figure)
        return cx, baseline, opacity * fade

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

