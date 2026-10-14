"""The arena: the isometric stage, the five verbs, and the fight being played.

**M1.** M0 was a picture; this one is a fight. The stage is unchanged in
ambition -- the dungeon's alphabet, enlarged: a monster is the letter it always
was, the room is the dungeon's ``#``, and both are pasted onto the frame because
neither fits in a character cell. What is new is that the letters *are* the
monsters: the actors standing on the floor are the ones staged here, with their
own health under them and their own name in the log when they fall.

**The fight is played, not printed.** :class:`~neverdeads_revenge.game.battle.Battle`
decides a whole round at once and hands back a list of events; this screen keeps
them in a queue and plays one per beat, so a blow lands when it is shown to land
rather than when it was rolled. The health bars follow the *playback* and not
the state, for the same reason: a bar that had already dropped before the sword
came down would be telling the player about the future.

Nothing here knows a rule. It knows where things stand, what the five verbs are
called, which sound a landed blow makes, and how long a beat lasts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtGui import QColor, QFontMetrics, QPainter, QTransform

from ...game.battle import (
    ATTACK,
    DEFEND,
    FLEE,
    ITEM,
    SPECIAL,
    VERBS,
    Battle,
    Guarded,
    Over,
    Said,
    Struck,
)
from ..buffer import PatternBuffer
from ..chrome import ASH, BLOOD, BONE, box, rule
from ..font import BitmapFont
from ..render import log_style
from ..sprites import sprite as sprite_for
from ..theme import Style, parse_style
from .base import Screen

__all__ = ["BattleScreen", "Popup", "Staged"]

#: The floor's two tile tones at the hero's feet, and the same two at the far
#: edge. Distance is shade here, not size: the far rows fade into the dark the
#: way a remembered wall does, because the phosphor fades rather than switches.
FLOOR_NEAR = QColor("#2c2c36")
FLOOR_NEAR_ALT = QColor("#202028")
FLOOR_FAR = QColor("#16161c")
FLOOR_FAR_ALT = QColor("#101014")
#: Where something is standing: the tiles in front of it go nearly black, and
#: the ends of the pool fade rather than stop, so a shadow reads as a shape
#: under a figure instead of as a stripe across the floor.
SHADOW = QColor("#07070a")
SHADOW_EDGE = QColor("#131318")
#: The wall: the dungeon's remembered greys. The far wall is darkest, the near
#: end of the side walls lightest, and the fade between them is the depth.
WALL_NEAR = "grey30"
WALL_MID = "grey23"
WALL_FAR = "grey19"
#: How thick a letter is: a dark copy of it sits this many pixels lower, and the
#: bright one is drawn over it, so what shows is the slab's edge.
THICKNESS = 5
#: How far the floor's edges are pulled in at the back, as a share of the width.
#: This is the *only* perspective number: the walls are derived from it, so a
#: room that is deeper or shallower is one edit and not four.
TAPER = 0.18
#: The most monsters the stage holds. A crowd is a second row and a wider glass,
#: which is M3's business; three is what a fight of this shape is about.
STAGE = 3

#: Where a row of monsters stands, by how many there are: the lane across the
#: room and how far into it, both as fractions of the ground's width and height.
#:
#: A fight of *one* should look like a fight of one. The stage was built for
#: three, and a single monster was being shoved into the left-hand slot of a row
#: that was not there -- so the row is laid out by its own count: one in the
#: middle of the room, two on either side of that middle, and three in the
#: shallow arc the stage was drawn for, with the outer ones a little nearer, the
#: way a line of anything stands.
ROWS: dict[int, tuple[tuple[float, float], ...]] = {
    1: ((0.0, 0.18),),
    2: ((-0.26, 0.32), (0.26, 0.32)),
    3: ((-0.40, 0.32), (-0.06, 0.14), (0.40, 0.48)),
}

#: How big a letter stands, in font pixels. The hero is nearest and largest; the
#: monsters scale with their depth.
MONSTER_SIZES = (62, 52, 46)
HERO_SIZE = 88
#: The arrow over the one the choice is on.
ARROW = "▼"
#: How long one event holds the stage. A fight that printed a whole round at
#: once would be a spreadsheet with letters drawn on it.
BEAT = 0.42
#: How long a number hangs in the air over a head.
POPUP_LIFE = 0.85
#: How many lines of the fight are readable at once.
LOG_LINES = 3


_LETTERS: dict[int, BitmapFont] = {}


def letter_font(size: int) -> BitmapFont:
    """The font a letter or a hash is drawn in, measured once per size.

    A frame is drawn thirty times a second and a font is four faces plus their
    metrics, so the sizes are kept: there are a handful of them, and they are
    the same handful for the whole game.
    """
    font = _LETTERS.get(size)
    if font is None:
        font = BitmapFont(pixel_size=size)
        _LETTERS[size] = font
    return font


@dataclass(slots=True)
class Popup:
    """A number that was just dealt, hanging over the head it landed on.

    Its own clock rather than a timer: it is drawn by the same frames that draw
    everything else, and a popup that outlived the fight would be a number
    floating over a screen nobody is fighting on any more.
    """

    text: str
    colour: str
    x: int
    y: int
    crit: bool = False
    age: float = 0.0

    #: Not a field: the same life for every number, and the only place it lives.
    LIFE = POPUP_LIFE


class Staged:
    """One figure on the stage: which actor it is, and where it stands.

    The letters are drawn in pixels, so a figure is placed in pixels too -- a
    centre and a cell row -- and the *shadow* and the health bar under it are
    drawn in cells, because that is where the floor is. One layout produces both,
    so a monster cannot be drawn in one place and stand in another.
    """

    __slots__ = (
        "actor",
        "glyph",
        "colour",
        "size",
        "cx",
        "row",
        "cells",
        "chosen",
        "sprite",
    )

    def __init__(
        self,
        actor,
        glyph: str,
        colour: str,
        size: int,
        cx: int,
        row: int,
        cells: int,
        chosen: bool = False,
        sprite=None,
    ) -> None:
        self.actor = actor
        #: The painted sprite for this actor, if the sheets have one. ``None``
        #: means draw the letter, which is a fallback and not a failure.
        self.sprite = sprite
        self.glyph = glyph
        self.colour = colour
        self.size = size
        #: The centre of the letter, in pixels.
        self.cx = cx
        #: The cell row it stands on: the top of the pool of shadow, so the
        #: figure stands behind its own shadow rather than on top of it.
        self.row = row
        self.cells = cells
        self.chosen = chosen


class BattleScreen(Screen):
    """The stage, and one fight, played a beat at a time."""

    def __init__(self, battle: Battle) -> None:
        self.battle = battle
        self.state = battle.state
        self.verb = 0
        self.target = 0
        #: The fight's last few lines, in the log's own colours.
        self.lines: list[Said] = []
        #: The round being played back, one event per beat. The opening round is
        #: queued here rather than in a call the caller has to remember: anything
        #: quicker than the hero acts before the first command, and that has to
        #: happen the moment the fight opens or it never happens at all.
        self._queue = list(battle.begin())
        self._beat = 0.0
        self._popups: list[Popup] = []
        #: What the health bars show, which lags the state by exactly the blows
        #: that have been played rather than the ones that have been rolled.
        self._shown: dict[int, int] = {}
        self.verdict: str | None = None
        self._size: tuple[int, int] | None = None

    # -- the contract -------------------------------------------------------
    def draw(self, buffer: PatternBuffer, app) -> None:
        #: The size this screen is being drawn at, remembered: the letters are
        #: placed in pixels and the paste step has to agree with the grid pass
        #: about where the floor is, and the grid pass is the one that knows.
        self._size = (buffer.cols, buffer.rows)
        buffer.clear()
        areas = self._areas(buffer.cols, buffer.rows)
        self._draw_ground(buffer, areas["ground"])
        self._draw_shadows(buffer, areas["ground"])
        self._draw_health(buffer, areas["ground"])
        self._draw_log(buffer, areas["log"])
        self._draw_plate(buffer, *areas["plate"])
        self._draw_commands(buffer, *areas["commands"])

    def paste(self, image, app) -> None:
        """The room and the models: walls, letters, the arrow, and the numbers.

        Drawn here rather than in the grid because neither a monster nor a block
        of masonry fits in a cell -- the whole look of the game is one fixed
        cell, and this is the one place that has to leave it.
        """
        cols, rows = self._dims(app)
        figures = self._figures(cols, rows, app.font)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        field = self._field(cols, rows, app.font.cell_w, app.font.cell_h)
        self._paste_walls(painter, field)
        for figure in figures:
            self._paste_model(painter, figure, app.font.cell_h)
        for figure in figures:
            if figure.chosen:
                self._paste_arrow(painter, figure, app.font.cell_h)
        for popup in self._popups:
            self._paste_popup(painter, popup)
        if self.verdict is not None:
            self._paste_verdict(painter, cols, rows, app)
        painter.end()

    def _paste_verdict(
        self, painter: QPainter, cols: int, rows: int, app
    ) -> None:
        """What the fight came to, over the room and over the letters in it.

        Drawn in the paste rather than in the grid because the monsters are
        pasted *after* the grid: a panel drawn into the buffer would have a
        hero's letter standing through the middle of it. A little buffer of its
        own keeps the game's own chrome -- the box, the rule, the hint -- and
        still lands on top of everything the stage put down.

        Set on the *stage* and not in the middle of the glass: the last lines of
        the fight are the only account of how it ended, and a panel dropped over
        them would be covering the story with its title.
        """
        text = self.verdict or ""
        width = min(cols - 6, max(24, len(text) + 10))
        height = 5
        areas = self._areas(cols, rows)
        _, wall_y, _, wall_h = areas["wall"]
        _, log_y, _, _ = areas["log"]
        top = wall_y + wall_h
        x = max(0, (cols - width) // 2)
        y = max(0, min(log_y - height, top + (log_y - top - height) // 2))

        panel = PatternBuffer(width, height, app.font)
        colour = {"YOU DIED": BLOOD, "VICTORY": "bright_yellow"}.get(text, ASH)
        box(panel, 0, 0, width, height, border=colour, fill=True)
        ink = parse_style(f"bold {BONE}")
        left = 3 + max(0, (width - 6 - len(text)) // 2)
        panel.text(left, 2, text, ink)
        rule(panel, 1, height - 2, width - 2, ASH)
        panel.text(2, height - 1, "enter  leave the arena", parse_style(ASH))
        painter.drawImage(x * app.font.cell_w, y * app.font.cell_h, panel.render())

    def _dims(self, app) -> tuple[int, int]:
        """The grid this screen is drawn into: its own record, or the app's."""
        if self._size is not None:
            return self._size
        buffer = getattr(app, "_buffer", None)
        if buffer is None:
            return (0, 0)
        return (buffer.cols, buffer.rows)

    def key(self, name: str, event, app) -> bool:
        if name == "escape":
            app.leave_battle()
            return True
        if self.battle.over:
            # The fight is decided, but the arena may still be playing the last
            # blow: leaving on a keypress before the verdict has been shown would
            # be the player skipping the one thing they just earned.
            if not self.busy and name in ("enter", "return", "space"):
                app.leave_battle()
            return True
        if self.busy:
            # The fight is talking. It will not be interrupted mid-sentence, or
            # a player drumming on the keyboard would be choosing the next verb
            # for a blow they have not seen land yet.
            return True
        living = self._targets()
        if name in ("left", "h") and living:
            self.target = (self.target - 1) % len(living)
            return True
        if name in ("right", "l") and living:
            self.target = (self.target + 1) % len(living)
            return True
        if name == "up":
            self.verb = (self.verb - 1) % len(VERBS)
            return True
        if name == "down":
            self.verb = (self.verb + 1) % len(VERBS)
            return True
        shortcut = {"a": ATTACK, "s": SPECIAL, "i": ITEM, "d": DEFEND, "f": FLEE}
        if name in shortcut:
            self.verb = VERBS.index(shortcut[name])
            self._choose(app)
            return True
        if name in ("enter", "return", "space"):
            self._choose(app)
            return True
        return True

    @property
    def busy(self) -> bool:
        """Whether the fight still has something to say or show."""
        return bool(self._queue) or self._beat > 0 or bool(self._popups)

    def step(self, dt: float, app) -> None:
        """A frame went by: age the numbers, and land the next event.

        Everything the fight does is on this clock -- the beat between blows and
        the life of a damage number -- because a screen that kept a timer of its
        own would keep running after the window it is drawn in has gone.
        """
        for popup in self._popups:
            popup.age += dt
        self._popups = [popup for popup in self._popups if popup.age < Popup.LIFE]
        if self._beat > 0:
            self._beat = max(0.0, self._beat - dt)
            return
        if not self._queue:
            self._resync()
            return
        self._play(self._queue.pop(0), app)
        self._beat = BEAT

    # -- the fight, played ------------------------------------------------
    def _targets(self) -> list:
        """Who the choice can be on: the monsters the stage is actually showing.

        The stage holds three. A bigger fight is a second row and a wider glass
        (M3), and until there is one, an arrow that could point at a monster the
        player cannot see would be pointing at nothing.
        """
        return [enemy for enemy in self.battle.enemies[:STAGE] if enemy.stats.alive]

    def _choose(self, app) -> None:
        """Take the highlighted verb, and queue the round it sets off."""
        living = self._targets()
        target = living[self.target % len(living)] if living else None
        # The state is decided the instant the player commits; what the screen
        # shows is not, and this is where the two are told apart.
        self._snapshot()
        self._queue = list(self.battle.choose(VERBS[self.verb], target))
        self._beat = 0.0
        if VERBS[self.verb] == SPECIAL:
            app.play("void")
        elif VERBS[self.verb] == ITEM:
            app.play("item")
        if not living:
            self._resync()

    def _snapshot(self) -> None:
        """Freeze what the bars say, so the playback can move them itself."""
        for actor in [self.battle.hero, *self.battle.enemies]:
            self._shown[id(actor)] = actor.stats.hp

    def _resync(self) -> None:
        """Truth, once the round has finished being played."""
        for actor in [self.battle.hero, *self.battle.enemies]:
            self._shown[id(actor)] = actor.stats.hp

    def _play(self, event, app) -> None:
        """One event, on the screen and in the ear."""
        if isinstance(event, Said):
            self.lines = [*self.lines, event][-LOG_LINES:]
            return
        if isinstance(event, Guarded):
            point = self._point_of(self.battle.hero, app)
            if point is not None:
                app.effects.spark(point, "grey70", count=8)
            return
        if isinstance(event, Over):
            self.verdict = (
                "VICTORY"
                if event.won
                else "YOU GOT AWAY"
                if event.escaped
                else "YOU DIED"
            )
            app.play("victory" if event.won else "stairs" if event.escaped else "death")
            if not event.won and not event.escaped:
                # The run ended in here. The arena steps out of the way first:
                # the summary is about the run, and the run is what is standing
                # behind the arena.
                app.leave_battle()
                app.show_game_over(won=False)
            return
        if isinstance(event, Struck):
            self._land(event, app)

    def _land(self, struck: Struck, app) -> None:
        """A blow landing: a number, a shove, and a sound that matches it."""
        outcome = struck.outcome
        figure = self._figure_of(struck.target, app)
        if outcome.hit and not outcome.dodged:
            before = self._shown.get(id(struck.target), struck.target.stats.hp)
            self._shown[id(struck.target)] = max(0, before - outcome.damage)
        if figure is not None:
            text = str(outcome.damage) if outcome.hit else "miss"
            colour = (
                "#ffd34d"
                if outcome.crit
                else struck.target.color
                if outcome.hit
                else "grey70"
            )
            self._popups.append(self._popup(text, colour, figure, app, outcome.crit))
            if outcome.hit:
                point = self._point_of(struck.target, app)
                if point is not None:
                    app.view.shake(strength=4 if outcome.crit else 2, seconds=0.16)
        if not outcome.hit:
            return
        if struck.actor is self.battle.hero:
            app.play("kill" if outcome.killed else "crit" if outcome.crit else "hit")
        else:
            app.play("hurt")

    @staticmethod
    def _popup(text: str, colour: str, figure: Staged, app, crit: bool) -> Popup:
        """A number placed over the head it landed on, ready to rise.

        Above the *arrow* as well as above the letter: the two cannot share a
        spot, or the number a player is reading would be standing exactly where
        the target marker is, on the frame where both matter most.
        """
        cap = QFontMetrics(letter_font(figure.size).bold).capHeight()
        arrow = QFontMetrics(letter_font(max(16, figure.size // 2)).bold).height()
        baseline = figure.row * app.font.cell_h - THICKNESS - cap - arrow - 4
        return Popup(text=text, colour=colour, x=figure.cx, y=baseline, crit=crit)

    # -- where things are --------------------------------------------------
    def _areas(self, cols: int, rows: int) -> dict[str, tuple[int, int, int, int]]:
        """Where the pieces sit, in cells: wall, ground, log, plate, commands.

        Five bands, bottom to top: the panels, the lines the fight speaks in,
        the floor, and the strip the walls stand up into. The wall strip is
        reserved rather than overlaid -- a wall drawn over the floor would be a
        wall standing in front of the hero.
        """
        margin = max(1, min(3, cols // 24))
        panel_h = 7 if rows >= 26 else 5 if rows >= 16 else 3
        panel_y = max(1, rows - panel_h - margin)
        log_h = 3 if rows >= 26 else 2 if rows >= 18 else 1
        log_y = max(1, panel_y - log_h)
        wall_h = max(2, min(3, rows // 8))
        wall_y = margin
        ground_y = min(log_y - 1, wall_y + wall_h)
        ground_h = max(1, log_y - ground_y)
        panel_w = max(12, min((cols - margin * 3) // 2, 36))
        return {
            "wall": (margin, wall_y, max(1, cols - margin * 2), wall_h),
            "ground": (margin, ground_y, max(1, cols - margin * 2), ground_h),
            "log": (margin, log_y, max(1, cols - margin * 2), log_h),
            "plate": (margin, panel_y, panel_w, panel_h),
            "commands": (max(0, cols - margin - panel_w), panel_y, panel_w, panel_h),
        }

    def _field(
        self, cols: int, rows: int, cell_w: int, cell_h: int
    ) -> dict[str, float]:
        """The floor in pixels, plus the one number the walls are built from.

        Everything that has to agree about the room reads this: the tiles, the
        shadows, the two side walls and their shear. ``edge`` is one point of
        floor going away from the viewer.
        """
        x0, y0, width, height = self._areas(cols, rows)["ground"]
        inset = max(1, round(width * TAPER))
        left, right = x0 * cell_w, (x0 + width) * cell_w
        top, bottom = y0 * cell_h, (y0 + height) * cell_h
        dx = inset * cell_w
        dy = bottom - top
        length = math.hypot(dx, dy) or 1.0
        return {
            "left": left,
            "right": right,
            "top": top,
            "bottom": bottom,
            "width_px": right - left,
            "height_px": dy,
            "inset_px": dx,
            "cell_w": cell_w,
            "cell_h": cell_h,
            "cells_x0": x0,
            "cells_y0": y0,
            "cells_w": width,
            "cells_h": height,
            "edge_x": dx / length,
            "edge_y": -dy / length,
            "edge_len": length,
        }

    def _figures(self, cols: int, rows: int, font) -> list[Staged]:
        """The staged figures for this window.

        Worked out per call rather than kept: the staging carries *which* monster
        the choice is on, and a cache that remembered the arrow would leave it
        pointing at whoever was chosen when the window was last resized.
        """
        return self._stage(self._field(cols, rows, font.cell_w, font.cell_h))

    def _stage(self, field: dict[str, float]) -> list[Staged]:
        """Who stands where: the monsters in the far half, the hero in front.

        The monsters are the actors themselves, in the order they were met --
        their glyph, their colour, their depth. Nothing is invented here: a fight
        against three vipers is three v's on the floor, and a fight against one
        is one v in the middle of it.
        """
        cell_w = int(field["cell_w"])
        x0, y0 = int(field["cells_x0"]), int(field["cells_y0"])
        width, height = int(field["cells_w"]), int(field["cells_h"])
        centre = x0 + width // 2
        living = self._targets()
        marked = living[self.target % len(living)] if living else None
        scale = 1.35 if width >= 120 else 1.0
        monsters = self.battle.enemies[:STAGE]
        places = ROWS.get(len(monsters), ROWS[STAGE])
        staged: list[Staged] = []
        for index, enemy in enumerate(monsters):
            lane, depth = places[min(index, len(places) - 1)]
            size = round(MONSTER_SIZES[min(index, len(MONSTER_SIZES) - 1)] * scale)
            art = sprite_for(enemy.name)
            staged.append(
                Staged(
                    actor=enemy,
                    glyph=enemy.glyph,
                    colour=enemy.color,
                    size=size,
                    cx=(centre + round(lane * width) + 1) * cell_w,
                    row=y0 + max(1, round(depth * height)),
                    cells=self._span(enemy.glyph, size, cell_w, art),
                    chosen=enemy is marked,
                    sprite=art,
                )
            )
        hero = self.battle.hero
        size = round(HERO_SIZE * scale)
        art = sprite_for(hero.name)
        staged.append(
            Staged(
                actor=hero,
                glyph=hero.glyph,
                colour=hero.color,
                size=size,
                cx=(centre + 1) * cell_w,
                row=y0 + height - 1,
                cells=self._span(hero.glyph, size, cell_w, art),
                sprite=art,
            )
        )
        return staged

    @staticmethod
    def _span(glyph: str, size: int, cell_w: int, art=None) -> int:
        """How many cells wide the pool of shadow under a figure has to be.

        A sprite's own width when there is one, and the letter's advance when
        there is not: the shadow is the figure's footprint, and it should be the
        footprint of what is standing there.
        """
        if art is not None:
            return max(2, round(art.width() / cell_w))
        font = letter_font(size)
        advance = QFontMetrics(font.bold).horizontalAdvance(glyph)
        return max(2, round(advance / cell_w))

    def _figure_of(self, actor, app) -> Staged | None:
        cols, rows = self._dims(app)
        for figure in self._figures(cols, rows, app.font):
            if figure.actor is actor:
                return figure
        return None

    def _point_of(self, actor, app) -> tuple[float, float] | None:
        """Where a figure stands on the frame, in pixels, for the picture stuff."""
        figure = self._figure_of(actor, app)
        if figure is None:
            return None
        cell_w, cell_h = app.font.cell_w, app.font.cell_h
        return (figure.cx, figure.row * cell_h)

    @staticmethod
    def _place_popup(popup: Popup, figure: Staged, app) -> None:
        """Hang a number over the head it landed on."""
        cap = QFontMetrics(letter_font(figure.size).bold).capHeight()
        baseline = figure.row * app.font.cell_h - THICKNESS
        popup.y = baseline - cap - 6

    # -- what is pasted -----------------------------------------------------
    def _paste_walls(self, painter: QPainter, field: dict[str, float]) -> None:
        """The room: the dungeon's ``#``, big, on three planes.

        One plane is the far wall, which faces the viewer and needs no shear at
        all. The other two are the side walls, and each is the *same* transform
        of the same glyph: the plane's horizontal axis is the floor's own edge
        and its vertical axis is the vertical, which is what a wall is. The
        hashes are all one size -- a parallel projection has no nearer and
        further, which is the whole of the isometric look.
        """
        size = self._hash_size(field)
        font = letter_font(size)
        painter.setFont(font.bold)
        advance = QFontMetrics(font.bold).horizontalAdvance("#")

        painter.setPen(parse_style(WALL_FAR).fg)
        span = field["width_px"] - field["inset_px"] * 2
        count = max(1, round(span / advance))
        start = field["left"] + field["inset_px"]
        for i in range(count):
            painter.drawText(int(start + i * advance), int(field["top"]), "#")

        side_size = max(12, int(size * 0.62))
        side_font = letter_font(side_size)
        painter.setFont(side_font.bold)
        advance = QFontMetrics(side_font.bold).horizontalAdvance("#")
        far_ink = parse_style(WALL_FAR).fg
        near_ink = parse_style(WALL_NEAR).fg
        for side in (0, 1):
            # Each wall recedes its own way: the left one goes away up and to
            # the right, the right one up and to the left, and both are the same
            # glyph under the same kind of transform.
            ux = field["edge_x"] if side == 0 else -field["edge_x"]
            uy = field["edge_y"]
            if side:
                ax0 = field["right"] - field["inset_px"]
                ax1 = field["right"]
            else:
                ax0 = field["left"] + field["inset_px"]
                ax1 = field["left"]
            ay0, ay1 = field["top"], field["bottom"]
            steps = max(1, round(field["edge_len"] / advance))
            for i in range(steps):
                t = (i + 0.5) / steps
                ax = ax0 + (ax1 - ax0) * t
                ay = ay0 + (ay1 - ay0) * t
                painter.setPen(
                    QColor(
                        int(far_ink.red() + (near_ink.red() - far_ink.red()) * t),
                        int(far_ink.green() + (near_ink.green() - far_ink.green()) * t),
                        int(far_ink.blue() + (near_ink.blue() - far_ink.blue()) * t),
                    )
                )
                painter.save()
                painter.setTransform(QTransform(ux, uy, 0.0, 1.0, ax, ay), combine=True)
                painter.drawText(0, 0, "#")
                painter.restore()

    @staticmethod
    def _hash_size(field: dict[str, float]) -> int:
        """How big one ``#`` is: as tall as the strip the wall stands in.

        The glyph is measured by its cap height rather than its point size, so
        the masonry fills the wall band on a 27-row window and on a 60-row one
        without a second number to keep in step.
        """
        band = field["cell_h"] * 3
        probe = 100
        cap = QFontMetrics(letter_font(probe).bold).capHeight() or probe
        return max(12, int(probe * band / cap))

    def _paste_model(self, painter: QPainter, figure: Staged, cell_h: int) -> None:
        """One figure on the floor: its picture if the sheets have one, its
        letter if they do not.

        The sprite is drawn at its own size and not scaled -- these are painted
        figures, and a painted figure put through a nearest-neighbour resize
        looks like a mistake -- so what the sheets made is what the arena shows.
        The letter is the fallback and is drawn exactly as it was before: the
        whole game looked like that, and a monster the sheets have never heard
        of should not be the one fight with nothing on the floor.
        """
        baseline = figure.row * cell_h - THICKNESS
        if figure.sprite is not None:
            image = figure.sprite
            faded = not figure.actor.stats.alive
            left = figure.cx - image.width() // 2
            if faded:
                # A monster that is out of the fight stays where it fell, dimmed
                # rather than removed: a corpse that vanished on the last blow
                # would make the end of a fight unreadable.
                painter.setOpacity(0.45)
            painter.drawImage(left, baseline - image.height(), image)
            painter.setOpacity(1.0)
            return

        font = letter_font(figure.size)
        painter.setFont(font.bold)
        metrics = QFontMetrics(font.bold)
        left = figure.cx - metrics.horizontalAdvance(figure.glyph) // 2
        ink = parse_style(figure.colour).fg
        dead = not figure.actor.stats.alive
        painter.setPen(ink.darker(320))
        painter.drawText(left, baseline + THICKNESS, figure.glyph)
        if dead:
            faded_ink = QColor(ink)
            faded_ink.setRed((faded_ink.red() + 20) // 3)
            faded_ink.setGreen((faded_ink.green() + 20) // 3)
            faded_ink.setBlue((faded_ink.blue() + 20) // 3)
            painter.setPen(faded_ink)
        else:
            painter.setPen(ink)
        painter.drawText(left, baseline, figure.glyph)

    def _paste_arrow(self, painter: QPainter, figure: Staged, cell_h: int) -> None:
        """The blade over the chosen one -- the menus' marker, standing up.

        It hangs above the letter rather than beside it, because beside a letter
        is where the next monster is: an arrow that means "this one" has to point
        at the one it means.
        """
        font = letter_font(max(16, figure.size // 2))
        painter.setFont(font.bold)
        metrics = QFontMetrics(font.bold)
        ink = parse_style(figure.colour).fg
        if figure.sprite is not None:
            top = figure.sprite.height()
        else:
            top = QFontMetrics(letter_font(figure.size).bold).capHeight()
        baseline = figure.row * cell_h - THICKNESS - top - metrics.height() // 3
        left = figure.cx - metrics.horizontalAdvance(ARROW) // 2
        painter.setPen(ink.darker(320))
        painter.drawText(left, baseline + THICKNESS, ARROW)
        painter.setPen(ink)
        painter.drawText(left, baseline, ARROW)

    def _paste_popup(self, painter: QPainter, popup: Popup) -> None:
        """A number on its way up and out: the only thing here that moves."""
        font = letter_font(34 if popup.crit else 26)
        painter.setFont(font.bold)
        metrics = QFontMetrics(font.bold)
        rise = int(popup.age / Popup.LIFE * 26)
        left = popup.x - metrics.horizontalAdvance(popup.text) // 2
        baseline = popup.y - rise
        ink = QColor(popup.colour)
        # Fading toward the dark the way everything else in this game fades:
        # a number does not shrink away, the phosphor just stops holding it.
        fade = max(0.25, 1.0 - popup.age / Popup.LIFE)
        ink = QColor(
            int(ink.red() * fade), int(ink.green() * fade), int(ink.blue() * fade)
        )
        painter.setPen(ink.darker(240))
        painter.drawText(left, baseline + 3, popup.text)
        painter.setPen(ink)
        painter.drawText(left, baseline, popup.text)

    # -- the ground ---------------------------------------------------------
    def _draw_ground(
        self, buffer: PatternBuffer, area: tuple[int, int, int, int]
    ) -> None:
        """Rows of filled tiles, staggered, narrowing and fading as they recede.

        Row ``i`` counts from the far edge down to the hero's feet. Its inset
        grows with the distance to the back, and its tone falls off on the way,
        so the same two colours in the same two glyphs turn into a floor that
        goes somewhere.
        """
        x0, y0, width, height = area
        if width < 8 or height < 3:
            return
        back_inset = max(1, round(width * TAPER))
        for i in range(height):
            depth = i / (height - 1)
            inset = round((1.0 - depth) * back_inset)
            # Half a tile of stagger per row: this is the whole of the
            # isometric illusion. Two cells are one tile, so the phase is a cell.
            phase = i % 2
            for x in range(inset, width - inset):
                alt = ((x + phase) // 2) % 2 == 0
                buffer.put(x0 + x, y0 + i, " ", Style(bg=self._tile(depth, alt)))

    @staticmethod
    def _tile(depth: float, alt: bool) -> QColor:
        """The floor's colour at ``depth``: 0 at the far edge, 1 at the hero."""
        near, far = (FLOOR_NEAR, FLOOR_FAR) if alt else (FLOOR_NEAR_ALT, FLOOR_FAR_ALT)
        return QColor(
            int(far.red() + (near.red() - far.red()) * depth),
            int(far.green() + (near.green() - far.green()) * depth),
            int(far.blue() + (near.blue() - far.blue()) * depth),
        )

    def _draw_shadows(
        self, buffer: PatternBuffer, area: tuple[int, int, int, int]
    ) -> None:
        """In front of each figure: the tiles it stands on, gone nearly black.

        A row *below* the feet rather than under them, because a figure stands
        behind its own shadow, and the ends fade instead of stopping so the pool
        reads as a shape rather than as a stripe.
        """
        font = buffer.font
        for figure in self._figures(buffer.cols, buffer.rows, font):
            span = figure.cells + 2
            left = round(figure.cx / font.cell_w) - span // 2
            for i in range(span):
                edge = i in (0, span - 1)
                tile = SHADOW_EDGE if edge else SHADOW
                buffer.put(left + i, figure.row, " ", Style(bg=tile))

    def _draw_health(
        self, buffer: PatternBuffer, area: tuple[int, int, int, int]
    ) -> None:
        """Under each monster, the part of it that is left.

        Not a name: the letter *is* the monster, and who did what to whom is the
        log's business. What the letter cannot say is how much of it there is,
        and that is the one number a fight is actually about. Drawn half a cell
        tall and long -- a stripe on the floor rather than a slab of colour --
        because a monster's bar is a fact about the room and not a panel.
        """
        font = buffer.font
        for figure in self._figures(buffer.cols, buffer.rows, font):
            if figure.actor is self.battle.hero:
                continue
            total = max(1, figure.actor.max_hp)
            shown = self._shown.get(id(figure.actor), figure.actor.stats.hp)
            cells = max(8, min(14, figure.cells * 2))
            left = round(figure.cx / font.cell_w) - cells // 2
            self._bar(buffer, left, figure.row + 1, cells, shown / total, thin=True)

    def _draw_log(self, buffer: PatternBuffer, area: tuple[int, int, int, int]) -> None:
        """The lines the fight speaks in, newest last, in the dungeon's colours.

        The same mapping the dungeon log uses, which is the point: a curse is
        the same red here as it is down there, and a kill is the same bad news.
        """
        x, y, width, height = area
        if width < 20:
            return
        shown = self.lines[-height:]
        for index, line in enumerate(shown):
            text = line.text[: max(0, width - 4)]
            style = parse_style(log_style(line.kind))
            buffer.text(x + 2, y + index, text, style)
            if index == len(shown) - 1:
                buffer.put(x, y + index, "►", style)

    # -- the panels ---------------------------------------------------------
    def _draw_plate(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The hero's plate: who he is, how much of him is left, what he carries."""
        hero = self.battle.hero
        title = hero.name.upper()
        box(buffer, x, y, width, height, title=title, border=BLOOD, fill=True)
        if height < 4 or width < 14:
            return
        shown = self._shown.get(id(hero), hero.stats.hp)
        total = max(1, hero.max_hp)
        bar = min(12, max(4, width - 22))
        buffer.text(x + 2, y + 1, "HP", parse_style(ASH))
        self._bar(buffer, x + 5, y + 1, bar, shown / total)
        buffer.text(x + 6 + bar, y + 1, f" {shown:>2}/{total}", parse_style(BONE))
        if height >= 5:
            draughts = len(self.state.floor_draughts)
            marks = "●" * min(3, draughts) + "○" * max(0, 3 - draughts)
            pack = len([item for item in self.state.inventory if item.heal > 0])
            buffer.text(x + 2, y + 2, f"PACK {pack}", parse_style(ASH))
            buffer.text(x + 10, y + 2, marks, parse_style("dim #a855f7"))
        if height >= 6:
            ready = self.battle.special_ready()
            buffer.text(x + 2, y + 3, "THE VOID", parse_style(ASH))
            buffer.text(
                x + 12,
                y + 3,
                "ready" if ready else "spent",
                parse_style("bold bright_yellow" if ready else "grey30"),
            )
        if height >= 7:
            buffer.text(x + 2, y + height - 2, "esc  leave the arena", parse_style(ASH))

    def _draw_commands(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The verbs, arranged the way every menu in this game is.

        The ask is drawn dim when the dark will not answer: a verb that costs a
        turn to refuse is a verb that punishes curiosity.
        """
        box(buffer, x, y, width, height, title="COMMAND", border=BLOOD, fill=True)
        if height < 4 or width < 12:
            return
        keys = {ATTACK: "a", SPECIAL: "s", ITEM: "i", DEFEND: "d", FLEE: "f"}
        rows = [(keys[verb], verb.upper()) for verb in VERBS[: height - 2]]
        chosen = self.verb if self.verb < len(rows) else 0
        ready = self.battle.special_ready()
        for index, (key, label) in enumerate(rows):
            lit = index == chosen
            marker = "►" if lit else " "
            verb = VERBS[index]
            if lit:
                style = parse_style(f"bold {BONE}")
            elif verb == SPECIAL and not ready:
                style = parse_style("grey23")
            else:
                style = parse_style(ASH)
            buffer.text(x + 2, y + 1 + index, f"{marker} {key}  {label}", style)

    @staticmethod
    def _bar(
        buffer: PatternBuffer,
        x: int,
        y: int,
        cells: int,
        ratio: float,
        thin: bool = False,
    ) -> None:
        """A health bar: filled, then empty, in the colour the ratio has earned.

        ``thin`` draws it half a cell tall, which is what the floor wants -- a
        stripe under a monster rather than a second panel -- and the plate in the
        corner keeps its full height, because there the bar *is* the panel.
        """
        filled = max(0, min(cells, round(cells * ratio)))
        ink, hollow = ("▄", "▄") if thin else ("█", "░")
        colour = (
            "bright_green"
            if ratio > 0.5
            else "bright_yellow"
            if ratio > 0.25
            else "bright_red"
        )
        buffer.text(x, y, ink * filled, parse_style(colour))
        buffer.text(x + filled, y, hollow * (cells - filled), parse_style("grey19"))
