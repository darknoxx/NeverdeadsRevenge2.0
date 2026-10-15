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
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen

from ..render import screen_point
from ..theme import parse_style
from .base import Screen

__all__ = ["EncounterScreen"]

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


def _ease(progress: float) -> float:
    """Slow, then all at once: a thing coming *at* the camera is not a thing
    sliding across it. The last third of the movement covers half the frame."""
    return progress * progress


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

    def paste(self, image, app) -> None:
        """The three movements, over whatever the floor drew."""
        cell_w, cell_h = app.font.cell_w, app.font.cell_h
        origin = self._origin(app, cell_w, cell_h)
        if origin is None:
            return
        ox, oy = origin
        width, height = float(image.width()), float(image.height())
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        self._paste_dark(painter, width, height)
        self._paste_rings(painter, ox, oy, width, height)
        self._paste_streaks(painter, ox, oy)
        self._paste_letter(painter, ox, oy, image, cell_h)
        self._paste_white(painter, width, height)
        painter.end()

    def _origin(self, app, cell_w: int, cell_h: int) -> tuple[float, float] | None:
        """Where the monster was standing, in the frame's own pixels."""
        if self._size is None or app.run is None:
            return None
        cols, rows = self._size
        position = getattr(self.trigger, "position", None)
        if position is None:
            return None
        return screen_point(app.run, position, cols, rows, cell_w, cell_h)

    def _paste_dark(self, painter: QPainter, width: float, height: float) -> None:
        """The floor leaving: the dungeon goes under while the thing comes up."""
        progress = _clamp((self.age - DIM_FROM) / (DIM_TO - DIM_FROM))
        if progress <= 0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(DIM * progress)
        painter.setBrush(QColor(0, 0, 0))
        painter.drawRect(QRectF(0.0, 0.0, width, height))
        painter.setOpacity(1.0)

    def _paste_rings(self, painter: QPainter, ox: float, oy: float, width: float, height: float) -> None:
        """Rings out of the square that was walked into. An ellipse, not a
        circle: the room is a floor seen at an angle, and so is everything on
        it."""
        reach = max(width, height) * 0.6
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index, delay in enumerate((0.0, 0.09, 0.18)):
            age = self.age - delay
            if age < 0 or age > FLASH_IN * 2:
                continue
            progress = age / (FLASH_IN * 2)
            radius = 16.0 + progress * reach
            ink = QColor(BLOW)
            ink.setAlpha(int(220 * (1.0 - progress)))
            painter.setPen(QPen(ink, max(1, int(6 * (1.0 - progress)))))
            painter.drawEllipse(
                QRectF(ox - radius, oy - radius * 0.62, radius * 2, radius * 1.24)
            )

    def _paste_streaks(self, painter: QPainter, ox: float, oy: float) -> None:
        """What the room does when something comes at the camera: lines, flying
        out of the middle of it."""
        if not STREAK_FROM < self.age < STREAK_TO:
            return
        progress = (self.age - STREAK_FROM) / (STREAK_TO - STREAK_FROM)
        ink = QColor(BLOW)
        ink.setAlpha(int(150 * math.sin(progress * math.pi)))
        painter.setPen(QPen(ink, 2))
        for index in range(28):
            angle = index * math.pi / 14 + 0.11
            near = 60.0 + progress * 420.0
            far = near + 40.0 + progress * 260.0
            painter.drawLine(
                QPointF(ox + math.cos(angle) * near, oy + math.sin(angle) * near * 0.72),
                QPointF(ox + math.cos(angle) * far, oy + math.sin(angle) * far * 0.72),
            )

    def _paste_letter(self, painter: QPainter, ox: float, oy: float, image, cell_h: int) -> None:
        """The monster, in the only shape it has ever had on the floor.

        Drawn at its own glyph and its own colour, growing and coming at the
        camera as one movement: the same two passes the arena uses for a letter
        -- a dark copy under a bright one -- so the edge of it is the game's own
        edge and not a drop shadow.
        """
        progress = _ease(_clamp((self.age - GROW_FROM) / (GROW_TO - GROW_FROM)))
        if progress <= 0:
            return
        glyph = getattr(self.trigger, "glyph", "") or "?"
        size = round(cell_h * (LETTER_FROM + progress * (LETTER_TO - LETTER_FROM)))
        font = _letter_font(size)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        centre_x = image.width() / 2.0
        centre_y = image.height() / 2.0
        x = ox + (centre_x - ox) * progress
        y = oy + (centre_y - oy) * progress
        left = x - metrics.horizontalAdvance(glyph) / 2.0
        baseline = y + metrics.capHeight() / 2.0
        ink = parse_style(getattr(self.trigger, "color", "#ffffff")).fg
        weight = max(3.0, size / 22.0)
        painter.setPen(ink.darker(340))
        painter.drawText(QPointF(left, baseline + weight), glyph)
        painter.setPen(ink)
        painter.drawText(QPointF(left, baseline), glyph)

    def _paste_white(self, painter: QPainter, width: float, height: float) -> None:
        """The blow, and the way out: white comes up under everything and the
        arena is standing where the floor was."""
        alpha = max(
            _clamp(self.age / FLASH_IN) * (1.0 - self.age / FLASH_IN),
            _clamp((self.age - WHITE_FROM) / (LIFE - WHITE_FROM)),
        )
        if alpha <= 0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(min(1.0, alpha))
        painter.setBrush(QColor(BLOW))
        painter.drawRect(QRectF(0.0, 0.0, width, height))
        painter.setOpacity(1.0)

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
                app.effects.spark(
                    origin, getattr(self.trigger, "color", BLOW), 34
                )
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


def _letter_font(size: int):
    """The arena's own letters, imported here rather than copied: one cache for
    both, or the game would have two ideas of what a big letter is."""
    from .battle import letter_font

    return letter_font(size).bold
