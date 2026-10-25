"""The fight's shared vocabulary: constants, small helpers and dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from ...game.battle import (
    ATTACK,
    SPECIAL,
)
from ..art import monster_art
from ..theme import Colour





def _picture(name: str) -> str | None:
    """The art for an actor, by name, or ``None`` if the sheets have none.

    Asked of the *sheets* and not of a toolkit: whether a figure has a picture is
    a fact about the art, and the room has to know it -- a sprite is drawn over
    its cell and a letter is not. The painting loads the file; the room only ever
    needs the name.
    """
    # A monster's picture is its *name*, with the spaces as underscores: "the
    # kindly one" is a sentence in the log and a file on disk, and the file cannot
    # have the space. The rule lives with the art, because the Almanac needs the
    # same answer about the same monster.
    return monster_art(name)

FLOOR_NEAR = Colour(0x2C, 0x2C, 0x36)
FLOOR_NEAR_ALT = Colour(0x20, 0x20, 0x28)
FLOOR_FAR = Colour(0x16, 0x16, 0x1C)
FLOOR_FAR_ALT = Colour(0x10, 0x10, 0x14)
WALL_NEAR = "grey30"
WALL_MID = "grey23"
WALL_FAR = "grey19"
THICKNESS = 5
TAPER = 0.18
POINT = "◆"
HOLLOW = "◇"
POINT_COLOUR = "bold #c084fc"
LEVEL_UP = "\u25b2 LVL UP"
LEVEL_UP_COLOUR = "#ffd34d"

ORDER_SHOWN = 3

STAGE = 3
AIMED: tuple[str, ...] = (ATTACK, SPECIAL)

ROWS: dict[int, tuple[tuple[float, float, float], ...]] = {
    # One monster stands where the middle of three stands and not dead centre:
    # the hero is centred, and a single enemy straight above him is a statue on
    # the same axis. The nudge is the middle lane's, so a fight reads the same
    # whether the room is full or holds one thing.
    1: ((-0.065, 0.88, 0.0),),
    2: ((-0.20, 1.00, 0.0), (0.20, 1.00, 0.0)),
    3: ((-0.30, 1.00, -1.0), (-0.065, 0.88, -0.75), (0.30, 1.13, -1.0)),
}

ECHO_STEP = 2
ECHO_LANE = -0.18

PANEL_ROWS = 7
LOG_ROWS = 3

ORDER_CELLS = 14
PANEL_FLOOR = 21

ARC_ROWS = 25 / 3

HERO_CLEARANCE = 4
HERO_CLEARANCE_CELLS = 4

HERO_DROP = 7.25

STAGE_LIFT = 1

MONSTER_SIZES = (62, 52, 46)
HERO_SIZE = 88
DRIFT_LIFE = 1.1
DRIFT_RISE = 86
DRIFT_SCALE = 0.65

ARROW = "▼"
FLAIR_COLOURS: dict[str, str] = {
    # Noxx: the dagger, the orb, the shadow, the vein, the step, the red wall.
    "left_hand": "#5bd75b",
    "orb_of_ptamera": "#2ee6cf",
    "fleeting_shadow": "#8ff0e0",
    "devouring_darkness": "#a45cff",
    "paint_the_walls_red": "#2ee6cf",
    "open_vein": "#d83a3a",
    "between_blows": "#b06bff",
    # Yeti: the mountain, the blizzard, the quake, the winter, the cold.
    "avalanche": "#cfe8ff",
    "snow_blind": "#dff4ff",
    "quake": "#bcdcff",
    "long_winter": "#8fcdf0",
    "rime": "#9fd8f5",
    "hoarfrost": "#bff0ff",
    "stillness": "#7fd4ff",
    # Walkyrion: the note, the throw, the true note, the echo, the chord.
    "first_note": "#ffd34d",
    "overture": "#ffdd77",
    "ringing_chord": "#ffc21f",
    "silence_after": "#fff3c4",
    "bells_throw": "#ffc21f",
    "true_note": "#ffb000",
    "echoing_cut": "#ffe9a8",
    # Inferno: the fists, and the fire that is the only rider he has.
    "jab": "#ffd9a8",
    "gut_punch": "#e0703f",
    "ember_fist": "#ff7a1f",
    "headbutt": "#ff5533",
    "red_mist": "#ff3b1f",
    "haymaker": "#ffb066",
    "roundhouse": "#ff8c42",
}
STATUS_COLOURS: dict[str, str] = {
    "bleed": "#e03131",
    "maul": "#ff5a4a",
    "poison": "#5bd75b",
    "burn": "#ff7a1f",
    "chill": "#9fd8f5",
    "numb": "#7fb3d5",
    "taint": "#7fbf5f",
}
STATUS_LOOKS: dict[str, str] = {
    "bleed": "bleed",
    "maul": "bleed",
    "poison": "poison",
    "burn": "burn",
    "chill": "frost",
}
STATUS_SOUNDS: dict[str, str] = {
    "bleed": "status_tick",
    "maul": "sword_heavy",
    "poison": "poison_hit",
    "burn": "fire_hit",
    "chill": "ice_shatter",
}
STATUS_ICONS: dict[str, str] = {
    "bleed": "bleed",
    "maul": "bleed",
    "poison": "poison",
    "burn": "burn",
    "chill": "chill",
    #: Two states with no picture of their own: they borrow the nearest one they
    #: are a sharper version of, because an icon is a *recognition*, and a plate
    #: with no badge for "numb" is a status the player cannot see at all.
    "numb": "chill",
    "taint": "poison",
}
STATUS_BADGE = 52
STATUS_ROW_IN = 20
STATUS_ROW_DOWN = 2
STATUS_GAP = 4
MONSTER_BADGE = 34
MONSTER_BADGE_GAP = 4
STATUS_SLOT = 0.95
FAR_LIGHT = 0.62
WALL_STONES: tuple[str, ...] = (
    "wall",
    "wall",
    "wall_vines",
    "wall",
    "wall",
    "wall_vines",
    "wall",
)
FLOOR_BONES = 45
GONE_LIFE = 0.6
WALL_LIFE = 1.2
SINK_LIFE = 0.9
SINK_DROP = 46
PAGE_AFTER = 0.45
FLOURISH_LIFE = 0.40
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
SELF_LOOKS: frozenset[str] = frozenset({"wall", "aura", "pulse", "fleet"})
SHAKES: dict[str, int] = {
    "shatter": 6,
    "wave": 6,
    "dissolve": 7,
    "throw": 4,
    "orb": 4,
    "drain": 3,
}
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
CRIT_SHOVE = 1.6
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
FLASH_LIFE = 0.11
FLASH_ALPHA = 0.10
FLASH_HARD_ALPHA = 0.18
HARD_BLOWS: frozenset[str] = frozenset({"shatter", "wave", "dissolve"})
BEAT = 0.34
LINE_BEAT = 0.12
END_BEAT = 0.06
POPUP_LIFE = 0.60
BOB_SPEED = 3.4
BOB_HEIGHT = 2
STRIKE = 0.26
IMPACT_AT = STRIKE * 0.46
JOLT = 0.20
JOLT_PIXELS = 3
LOG_LINES = 3



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
    #: The face this number hangs over. A painter needs it to sit the number
    #: above the *figure* -- over its arrow and not on it -- and how tall a face
    #: is is the painter's business, which is why this is a size and not an
    #: offset.
    size: int = 0
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
        "art",
        "affix",
        "warden",
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
        art: str | None = None,
        affix: str | None = None,
        warden: bool = False,
        phase: float = 0.0,
    ) -> None:
        self.actor = actor
        #: Where this figure is in its own breath. Different for every figure, or
        #: a row of them would rise and fall like a wave.
        self.phase = phase
        #: The art for this actor, *by name* -- ``sprites/ghoul.png`` -- or
        #: ``None`` if the sheets have nothing, which means draw the letter. A
        #: name and not an image, because the staging is what both front ends
        #: read and a picture is the painter's to hold.
        self.art = art
        #: Which aspect the figure wears, if any: the painter gives it an aura
        #: and the name already carries the word.
        self.affix = affix
        #: The keeper of the ring wears a second, gold light under it. It is a
        #: job, not an aspect; the name is the other half of the mark.
        self.warden = warden
        self.glyph = glyph
        self.colour = colour
        self.size = size
        #: The centre of the letter, in pixels.
        self.cx = cx
        #: The cell row it stands on: the top of the pool of shadow, so the
        #: figure stands behind its own shadow rather than on top of it. A whole
        #: row usually and *half* a row where half a row is the right place to
        #: stand -- it is multiplied out into pixels by both painters, so a
        #: fraction costs nothing and saves the row of floor the eye can see.
        self.row = row
        self.cells = cells
        self.chosen = chosen


