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

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QImage,
    QPainter,
    QPen,
    QPolygonF,
    QRadialGradient,
    QTransform,
)

from ...game.battle import (
    ATTACK,
    DEFEND,
    FLEE,
    ITEM,
    SPECIAL,
    VERBS,
    Battle,
    Flourish,
    Guarded,
    Over,
    Said,
    Struck,
)
from ...game.specials import SPECIALS, Special, special_by_key
from ...game.state import LogKind
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
#: The verbs that have to be pointed at somebody. Confirming one of these opens
#: the aim instead of spending the turn: the trick is picked and *then* the
#: monster, which is the order every fight in this genre ever had -- and the
#: order a player can see, because the arrow is on the room and the choice is a
#: name in a panel. Quaffing a draught and setting your feet are aimed at nobody
#: and still happen on one key, because a turn spent on nothing is a turn.
AIMED: tuple[str, ...] = (ATTACK, SPECIAL)

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
#: What a blow's word is painted in -- the flash a struck figure wears. Green for
#: the dagger, petrol for the shadow, red for the vein, and the void's own pale
#: light: the tricks are asked for in words and answered in colour.
FLAIR_COLOURS: dict[str, str] = {
    # Noxx: the dagger, the shadow, the opened vein, the step, the void.
    "left_hand": "#5bd75b",
    "atritas": "#2ee6cf",
    "open_vein": "#d83a3a",
    "between_blows": "#b06bff",
    "the_void": "#e8ffff",
    # Yeti: the mountain, the rime, the hoarfrost, the stillness, the wall.
    "avalanche": "#cfe8ff",
    "rime": "#9fd8f5",
    "hoarfrost": "#bff0ff",
    "stillness": "#7fd4ff",
    "frozen_fortress": "#dff4ff",
    # Walkyrion: the note, the throw, the true note, the echo, the bell.
    "first_note": "#ffd34d",
    "bells_throw": "#ffc21f",
    "true_note": "#ffb000",
    "echoing_cut": "#ffe9a8",
    "shattered_bell": "#fff3c4",
}
#: How long a wall of ice stands in front of the hero after it is raised.
WALL_LIFE = 1.6
#: How long a blow's own flourish lasts. Inside the beat that carries it, so the
#: fight still reads one blow at a time -- but long enough to be *seen*, which is
#: the whole point of fifteen tricks looking like fifteen tricks.
FLOURISH_LIFE = 0.55
#: How many sparks each look throws. The loud ones throw more: a shatter should
#: look like the mountain, and a rime like a bit of frost.
SPARKS: dict[str, int] = {
    "slash": 14,
    "shadow": 22,
    "bleed": 18,
    "trail": 16,
    "dissolve": 30,
    "shatter": 34,
    "frost": 20,
    "pulse": 22,
    "aura": 24,
    "ring": 26,
    "throw": 24,
    "wave": 36,
    "wall": 20,
}
#: The three shapes that belong to the *hero* and not to what he hit: an ice
#: wall in front of him, a glow on him, and a cold ring out of him. They are the
#: tricks that are not blows, so they have nowhere else to be seen.
SELF_LOOKS: frozenset[str] = frozenset({"wall", "aura", "pulse"})
#: And how hard each one knocks the camera. The ultimates land like a floor.
SHAKES: dict[str, int] = {
    "shatter": 6,
    "wave": 6,
    "dissolve": 7,
    "throw": 4,
}
#: Everything that lands *moves* what it hit: the figure is shoved a fraction of
#: its own height up the room and drifts back. A thrown monster goes the whole
#: way (that is the trick); a stick hit moves a quarter of it, and the number
#: says how much it cost. Weight is a thing that is seen and not only read.
THROWN = 1.2
SHOVES: dict[str, float] = {
    "shatter": 0.7,
    "wave": 0.6,
    "dissolve": 0.8,
    "throw": THROWN,
    "ring": 0.45,
    "slash": 0.35,
    "bleed": 0.3,
    "frost": 0.3,
    "shadow": 0.4,
    "trail": 0.35,
}
SHOVE = 0.26
#: How much more of a shove a crit is.
CRIT_SHOVE = 1.6
#: How long the room holds still on a landed blow, and the same by shape. This is
#: a hitstop and it is the whole of the weight: three frames in which *nothing*
#: moves, so the hit lands on a room that has stopped rather than on one that is
#: politely carrying on. Short enough to feel like impact and not like a stall.
HITSTOP = 0.05
CRIT_STOP = 0.09
HITSTOPS: dict[str, float] = {
    "shatter": 0.11,
    "wave": 0.11,
    "dissolve": 0.14,
    "throw": 0.09,
    "shadow": 0.08,
    "ring": 0.07,
    "frost": 0.07,
}
#: The wash over the whole room when a blow lands, and how long it holds. Drawn
#: last and felt first: on a small screen a frame of colour across everything is
#: the loudest thing there is, and it costs one rectangle.
FLASH_LIFE = 0.13
FLASH_ALPHA = 0.10
FLASH_HARD_ALPHA = 0.18
#: The blows that shake the *seat* rather than the figure: the three that cost
#: the whole floor rather than the fight's exchange. A crit is in the same league
#: whatever it was struck with.
HARD_BLOWS: frozenset[str] = frozenset({"shatter", "wave", "dissolve"})
#: How long one event holds the stage. A fight that printed a whole round at
#: once would be a spreadsheet with letters drawn on it.
BEAT = 0.42
#: How long a number hangs in the air over a head.
POPUP_LIFE = 0.85
#: The idle breath: how fast a figure rises and falls, and how far. Small on
#: purpose -- two pixels is the difference between a fight and a photograph.
BOB_SPEED = 3.4
BOB_HEIGHT = 2
#: How long a strike takes, and when inside it the blow lands. A blink: out
#: where the striker stands, back in beside what it is hitting, and gone again
#: before the beat that started it is over.
STRIKE = 0.62
IMPACT_AT = STRIKE * 0.46
#: How long a struck figure shakes, and how far.
JOLT = 0.26
JOLT_PIXELS = 3
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


@dataclass
class Wash:
    """The colour across the whole room when a blow lands.

    Its own thing because it has two moments and not one: it is *set* when the
    swing begins and it *lands* when the blow does, and the room only holds still
    on the second of those. A freeze that came with the decision to swing would
    be a freeze in the wrong place -- the pause before a punch is not the punch.
    """

    colour: str
    when: float
    strength: float
    stop: float
    #: Whether the room has already stopped for it. Set once, on the frame the
    #: impact falls in, so that the freeze is spent at the impact and not before.
    spent: bool = False


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
        "phase",
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
        phase: float = 0.0,
    ) -> None:
        self.actor = actor
        #: Where this figure is in its own breath. Different for every figure, or
        #: a row of them would rise and fall like a wave.
        self.phase = phase
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
        #: Whether the five are being looked at: SPECIAL opens a list rather than
        #: spending the first one it finds, because a player who cannot choose is
        #: not being offered anything.
        self.picking = False
        self.special = 0
        #: Whether the arrow is out on the room, waiting for a monster to be
        #: walked to and taken. The trick is chosen first and the *victim* second:
        #: a turn that named a monster in the rules and hid it from the player
        #: would be a choice made by whoever was standing under the arrow.
        self.aiming = False
        #: Where the aim was opened from, so escape goes back there: ``"list"``
        #: for the five, ``"verbs"`` for the command panel.
        self._aim_from = "verbs"
        #: Which of the five the aim is going to spend. The list picks the trick
        #: and the arrow picks the monster, so the trick has to be kept.
        self._picked: str | None = None
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
        #: The arena's own clock, in seconds. The idle breath and every phase of
        #: a strike are read off it, so nothing here owns a timer.
        self._clock = 0.0
        #: Who is mid-strike: ``id(attacker) -> (id(target), when it began)``.
        self._strikes: dict[int, tuple[int, float]] = {}
        #: Who was struck: when the blow inside their strike lands, and the
        #: colour the trick that landed it is painted in.
        self._hurts: dict[int, tuple[float, str, str]] = {}
        #: Who has just been thrown back, by how far and when. A knockback is a
        #: *place* and not a colour, so it is kept apart from the flashes.
        self._knocked: dict[int, tuple[float, float]] = {}
        #: The room holding still on a landed blow, in seconds left to hold.
        self._hitstop = 0.0
        #: The wash over the room on a landed blow. The loudest thing here and
        #: the cheapest -- and named apart from the white flash a *sprite* wears,
        #: which is the blow's mark on the figure rather than on the room.
        self._wash: Wash | None = None
        #: White silhouettes of the sprites, made once and reused: a hit flash is
        #: the figure painted solid white for a few frames.
        self._flashes: dict[tuple[int, str], QImage] = {}
        #: The hero's sprite washed petrol, for the shadow that goes in his place.
        self._shadows: dict[int, QImage] = {}
        #: What a trick left standing on the *hero*: its look, its colour, when.
        self._self: tuple[str, str, float] | None = None
        #: A trick that was not a blow: its word, and when it happened. Only the
        #: hero raises one, and only one at a time -- a wall and an aura at once
        #: would be two answers to one turn.
        self._flourish: tuple[str, float] | None = None

    # -- the contract -------------------------------------------------------
    def draw(self, buffer: PatternBuffer, app) -> None:
        #: The size this screen is being drawn at, remembered: the letters are
        #: placed in pixels and the paste step has to agree with the grid pass
        #: about where the floor is, and the grid pass is the one that knows.
        self._size = (buffer.cols, buffer.rows)
        buffer.clear()
        areas = self._areas(buffer.cols, buffer.rows)
        self._draw_ground(buffer, areas["ground"])
        self._draw_health(buffer, areas["ground"])
        self._draw_log(buffer, areas["log"])
        self._draw_plate(buffer, *areas["plate"])
        self._draw_commands(buffer, *areas["commands"])

    def paste(self, image, app) -> None:
        """The room, the models, and everything that moves in them.

        Drawn here rather than in the grid because neither a monster nor a block
        of masonry fits in a cell -- and drawn in two passes, because a striker
        lands *in front of* what it is hitting: everybody stands first, and the
        one mid-blow is painted over the top of them.
        """
        cols, rows = self._dims(app)
        figures = self._figures(cols, rows, app.font)
        field = self._field(cols, rows, app.font.cell_w, app.font.cell_h)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        self._paste_walls(painter, field)
        # The shadows first: they live on the floor, so a figure standing on one
        # stands on it rather than carrying it around.
        for figure in figures:
            self._paste_shadow(painter, figure, app.font.cell_w, app.font.cell_h)
        # Then the ones in the wrong order -- a monster that came for the hero
        # lands *behind* him and is covered by him, which is where it came from;
        # the hero lands over whatever he is hitting. Everybody else is standing
        # still and goes in the middle.
        hero = self.battle.hero
        behind = [
            figure
            for figure in figures
            if id(figure.actor) in self._strikes and figure.actor is not hero
        ]
        front = [
            figure
            for figure in figures
            if id(figure.actor) in self._strikes and figure.actor is hero
        ]
        for figure in behind:
            self._paste_figure(painter, figure, app, figures)
        for figure in figures:
            if figure not in behind and figure not in front:
                self._paste_figure(painter, figure, app, figures)
        for figure in front:
            self._paste_figure(painter, figure, app, figures)
        for figure in figures:
            if figure.chosen:
                self._paste_arrow(painter, figure, app.font.cell_h)
        for popup in self._popups:
            self._paste_popup(painter, popup)
        if self.verdict is not None:
            self._paste_verdict(painter, cols, rows, app)
        self._paste_wash(painter, image)
        painter.end()

    def _paste_wash(self, painter: QPainter, image) -> None:
        """The wash over the whole room on a landed blow.

        Drawn last, over everything including the verdict, because it is not a
        thing in the room -- it is the room's own reaction to being hit, and it
        costs one rectangle to make a small fight feel like it has weight.
        """
        if self._wash is None:
            return
        age = self._clock - self._wash.when
        if age < 0:
            return
        if age > FLASH_LIFE:
            self._wash = None
            return
        tint = QColor(self._wash.colour)
        painter.setOpacity(self._wash.strength * (1.0 - age / FLASH_LIFE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint)
        painter.drawRect(QRectF(0.0, 0.0, float(image.width()), float(image.height())))
        painter.setOpacity(1.0)

    # -- where a figure stands, this frame ---------------------------------
    def _paste_figure(self, painter: QPainter, figure: Staged, app, figures) -> None:
        """One figure, where its own breath and its own strike put it.

        Every moving part of a fight is decided here and nowhere else: a figure
        stands where the stage says, rises and falls on the arena's clock, and --
        while it is striking -- is somewhere else and see-through.
        """
        cell_w, cell_h = app.font.cell_w, app.font.cell_h
        # A figure breathes on its own phase, taken from its own place on the
        # floor: a row of monsters rising together would look like a wave.
        raise_px = 0
        if figure.actor.stats.alive:
            # Off its own phase, taken from its place in the row: side by side,
            # rising and falling together, they would read as one wave -- and the
            # hero, who stands in front of all of them, has a phase of his own.
            raise_px = round(
                math.sin(self._clock * BOB_SPEED + figure.phase) * BOB_HEIGHT
            )
        home = figure.row * cell_h - THICKNESS
        # Thrown back: up the room and drifting home again, which is where
        # "thrown" is read -- a bell's throw that only changed the queue would be
        # a rule nobody could see.
        home -= self._knockback(figure, cell_h)
        cx, baseline, opacity = figure.cx, home - raise_px, 1.0
        pose = self._strike_pose(figure, figures, home, cell_w, cell_h)
        if pose is not None:
            cx, baseline, opacity = pose
        else:
            cx += self._jolt(figure)
        self._paste_extra(painter, figure, app, figures, cell_w, cell_h, baseline)
        self._paste_model(painter, figure, cx, baseline, opacity, app.font)
        self._paste_flourish(painter, figure, cell_w, cell_h, baseline)
        if figure.actor is self.battle.hero:
            self._paste_self(painter, figure, cell_w, cell_h, baseline)

    def _paste_shadow(
        self, painter: QPainter, figure: Staged, cell_w: int, cell_h: int
    ) -> None:
        """A pool of ground under a figure, soft in *pixels*.

        Drawn rather than written into the grid, because a shadow is the one
        thing here that has to have soft edges: a rectangle of black cells under
        a painted sprite reads as a hole in the floor, and the grid's whole charm
        is that every cell of it has hard ones. The gradient goes to nothing at
        the rim, so the pool fades into the floor instead of stopping.
        """
        width = max(20.0, float(figure.cells * cell_w) * 1.05)
        height = max(6.0, width * 0.24)
        centre_x = float(figure.cx)
        centre_y = float(figure.row * cell_h) - 1.0
        gradient = QRadialGradient(QPointF(centre_x, centre_y), width / 2.0)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 120))
        gradient.setColorAt(0.55, QColor(0, 0, 0, 74))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(
            QRectF(centre_x - width / 2.0, centre_y - height / 2.0, width, height)
        )

    def _strike_pose(
        self,
        figure: Staged,
        figures,
        home: int,
        cell_w: int,
        cell_h: int,
    ) -> tuple[int, int, float] | None:
        """Where a striker is and how solid, or ``None`` if it is standing still.

        The blow is a blink: the striker goes out where it stands, comes back in
        beside whatever it is hitting, and is gone again before the beat that
        started it is over. Nothing *travels* -- a fight this size has no room for
        a walk, and a monster that walked over would make every round twice as
        long as the blow it holds -- but the eye reads the two places as one
        movement, which is the whole trick.
        """
        strike = self._strikes.get(id(figure.actor))
        if strike is None:
            return None
        target_id, began, flair = strike
        look = self._look(flair)
        progress = (self._clock - began) / STRIKE
        if progress >= 1.0:
            del self._strikes[id(figure.actor)]
            return None
        near_x, near_y = self._beside_target(
            figure, target_id, figures, home, cell_w, cell_h
        )
        if look in ("shadow", "trail"):
            # Neither of these moves the hero. The shadow is a second figure
            # going instead of him, and the trail is where he *is*: a step so
            # quick that the room cannot follow it.
            return figure.cx, home, 1.0
        if look == "dissolve":
            # Giving in: he is not in the room for the middle of it.
            return figure.cx, home, 0.10 if 0.22 < progress < 0.78 else 1.0
        if progress < 0.20:  # out, where it stands
            return figure.cx, home, 1.0 - progress / 0.20
        if progress < 0.34:  # in, beside the one being hit
            return near_x, near_y, (progress - 0.20) / 0.14
        if progress < 0.70:  # the blow itself
            return near_x, near_y, 1.0
        if progress < 0.84:  # out again, over there
            return near_x, near_y, 1.0 - (progress - 0.70) / 0.14
        return figure.cx, home, (progress - 0.84) / 0.16  # back where it belongs

    def _beside_target(
        self,
        figure: Staged,
        target_id: int,
        figures,
        home: int,
        cell_w: int,
        cell_h: int,
    ) -> tuple[int, int]:
        """Where a striker appears, relative to the one it is hitting.

        The hero comes at the monsters from the front, so he lands low and to the
        left of his target -- standing *in front of* it, both of them visible.
        A monster comes for the hero from beyond him, so it lands high and to the
        right: behind him, and under him, because the floor runs away towards the
        top of the room and the hero is standing nearer to the player than it is.
        """
        behind = figure.actor is not self.battle.hero
        for other in figures:
            if id(other.actor) == target_id:
                if behind:
                    return other.cx + cell_w * 3, other.row * cell_h - cell_h
                return other.cx - cell_w * 3, other.row * cell_h + cell_h * 4 // 5
        return figure.cx, home

    @staticmethod
    def _look(flair: str) -> str:
        """How a blow was struck, as its own word -- or ``""`` for a plain one.

        The rules say which *trick* was used; what that trick looks like is the
        screen's to know, so a hero can get a look without the fight learning a
        colour.
        """
        special = special_by_key(flair) if flair else None
        return special.look if special is not None else ""

    def _paste_extra(
        self, painter: QPainter, figure: Staged, app, figures, cell_w: int, cell_h: int, home: int
    ) -> None:
        """What a trick puts on the floor besides the blow.

        Two of the five are *not* the hero moving: ATRITAS sends his shadow, and
        BETWEEN BLOWS leaves echoes of him where he stands. Both are drawn here,
        under and over the figures as they belong, and both are only ever the
        sprite he already has -- there is no second set of art for a shadow.
        """
        strike = self._strikes.get(id(figure.actor))
        if strike is None or figure.sprite is None:
            return
        target_id, began, flair = strike
        look = self._look(flair)
        progress = (self._clock - began) / STRIKE
        image = figure.sprite
        if look == "shadow":
            if not 0.20 < progress < 0.88:
                return
            opacity = min(1.0, (progress - 0.20) / 0.14, (0.88 - progress) / 0.14)
            near_x, near_y = self._beside_target(
                figure, target_id, figures, home, cell_w, cell_h
            )
            painter.setOpacity(max(0.0, opacity) * 0.85)
            painter.drawImage(
                near_x - image.width() // 2, near_y - image.height(), self._shadow(image)
            )
            painter.setOpacity(1.0)
            return
        if look == "trail":
            for dx, fade in ((9, 0.32), (18, 0.20), (27, 0.11)):
                painter.setOpacity(fade)
                painter.drawImage(
                    figure.cx - image.width() // 2 + dx, home - image.height(), image
                )
            painter.setOpacity(1.0)

    def _shadow(self, image: QImage) -> QImage:
        """The same figure, in the colour his shadow is.

        A wash of petrol laid over the sprite's own pixels -- `SourceAtop` keeps
        the alpha it has -- so the shadow is the hero's silhouette and not a
        second drawing of him. Made once and kept.
        """
        cached = self._shadows.get(id(image))
        if cached is None:
            cached = QImage(image.size(), QImage.Format.Format_ARGB32)
            cached.fill(QColor(0, 0, 0, 0))
            painter = QPainter(cached)
            painter.drawImage(0, 0, image)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceAtop
            )
            painter.fillRect(cached.rect(), QColor(12, 64, 62, 200))
            painter.end()
            self._shadows[id(image)] = cached
        return cached

    # -- the flourishes: every trick has its own shape ----------------------
    def _paste_self(
        self, painter: QPainter, figure: Staged, cell_w: int, cell_h: int, baseline: int
    ) -> None:
        """What a trick leaves standing on the *hero*: ice, a glow, or a ring.

        The three that are not blows at all have to show somewhere, and the hero
        is where: the wall stands in front of him, the stillness glows on him, and
        the cold rings out of him.
        """
        if self._self is None:
            return
        look, colour, when = self._self
        age = self._clock - when
        if age < 0:
            return
        if look == "wall":
            if age > WALL_LIFE:
                return
            width = float(figure.cells * cell_w) * 1.25
            # He stands *behind* it: tall enough to cover his legs and no taller.
            height = float(cell_h) * 1.2
            fade = 1.0 - age / WALL_LIFE
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(190, 233, 255, int(120 * fade)))
            painter.drawRect(QRectF(figure.cx - width / 2, baseline - height, width, height))
            painter.setBrush(QColor(255, 255, 255, int(90 * fade)))
            painter.drawRect(
                QRectF(figure.cx - width / 2, baseline - height, width, height * 0.22)
            )
            return
        if age > FLOURISH_LIFE * 1.5:
            return
        if look == "aura":
            self._glow(painter, figure.cx, baseline, cell_w, cell_h, colour, age)
            return
        if look == "pulse":
            self._ripple(painter, figure.cx, baseline - cell_h, colour, age, reach=4.0)

    def _paste_flourish(
        self, painter: QPainter, figure: Staged, cell_w: int, cell_h: int, baseline: int
    ) -> None:
        """The shape a blow made, over the figure that took it.

        Fifteen tricks and not fifteen colours: a slash is a cut, a bleed drips, a
        shatter throws shards, a rime leaves crystals, a ring travels, a wave goes
        through the room -- and the rest climb, so that every one of them *moves*
        and none of them is only a tint.
        """
        struck = self._hurts.get(id(figure.actor))
        if struck is None:
            return
        when, colour, look = struck
        age = self._clock - when
        if age < 0 or age > FLOURISH_LIFE:
            return
        if look in SELF_LOOKS:
            # Drawn on the hero instead: a wall on what it hit would be a wall in
            # the wrong room.
            return
        top = baseline - cell_h * 1.4
        # Every trick opens with the same thing a punch does: a flash where it
        # landed. The shapes below say *which* trick; the flash says *that* it
        # hit, and it is what makes a hit read at a glance.
        self._impact(painter, figure.cx, baseline - cell_h * 1.05, colour, age)
        if look == "slash":
            self._slash(painter, figure.cx, top, baseline, cell_w, colour, age)
        elif look == "bleed":
            self._drips(painter, figure.cx, top, cell_h, colour, age)
        elif look == "shatter":
            self._shards(painter, figure.cx, top, cell_w, colour, age)
        elif look == "frost":
            self._crystals(painter, figure.cx, top, cell_w, colour, age)
        elif look == "ring":
            self._ripple(painter, figure.cx, top, colour, age, reach=3.4)
        elif look == "wave":
            self._band(painter, figure.cx, top, cell_w, colour, age)
        elif look == "dissolve":
            self._ripple(painter, figure.cx, top, colour, age, reach=5.5)
            self._climb(painter, figure.cx, top, cell_h, colour, age, count=6)
        elif look == "throw":
            self._climb(painter, figure.cx, top, cell_h, colour, age, count=5, up=True)
        elif look == "shadow":
            self._climb(painter, figure.cx, top, cell_h, colour, age, count=6)
        else:
            self._climb(painter, figure.cx, top, cell_h, colour, age, count=4)

    # -- the shapes themselves, in pixels ----------------------------------
    def _impact(self, painter, cx, cy, colour, age) -> None:
        """The flash of a landed blow: bright, brief, and gone before the shape."""
        if age > 0.20:
            return
        t = age / 0.20
        radius = 12.0 + t * 30.0
        tint = QColor(colour)
        gradient = QRadialGradient(QPointF(cx, cy), radius)
        gradient.setColorAt(0.0, QColor(255, 255, 255, int(235 * (1.0 - t))))
        gradient.setColorAt(
            0.45, QColor(tint.red(), tint.green(), tint.blue(), int(160 * (1.0 - t)))
        )
        gradient.setColorAt(1.0, QColor(tint.red(), tint.green(), tint.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

    def _slash(self, painter, cx, top, baseline, cell_w, colour, age) -> None:
        """A cut: a bright line through the figure, white at its core.

        Two lines and not one, because a cut has a *side*: the coloured edge is
        wider and fades, and the white one stays, so the slash is still there at
        the end of the beat instead of having been a tint that passed.
        """
        grow = min(1.0, age / 0.09)
        half = cell_w * 2.6 * grow
        fade = 1.0 - min(1.0, age / FLOURISH_LIFE)
        edge = QColor(colour)
        edge.setAlpha(int(255 * fade))
        painter.setPen(QPen(edge, 5))
        painter.drawLine(QPointF(cx - half, top - 6), QPointF(cx + half, baseline - 4))
        core = QColor("#ffffff")
        core.setAlpha(int(255 * (0.5 + 0.5 * fade)))
        painter.setPen(QPen(core, 2))
        painter.drawLine(
            QPointF(cx - half * 0.75, top - 1), QPointF(cx + half * 0.75, baseline - 9)
        )

    def _drips(self, painter, cx, top, cell_h, colour, age) -> None:
        """A wound: a stain, and drops coming off it that keep going down."""
        stain = QColor(colour)
        stain.setAlpha(200)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(stain)
        painter.drawEllipse(QRectF(cx - 9, top + 2, 18, 7))
        fall = min(1.0, age / 0.42)
        for index in range(4):
            x = cx - 15 + index * 10
            y = top + 6 + fall * cell_h * 1.4 + index * 3
            drop = QColor(colour)
            drop.setAlpha(int(255 * (1.0 - fall)))
            painter.setPen(QPen(drop, 2))
            painter.drawLine(QPointF(x, y), QPointF(x, y + 8))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(drop)
            painter.drawEllipse(QRectF(x - 2, y + 8, 4, 4))

    def _shards(self, painter, cx, top, cell_w, colour, age) -> None:
        """A shatter: a dozen wedges of ice thrown out of the figure."""
        throw = min(1.0, age / 0.30)
        shard = QColor(colour)
        shard.setAlpha(int(255 * (1.0 - throw)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shard)
        for index in range(12):
            angle = index * math.pi / 6 + 0.3
            dx, dy = math.cos(angle), math.sin(angle) * 0.65
            near = 4 + throw * 12
            far = 8 + throw * (cell_w * 2.2)
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(cx + dx * near, top + dy * near),
                        QPointF(cx + dx * far + dy * 3, top + dy * far - dx * 3),
                        QPointF(cx + dx * far - dy * 3, top + dy * far + dx * 3),
                    ]
                )
            )
        core = QColor("#ffffff")
        core.setAlpha(int(200 * (1.0 - throw)))
        painter.setPen(QPen(core, 2))
        for index in range(0, 12, 3):
            angle = index * math.pi / 6 + 0.3
            dx, dy = math.cos(angle), math.sin(angle) * 0.65
            painter.drawLine(
                QPointF(cx + dx * 4, top + dy * 4),
                QPointF(cx + dx * (10 + throw * 9), top + dy * (10 + throw * 9)),
            )

    def _crystals(self, painter, cx, top, cell_w, colour, age) -> None:
        """A rime: crystals on a ring of frost, breathing in and out.

        Twelve of them, each a diamond rather than a square, so the rime reads as
        ice and not as the grid the rest of the screen is made of.
        """
        breathe = 1.0 + 0.22 * math.sin(age * 24)
        radius = cell_w * 1.7 * breathe
        frost = QColor(colour)
        frost.setAlpha(80)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(frost, 1))
        painter.drawEllipse(QRectF(cx - radius, top - radius * 0.55, radius * 2, radius * 1.1))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colour))
        for index in range(12):
            angle = index * math.pi / 6
            x = cx + math.cos(angle) * radius
            y = top + math.sin(angle) * radius * 0.55
            size = 5 if index % 3 == 0 else 3
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(x, y - size),
                        QPointF(x + size, y),
                        QPointF(x, y + size),
                        QPointF(x - size, y),
                    ]
                )
            )

    def _ripple(self, painter, cx, cy, colour, age, *, reach: float) -> None:
        """A ring, and a second one after it: the sound of a thing, twice."""
        for step, delay in ((1.0, 0.0), (0.7, 0.22)):
            t = (age - delay) / FLOURISH_LIFE
            if t < 0:
                continue
            radius = 5 + t * reach * 12
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(colour), max(1, int(step * 3 * (1 - t)))))
            painter.drawEllipse(QRectF(cx - radius, cy - radius * 0.55, radius * 2, radius * 1.1))

    def _band(self, painter, cx, top, cell_w, colour, age) -> None:
        """A wave: a bar of sound going out through the room, both ways."""
        spread = min(1.0, age / (FLOURISH_LIFE * 0.7))
        half = cell_w * 1.5 + spread * cell_w * 14
        fade = max(0, int(255 * (1.0 - spread)))
        bar = QColor(colour)
        bar.setAlpha(fade)
        painter.setPen(QPen(bar, 3))
        painter.drawLine(QPointF(cx - half, top), QPointF(cx + half, top))
        core = QColor("#ffffff")
        core.setAlpha(fade // 2)
        painter.setPen(QPen(core, 1))
        painter.drawLine(QPointF(cx - half, top - 3), QPointF(cx + half, top - 3))

    def _climb(self, painter, cx, top, cell_h, colour, age, *, count: int, up: bool = False) -> None:
        """Sparks climbing off the figure -- or, for a throw, thrown up with it."""
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(count):
            phase = (age * 34 + index * 9) % (cell_h * 1.5)
            rise = phase if up else cell_h * 1.5 - phase
            x = cx - 16 + index * 6 + (3 if up else 0)
            painter.setBrush(QColor(colour))
            painter.drawRect(QRectF(x, top + rise, 3, 3))

    def _glow(self, painter, cx, baseline, cell_w, cell_h, colour, age) -> None:
        """An aura: a pool of colour around the hero, a ring at its rim, sparks.

        Thick at the rim and thin in the middle, because the middle is where the
        hero is: a glow that swallowed him would be a silhouette with nothing in
        it, and this one is *his*.
        """
        breath = 1.0 + 0.16 * math.sin(age * 12)
        width = float(cell_w) * 4.4 * breath
        tint = QColor(colour)
        gradient = QRadialGradient(QPointF(cx, baseline - cell_h * 0.35), width / 2)
        gradient.setColorAt(0.0, QColor(tint.red(), tint.green(), tint.blue(), 55))
        gradient.setColorAt(0.62, QColor(tint.red(), tint.green(), tint.blue(), 90))
        gradient.setColorAt(1.0, QColor(tint.red(), tint.green(), tint.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(
            QRectF(cx - width / 2, baseline - cell_h * 1.0, width, cell_h * 1.2)
        )
        rim = QColor(colour)
        rim.setAlpha(170)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(rim, 2))
        painter.drawEllipse(
            QRectF(cx - width * 0.36, baseline - cell_h * 0.78, width * 0.72, cell_h * 0.66)
        )
        self._climb(painter, cx, baseline - cell_h * 1.2, cell_h, colour, age, count=6, up=True)

    def _knockback(self, figure: Staged, cell_h: int) -> int:
        """How far up the room a shoved figure is, right now.

        Up the room and not across it, because the floor runs away towards the
        top: a shove that moved a monster sideways would be a monster standing
        somewhere it is not, which is the one thing the isometric view cannot
        afford. ``push`` is in cell heights, so the bell's throw and a stick hit
        are the same movement at two sizes.
        """
        knocked = self._knocked.get(id(figure.actor))
        if knocked is None:
            return 0
        when, push = knocked
        age = self._clock - when
        if age < 0:
            return 0
        if age > FLOURISH_LIFE:
            del self._knocked[id(figure.actor)]
            return 0
        # Out fast, home slowly: a knock is not a shove back into place.
        out = min(1.0, age / 0.14)
        back = max(0.0, (age - 0.30) / (FLOURISH_LIFE - 0.30))
        return round(cell_h * push * out * (1.0 - back))

    def _jolt(self, figure: Staged) -> int:
        """How far a struck figure is shaking, in pixels, right now."""
        struck = self._hurts.get(id(figure.actor))
        if struck is None:
            return 0
        age = self._clock - struck[0]
        if age < 0:
            return 0
        if age > JOLT:
            del self._hurts[id(figure.actor)]
            return 0
        return round(math.sin(age * 46.0) * JOLT_PIXELS)

    def _flash(self, image: QImage, colour: str) -> QImage:
        """The figure as a silhouette in ``colour``, made once and kept."""
        cached = self._flashes.get((id(image), colour))
        if cached is None:
            cached = QImage(image.size(), QImage.Format.Format_ARGB32)
            cached.fill(QColor(0, 0, 0, 0))
            painter = QPainter(cached)
            painter.drawImage(0, 0, image)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn
            )
            painter.fillRect(cached.rect(), QColor(colour))
            painter.end()
            self._flashes[(id(image), colour)] = cached
        return cached

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
        if self.battle.over:
            # The fight is decided, but the arena may still be playing the last
            # blow: leaving on a keypress before the verdict has been shown would
            # be the player skipping the one thing they just earned.
            if not self.busy and name in ("enter", "return", "space"):
                app.leave_battle()
            return True
        if self.picking:
            # The five, being looked at: everything goes to the list until it is
            # closed, escape included -- *there* escape is the way back and not
            # the way out, and the list has to hear it before the arena does.
            return self._pick_special(name, app)
        if self.aiming:
            # The arrow, being walked across the room: everything goes to the aim
            # until a monster is taken or the choice is given back.
            return self._aim(name, app)
        if name == "escape":
            # There is no way out of a fight but through it. Fleeing is a *verb*
            # with a price -- everything still standing gets a blow at the hero's
            # back -- and a key that walks out for nothing would make every
            # encounter in the dungeon optional.
            self.lines = [
                *self.lines,
                Said("The only way out of this is through it.", LogKind.PLAIN),
            ][-LOG_LINES:]
            return True
        if self.busy:
            # The fight is talking. It will not be interrupted mid-sentence, or
            # a player drumming on the keyboard would be choosing the next verb
            # for a blow they have not seen land yet.
            return True
        living = self._targets()
        if name in ("left", "h") and living:
            self._walk(-1, app)
            return True
        if name in ("right", "l") and living:
            self._walk(1, app)
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
            self._confirm(app)
            return True
        if name in ("enter", "return", "space"):
            self._confirm(app)
            return True
        return True

    def _confirm(self, app) -> None:
        """Take the highlighted verb.

        SPECIAL is a door rather than a verb: the hero has five ways to spend a
        turn and the player is entitled to pick which. The first available one is
        not good enough, because a choice nobody can make is not a choice -- and
        neither is a monster nobody was shown. So the two verbs that are *aimed*
        open the arrow instead of spending the turn: the trick first, the victim
        second, both of them on the screen.
        """
        if VERBS[self.verb] == SPECIAL:
            self.picking = True
            self.special = 0
            return
        if VERBS[self.verb] in AIMED:
            self.aiming = True
            self._aim_from = "verbs"
            self._picked = None
            return
        self._choose(app)

    def _walk(self, step: int, app) -> None:
        """Move the arrow to another monster, and say so.

        The blip is not decoration. A cursor that moves in silence makes the
        player look down at the panel to find out whether the key registered,
        and a fight is watched on the floor.
        """
        living = self._targets()
        if not living:
            return
        self.target = (self.target + step) % len(living)
        app.play("move")

    def _aim(self, name: str, app) -> bool:
        """A monster is being walked to, and the next enter spends the turn.

        Left and right cross the room, the blip marks every step of it, and the
        note on the way in is the commitment: the arrow says *which*, and the
        ears say that the choice was taken.
        """
        # Left and right only, and not up and down: the row of monsters runs
        # across the room, and a key that walked the arrow "up" would walk it
        # along an axis the room does not have.
        if name in ("left", "h"):
            self._walk(-1, app)
            return True
        if name in ("right", "l"):
            self._walk(1, app)
            return True
        if name == "escape":
            # Back where the choice came from, with the trick still picked: the
            # aim is a step in a menu and not a trap.
            self.aiming = False
            if self._aim_from == "list":
                self.picking = True
            return True
        if name in ("enter", "return", "space", "a"):
            app.play("pick")
            self.aiming = False
            self._choose(app, special=self._picked)
            return True
        return True

    def _list_rows(self, app) -> int:
        """How many names fit in one column of the list, as it is drawn now.

        Asked rather than assumed: the wall the list is drawn on is sized from
        the window, and a jump that used the wrong number would land in the
        middle of the other column.
        """
        cols, rows = self._dims(app)
        return max(1, self._areas(cols, rows)["commands"][3] - 4)

    def _pick_special(self, name: str, app) -> bool:
        """The five, being looked at: pick one, or come back."""
        specials = self.battle.specials()
        index = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4}.get(name)
        if name == "escape":
            self.picking = False
            return True
        rows = self._list_rows(app)
        if name in ("up", "w"):
            self.special = (self.special - 1) % len(specials)
            return True
        if name in ("down", "s"):
            self.special = (self.special + 1) % len(specials)
            return True
        if name in ("left", "h", "right", "l"):
            # The list is two columns, so across is a whole column away -- and it
            # stays where it is rather than wrapping, because a jump that lands
            # somewhere unrelated is a jump that loses the player's place.
            jump = -rows if name in ("left", "h") else rows
            moved = self.special + jump
            if 0 <= moved < len(specials):
                self.special = moved
            return True
        if index is None and name in ("enter", "return", "space"):
            index = self.special
        if index is None or index >= len(specials):
            return True
        chosen = specials[index]
        if self.battle.special_available(chosen):
            # The trick is picked, and the *victim* is still to be picked: the
            # list closes and the arrow takes over, on the floor where the
            # monsters are, with the trick kept for whoever it ends up on.
            self.picking = False
            self.aiming = True
            self._aim_from = "list"
            self._picked = chosen.key
            app.play("pick")
        return True

    @property
    def busy(self) -> bool:
        """Whether the fight still has something to say or show.

        Talking, and only talking: the keyboard is held while the round is being
        played, because a player drumming on enter would be choosing the next
        verb for a blow they have not seen land.
        """
        return bool(self._queue) or self._beat > 0 or bool(self._popups)

    @property
    def animating(self) -> bool:
        """A fight always breathes, so the arena is always being repainted."""
        return True

    def step(self, dt: float, app) -> None:
        """A frame went by: age the numbers, and land the next event.

        Everything the fight does is on this clock -- the beat between blows and
        the life of a damage number -- because a screen that kept a timer of its
        own would keep running after the window it is drawn in has gone.
        """
        if self._hitstop > 0:
            # The room holds still on a landed blow: no clock, no breath, no
            # beat. Three frames in which nothing moves is the difference between
            # a hit that lands on something and a number that arrives politely --
            # and it is spent *inside* the beat, so the round is not longer.
            self._hitstop = max(0.0, self._hitstop - dt)
            return
        self._clock += dt
        if self._wash is not None and not self._wash.spent and self._clock >= self._wash.when:
            # The blow landed inside this frame, so the room stops for the next
            # few: the hitstop is spent *at* the impact and not at the swing.
            self._wash.spent = True
            self._hitstop = self._wash.stop
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

    def _choose(self, app, *, special: str | None = None) -> None:
        """Take the highlighted verb, and queue the round it sets off."""
        living = self._targets()
        target = living[self.target % len(living)] if living else None
        # The state is decided the instant the player commits; what the screen
        # shows is not, and this is where the two are told apart.
        self._snapshot()
        self._queue = list(self.battle.choose(VERBS[self.verb], target, special=special))
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
        if isinstance(event, Flourish):
            self._flourish = (event.flair, self._clock)
            look = self._look(event.flair)
            self._self = (look, FLAIR_COLOURS.get(event.flair, "#ffffff"), self._clock)
            point = self._point_of(event.actor, app)
            if point is not None:
                app.effects.spark(
                    point, FLAIR_COLOURS.get(event.flair, "#ffffff"), SPARKS.get(look, 20)
                )
            if look == "aura":
                point = self._point_of(event.actor, app)
                if point is not None:
                    app.effects.spark(
                        point, FLAIR_COLOURS.get(event.flair, "#ffffff"), 26
                    )
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
            # The number waits for the blow. It is *set* when the swing starts --
            # there is one moment to write it down -- but it must not be read
            # before the sword is in the monster, so its clock starts negative
            # and it appears on the frame the impact falls in.
            number = self._popup(text, colour, figure, app, outcome.crit)
            number.age = -IMPACT_AT
            self._popups.append(number)
            if outcome.hit and not outcome.dodged:
                point = self._point_of(struck.target, app)
                if point is not None:
                    look = self._look(struck.flair)
                    app.view.shake(
                        strength=SHAKES.get(look, 4 if outcome.crit else 2), seconds=0.2
                    )
                # And the whole room takes it: a frame of the trick's own colour
                # across everything, which is what a blow sounds like with the
                # sound off. The heavy ones land harder than a stick does.
                self._wash_blow(struck, app)
        # The strike is recorded whether or not it lands: a swing that missed
        # was still a swing, and a hero who did not move would look like a hero
        # who did nothing.
        self._strikes[id(struck.actor)] = (
            id(struck.target),
            self._clock,
            struck.flair,
        )
        if outcome.hit and not outcome.dodged:
            look = self._look(struck.flair)
            when = self._clock + IMPACT_AT
            self._hurts[id(struck.target)] = (
                when,
                FLAIR_COLOURS.get(struck.flair, "#ffffff"),
                look,
            )
            # Thrown *back*: up the room, which is away from the hero, and back
            # again -- the dungeon's version of the bell only makes it walk. Every
            # other blow shoves a little of the same way, so that a hit moves
            # something whether or not there is a number over it.
            push = SHOVES.get(look, SHOVE) * (CRIT_SHOVE if outcome.crit else 1.0)
            self._knocked[id(struck.target)] = (when, push)
        if not outcome.hit:
            return
        # A shower of sparks in the trick's own colour, from the figure that took
        # it: the flashes say *where*, the particles say *how much*.
        look = self._look(struck.flair)
        point = self._point_of(struck.target, app)
        if point is not None:
            app.effects.spark(
                point,
                FLAIR_COLOURS.get(struck.flair, "#ffffff"),
                SPARKS.get(look, 16),
            )
        if struck.actor is self.battle.hero:
            app.play("kill" if outcome.killed else "crit" if outcome.crit else "hit")
        else:
            app.play("hurt")

    def _wash_blow(self, struck: Struck, app) -> None:
        """What a landed blow does to the *room*: it stops it, and it colours it.

        The two together are the weight. Everything else a hit has -- the shove,
        the sparks, the number -- happens inside a room that is carrying on as
        before, and a room that carries on is a room in which nothing much
        happened. Both are timed at the impact and not at the swing, so they land
        with the blow and not with the decision to throw it.
        """
        look = self._look(struck.flair)
        hard = struck.outcome.crit or look in HARD_BLOWS
        stop = max(
            HITSTOPS.get(look, HITSTOP),
            CRIT_STOP if struck.outcome.crit else 0.0,
        )
        self._wash = Wash(
            colour=FLAIR_COLOURS.get(struck.flair, "#ffffff"),
            when=self._clock + IMPACT_AT,
            strength=FLASH_HARD_ALPHA if hard else FLASH_ALPHA,
            stop=stop,
        )

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
                    phase=index * 1.9,
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
                # In front of the row and out of step with it: the hero breathes
                # on his own, as somebody standing still in front of a crowd does.
                phase=len(monsters) * 1.9 + 0.9,
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

    def _paste_model(
        self,
        painter: QPainter,
        figure: Staged,
        cx: int,
        baseline: int,
        opacity: float,
        font,
    ) -> None:
        """One figure on the floor: its picture if the sheets have one, its
        letter if they do not, with its own opacity and its own place.

        The sprite is drawn at its own size and not scaled -- these are painted
        figures, and a painted figure put through a nearest-neighbour resize looks
        like a mistake -- so what the sheets made is what the arena shows.
        """
        struck = self._hurts.get(id(figure.actor))
        flash_age = None if struck is None else self._clock - struck[0]
        colour = "#ffffff" if struck is None else struck[1]
        look = "" if struck is None else struck[2]
        if flash_age is not None and 0 <= flash_age <= JOLT:
            pass
        else:
            flash_age = None

        if figure.sprite is not None:
            image = figure.sprite
            left = cx - image.width() // 2
            top = baseline - image.height()
            if not figure.actor.stats.alive:
                # A monster that is out of the fight stays where it fell, dimmed
                # rather than removed: a corpse that vanished on the last blow
                # would make the end of a fight unreadable.
                opacity *= 0.45
            painter.setOpacity(opacity)
            painter.drawImage(left, top, image)
            if flash_age is not None:
                painter.setOpacity(opacity * (1.0 - flash_age / JOLT) * 0.85)
                painter.drawImage(left, top, self._flash(image, colour))
            painter.setOpacity(1.0)
            return

        glyph_font = letter_font(figure.size)
        painter.setFont(glyph_font.bold)
        metrics = QFontMetrics(glyph_font.bold)
        left = cx - metrics.horizontalAdvance(figure.glyph) // 2
        ink = parse_style(figure.colour).fg
        if not figure.actor.stats.alive:
            faded = QColor(ink)
            faded.setRed((faded.red() + 20) // 3)
            faded.setGreen((faded.green() + 20) // 3)
            faded.setBlue((faded.blue() + 20) // 3)
            ink = faded
        painter.setOpacity(opacity)
        painter.setPen(ink.darker(320))
        painter.drawText(left, baseline + THICKNESS, figure.glyph)
        if flash_age is not None:
            painter.setPen(QColor(colour))
            painter.setOpacity(opacity * (1.0 - flash_age / JOLT) * 0.85)
        else:
            painter.setPen(ink)
        painter.drawText(left, baseline, figure.glyph)
        painter.setOpacity(1.0)

    def _paste_arrow(self, painter: QPainter, figure: Staged, cell_h: int) -> None:
        """The blade over the chosen one -- the menus' marker, standing up.

        It hangs above the letter rather than beside it, because beside a letter
        is where the next monster is: an arrow that means "this one" has to point
        at the one it means.

        While it is being *aimed*, it also breathes: the same figure rising and
        falling, so the one the arrow is on is moving while all the others are
        still. A marker that stands as still as everything under it is a marker a
        player has to hunt for.
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
        if self.aiming:
            baseline -= round(math.sin(self._clock * 5.0) * 2) - 1
        left = figure.cx - metrics.horizontalAdvance(ARROW) // 2
        painter.setPen(ink.darker(320))
        painter.drawText(left, baseline + THICKNESS, ARROW)
        painter.setPen(ink)
        painter.drawText(left, baseline, ARROW)

    def _paste_popup(self, painter: QPainter, popup: Popup) -> None:
        """A number on its way up and out: the only thing here that moves."""
        if popup.age < 0:
            # Written down, not yet landed. A number over a monster before the
            # blow reaches it is the fight telling the player the future.
            return
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
            # In the figure's own row, which is the one its feet are at the top
            # of: a bar a row lower was a bar floating about on its own.
            self._bar(buffer, left, figure.row, cells, shown / total, thin=True)

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
            # What escape *does* depends on where the player is: out of the arena
            # from the verbs, and one step back from either of the two menus.
            # A footer that lied about the way out is worse than no footer.
            hint = "esc  back" if self.picking or self.aiming else "esc  leave the arena"
            buffer.text(x + 2, y + height - 2, hint, parse_style(ASH))

    def _draw_commands(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The verbs, arranged the way every menu in this game is.

        The ask is drawn dim when the dark will not answer: a verb that costs a
        turn to refuse is a verb that punishes curiosity.
        """
        if self.picking:
            # The list takes the whole strip rather than the verbs' half of it:
            # five names and a sentence about the chosen one do not fit in a
            # column three lines tall, and a list nobody can read is a list
            # nobody can choose from.
            self._draw_specials(
                buffer,
                self._areas(buffer.cols, buffer.rows)["plate"][0],
                y,
                buffer.cols - 2 * self._areas(buffer.cols, buffer.rows)["plate"][0],
                height,
            )
            return
        if self.aiming:
            self._draw_targets(buffer, x, y, width, height)
            return
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

    def _draw_targets(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """Who the arrow is on, said in words.

        The one place in a fight where a monster's name is written on a panel
        rather than spoken in the log: a name under a figure would be a label on
        the room, but this is the *choice*, and a choice has to be readable. The
        arrow on the floor and the name in the panel are the same answer twice,
        which is how a player learns to trust the arrow.
        """
        box(buffer, x, y, width, height, title="TARGET", border=BLOOD, fill=True)
        if height < 3 or width < 12:
            return
        living = self._targets()
        chosen = self.target % len(living) if living else 0
        for index, enemy in enumerate(living[: height - 2]):
            lit = index == chosen
            marker = "►" if lit else " "
            style = parse_style(f"bold {BONE}" if lit else ASH)
            buffer.text(x + 2, y + 1 + index, f"{marker} {enemy.name}"[: width - 2], style)
        buffer.text(x + 2, y + height - 2, "◄ ►  pick", parse_style(ASH))

    def _draw_specials(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The five, across the whole strip the panels share.

        Two columns, because five names and a sentence about the chosen one do
        not fit in a column three lines tall -- and the hint goes in the frame's
        own title row, which is the one line of a panel nobody minds sharing.

        The ones that cannot be spent are dim rather than hidden: a lock is a
        promise, and a name the player can read is what makes a level worth
        reaching for. *Why* one cannot be spent is the fight's to say, in the log,
        when it is asked for; a panel of reasons would be a manual.
        """
        box(
            buffer,
            x,
            y,
            width,
            height,
            title="THE DARK      enter  ask      esc  back",
            border=BLOOD,
            fill=True,
        )
        if height < 4 or width < 24:
            return
        specials = self.battle.specials()
        rows = max(1, height - 4)
        column_w = width // 2
        for index, special in enumerate(specials):
            usable = self.battle.special_available(special)
            chosen = index == self.special
            marker = "►" if chosen else " "
            line = f"{marker} {index + 1}  {special.name}"
            if not usable:
                style = parse_style("grey23")
            elif chosen:
                style = parse_style(f"bold {BONE}")
            else:
                style = parse_style(ASH)
            buffer.text(
                x + 2 + (index // rows) * column_w,
                y + 1 + (index % rows),
                line[: column_w - 2],
                style,
            )
        if specials:
            blurb = specials[min(self.special, len(specials) - 1)].blurb
            rule(buffer, x + 1, y + height - 3, width - 2, ASH)
            buffer.text(x + 2, y + height - 2, blurb[: width - 4], parse_style(ASH))

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
