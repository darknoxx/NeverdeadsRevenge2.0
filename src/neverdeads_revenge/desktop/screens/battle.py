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
from ...game.statuses import status_by_key
from ...game.state import LogKind
from ..buffer import PatternBuffer
from ..chrome import ASH, BLOOD, BONE, box, rule
from ..font import BitmapFont
from ..render import log_style
from ..sprites import sprite as sprite_for
from ..sprites import status_icon
from ..tiles import tile
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
#: Kill points are drawn as stones, not as a bar: one mark a point, filled when
#: he has it and hollow when he does not. A bar says *how much*, which is the
#: wrong question -- the points are *spent*, one trick at a time, and a picture
#: of countable things is the picture of a purse.
POINT = "◆"
HOLLOW = "◇"
#: The colour the filled ones are drawn in: the dark's own violet, because that
#: is where they come from.
POINT_COLOUR = "bold #c084fc"
#: What a level-up looks like over the hero's head, and the colour it wears. The
#: arrow is the whole message: the one thing in a fight that is about *him*
#: rather than about what just happened to somebody else.
LEVEL_UP = "\u25b2 LVL UP"
LEVEL_UP_COLOUR = "#ffd34d"

#: How many turns the strip at the bottom of the room shows: the one being taken
#: and the two after it, which is what a decision is actually made against.
ORDER_SHOWN = 3

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
#:
#: Nothing stands at the rim. The floor tapers, so the far corners of it are
#: *wall* -- an outer monster at the very edge was standing in the masonry with
#: its health bar running off the frame, and the row was as wide as the room
#: instead of as wide as a row. The arc is the same shape, pulled in.
ROWS: dict[int, tuple[tuple[float, float], ...]] = {
    1: ((0.0, 0.18),),
    2: ((-0.20, 0.30), (0.20, 0.30)),
    3: ((-0.30, 0.30), (-0.02, 0.10), (0.30, 0.46)),
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
    # Noxx: the dagger, the orb, the shadow, the vein, the step, the void.
    "left_hand": "#5bd75b",
    "orb_of_ptamera": "#2ee6cf",
    "fleeting_shadow": "#8ff0e0",
    "devouring_darkness": "#a45cff",
    "friends_like_these": "#2ee6cf",
    "open_vein": "#d83a3a",
    "between_blows": "#b06bff",
    "the_void": "#e8ffff",
    # Yeti: the mountain, the rime, the hoarfrost, the stillness, the wall.
    "avalanche": "#cfe8ff",
    "snow_blind": "#dff4ff",
    "quake": "#bcdcff",
    "long_winter": "#8fcdf0",
    "rime": "#9fd8f5",
    "hoarfrost": "#bff0ff",
    "stillness": "#7fd4ff",
    "frozen_fortress": "#dff4ff",
    # Walkyrion: the note, the throw, the true note, the echo, the bell.
    "first_note": "#ffd34d",
    "overture": "#ffdd77",
    "ringing_chord": "#ffc21f",
    "silence_after": "#fff3c4",
    "bells_throw": "#ffc21f",
    "true_note": "#ffb000",
    "echoing_cut": "#ffe9a8",
    "shattered_bell": "#fff3c4",
}
#: What a *wound* looks like -- and this is not the colour of the blow that made
#: it but the colour of what is happening to the one wearing it. A monster going
#: green at the edges is poisoned whatever the blade was made of, which is the
#: whole point: a status has to be readable from across the room, on the figure,
#: without reading a word of the log.
STATUS_COLOURS: dict[str, str] = {
    "bleed": "#e03131",
    "maul": "#ff5a4a",
    "poison": "#5bd75b",
    "burn": "#ff7a1f",
    "chill": "#9fd8f5",
}
#: The shape its tick makes. A bleed drips, a poison climbs, a burn goes out
#: through the room as a wave of heat, and the cold leaves crystals.
STATUS_LOOKS: dict[str, str] = {
    "bleed": "bleed",
    "maul": "bleed",
    "poison": "poison",
    "burn": "burn",
    "chill": "frost",
}
#: What each wound sounds like when it bites. Nothing new to generate: the set
#: already has a wet one, a bad one, a sharp one and a cold one.
STATUS_SOUNDS: dict[str, str] = {
    "bleed": "hurt",
    "maul": "hurt",
    "poison": "curse",
    "burn": "crit",
    "chill": "ice",
}
#: Which picture a wound wears on the plate. ``maul`` has none of its own and
#: wears the bleeding one, exactly as it shares the shape its tick makes -- a
#: deep wound and a wound are the same wound, one of them deeper.
STATUS_ICONS: dict[str, str] = {
    "bleed": "bleed",
    "maul": "bleed",
    "poison": "poison",
    "burn": "burn",
    "chill": "chill",
}
#: The row of them: how tall one may be drawn (the sheets' own size, so a plate
#: with room for one shows it as painted), where it starts -- one row under the
#: life bar and past the pack, the purse and the count, which own the left of
#: the plate -- and the gap between two of them.
STATUS_BADGE = 52
STATUS_ROW_IN = 20
STATUS_ROW_DOWN = 2
STATUS_GAP = 4
#: And the same symbols for the monsters, whose bars are on the floor: smaller,
#: because a badge half the size of the thing wearing it is a label rather than a
#: mark, and set on the *end* of the bar, which is where the next one goes.
MONSTER_BADGE = 34
MONSTER_BADGE_GAP = 4
#: How wide a slot is against its height. The sheets' four symbols are not the
#: same shape as each other -- the frozen one is nearly square and the bleeding
#: one is a tall drop -- so the slot is cut for the widest of them and each is
#: fitted into its own rather than stretched to a common box: a drop pulled into
#: a square is a drop nobody recognises at a glance, which is the whole job.
STATUS_SLOT = 0.95
#: And *nearest* when it is fitted, because the sheets' four are pixels now: a
#: painted figure put through a resize looks like a mistake, and a pixel figure
#: put through a smooth one looks like a smudge. Drawing at a size the source
#: divides into keeps the grid square; anything else is a rounding, and a
#: rounding is what the source is made of anyway. (Nearest is the default, and
#: it is asked for anyway -- the room sets its own hints, and this row is drawn
#: in the middle of them.)
#: How much of the room's own dark is laid over a stone, at the far end of it.
#: The hashes were drawn in three greys; a picture cannot be, so the difference
#: between the wall behind the monsters and the near corner is a wash of the
#: darkness over the top of it -- the same idea, one layer up. Light enough that
#: the masonry still reads as masonry: a wall nobody can see is not a wall.
FAR_LIGHT = 0.62
#: Which stone goes where in a wall. Mostly plain, with a vine here and there,
#: because a room where every stone is decorated is a room with a pattern in it --
#: and the scatter is picked from the *place* and not from a dice roll, so the
#: room is the same room on every frame. A vine that moved between frames would
#: be a vine nobody believes.
WALL_STONES: tuple[str, ...] = (
    "wall",
    "wall",
    "wall_vines",
    "wall",
    "wall",
    "wall_vines",
    "wall",
)
#: And what is lying on the floor: nothing, mostly -- one stone in this many.
#: Bone belongs on the ground and not in the wall: on masonry it reads as a trophy
#: somebody hung up, and on the ground as somebody who did not get up.
FLOOR_BONES = 45
#: How long a monster takes to go, once the blow that killed it has *landed*.
#: It does not wink out and it is not a dimmed corpse left standing: the room
#: keeps it for half a second and then does not. See GONE_LIFE's use in _fade.
GONE_LIFE = 0.6
#: How long a wall of ice stands in front of the hero after it is raised.
WALL_LIFE = 1.2
#: How long Atritas stands there after FRIENDS LIKE THESE has called him. Longer
#: than a flourish, because he *is* the trick: a shadow the player never got a
#: look at is a shadow the trick did not really have.
SHADOW_LIFE = 1.3
#: How far out of his own outline the shadow stands, in cells, and how wide the
#: light behind him is. Far enough to read as a second figure: Noxx is petrol
#: himself, so a petrol silhouette in his own place is a silhouette nobody sees.
SHADOW_OFFSET = 2.6
SHADOW_LIGHT = 4.6
#: How long a blow's own flourish lasts. Inside the beat that carries it, so the
#: fight still reads one blow at a time -- but long enough to be *seen*, which is
#: the whole point of fifteen tricks looking like fifteen tricks.
FLOURISH_LIFE = 0.40
#: How many sparks each look throws. The loud ones throw more: a shatter should
#: look like the mountain, and a rime like a bit of frost.
SPARKS: dict[str, int] = {
    "slash": 14,
    "shadow": 22,
    "orb": 26,
    "drain": 24,
    "fleet": 18,
    "bleed": 18,
    "trail": 16,
    "dissolve": 30,
    "shatter": 34,
    "frost": 20,
    "poison": 16,
    "burn": 24,
    "pulse": 22,
    "aura": 24,
    "ring": 26,
    "throw": 24,
    "wave": 36,
    "wall": 20,
}
#: The shapes that belong to the *hero* and not to what he hit: an ice wall in
#: front of him, a glow on him, a cold ring out of him, and the smoke he leaves
#: when he is simply not there any more. They are the tricks that are not blows
#: aimed at anybody, so they have nowhere else to be seen.
SELF_LOOKS: frozenset[str] = frozenset({"wall", "aura", "pulse", "fleet"})
#: And how hard each one knocks the camera. The ultimates land like a floor.
SHAKES: dict[str, int] = {
    "shatter": 6,
    "wave": 6,
    "dissolve": 7,
    "throw": 4,
    "orb": 4,
    "drain": 3,
}
#: Everything that lands *moves* what it hit: the figure is shoved a fraction of
#: its own height up the room and drifts back. A thrown monster goes the whole
#: way (that is the trick); a stick hit moves a quarter of it, and the number
#: says how much it cost. Weight is a thing that is seen and not only read.
THROWN = 1.2
SHOVES: dict[str, float] = {
    "orb": 0.45,
    "drain": 0.35,
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
HITSTOP = 0.035
CRIT_STOP = 0.05
HITSTOPS: dict[str, float] = {
    "orb": 0.05,
    "drain": 0.045,
    "shatter": 0.065,
    "wave": 0.065,
    "dissolve": 0.07,
    "throw": 0.05,
    "shadow": 0.045,
    "ring": 0.045,
    "frost": 0.045,
}
#: The wash over the whole room when a blow lands, and how long it holds. Drawn
#: last and felt first: on a small screen a frame of colour across everything is
#: the loudest thing there is, and it costs one rectangle.
FLASH_LIFE = 0.11
FLASH_ALPHA = 0.10
FLASH_HARD_ALPHA = 0.18
#: The blows that shake the *seat* rather than the figure: the three that cost
#: the whole floor rather than the fight's exchange. A crit is in the same league
#: whatever it was struck with.
HARD_BLOWS: frozenset[str] = frozenset({"shatter", "wave", "dissolve"})
#: How long one event holds the stage. A fight that printed a whole round at
#: once would be a spreadsheet with letters drawn on it -- but a fight that
#: *narrates* at the speed it strikes is a fight that makes the player wait for
#: its own prose, so a blow and a line do not hold the stage for the same time.
BEAT = 0.34
#: A line is read at a glance and does not need to be *watched*: a fifth of a
#: beat. A round is a handful of blows and twice as many lines, and this is the
#: difference between a fight and a queue.
LINE_BEAT = 0.12
#: The invariant the three of them keep: a *beat* is long enough for the
#: animation it starts, plus the longest stop a blow can be given. Everything
#: else in a fight waits on the beat -- the next event, the line about it, a
#: level-up over the hero's head -- so a beat shorter than the blink means the
#: player is told what happens next before it has finished happening. That is
#: what it looked like: the sword still coming down and "LVL UP" already over
#: him. A test holds it.
#:
#: And the end holds the stage for almost nothing. The blow that finishes a fight
#: has already been watched; the verdict is what the player is waiting for, and
#: waiting a further beat for the *frame* it arrives in is the fight refusing to
#: be over -- which is exactly what it looked like from the outside: a fight that
#: took a few more presses of enter to admit it had ended.
END_BEAT = 0.06
#: How long a number hangs in the air over a head. Short: it is not holding the
#: keyboard any more (see :attr:`BattleScreen.busy`), and a number that outlives
#: the blow it belongs to is the fight talking about itself.
POPUP_LIFE = 0.60
#: The idle breath: how fast a figure rises and falls, and how far. Small on
#: purpose -- two pixels is the difference between a fight and a photograph.
BOB_SPEED = 3.4
BOB_HEIGHT = 2
#: How long a strike takes, and when inside it the blow lands. A blink: out
#: where the striker stands, back in beside what it is hitting, and gone again
#: before the beat that started it is over -- and the blow lands a fifth of a
#: second after the player asked for it, which is the number that decides whether
#: a fight feels like a fight or like a form to fill in.
STRIKE = 0.26
IMPACT_AT = STRIKE * 0.46
#: How long a struck figure shakes, and how far.
JOLT = 0.20
JOLT_PIXELS = 3
#: How many lines of the fight are readable at once.
LOG_LINES = 3


_LETTERS: dict[int, BitmapFont] = {}


def _scatter(along: int, across: int) -> int:
    """A stable, well-mixed number for a place in the room.

    Stable because the room must not redecorate itself between frames, and
    *mixed* because the obvious way to make one -- ``along * 7 + across * 5`` --
    is not scattered at all: it is a lattice. A lattice of bones reads as a
    pattern on the floor rather than as litter on it, and it is what the first
    attempt at this drew: evenly spaced, which is the one thing litter never is.

    Two coordinates multiplied by two large primes and folded into each other
    have no such structure -- the places that come up are the places a hash comes
    up with, which is what scattered looks like. This is not cryptography, it is
    a floor with some bones on it.
    """
    mixed = (along * 73856093) ^ (across * 19349663)
    mixed = (mixed ^ (mixed >> 13)) * 1274126177
    return (mixed ^ (mixed >> 16)) & 0x7FFFFFFF


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
    #: What it is *about*: how much of whom. The bar drops when the number
    #: appears and not when the swing started -- the two are one fact and they
    #: are read together, a fifth of a second after the player asked for the blow.
    damage: int = 0
    target_id: int = 0
    #: And whether it was the blow that finished them, and what it sounds like.
    #: The rules have known both since the swing -- they resolve at once -- and
    #: the *room* must not: a monster that goes transparent while the sword is
    #: still in the air is a fight that told the player the ending early.
    killed: bool = False
    sound: str = ""

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
        self._order: list = list(battle.upcoming(ORDER_SHOWN + 2))
        #: Sparks owed to blows that have not landed yet: a shower over a monster
        #: the sword has not reached is the fight telling the player the future,
        #: in the same way a number is. ``(when, point, colour, how many)``.
        self._showers: list[tuple[float, tuple[float, float], str, int]] = []
        #: Lines that describe a blow that has not landed yet. The log is read
        #: left to right and top to bottom, so a sentence about a hit has to wait
        #: for the hit -- see :meth:`_play`.
        self._late: list[tuple[float, Said]] = []
        #: The wash over the room on a landed blow. The loudest thing here and
        #: the cheapest -- and named apart from the white flash a *sprite* wears,
        #: which is the blow's mark on the figure rather than on the room.
        self._wash: Wash | None = None
        #: Who has been *seen* to die, and when: the frame the killing blow
        #: landed, not the moment the rules decided it. Everything that reads a
        #: figure's aliveness for the picture reads this instead.
        self._dying: dict[int, float] = {}
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
        self._draw_order(buffer, *areas["order"])

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
        self._paste_floor(painter, field)
        self._paste_walls(painter, field)
        # The bars are painted here and not written into the grid: the floor is a
        # picture now, and a bar in the grid would be a bar *under* the picture.
        self._paste_health(painter, figures, app.font)
        self._paste_wounds(painter, cols, rows, app)
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

    def _paste_floor(self, painter: QPainter, field: dict[str, float]) -> None:
        """The floor, in flagstones: the grid's own geometry with a picture on it.

        Two cells to a stone and half a stone of stagger on every row -- the same
        tile the grid floor has always laid down, in the same place -- and the two
        variants alternate exactly where the two tones used to. The fade is still
        a fade and not a texture: one black wash a row, heavier the further back
        the row is, which is how distance has been drawn here since the start.

        Drawn over the grid floor and not instead of it: no art, or art that will
        not load, and the room the arena has always had is already underneath.
        """
        light, dark = tile("floor_a"), tile("floor_b")
        if light is None or dark is None:
            return
        left, right = float(field["left"]), float(field["right"])
        top = float(field["top"])
        width_px, inset_px = field["width_px"], float(field["inset_px"])
        rows = int(field["cells_h"])
        tw = light.width()
        for row in range(rows):
            depth = row / max(1, rows - 1)
            y = top + row * float(field["cell_h"])
            inset = round((1.0 - depth) * inset_px)
            # The stagger, and the clip that keeps it inside the taper: a tile
            # that started half a stone to the left would be floor outside the
            # floor, which is the one thing the taper is for.
            painter.save()
            painter.setClipRect(QRectF(left + inset, y, width_px - inset * 2, float(field["cell_h"])))
            x = left + inset - (row % 2) * (tw // 2)
            index = 0
            while x < right - inset:
                stone = self._floor_stone(index, row, index % 2 == 0)
                painter.drawImage(int(x), int(y), stone or (light if index % 2 == 0 else dark))
                x += tw
                index += 1
            fade = int(140 * (1.0 - depth))
            if fade:
                painter.fillRect(
                    QRectF(left, y, width_px, float(field["cell_h"])),
                    QColor(6, 6, 10, fade),
                )
            painter.restore()

    def _paste_health(self, painter: QPainter, figures, font) -> None:
        """The bar under every monster, in pixels, on the floor it is standing on.

        The same stripe in the same place the grid used to write -- half a cell
        tall, under the feet -- and none under the hero: the letter is the monster
        and the log is the story, so the one thing a monster cannot say about
        itself is how much of it is left.
        """
        for figure in figures:
            if figure.actor is self.battle.hero:
                continue
            if self._fade(id(figure.actor)) < 1.0:
                # The bar goes with the monster and not before it: a stripe left
                # lying on the floor under nobody is a stripe about nobody.
                continue
            total = max(1, figure.actor.max_hp)
            shown = self._shown.get(id(figure.actor), figure.actor.stats.hp)
            ratio = max(0.0, min(1.0, shown / total))
            cells = max(8, min(14, figure.cells * 2))
            width = float(cells * font.cell_w)
            height = float(font.cell_h // 2)
            left = float(figure.cx) - width / 2.0
            top = float(figure.row * font.cell_h) + height
            colour = (
                "bright_green"
                if ratio > 0.5
                else "bright_yellow"
                if ratio > 0.25
                else "bright_red"
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.fillRect(QRectF(left, top, width, height), parse_style("grey19").fg)
            painter.fillRect(
                QRectF(left, top, width * ratio, height), parse_style(colour).fg
            )
            # And what is eating it, at the end of the bar: the room used to say
            # this with a light around the figure, and a light could not say
            # *which* wound. A monster whose bar says how much of it is left is
            # the one place that can also say what is still taking it.
            self._wound_row(
                painter,
                figure.actor,
                left + width + MONSTER_BADGE_GAP,
                top + height / 2.0,
                MONSTER_BADGE,
            )

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
        fade = self._fade(id(figure.actor))
        if fade <= 0.0:
            return
        width = max(20.0, float(figure.cells * cell_w) * 1.05)
        height = max(6.0, width * 0.24)
        centre_x = float(figure.cx)
        centre_y = float(figure.row * cell_h) - 1.0
        gradient = QRadialGradient(QPointF(centre_x, centre_y), width / 2.0)
        gradient.setColorAt(0.0, QColor(0, 0, 0, int(120 * fade)))
        gradient.setColorAt(0.55, QColor(0, 0, 0, int(74 * fade)))
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
        if look in ("shadow", "trail", "orb"):
            # None of these moves the hero. The shadow is a second figure going
            # instead of him, the trail is where he *is* -- a step so quick that
            # the room cannot follow it -- and the orb is *thrown*: he stands
            # still and the dark does the travelling.
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
        if look == "orb":
            # The flight is timed to the *blow* and not to the swing, so the orb
            # is at the throat on the frame the number comes off it. Anything
            # else and the fight would be showing two different moments.
            lands = IMPACT_AT / STRIKE
            if not 0.05 < progress < lands:
                return
            other = self._figure_at(figures, target_id)
            if other is None:
                return
            where = (progress - 0.05) / (lands - 0.05)
            start_x, start_y = figure.cx + cell_w * 2.0, home - image.height() * 0.62
            end_x, end_y = other.cx, other.row * cell_h - cell_h * 1.5
            length = math.hypot(end_x - start_x, end_y - start_y) or 1.0
            self._orb(
                painter,
                start_x + (end_x - start_x) * where,
                start_y + (end_y - start_y) * where,
                (end_x - start_x) / length,
                (end_y - start_y) / length,
                FLAIR_COLOURS.get(flair, "#ffffff"),
                float(cell_w) * 1.5,
            )
            return
        if look == "trail":
            for dx, fade in ((9, 0.32), (18, 0.20), (27, 0.11)):
                painter.setOpacity(fade)
                painter.drawImage(
                    figure.cx - image.width() // 2 + dx, home - image.height(), image
                )
            painter.setOpacity(1.0)

    @staticmethod
    def _figure_at(figures, target_id: int) -> Staged | None:
        """The figure standing at an actor id, or ``None``."""
        for other in figures:
            if id(other.actor) == target_id:
                return other
        return None

    def _orb(self, painter: QPainter, x, y, ux, uy, colour, size) -> None:
        """The orb of Ptamera in flight: a hole with a rim on it.

        Black, because it is made of the absence of anything -- and the rim is
        what makes an absence visible at all. A black ball on a dark floor is a
        smudge; a black ball with a lit edge is a hole in the room, travelling.
        """
        painter.setPen(Qt.PenStyle.NoPen)
        for step in (3, 2, 1):
            trail = QColor(colour)
            trail.setAlpha(20 + step * 16)
            painter.setBrush(trail)
            radius = size * (1.0 - step * 0.22)
            painter.drawEllipse(
                QRectF(
                    x - ux * step * size * 0.75 - radius / 2,
                    y - uy * step * size * 0.75 - radius / 2,
                    radius,
                    radius,
                )
            )
        painter.setBrush(QColor("#04060a"))
        painter.drawEllipse(QRectF(x - size / 2, y - size / 2, size, size))
        rim = QColor(colour)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(rim, 2))
        painter.drawEllipse(QRectF(x - size / 2, y - size / 2, size, size))

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
        if look == "shadow":
            # Handled above the gate the other flourishes share, because it lives
            # longer than they do: see SHADOW_LIFE.
            self._paste_atritas(painter, figure, cell_w, cell_h, baseline, colour, age)
            return
        if age > FLOURISH_LIFE * 1.5:
            return
        if look == "aura" or look == "drain":
            # "drain" on the hero is the other half of the steal: the darkness
            # went down out of the monster and arrived here, and what it looks
            # like on this end is *him* glowing. The same pool of colour, and the
            # same reason: something is happening to the hero and it has to be
            # visible on him.
            self._glow(painter, figure.cx, baseline, cell_w, cell_h, colour, age)
            return
        if look == "pulse":
            self._ripple(painter, figure.cx, baseline - cell_h, colour, age, reach=4.0)
            return
        if look == "fleet":
            # Smoke where he was: nothing is left of him but what he was standing
            # in, and it is already going.
            self._climb(painter, figure.cx, baseline - cell_h, cell_h, colour, age, count=9, up=True)
            self._glow(painter, figure.cx, baseline, cell_w, cell_h, colour, age)
            return

    def _fade(self, actor_id: int) -> float:
        """How much of a figure is still in the room: 1 until it is killed, 0 gone.

        The rules kill at the swing and the room lets go at the *blow*, which is
        a fifth of a second later -- and then it does not leave a dimmed corpse
        lying about, it lets the whole figure go. A dead monster is not a monster
        in half a light: it is one that was there and now is not.
        """
        when = self._dying.get(actor_id)
        if when is None:
            return 1.0
        age = self._clock - when
        if age >= GONE_LIFE:
            return 0.0
        return max(0.0, 1.0 - age / GONE_LIFE)

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
        elif look == "poison":
            # It climbs: a poison is not a hit, it is something working its way
            # up out of the thing it is in.
            self._ripple(painter, figure.cx, top, colour, age, reach=1.6)
            self._climb(painter, figure.cx, top, cell_h, colour, age, count=7, up=True)
        elif look == "burn":
            # Fire goes *out*: a wave of heat through the room, and the flames
            # coming off the figure the whole time it burns.
            self._band(painter, figure.cx, top, cell_w, colour, age)
            self._climb(painter, figure.cx, top, cell_h, colour, age, count=8, up=True)
        elif look == "orb":
            # Where the hole came apart: a ring going out, and the dark climbing
            # off the wound it left.
            self._ripple(painter, figure.cx, top, colour, age, reach=2.6)
            self._climb(painter, figure.cx, top, cell_h, colour, age, count=6)
        elif look == "drain":
            self._siphon(painter, figure.cx, top, cell_h, colour, age)
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

    def _paste_atritas(
        self, painter: QPainter, figure: Staged, cell_w: int, cell_h: int, baseline: int, colour: str, age: float
    ) -> None:
        """Atritas steps out of him, and stands there a while.

        His *own* silhouette in petrol and not a second drawing -- there is no
        second set of art for him -- put out to the side far enough to read as a
        second figure, with a light behind it. Noxx is petrol himself, so a petrol
        silhouette in his own place would be a silhouette nobody ever saw: what
        makes the shadow visible is the *room* behind it lighting up.
        """
        if age > SHADOW_LIFE or figure.sprite is None:
            return
        image = figure.sprite
        # In fast, out slow: he is *there* for most of it and gone at the end.
        rise = min(1.0, age / 0.12)
        fall = max(0.0, (age - SHADOW_LIFE * 0.6) / (SHADOW_LIFE * 0.4))
        solid = max(0.0, rise - fall)
        if solid <= 0:
            return
        cx = figure.cx + cell_w * SHADOW_OFFSET
        cy = baseline - image.height() * 0.5
        radius = cell_w * SHADOW_LIGHT
        tint = QColor(colour)
        gradient = QRadialGradient(QPointF(cx, cy), radius)
        gradient.setColorAt(0.0, QColor(tint.red(), tint.green(), tint.blue(), int(120 * solid)))
        gradient.setColorAt(1.0, QColor(tint.red(), tint.green(), tint.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        painter.setOpacity(solid * 0.95)
        painter.drawImage(
            cx - image.width() // 2, baseline - image.height(), self._shadow(image)
        )
        painter.setOpacity(1.0)

    def _worn(self, actor) -> list[str]:
        """Which wounds somebody is wearing, in a stable order."""
        return sorted(key for key in actor.statuses if key in STATUS_ICONS)

    def _wound_row(
        self, painter: QPainter, actor, start: float, middle: float, size: int
    ) -> None:
        """One row of wound symbols, from ``start`` and centred on ``middle``.

        One helper for both rows -- the plate's, which is the hero's own numbers,
        and the little one at the end of every monster's bar on the floor --
        because a player who has learned a symbol in one place should find the
        same symbol in the other, drawn the same way. Sized by the caller: the
        plate has a panel to fill and the floor has a monster to avoid covering.
        """
        icons = [
            art
            for art in (
                status_icon(STATUS_ICONS[key]) for key in self._worn(actor)
            )
            if art is not None
        ]
        if not icons:
            return
        slot = max(6, round(size * STATUS_SLOT))
        step = slot + STATUS_GAP
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        for index, art in enumerate(icons):
            # Fitted, not stretched: the largest box of its own shape that fits
            # in the slot, and then centred in it, so the row's spacing is even
            # and every symbol keeps its own proportions.
            scale = min(slot / art.width(), size / art.height())
            width = max(1.0, art.width() * scale)
            height = max(1.0, art.height() * scale)
            x = start + index * step + (slot - width) / 2.0
            painter.drawImage(
                QRectF(x, middle - height / 2.0, width, height),
                art,
                QRectF(art.rect()),
            )
        painter.restore()

    def _paste_wounds(self, painter: QPainter, cols: int, rows: int, app) -> None:
        """The hero's wounds, as the sheets' symbols, beside his life bar.

        A wound used to be a *light*: the figure stood in a pool of the colour of
        whatever was eating it until it stopped. This says the same thing more
        exactly -- which wound, and all of them side by side rather than one
        muddy colour per figure -- and it says it on the plate, which is the one
        place in the arena that owns the hero's own numbers.

        Sized to fit and *not* left to run off the plate: one wound is drawn at
        the size the sheets painted it, and five share the room the row has,
        because a row that fell off the end would tell the player about four of
        their five problems.
        """
        worn = self._worn(self.battle.hero)
        if not worn:
            return
        x, y, width, height = self._areas(cols, rows)["plate"]
        if height < 4 or width < 12:
            return
        cell_w, cell_h = app.font.cell_w, app.font.cell_h
        left = (x + min(STATUS_ROW_IN, max(2, width - 6))) * cell_w
        right = (x + width - 1) * cell_w
        room = max(0, right - left)
        size = max(
            10,
            min(
                STATUS_BADGE,
                3 * cell_h,
                (room - (len(worn) - 1) * STATUS_GAP) // max(1, round(len(worn) * STATUS_SLOT)),
            ),
        )
        top = (y + STATUS_ROW_DOWN) * cell_h
        self._wound_row(painter, self.battle.hero, left, top + size / 2.0, size)

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

    def _siphon(self, painter, cx, top, cell_h, colour, age) -> None:
        """Darkness leaving him *downwards*.

        The hero is always at the bottom of the frame, so the way a stolen thing
        travels needs no second address: it goes down, and the eye follows it home.
        """
        fall = min(1.0, age / FLOURISH_LIFE)
        fade = 1.0 - fall
        for index in range(5):
            x = cx - 20 + index * 10
            head = top + fall * cell_h * 2.4 + index * 4
            streak = QColor(colour)
            streak.setAlpha(int(210 * fade))
            painter.setPen(QPen(streak, 2))
            painter.drawLine(QPointF(x, head - 14), QPointF(x, head))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(streak)
            painter.drawEllipse(QRectF(x - 2, head - 2, 4, 4))

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
        # No arrow here. A target is picked *after* the trick is picked, in the
        # one place where the fight is going to read it: aiming at a monster
        # before knowing what is being aimed would be choosing the answer to a
        # question nobody has been asked yet.
        if name == "up":
            self.verb = (self.verb - 1) % len(VERBS)
            app.play("move")
            return True
        if name == "down":
            self.verb = (self.verb + 1) % len(VERBS)
            app.play("move")
            return True
        shortcut = {"a": ATTACK, "s": SPECIAL, "i": ITEM, "f": FLEE}
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
            if not self.battle.learned():
                # Nothing learned yet: there is no list to open, and a panel with
                # nothing in it is worse than a key that says no.
                app.play("deny")
                return
            self.picking = True
            self.special = 0
            app.play("move")
            return
        if VERBS[self.verb] in AIMED:
            self.aiming = True
            self._aim_from = "verbs"
            self._picked = None
            app.play("move")
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
            app.play("move")
            if self._aim_from == "list":
                self.picking = True
            return True
        if name in ("enter", "return", "space", "a"):
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
        """What he has learned, being looked at: pick one, or come back."""
        specials = self.battle.learned()
        if not specials:
            # Nothing on the menu and no way to have got here: the verbs refuse
            # to open an empty list, and this is the guard for anything that
            # finds another road in.
            self.picking = False
            app.play("deny")
            return True
        # The number keys still work and are no longer *shown*: the list carries
        # the price of each trick where the number used to be, and a shortcut is
        # a convenience for the player who already knows the list by heart.
        index = {str(digit): digit - 1 for digit in range(1, 10)}.get(name)
        if name == "escape":
            self.picking = False
            app.play("move")
            return True
        rows = self._list_rows(app)
        if name in ("up", "w"):
            self.special = (self.special - 1) % len(specials)
            app.play("move")
            return True
        if name in ("down", "s"):
            self.special = (self.special + 1) % len(specials)
            app.play("move")
            return True
        if name in ("left", "h", "right", "l"):
            # The list is two columns, so across is a whole column away -- and it
            # stays where it is rather than wrapping, because a jump that lands
            # somewhere unrelated is a jump that loses the player's place.
            jump = -rows if name in ("left", "h") else rows
            moved = self.special + jump
            if 0 <= moved < len(specials):
                self.special = moved
            app.play("move")
            return True
        if index is None and name in ("enter", "return", "space"):
            index = self.special
        if index is None or index >= len(specials):
            return True
        chosen = specials[index]
        if self.battle.special_available(chosen):
            self.picking = False
            app.play("pick")
            if not chosen.needs_target:
                # Set on himself, or through everything standing: there is nobody
                # to walk the arrow to, and asking would be asking a question the
                # fight was never going to read.
                self._choose(app, special=chosen.key)
                return True
            # The trick is picked, and the *victim* is still to be picked: the
            # list closes and the arrow takes over, on the floor where the
            # monsters are, with the trick kept for whoever it ends up on.
            self.aiming = True
            self._aim_from = "list"
            self._picked = chosen.key
        else:
            # Locked, or already spent this fight. Answered out loud and not with
            # silence: the same note for a refusal as for a commitment is a menu
            # the player cannot read with their ears.
            app.play("deny")
        return True

    @property
    def kill_points(self) -> int:
        """How much of the purse the tricks are paid from is left."""
        return self.state.kill_points

    @property
    def busy(self) -> bool:
        """Whether the fight still has something to say or show.

        Talking, and only talking: the keyboard is held while the round is being
        played, because a player drumming on enter would be choosing the next
        verb for a blow they have not seen land.

        *Talking* and not *fading*: the damage numbers are deliberately not in
        here. They are the fight's last word about a blow that has already
        landed, and a number on its way out is not a reason to hold the player's
        hands -- it used to be three quarters of a second of pure waiting every
        single round, which is exactly the wait a fight should never have.
        """
        return bool(self._queue) or self._beat > 0

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
        self._fall_due(app)
        for popup in self._popups:
            # A number on its way *to* the fight and not out of it: it goes live
            # on the frame the blow lands, and the bar drops with it. Both are one
            # fact -- how much of whom -- and a bar that went down while the sword
            # was still in the air was the fight spending the blow for the player.
            if popup.age < 0 <= popup.age + dt:
                if popup.damage:
                    before = self._shown.get(popup.target_id, popup.damage)
                    self._shown[popup.target_id] = max(0, before - popup.damage)
                if popup.sound:
                    app.play(popup.sound)
                if popup.killed:
                    # *Now* it dies, which is the moment the number came off it.
                    # The rules knew at the swing; the room is told here, and the
                    # two moments are different on purpose.
                    self._dying[popup.target_id] = self._clock
            popup.age += dt
        self._popups = [popup for popup in self._popups if popup.age < Popup.LIFE]
        if self._beat > 0:
            self._beat = max(0.0, self._beat - dt)
            return
        if not self._queue:
            self._resync()
            return
        event = self._queue.pop(0)
        self._play(event, app)
        self._beat = self._beat_for(event)

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
        # The strip the player is about to watch: the round that was just decided,
        # in the order it was decided, and then what the queue says comes after it
        # -- with enough runway that counting the round off the front never leaves
        # the strip shorter than the row it draws.
        played = self.battle.turns()
        self._order = [*played, *self.battle.upcoming(ORDER_SHOWN + len(played))]
        # The confirmation, and only one of it: a trick and a draught have a
        # voice of their own, and a blip over the top of the dark's own sound
        # would be a stutter rather than a flourish. Everything else -- a swing,
        # a guard, a run for it -- has nothing to say for itself yet, so the note
        # that the key registered is all the player hears until it lands.
        if VERBS[self.verb] == SPECIAL:
            app.play("void")
        elif VERBS[self.verb] == ITEM:
            app.play("item")
        else:
            app.play("pick")
        if not living:
            self._resync()

    def _snapshot(self) -> None:
        """Freeze what the bars say, so the playback can move them itself."""
        for actor in [self.battle.hero, *self.battle.enemies]:
            self._shown[id(actor)] = actor.stats.hp

    def _fall_due(self, app) -> None:
        """Everything that was owed to a blow, once its moment has come.

        The lines that describe a hit, and the sparks it throws: both are the
        blow's, both are timed off it, and neither is allowed to arrive early --
        a fight that reads out a hit before it happens has told the player the
        ending of the sentence they are in the middle of.
        """
        if self._late:
            due = [line for when, line in self._late if self._clock >= when]
            self._late = [(when, line) for when, line in self._late if self._clock < when]
            for line in due:
                self.lines = [*self.lines, line][-LOG_LINES:]
        if self._showers:
            due = [one for one in self._showers if self._clock >= one[0]]
            self._showers = [one for one in self._showers if self._clock < one[0]]
            for _when, point, colour, count in due:
                app.effects.spark(point, colour, count)

    @staticmethod
    def _beat_for(event) -> float:
        """How long this event holds the stage.

        A blow is *watched* and gets the full beat; a line is read at a glance
        and gets a fifth of one. Splitting them is the whole of the fight's pace:
        a round is a handful of blows and twice as many lines, and one number for
        both was the fight narrating at the speed it strikes.
        """
        if isinstance(event, Said):
            return LINE_BEAT
        if isinstance(event, Over):
            return END_BEAT
        return BEAT

    def _resync(self) -> None:
        """Truth, once the round has finished being played."""
        for actor in [self.battle.hero, *self.battle.enemies]:
            self._shown[id(actor)] = actor.stats.hp
        # And the order: `upcoming` already begins with the turn in flight, so
        # standing still and mid-swing give the same strip and nothing slides. A
        # couple spare, so that the row the panel draws is never shorter than the
        # row it drew a moment ago.
        self._order = list(self.battle.upcoming(ORDER_SHOWN + 2))

    def _play(self, event, app) -> None:
        """One event, on the screen and in the ear."""
        if isinstance(event, Said):
            if event.text.startswith("Level "):
                # The one line in a fight that gets a picture of its own: the
                # arrow over his head, and the note that goes with it. The rules
                # wrote it, and the rules do not know what a picture is.
                self._level_up(app)
            # The log is the fight's voice, and its voice does not run ahead of
            # its hands: a line that describes a blow *waits* for the blow, and
            # turns up on the frame the sword does. Lines that are not about a
            # blow -- a curse arriving, a hero setting his feet -- are read at
            # once, because there is nothing for them to wait on.
            follows = self._queue[0] if self._queue else None
            if isinstance(follows, Struck):
                waits = self._beat_for(event) + IMPACT_AT
                self._late.append((self._clock + waits, event))
            else:
                self.lines = [*self.lines, event][-LOG_LINES:]
            return
        if isinstance(event, Flourish):
            status = status_by_key(event.flair)
            if status is not None:
                self._wound(event.actor, status, app)
                return
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
            # A guard is the hero's turn and carries his *name*: the strip is
            # about actors, and there is exactly one actor a guard can belong to.
            self._took_a_turn(self.battle.hero)
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
            self._took_a_turn(event.actor)
            self._land(event, app)

    def _land(self, struck: Struck, app) -> None:
        """A blow landing: a number, a shove, and a sound that matches it."""
        outcome = struck.outcome
        figure = self._figure_of(struck.target, app)
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
            number.damage = outcome.damage if outcome.hit and not outcome.dodged else 0
            number.target_id = id(struck.target)
            number.killed = outcome.killed
            # The sound belongs to the *blow* and not to the swing, like the
            # number and the bar and the sparks: everything the player hears and
            # sees about a hit happens on the frame it lands in.
            number.sound = (
                (
                    "kill"
                    if outcome.killed
                    else "crit"
                    if outcome.crit
                    else "hit"
                )
                if struck.actor is self.battle.hero
                else "hurt"
            )
            if not outcome.hit:
                number.sound = ""
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
        # it: the flashes say *where*, the particles say *how much*. Owed, not
        # thrown: it belongs to the impact and not to the swing, so it is put on
        # the same clock as everything else the blow does.
        look = self._look(struck.flair)
        point = self._point_of(struck.target, app)
        if point is not None:
            self._showers.append(
                (
                    self._clock + IMPACT_AT,
                    point,
                    FLAIR_COLOURS.get(struck.flair, "#ffffff"),
                    SPARKS.get(look, 16),
                )
            )


    def _wound(self, actor, status, app) -> None:
        """A wound biting: what the fight shows at the monster's own turn.

        The damage is the *domain's* and has already been taken -- on the turn
        the wound belongs to, which is the rule -- so this is only the reading of
        it: the figure flashes in the colour of what is eating it, a number comes
        off it, the bar drops to where the wound left it, and the shape goes out
        (a drip, a climb, a wave of heat, a breath of cold).

        Everything a blow gets except the blow. A wound is not a hit and must not
        look like one: it is the same monster, one turn later, still being eaten.
        """
        # Brighter than the light the wound *wears*, and not the same colour of it:
        # a bite that is the same green as the monster already is is a bite nobody
        # sees. The mark and the moment are two different things.
        colour = QColor(STATUS_COLOURS.get(status.key, "#ffffff")).lighter(150).name()
        look = STATUS_LOOKS.get(status.key, "")
        figure = self._figure_of(actor, app)
        if figure is None:
            return
        self._hurts[id(actor)] = (self._clock, colour, look)
        if status.damage:
            # The bar was at the *unwounded* value: the domain has already taken
            # the damage off the real actor, and this is the screen catching up.
            was = self._shown.get(id(actor), actor.stats.hp + status.damage)
            self._shown[id(actor)] = max(0, was - status.damage)
            self._popups.append(self._popup(str(status.damage), colour, figure, app, False))
        point = self._point_of(actor, app)
        if point is not None:
            app.effects.spark(point, colour, SPARKS.get(look, 16))
            app.view.shake(strength=2, seconds=0.12)
        app.play(STATUS_SOUNDS.get(status.key, "hurt"))

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
        # The strip lives in the gap the two panels leave between them: the plate
        # on the left, the verbs on the right, and the order in the middle, which
        # is where a player's eye already is when they are deciding.
        order_x = margin + panel_w + 1
        order_w = max(0, cols - margin - panel_w - order_x - 1)
        return {
            "wall": (margin, wall_y, max(1, cols - margin * 2), wall_h),
            "ground": (margin, ground_y, max(1, cols - margin * 2), ground_h),
            "log": (margin, log_y, max(1, cols - margin * 2), log_h),
            "plate": (margin, panel_y, panel_w, panel_h),
            "commands": (max(0, cols - margin - panel_w), panel_y, panel_w, panel_h),
            "order": (order_x, panel_y, order_w, panel_h),
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
        wx, wy, ww, wh = self._areas(cols, rows)["wall"]
        return {
            "wall_top": float(wy * cell_h),
            "wall_h": float(wh * cell_h),
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
        # The arrow is out only while something is being aimed: it marks the
        # *question*, and there is no question on the floor until a trick has
        # asked one.
        marked = living[self.target % len(living)] if self.aiming and living else None
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
        """The room: three planes of the same stone.

        One plane is the far wall, which faces the viewer and needs no shear at
        all. The other two are the side walls, and each is the *same* transform
        of the same tile: the plane's horizontal axis is the floor's own edge and
        its vertical axis is the vertical, which is what a wall is. Every stone is
        the same size -- a parallel projection has no nearer and further, which is
        the whole of the isometric look.

        Painted from ``tiles/wall.png`` where the game has it, and from the
        dungeon's own ``#`` where it has not: the alphabet is still underneath
        every picture in here, which is what makes the art safe to ship.
        """
        art = tile("wall")
        if art is None:
            self._paste_hash_walls(painter, field)
            return
        left, right = float(field["left"]), float(field["right"])
        inset_px = float(field["inset_px"])
        ground_top = float(field["top"])
        wall_top = float(field.get("wall_top", ground_top - 60.0))
        band = ground_top - wall_top
        far_ink, near_ink = parse_style(WALL_FAR).fg, parse_style(WALL_NEAR).fg
        # Everything is masonry, and the room is the band it stands in: the wall
        # behind the monsters and the two at the sides all end at the same line,
        # because in this projection they are all the same height. Without the
        # clip the courses climb off the top of the frame.
        bottom = float(field["bottom"])
        painter.save()
        painter.setClipRect(QRectF(0.0, wall_top, 10000.0, bottom - wall_top + 1.0))

        # The far wall: as many stones as fit between the floor's own edges, and
        # as many courses as the band is tall. Laid *up* from the floor's far
        # edge and not down from the top: a wall that grew downwards would be
        # standing on the floor, which is not what a wall does.
        span = float(field["width_px"]) - inset_px * 2
        across = max(1, math.ceil(span / art.width()))
        down = max(1, math.ceil(band / art.height()))
        for index in range(across):
            x = int(left + inset_px + index * art.width())
            for course in range(down):
                y = int(ground_top - (course + 1) * art.height())
                stone = self._stone(index, course)
                painter.drawImage(x, y, stone)
                self._shade(painter, x, y, stone, far_ink, FAR_LIGHT)

        # And the two sides, sheared along the floor's own edge.
        edge_x, edge_y = float(field["edge_x"]), float(field["edge_y"])
        length = float(field["edge_len"])
        steps = max(1, round(length / art.width()))
        for side in (0, 1):
            ux = edge_x if side == 0 else -edge_x
            uy = edge_y
            if side:
                ax0, ax1 = right - inset_px, right
            else:
                ax0, ax1 = left + inset_px, left
            # The side walls run the *depth* of the room and not the wall band:
            # they are the floor's own edges standing up, so they start at the
            # floor's far edge and end where the floor does.
            ay0, ay1 = ground_top, float(field["bottom"])
            for step in range(steps):
                t_along = (step + 0.5) / steps
                ax = ax0 + (ax1 - ax0) * t_along
                ay = ay0 + (ay1 - ay0) * t_along
                painter.save()
                painter.setTransform(
                    QTransform(ux, uy, 0.0, 1.0, ax, ay), combine=True
                )
                # Up and out of the room: in the sheared space the tile is drawn
                # *above* the line its edge is on, which is where a wall is --
                # and courses of them, because one course is a kerb.
                for course in range(down):
                    stone = self._stone(step, course)
                    painter.drawImage(
                        -art.width() // 2, -(course + 1) * art.height(), stone
                    )
                    # The light comes from the hero's end: the far corner of each
                    # wall is the darkest thing in the room.
                    self._shade(
                        painter,
                        -art.width() // 2,
                        -(course + 1) * art.height(),
                        stone,
                        far_ink,
                        FAR_LIGHT - t_along * 0.75,
                    )
                painter.restore()
        painter.restore()

    @staticmethod
    def _floor_stone(along: int, row: int, light: bool):
        """Which flagstone is here: the tone the checker wants, and sometimes what
        is lying on it.

        Chosen from the place and not rolled for, for the same reason the wall's
        scatter is: bones stay where they were left.
        """
        tone = "a" if light else "b"
        if _scatter(along, row) % FLOOR_BONES == 0:
            return tile(f"floor_{tone}_bones") or tile(f"floor_{tone}")
        return tile(f"floor_{tone}")

    @staticmethod
    def _stone(along: int, course: int):
        """Which stone is at this place in a wall: mostly plain, sometimes not.

        Chosen from the place in the wall and not rolled for, so the scattered
        bones stay where they were laid: a room that re-dressed itself every frame
        would be a room made of flicker.
        """
        plain = tile("wall")
        wanted = WALL_STONES[_scatter(along, course) % len(WALL_STONES)]
        return tile(wanted) or plain

    def _shade(
        self,
        painter: QPainter,
        x: int,
        y: int,
        art,
        ink: QColor,
        how_much: float,
    ) -> None:
        """Lay the room's own dark over a stone, so the planes differ.

        The hashes were *drawn* in three greys; a picture cannot be, so the
        difference between the far wall and the near corner is a wash of the
        darkness over the top of it -- the same idea, one layer up.
        """
        alpha = int(150 * how_much)
        if alpha <= 0:
            return
        painter.fillRect(QRectF(float(x), float(y), float(art.width()), float(art.height())), QColor(6, 6, 10, alpha))

    def _paste_hash_walls(self, painter: QPainter, field: dict[str, float]) -> None:
        """The room as it was before the stone arrived: the dungeon's own ``#``.

        Kept, and not as decoration: this is what a machine with no tiles in it
        gets, and what the arena looked like for its first three hundred commits.
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
        fade = self._fade(id(figure.actor))
        if fade <= 0.0:
            return
        opacity *= fade
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
        at the one it means. It only exists while something is being aimed -- it
        marks the question, and there is no question until a trick has asked one.

        And it breathes, one pixel either way: the monster the arrow is on is
        moving while all the others are still. A marker that stands as still as
        everything under it is a marker a player has to hunt for.
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
            # The purse, as stones rather than as a bar: one mark a point, filled
            # and hollow. The old line here said whether the *void* was ready,
            # which told the player about one trick out of eight; this says what
            # there is to spend, and the price of everything is on the list.
            points = self.kill_points
            top = max(1, self.state.kill_points_max)
            # The number stays, small beside it, because at a deep level the
            # stones run out of room before the purse runs out of points.
            room = max(3, width - 14)
            shown = min(top, room)
            filled = min(points, shown)
            buffer.text(x + 2, y + 3, "KP", parse_style(ASH))
            buffer.text(x + 5, y + 3, POINT * filled, parse_style(POINT_COLOUR))
            buffer.text(
                x + 5 + filled, y + 3, HOLLOW * (shown - filled), parse_style("grey23")
            )
            buffer.text(
                x + 6 + shown, y + 3, f"{points}/{top}", parse_style(ASH)
            )
        if height >= 5:
            # The same count the side panel keeps, because a level is the one
            # thing a fight is *for* and the player should not have to leave the
            # room to find out how close it is.
            to_go = self.state.kills_to_level
            level = self.state.level
            buffer.text(
                x + 2,
                y + 4,
                f"{to_go} KILLS TO LVL {level + 1}" if to_go else "THE LAST LEVEL",
                parse_style(ASH),
            )
        if (self.picking or self.aiming) and height >= 7:
            # Escape is a step *back* in the two menus and nothing anywhere else
            # -- there is no way out of a fight but through it -- so the plate only
            # says anything about it while there is somewhere to go back to. The
            # line it used to carry ("leave the arena") was a promise no key could
            # keep.
            buffer.text(x + 2, y + height - 2, "esc  back", parse_style(ASH))

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
        keys = {ATTACK: "a", SPECIAL: "s", ITEM: "i", FLEE: "f"}
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
            if verb == ATTACK:
                self._draw_wield(buffer, x + 14, y + 1 + index, width - 16)

    def _draw_wield(
        self, buffer: PatternBuffer, x: int, y: int, room: int
    ) -> None:
        """What the blade in his hand does, beside the verb that swings it.

        Short, and in the colours the wounds are drawn in on the monsters: the
        menu and the room say the same thing, so a player learns the vocabulary
        once. `( = X` when his hand is empty -- which is worth saying, because
        fighting bare-handed is a *choice* the game lets him make.

        Read from the equipment and not remembered, so a weapon swapped mid-floor
        shows up here before the next swing rather than after it.
        """
        keys = self.state.player.weapon_inflicts
        if not keys:
            buffer.text(x, y, "( = X", parse_style("grey30"))
            return
        column = buffer.text(x, y, "( = ", parse_style(ASH))
        for index, key in enumerate(keys):
            if index:
                column = buffer.text(column, y, " + ", parse_style(ASH))
            if column - x >= room:
                return
            column = buffer.text(column, y, key, parse_style(STATUS_COLOURS[key]))

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
        trick = special_by_key(self._picked) if self._picked else None
        # The trick being aimed is named in the frame, because the aim is still
        # a choice about the *attack*: what is about to be thrown at one of them
        # has to stay in front of the player while they pick which one.
        title = "TARGET" if trick is None else f"TARGET  ·  {trick.name}"
        box(buffer, x, y, width, height, title=title, border=BLOOD, fill=True)
        if height < 3 or width < 12:
            return
        living = self._targets()
        chosen = self.target % len(living) if living else 0
        for index, enemy in enumerate(living[: max(1, height - 4)]):
            lit = index == chosen
            marker = "►" if lit else " "
            style = parse_style(f"bold {BONE}" if lit else ASH)
            buffer.text(x + 2, y + 1 + index, f"{marker} {enemy.name}"[: width - 2], style)
        if trick is not None and height >= 4:
            buffer.text(x + 2, y + height - 3, trick.effect[: width - 2], parse_style(BONE))
        buffer.text(x + 2, y + height - 2, "◄ ►  pick", parse_style(ASH))

    def _draw_order(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The next few turns, in the alphabet the whole game is made of.

        A glyph a turn, in the actor's own colour, the one being taken now the
        brightest of them: a player deciding what to do this turn is deciding
        against the next two, and this is that sentence written short.

        Letters and not names, and the *same* letters the room is drawn in -- ``N``
        for Noxx and whatever the ghoul is -- so the strip reads as part of this
        fight rather than as a legend about it.
        """
        if self.picking or self.battle.over or height < 3 or width < 8:
            # The list wants the whole strip when it is open, and a fight that is
            # over has no order left to show.
            return
        # A short box, sitting on the same line as the two beside it. The strip is
        # one row of letters, and a box the full height of the others would be a
        # box of mostly nothing.
        tall = min(height, 3)
        top = y + height - tall
        box(buffer, x, top, width, tall, title="ORDER", border=BLOOD, fill=True)
        row = top + 1
        shown = min(len(self._order), max(1, (width - 2) // 3))
        for index in range(shown):
            actor = self._order[index]
            # Bold for the turn being taken, plain for the rest: bright enough to
            # read, different enough to tell apart. A strip the player has to
            # squint at is a strip they will not look at.
            style = parse_style(f"bold {actor.color}" if index == 0 else actor.color)
            buffer.text(x + 2 + index * 3, row, actor.glyph, style)
            if index + 1 < shown:
                buffer.text(x + 3 + index * 3, row, ">", parse_style(ASH))

    def _level_up(self, app) -> None:
        """The arrow rising off the hero, and the note that goes with it.

        A popup like a damage number and deliberately *not* one: it is bigger,
        it is gold, it starts a little higher than a number lands so the two
        never share a spot, and it drifts up and fades exactly the way a number
        does -- which is the joke of it. The loudest thing in the room is a
        number about somebody else; this is the quiet one about him.
        """
        figure = self._figure_of(self.battle.hero, app)
        if figure is None:
            return
        popup = self._popup(LEVEL_UP, LEVEL_UP_COLOUR, figure, app, True)
        popup.y -= 12  # clear of the damage numbers, which land on the same head
        self._popups.append(popup)
        app.play("level")

    def _took_a_turn(self, actor) -> None:
        """The strip moves on: whoever acted is done and the rest come up.

        Dropped up to *and including* them, and not simply off the front: a turn
        whose events are not all blows -- the hero finding a note for his sword,
        a monster swinging at where he was -- would otherwise leave the strip one
        turn behind for the rest of the round.
        """
        for index, waiting in enumerate(self._order):
            if waiting is actor:
                del self._order[: index + 1]
                return

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
        # The purse is in the *frame* of the list and not only on the plate,
        # because the list is what covers the plate: a player choosing what to
        # spend has to be able to see what there is to spend.
        # The frame says what the panel is, what it costs and what the keys do --
        # in words a player has not had to learn from anywhere else. "The dark"
        # was the fight's own name for its tricks and it read as a mystery; the
        # purse is the same stones the plate counts.
        top = max(1, self.state.kill_points_max)
        purse = POINT * min(self.kill_points, top) + HOLLOW * max(
            0, top - self.kill_points
        )
        box(
            buffer,
            x,
            y,
            width,
            height,
            title=f"SPECIAL ATTACKS      {purse}      enter  use      esc  back",
            border=BLOOD,
            fill=True,
        )
        if height < 4 or width < 24:
            return
        specials = self.battle.learned()
        rows = max(1, height - 4)
        # The list is as many columns as its tricks need and no more: two for a
        # kit of five or six, three for Noxx's eight. A fixed two columns would
        # have run his last three names off the right-hand edge of the panel.
        columns = max(1, min(3, math.ceil(len(specials) / rows)))
        column_w = width // columns
        for index, special in enumerate(specials):
            usable = self.battle.special_available(special)
            chosen = index == self.special
            marker = "►" if chosen else " "
            # The price, as stones, on every line and whether he can pay it or
            # not: a menu that hid what it cost would be a menu of surprises.
            # The number in front of it used to be a *keypress*, which is not a
            # thing to read a menu by.
            line = f"{marker} {special.name} {POINT * special.cost}"
            # Three steps and not two, and the gap between them wide: what he
            # can pay for is *bright*, what he cannot is barely there, and the
            # one under the marker is brighter still. The old middle step (ash
            # next to grey) was a difference the player had to hunt for.
            if not usable:
                style = parse_style("grey23")
            elif chosen:
                style = parse_style(f"bold {BONE}")
            else:
                style = parse_style("bold #b9b3c8")
            buffer.text(
                x + 2 + (index // rows) * column_w,
                y + 1 + (index % rows),
                line[: column_w - 2],
                style,
            )
        if specials:
            shown = specials[min(self.special, len(specials) - 1)]
            # What it *does* first, in the readable ink, and then how the fight
            # says it, dim: the numbers are the offer and the voice is the
            # colour. A list that only had the voice would be a list the player
            # has to guess their way through, and guessing is not a choice.
            buffer.text(x + 2, y + height - 3, shown.effect[: width - 4], parse_style(BONE))
            buffer.text(x + 2, y + height - 2, shown.blurb[: width - 4], parse_style(ASH))

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
