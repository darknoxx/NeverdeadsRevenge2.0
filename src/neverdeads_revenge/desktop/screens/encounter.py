"""The floor turning into a fight.

The arena used to *arrive*: one frame the dungeon, the next a room with monsters
standing in it, and a hard cut was the only thing a player ever saw of the
moment a fight starts. This is that moment -- the step the hero took, the thing
he walked into, and the room coming up around it.

Three movements, and the whole of it is about a second:

* **the hit.** White, a shove, and rings going out from the square the monster
  was standing on, with the encounter's own sting. This is the part that has to
  read instantly: the player looked away from the sidebar for one keypress and
  the game has to say *that was a monster*.
* **the letter.** The monster's glyph -- which is what it *is* in the dungeon --
  comes up out of its own square at the camera until it fills the room. Nothing
  is scaled: this game's letters are drawn at any size, so the thing rushing at
  the player is the same glyph that was standing on the floor a moment ago,
  which is the one promise the arena was built on.
* **the white.** The frame goes out in the colour of the first blow, and the
  arena is standing where it was. The cut is still there; it is hidden under a
  flash, which is what a cut is *for*.

Nothing here knows a rule about fights. It knows where the monster stood, what
its letter looks like, and how long each of the three movements takes.

And like the other screens with a pixel pass, it does not *draw* any of it: it
works out the numbers -- how dark, which rings, which streaks, how big the
letter is and where -- and hands them over as a `Turn`. The Qt build paints them
with a `QPainter` and the second front end paints them with pygame, and there is
one idea of what the turning *is* rather than two.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..theme import parse_style
from .base import Screen

__all__ = ["EncounterScreen", "Letter", "Ring", "Streak", "Turn"]

#: The whole turning, in seconds: the step, the letter, and the white. Long
#: enough to be a moment and short enough not to be a wait -- a transition the
#: player starts drumming through is a transition that has overstayed.
LIFE = 1.15
#: The hit: white, and the rings going out of the square that was walked into.
FLASH_IN = 0.24
#: When the letter starts coming and when it has the room to itself.
GROW_FROM = 0.10
GROW_TO = 0.86
#: How tall the letter starts and how tall it ends: from the size it has on the
#: floor to bigger than the frame, so the last thing seen is its ink.
LETTER_FROM = 1.6
LETTER_TO = 13.0
#: When the streaks start and stop, and when the room starts going dark under
#: everything: the map has to *leave*, not be covered up.
STREAK_FROM = 0.42
STREAK_TO = 0.92
DIM_FROM = 0.18
DIM_TO = 0.88
#: How dark the floor gets before the white takes it, and how long the white
#: takes to come all the way up.
DIM = 0.82
WHITE_FROM = 0.86
#: The colour the step is struck in. Pale, and not any monster's own colour: it
#: is the room's reaction, and every fight in this game starts the same way.
BLOW = "#f2f7ff"

#: The delays of the three rings, and how far out they reach as a share of the
#: frame's larger side.
RING_DELAYS = (0.0, 0.09, 0.18)
RING_REACH = 0.6
#: The streaks: how many, and how far out they start and end.
STREAKS = 28
STREAK_NEAR = 60.0
STREAK_SPAN = 420.0
STREAK_LONG = 40.0
STREAK_STRETCH = 260.0
#: And the floor's own squash: this room is a floor seen at an angle, and so is
#: everything on it -- an ellipse and not a circle, a streak that is flattened.
FLAT = 0.72


def _ease(progress: float) -> float:
    """Slow, then all at once: a thing coming *at* the camera is not a thing
    sliding across it. The last third of the movement covers half the frame."""
    return progress * progress


@dataclass(frozen=True)
class Ring:
    """One ring going out of the square that was walked into."""

    x: float
    y: float
    rx: float
    ry: float
    alpha: int
    width: int


@dataclass(frozen=True)
class Streak:
    """One line flying out of the middle of the room."""

    x0: float
    y0: float
    x1: float
    y1: float
    alpha: int


@dataclass(frozen=True)
class Letter:
    """The monster, in the only shape it has ever had on the floor.

    Held by its *centre*, because that is the one thing both painters can agree
    about: a face has an advance and a cap height and a blitter has a cell, and
    neither of them is the other's business.
    """

    glyph: str
    colour: str
    x: float
    y: float
    size: int
    weight: float


@dataclass(frozen=True)
class Turn:
    """One frame of the turning, as numbers."""

    origin: tuple[float, float]
    dim: float = 0.0
    rings: tuple[Ring, ...] = field(default_factory=tuple)
    streaks: tuple[Streak, ...] = field(default_factory=tuple)
    letter: Letter | None = None
    white: float = 0.0


class EncounterScreen(Screen):
    """One step, played out: the hit, the letter, and the white."""

    #: The floor is still drawn under it, and has to be: the whole point is that
    #: the *dungeon* turns into the fight, and a black square that became an
    #: arena would be a cut with a longer cut in it.
    modal = False
    #: Always making something move, so the app gives it a beat per frame.
    animating = True

    def __init__(self, trigger, battle) -> None:
        #: The monster that was walked into, and the fight that is already
        #: decided about it: the turn is a *view* of an encounter the domain has
        #: had, and delaying the rules would only be delaying them.
        self.trigger = trigger
        self.battle = battle
        self.age = 0.0
        self._size: tuple[int, int] | None = None
        self._struck = False

    # -- drawing ------------------------------------------------------------
    def draw(self, buffer, app) -> None:
        # Nothing into the grid: the map under this screen is the picture, and
        # everything this screen does to it happens in pixels.
        self._size = (buffer.cols, buffer.rows)

    def _origin(self, app, cell_w: int, cell_h: int) -> tuple[float, float] | None:
        """Where the monster was standing, in the frame's own pixels."""
        if self._size is None or app.run is None:
            return None
        cols, rows = self._size
        position = getattr(self.trigger, "position", None)
        if position is None:
            return None
        from ..render import screen_point

        return screen_point(app.run, position, cols, rows, cell_w, cell_h)

    def frame(self, width: float, height: float, cell_w: int, cell_h: int, app) -> Turn | None:
        """The turning at this age, as the numbers a painter needs.

        Everything the three movements are made of, worked out once and in one
        place: how dark the floor has gone, where the rings are and how wide,
        where the streaks run, how big the letter is and where its middle sits,
        and how far up the white has come. A painter has no numbers of its own.
        """
        origin = self._origin(app, cell_w, cell_h)
        if origin is None:
            return None
        ox, oy = origin
        blow = parse_style(BLOW).fg

        dim = DIM * _clamp((self.age - DIM_FROM) / (DIM_TO - DIM_FROM))

        rings: list[Ring] = []
        reach = max(width, height) * RING_REACH
        for delay in RING_DELAYS:
            young = self.age - delay
            if young < 0 or young > FLASH_IN * 2:
                continue
            progress = young / (FLASH_IN * 2)
            radius = 16.0 + progress * reach
            rings.append(
                Ring(
                    x=ox,
                    y=oy,
                    rx=radius,
                    ry=radius * 0.62,
                    alpha=int(220 * (1.0 - progress)),
                    width=max(1, int(6 * (1.0 - progress))),
                )
            )

        streaks: list[Streak] = []
        if STREAK_FROM < self.age < STREAK_TO:
            progress = (self.age - STREAK_FROM) / (STREAK_TO - STREAK_FROM)
            alpha = int(150 * math.sin(progress * math.pi))
            near = STREAK_NEAR + progress * STREAK_SPAN
            far = near + STREAK_LONG + progress * STREAK_STRETCH
            for index in range(STREAKS):
                angle = index * math.pi / (STREAKS / 2) + 0.11
                streaks.append(
                    Streak(
                        x0=ox + math.cos(angle) * near,
                        y0=oy + math.sin(angle) * near * FLAT,
                        x1=ox + math.cos(angle) * far,
                        y1=oy + math.sin(angle) * far * FLAT,
                        alpha=alpha,
                    )
                )

        letter = None
        progress = _ease(_clamp((self.age - GROW_FROM) / (GROW_TO - GROW_FROM)))
        if progress > 0:
            size = round(cell_h * (LETTER_FROM + progress * (LETTER_TO - LETTER_FROM)))
            letter = Letter(
                glyph=getattr(self.trigger, "glyph", "") or "?",
                colour=getattr(self.trigger, "color", "#ffffff"),
                x=ox + (width / 2.0 - ox) * progress,
                y=oy + (height / 2.0 - oy) * progress,
                size=size,
                weight=max(3.0, size / 22.0),
            )

        white = max(
            _clamp(self.age / FLASH_IN) * (1.0 - self.age / FLASH_IN),
            _clamp((self.age - WHITE_FROM) / (LIFE - WHITE_FROM)),
        )
        return Turn(
            origin=(ox, oy),
            dim=dim,
            rings=tuple(rings),
            streaks=tuple(streaks),
            letter=letter,
            white=min(1.0, white),
        )

    def paste(self, image, app) -> None:
        """The three movements, over whatever the floor drew, in Qt.

        The numbers come from :meth:`frame`; this is the painter and nothing
        else, which is what lets the front end without a `QPainter` play the same
        turning in its own pixels.
        """
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen

        from ..buffer import qcolour

        cell_w, cell_h = app.font.cell_w, app.font.cell_h
        turn = self.frame(float(image.width()), float(image.height()), cell_w, cell_h, app)
        if turn is None:
            return
        width, height = float(image.width()), float(image.height())
        blow = parse_style(BLOW).fg

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)
        if turn.dim > 0:
            painter.setOpacity(turn.dim)
            painter.setBrush(QColor(0, 0, 0))
            painter.drawRect(QRectF(0.0, 0.0, width, height))
            painter.setOpacity(1.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for ring in turn.rings:
            ink = QColor(BLOW)
            ink.setAlpha(ring.alpha)
            painter.setPen(QPen(ink, ring.width))
            painter.drawEllipse(
                QRectF(ring.x - ring.rx, ring.y - ring.ry, ring.rx * 2, ring.ry * 2)
            )
        if turn.streaks:
            ink = QColor(BLOW)
            ink.setAlpha(turn.streaks[0].alpha)
            painter.setPen(QPen(ink, 2))
            for streak in turn.streaks:
                painter.drawLine(
                    QPointF(streak.x0, streak.y0), QPointF(streak.x1, streak.y1)
                )
        if turn.letter is not None:
            self._paste_letter(painter, turn.letter)
        painter.setPen(Qt.PenStyle.NoPen)
        if turn.white > 0:
            painter.setOpacity(turn.white)
            painter.setBrush(QColor(BLOW))
            painter.drawRect(QRectF(0.0, 0.0, width, height))
            painter.setOpacity(1.0)
        painter.end()

    def _paste_letter(self, painter, letter: Letter) -> None:
        """The monster's letter, at its size and in its own colour.

        Two passes, a dark copy under a bright one, so the edge of it is the
        game's own edge and not a drop shadow -- the same two passes the arena
        draws every letter with.
        """
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QFontMetrics
        from PySide6.QtGui import QColor

        from ..buffer import qcolour
        from .battle import letter_font

        font = letter_font(letter.size).bold
        metrics = QFontMetrics(font)
        painter.setFont(font)
        left = letter.x - metrics.horizontalAdvance(letter.glyph) / 2.0
        baseline = letter.y + metrics.capHeight() / 2.0
        ink = parse_style(letter.colour).fg
        painter.setPen(QColor(0, 0, 0, 255).darker(340))
        painter.drawText(QPointF(left, baseline + letter.weight), letter.glyph)
        painter.setPen(qcolour(ink))
        painter.drawText(QPointF(left, baseline), letter.glyph)

    # -- the clock ----------------------------------------------------------
    def step(self, dt: float, app) -> None:
        """A frame went by: age it, and hand the room over at the end."""
        self.age += dt
        if not self._struck:
            # The first frame is the moment of the step, and it is the only
            # frame that gets to make the noise: everything after it is the
            # fight that noise promised.
            self._struck = True
            app.play("encounter")
            app.view.shake(strength=9, seconds=0.45)
            origin = self._origin(app, app.font.cell_w, app.font.cell_h)
            if origin is not None:
                app.effects.spark(origin, getattr(self.trigger, "color", BLOW), 34)
        if self.age >= LIFE:
            self.hand_over(app)

    def hand_over(self, app) -> None:
        """The turning is done: the arena takes the screen, in this screen's
        place, so nothing is left underneath still drawing a dungeon."""
        app.enter_battle(self.battle)

    # -- input --------------------------------------------------------------
    def key(self, name: str, event, app) -> bool:
        """Everything goes nowhere: a moment that a drummed key can cut short is
        a moment the player will never see."""
        return True


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
