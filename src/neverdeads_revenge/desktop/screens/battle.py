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

from typing import Any

import math
from dataclasses import dataclass

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
from ..art import exists as art_exists
from ..art import size as art_size
from ..chrome import ASH, BLOOD, BONE, box, rule
from ..pattern import PatternBuffer
from ..render import log_style
from ..theme import Colour, Style, parse_style
from .base import Screen

__all__ = ["BattleScreen", "Popup", "Staged", "art_scale"]



def _picture(name: str) -> str | None:
    """The art for an actor, by name, or ``None`` if the sheets have none.

    Asked of the *sheets* and not of a toolkit: whether a figure has a picture is
    a fact about the art, and the room has to know it -- a sprite is drawn over
    its cell and a letter is not. The painting loads the file; the room only ever
    needs the name.
    """
    where = f"sprites/{name}.png"
    return where if art_exists(where) else None

#: The floor's two tile tones at the hero's feet, and the same two at the far
#: edge. Distance is shade here, not size: the far rows fade into the dark the
#: way a remembered wall does, because the phosphor fades rather than switches.
FLOOR_NEAR = Colour(0x2C, 0x2C, 0x36)
FLOOR_NEAR_ALT = Colour(0x20, 0x20, 0x28)
FLOOR_FAR = Colour(0x16, 0x16, 0x1C)
FLOOR_FAR_ALT = Colour(0x10, 0x10, 0x14)
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
#: room, how far into it, and a nudge up, all as fractions of the ground's width
#: and height. Both a lane and a depth are shares and not pixels, so the row moves
#: with the band; the third number is in rows as well, and half of one is the ten
#: pixels the eye asks for when whole rows stand a monster too low.
#:
#: A fight of *one* should look like a fight of one. The stage was built for
#: three, and a single monster was being shoved into the left-hand slot of a row
#: that was not there -- so the row is laid out by its own count: one in the
#: middle of the room, two on either side of that middle, and three in the
#: shallow arc the stage was drawn for, with the outer ones a little nearer, the
#: way a line of anything stands. The one in the arc that stands furthest back is
#: all three set below their depth lines now -- the outer two by a whole row each and
#: the middle by three quarters -- which is the fifth pass over this one number and the
#: first one that moved the *row* as a whole rather than the arc's shape. It was
#: raised twice by eye while the staging was still measured in the grid's rows and
#: the middle kept drifting into the wall, and once the stage was anchored to the
#: painting's floor those two nudges were a step too far. Half a row leaves it
#: standing in the floor band with a visible arc and no drift.
#:
#: Nothing stands at the rim. The floor tapers, so the far corners of it are
#: *wall* -- an outer monster at the very edge was standing in the masonry with
#: its health bar running off the frame, and the row was as wide as the room
#: instead of as wide as a row. The arc is the same shape, pulled in.
ROWS: dict[int, tuple[tuple[float, float, float], ...]] = {
    1: ((0.0, 0.88, 0.0),),
    2: ((-0.20, 1.00, 0.0), (0.20, 1.00, 0.0)),
    3: ((-0.30, 1.00, -1.0), (-0.065, 0.88, -0.75), (0.30, 1.13, -1.0)),
}

#: How tall the panels and the log are, in rows, at *every* grid. Two numbers and
#: not a ladder of them: what the window does to the grid is how much floor there
#: is, and the furniture is the furniture.
PANEL_ROWS = 7
LOG_ROWS = 3

#: The cell the sprites were installed for: ten pixels wide, twenty tall.
#:
#: The sheets are cut for this grid and every figure in the game is placed in
#: *cells* -- a row is a row and a lane is a lane at any size. The picture is the
#: one thing that does not follow the cell by itself, so it is scaled by the ratio
#: of the cell it is standing in to this one.
ART_CELL_W = 10


def art_scale(cell_w: int) -> int:
    """How much bigger a figure is drawn here than it was installed.

    A whole multiple, and rounded rather than exact: a painter's figure through a
    nearest-neighbour resize is a figure with one eye, and half a multiple is the
    same mistake at a different size. Ten-pixel cells answer 1 -- the desktop's own
    size, drawn as it always was -- and a handheld's twenty answer 2.

    Without it a handheld draws the same *pixels* as a desktop in a frame twice as
    tall, which is a ghoul at half its relative size and a hero lost in a room that
    got bigger around him. With it the composition is the same and only the grid
    differs, which is what every other thing in this game already did.
    """
    return max(1, round(cell_w / ART_CELL_W))


#: The ORDER strip's own width, in cells, and the narrowest a panel is allowed to
#: become to pay for it.
#:
#: The strip used to be *whatever the two panels left* between them, which reads
#: fine on a wide grid and is nothing on a narrow one: at the smallest grid the
#: game claims to support it came out two cells wide -- an order of battle two
#: characters across -- and a handheld's grid is narrower still. It is the thing
#: a player reads while deciding, so it is paid for out of the panels, and no
#: further than the width the plate's own numbers need -- twenty-one cells is
#: where the HP bar, the purse and the kills line still all fit.
ORDER_CELLS = 14
PANEL_FLOOR = 21

#: How many rows further back a lane stands, per unit of depth. The number is the
#: one the staging was tuned at -- twelve hundredths of a depth was a row -- and it
#: is fixed, so the arc is the same shape however many rows the window fit.
ARC_ROWS = 25 / 3

#: How many rows of room a monster leaves the hero when it is standing over him:
#: his own height, near enough. And how many cells to the side it stops counting as
#: "over him" -- a sprite is five or six cells wide, and so is his.
HERO_CLEARANCE = 4
HERO_CLEARANCE_CELLS = 4

#: How far below the foot of the floor band the hero stands, in rows. He is the
#: room's front: on the plate, which is four or five rows under the band whatever
#: grid the window was derived for -- so a row count keeps him there, and a share
#: of the band (which is what a depth is) would not. The quarter is the fifteen
#: pixels he was asked to come up by -- and then two rows *down* again, because the
#: sheets are drawn at twice the game's pixels now and a tall hero reaches up into the
#: room: standing lower is what gives the row above him its air back.
HERO_DROP = 7.25

#: How far up the whole stage stands, in rows, from the row it was laid out on.
#:
#: A quarter of a Noxx, near enough: twenty pixels, which is one row. The figures,
#: their stripes, their wound symbols and the aim arrow are all placed *from* the
#: row, so lifting the row lifts every one of them together -- which is the only
#: way they stay in step. The floor band does not move: the room is where it was
#: and the fight stands a little higher in it.
STAGE_LIFT = 1

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
    # Inferno: the fists, and the fire that is the only rider he has.
    "jab": "#ffd9a8",
    "gut_punch": "#e0703f",
    "ember_fist": "#ff7a1f",
    "headbutt": "#ff5533",
    "red_mist": "#ff3b1f",
    "haymaker": "#ffb066",
    "roundhouse": "#ff8c42",
    "bonfire": "#ff5a1f",
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
    "bleed": "status_tick",
    "maul": "sword_heavy",
    "poison": "poison_hit",
    "burn": "fire_hit",
    "chill": "ice_shatter",
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
        #: The grid this screen was last drawn into, kept because the paste step
        #: needs one part of it *again*: the panels are cells, the cells are under
        #: the art, and the menu has to end up on top of whoever is standing in
        #: front of it. The same reason ``_size`` is kept -- a painter that paints
        #: in two passes has to agree with itself about the first one.
        self._grid = None
        #: Where the painting's *wall* begins, in frame pixels from the top. Set by
        #: the front end that owns the artwork -- it is the one line only it knows,
        #: because it depends on where the painting was placed -- and no monster
        #: stands above it. ``None`` is a room of cells, which has no wall line.
        self.stage_horizon: float | None = None
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
        #: And which wounds have been *seen*: the same rule one step further, for
        #: the badge row. The rules inflict a wound at the swing -- they resolve
        #: the whole turn at once -- and the room must not: a badge that turned up
        #: while the sword was still in the air is the fight telling the player
        #: the ending of the sentence they are in the middle of.
        self._wearing: dict[int, tuple[str, ...]] = {}
        #: And how deep each of those is, read at the same moment: the badge
        #: carries a number once a wound is more than one stack, and a number
        #: that arrived before its blow would be the same lie as a badge that did.
        self._depths: dict[int, dict[str, int]] = {}
        #: Who the fight still owes a look at, and when. Everything in here is
        #: read at the frame it comes due, which is always the frame a blow lands
        #: in or a wound bites -- never the frame the rules knew.
        self._wounds_due: list[tuple[float, Any]] = []
        self._catching_up()
        #: The three numbers on the plate that a *level* moves -- the count, the
        #: level, and how wide the purse is -- read the way the bars are read and
        #: not live: the rules raise a level the moment the kill resolves, and the
        #: fight must not say so until the arrow is going up. Everything else on
        #: the plate is the hero's own turn rather than a blow's, and stays live.
        self._plate: dict[str, int] = {}
        self._reading()
        #: What a trick left standing on the *hero*: its look, its colour, when.
        self._self: tuple[str, str, float] | None = None
        #: A trick that was not a blow: its word, and when it happened. Only the
        #: hero raises one, and only one at a time -- a wall and an aura at once
        #: would be two answers to one turn.
        self._flourish: tuple[str, float] | None = None

    # -- the contract -------------------------------------------------------
    def draw(self, buffer: PatternBuffer, app, ground: bool = True) -> None:
        #: The size this screen is being drawn at, remembered: the letters are
        #: placed in pixels and the paste step has to agree with the grid pass
        #: about where the floor is, and the grid pass is the one that knows.
        self._size = (buffer.cols, buffer.rows)
        self._grid = buffer
        buffer.clear()
        areas = self._areas(buffer.cols, buffer.rows)
        # The cell floor is a *dial*, because a front end with a painting for a
        # room has no use for it: two thousand of the frame's cells written and
        # then written again in the room's own black was a millisecond a frame
        # thrown away. The painter's room is not a thing this screen knows about,
        # so it is told.
        if ground:
            self._draw_ground(buffer, areas["ground"])
        self._draw_health(buffer, areas["ground"])
        # The log lives at the *top* of the frame: the room has the bottom now,
        # and a fight's account of itself belongs where the eye goes first.
        self._draw_log(buffer, (0, 0, buffer.cols, areas["log"][3]))
        self._draw_plate(buffer, *areas["plate"])
        self._draw_commands(buffer, *areas["commands"])
        self._draw_order(buffer, *areas["order"])

    def panel_band(self, cols: int, rows: int) -> tuple[int, int]:
        """The rows the three panels own: the fight's own layer, top to bottom.

        The panels are written into the grid, and the grid is *under* the art -- so
        a figure standing in front of them is painted over the menu that is asking
        about it. Both painters put this band down a second time once the figures
        are in place, which is what keeps the menu on top of whoever is standing in
        front of it: the hero is covered by the plate he is standing in, and the
        list of tricks covers him entirely.

        A band and not the three areas, because which panel is showing is the
        screen's business: the verbs, the list of the five, the target row and the
        plate all come and go inside these rows.
        """
        plate = self._areas(cols, rows)["plate"]
        return plate[1], plate[1] + plate[3]

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

    @staticmethod
    def _look(flair: str) -> str:
        """How a blow was struck, as its own word -- or ``""`` for a plain one.

        The rules say which *trick* was used; what that trick looks like is the
        screen's to know, so a hero can get a look without the fight learning a
        colour.
        """
        special = special_by_key(flair) if flair else None
        return special.look if special is not None else ""

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

    def _worn(self, actor) -> list[str]:
        """Which wounds somebody is wearing, in a stable order."""
        return sorted(key for key in actor.statuses if key in STATUS_ICONS)

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

    def _verdict_panel(
        self, cols: int, rows: int, font
    ) -> tuple[PatternBuffer, int, int]:
        """What the fight came to, as a panel of cells and where it lands.

        Built here and not drawn, because *where* it goes is the arena's business
        and *what* it says is the fight's -- and because a second front end wants
        the same panel without a painter. Set on the *stage* and not in the middle
        of the glass: the last lines of the fight are the only account of how it
        ended, and a panel dropped over them would be covering the story with its
        title.
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

        panel = PatternBuffer(width, height, font)
        colour = {"YOU DIED": BLOOD, "VICTORY": "bright_yellow"}.get(text, ASH)
        box(panel, 0, 0, width, height, border=colour, fill=True)
        ink = parse_style(f"bold {BONE}")
        left = 3 + max(0, (width - 6 - len(text)) // 2)
        panel.text(left, 2, text, ink)
        rule(panel, 1, height - 2, width - 2, ASH)
        panel.text(2, height - 1, "enter  leave the arena", parse_style(ASH))
        return panel, x, y

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
            return True
        if name == "down":
            self.verb = (self.verb + 1) % len(VERBS)
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
                app.play("error_locked")
                return
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
            app.play("error_locked")
            return True
        # The number keys still work and are no longer *shown*: the list carries
        # the price of each trick where the number used to be, and a shortcut is
        # a convenience for the player who already knows the list by heart.
        index = {str(digit): digit - 1 for digit in range(1, 10)}.get(name)
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
            self.picking = False
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
            app.play("error_locked")
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
        from ...desktop.audio import cast_sound

        if VERBS[self.verb] == SPECIAL:
            trick = special_by_key(special) if special else None
            app.play(cast_sound(special, trick.look if trick else ""))
        elif VERBS[self.verb] == ITEM:
            app.play("potion_use")
        elif VERBS[self.verb] == FLEE:
            app.play("dash_roll")
        else:
            app.play("weapon_draw")
        if not living:
            self._resync()

    def _reading(self) -> None:
        """Take down what the plate is allowed to say about the level.

        Not a cache: a *reading*, taken at the moments the fight is not being
        watched -- the first frame, the end of a round -- and at the one moment
        it is being watched and ought to move, which is the level-up's own
        animation. The rules are a moment ahead of the room everywhere else too;
        this is the same promise the health bars keep.
        """
        self._plate = {
            "kills": self.state.kills_to_level,
            "level": self.state.level,
            "top": max(1, self.state.kill_points_max),
        }

    def _snapshot(self) -> None:
        """Freeze what the bars say, so the playback can move them itself."""
        for actor in [self.battle.hero, *self.battle.enemies]:
            self._shown[id(actor)] = actor.stats.hp
        self._catching_up()
        self._reading()

    def _catching_up(self, actor=None) -> None:
        """Read the rules' own wounds, for the badge row to catch up with.

        Called where the fight is *not being watched* -- the first frame, and
        the moment a round has finished being played -- so that a row can never
        arrive before the thing it is about. When an actor is named, only that
        one is read: that is the call the playback makes, one actor at a blow.
        """
        actors = (
            [actor]
            if actor is not None
            else [self.battle.hero, *self.battle.enemies]
        )
        for one in actors:
            self._wearing[id(one)] = self._worn_for(one)
            self._depths[id(one)] = dict(one.status_stacks)

    def _worn_for(self, actor) -> tuple[str, ...]:
        """What the *rules* say this figure is wearing, as a badge row."""
        return tuple(sorted(key for key in actor.statuses if key in STATUS_ICONS))

    def _worn(self, actor) -> tuple[str, ...]:
        """What the *room* has shown so far. Empty until an animation says so."""
        return self._wearing.get(id(actor), ())

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
        if self._wounds_due:
            # And the wounds, on the same clock as the numbers and the sparks:
            # this is the frame a blow lands in, and a wound belongs to the blow
            # that made it -- not to the swing, and not to the rules.
            due = [actor for when, actor in self._wounds_due if self._clock >= when]
            self._wounds_due = [
                (when, actor) for when, actor in self._wounds_due if self._clock < when
            ]
            for actor in due:
                self._catching_up(actor)

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
        self._catching_up()
        # And the plate reads again, so a kill that did *not* raise a level still
        # moves its count -- at the end of the round, which is where the next
        # choice is made and nothing is in the middle of being watched.
        self._reading()
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
            app.play(
                "quest_complete"
                if event.won
                else "dash_roll"
                if event.escaped
                else "death_game_over"
            )
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
            from ...desktop.audio import cast_sound, weapon_sound

            if struck.actor is self.battle.hero:
                trick = special_by_key(struck.flair) if struck.flair else None
                number.sound = (
                    "kill"
                    if outcome.killed
                    else "critical_hit"
                    if outcome.crit
                    else cast_sound(struck.flair, trick.look if trick else "")
                    if trick is not None
                    else weapon_sound(self.state.player.weapon_inflicts)
                )
            else:
                number.sound = "player_hurt"
            if not outcome.hit:
                # A swing that met air is its own sound and not silence: the
                # player has to hear that the turn was spent and nothing landed.
                number.sound = "miss_dodge"
            self._popups.append(number)
            # Owed, and paid at the impact: a wound the blow inflicts is read on
            # the frame the number is, which is what "the sword did it" means.
            self._wounds_due.append((self._clock + IMPACT_AT, struck.target))
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
        colour = parse_style(STATUS_COLOURS.get(status.key, "#ffffff")).fg.lighter().name()
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
            number = self._popup(str(status.damage), colour, figure, app, False)
            number.age = -IMPACT_AT
            number.target_id = id(actor)
            # A wound that finished it is a *killing blow* like any other, and
            # the room has to let the figure go -- which it does off this flag.
            # It was only ever set by a sword, so a monster that bled to death
            # stayed standing there: no health, the fight over, and a corpse
            # the arena had never been told about.
            number.killed = actor.stats.hp <= 0
            self._popups.append(number)
        point = self._point_of(actor, app)
        if point is not None:
            app.effects.spark(point, colour, SPARKS.get(look, 16))
            app.view.shake(strength=2, seconds=0.12)
        # And the badge row catches up on the same frame the number does -- which
        # is also the frame a wound that has *run out* stops being worn, so the
        # row is never a list of problems the fight is finished with.
        self._wounds_due.append((self._clock + IMPACT_AT, actor))
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

        Hung on the figure's own *line* and not at the height it will be read at:
        how far above a head a number has to sit depends on the face it is drawn
        in -- over the arrow as well as over the letter, or the number a player is
        reading would stand exactly where the target marker is -- and that is the
        painter's business, the same way the verdict panel's place is. The number
        says what it is about; the painter puts it down.
        """
        return Popup(
            text=text,
            colour=colour,
            x=figure.cx,
            y=round(figure.row * app.font.cell_h - THICKNESS),
            crit=crit,
            size=figure.size,
        )

    # -- where things are --------------------------------------------------
    def _areas(self, cols: int, rows: int) -> dict[str, tuple[int, int, int, int]]:
        """Where the pieces sit, in cells: wall, ground, log, plate, commands.

        Five bands, bottom to top: the panels, the lines the fight speaks in,
        the floor, and the strip the walls stand up into. The wall strip is
        reserved rather than overlaid -- a wall drawn over the floor would be a
        wall standing in front of the hero.
        """
        margin = max(1, min(3, cols // 24))
        # The panels and the log are *always* this tall, whatever the window did to
        # the grid. They used to shrink on a short grid -- seven rows above
        # twenty-six, five above sixteen -- which was written for a tiny window and
        # fired on a wide one: a 21:9 monitor derives 114x24, and the same game came
        # up with a shorter ORDER strip, a shorter log, and the hero standing twenty
        # pixels lower in his own plate. The composition is not a function of how
        # many cells the window happened to fit.
        panel_h = PANEL_ROWS
        # One row of air under the panels and not the margin's three: the room has
        # more use for those rows than the frame has for a border, and the log has
        # moved out of the bottom anyway.
        panel_y = max(1, rows - panel_h - 1)
        log_h = LOG_ROWS
        log_y = max(1, panel_y - log_h)
        wall_h = max(2, min(3, rows // 8))
        wall_y = margin
        ground_y = min(log_y - 1, wall_y + wall_h)
        ground_h = max(1, log_y - ground_y)
        # The strip is reserved *before* the panels -- and the panels are then
        # what takes the leftover, capped as they always were. That is the fix:
        # the strip used to be the leftover itself, which reads fine on a wide
        # grid and is nothing on a narrow one (two cells at eighty columns, none
        # at all on a handheld's sixty-odd), and it is the thing a player reads
        # while deciding. At ninety-six columns the cap is what pays for it,
        # exactly as it always did: 36 + 36 + 16 and the margins are 96.
        panel_w = max(PANEL_FLOOR, min((cols - margin * 3 - ORDER_CELLS) // 2, 36))
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

    def _floor_row(self, cols: int, rows: int) -> int:
        """The row the room's floor is on: the foot of the ground band.

        One number, asked of the layout, and the painting is fitted to it -- which
        is the other way round from fitting the staging to the painting, and the
        right way round: the room's floor is where the game's own furniture leaves
        it, and that is a fixed number of rows above the panels at every window.
        """
        _x, y0, _w, ground_h = self._areas(cols, rows)["ground"]
        return y0 + ground_h - 1

    def _row_for(self, depth: float, lift: float, y0: int, height: int) -> float:
        """Where a monster stands, in rows: the room's floor, and the depth from it.

        One rule for both kinds of room, and the *rows* are the truth in both: the
        floor is the foot of the ground band -- a fixed number of rows above the
        panels, at every window -- and a depth walks back from there by a fixed
        number of rows. It used to be a share of the band's own height, which is
        how the same fight came out spread further apart on a taller window; the
        grid decides how much floor there *is*, not how deep a lane stands.

        ``ARC_ROWS`` is the row of twenty pixels the staging was tuned at: a lane
        twelve hundredths of a depth behind the front one stands one row further
        back, and the front one stands on the floor line itself.
        """
        return (y0 + height - 1) - STAGE_LIFT - (1.0 - depth) * ARC_ROWS - lift

    def _stage(self, field: dict[str, float]) -> list[Staged]:
        """Who stands where: the monsters in the far half, the hero in front.

        The monsters are the actors themselves, in the order they were met --
        their glyph, their colour, their depth. Nothing is invented here: a fight
        against three vipers is three v's on the floor, and a fight against one
        is one v in the middle of it.
        """
        cell_w = int(field["cell_w"])
        cell_h = int(field["cell_h"])
        x0, y0 = int(field["cells_x0"]), int(field["cells_y0"])
        width, height = int(field["cells_w"]), int(field["cells_h"])
        centre = x0 + width // 2
        living = self._targets()
        # The arrow is out only while something is being aimed: it marks the
        # *question*, and there is no question on the floor until a trick has
        # asked one.
        marked = living[self.target % len(living)] if self.aiming and living else None
        scale = 1.35 if width >= 120 else 1.0
        # The room's floor, in rows: the band's own foot, or -- when the room is a
        # Where the hero will stand, in rows -- the monsters are kept off his head
        # below, and that rule does not care whether the room is a painting.
        hero_row = y0 + height - 1 + HERO_DROP - STAGE_LIFT
        # And never into the panels: a floor line low enough to be *inside* the
        # menu is a floor line the menu is standing on, so the monsters stop at the
        # first row above it. The grid's own size, which this screen is told every
        # time it is drawn -- the field below is the *room's* band and does not know
        # where the panels are.
        size = self._size or (0, 0)
        lowest = (
            max(1, self._areas(*size)["plate"][1] - 1)
            if size[0] and size[1]
            else y0 + height
        )
        # The back of the room: no monster stands above the wall. A lane with a
        # nudge of its own can cross it -- the middle of three is the only one that
        # has a nudge, which is why it is the only one that ever ended up in the
        # wall -- and the line is the artwork's, not the lane's.
        highest = -1e9
        if self.stage_horizon is not None:
            highest = (self.stage_horizon + THICKNESS) / max(1, cell_h)
        monsters = self.battle.enemies[:STAGE]
        places = ROWS.get(len(monsters), ROWS[STAGE])
        staged: list[Staged] = []
        for index, enemy in enumerate(monsters):
            lane, depth, lift = places[min(index, len(places) - 1)]
            size = round(MONSTER_SIZES[min(index, len(MONSTER_SIZES) - 1)] * scale)
            art = _picture(enemy.name)
            cx = (centre + round(lane * width) + 1) * cell_w
            # Standing over the hero is the one place a monster may not be: he is
            # the near figure and the plate is his home, and on a short frame -- a
            # very wide monitor derives fewer rows than a tall one -- the painting's
            # floor line and the panel band come close enough for a collision. The
            # room compresses instead, and only there.
            if abs(cx - (centre + 1) * cell_w) <= HERO_CLEARANCE_CELLS * cell_w:
                floor_here = min(lowest, hero_row - HERO_CLEARANCE)
            else:
                floor_here = lowest
            staged.append(
                Staged(
                    actor=enemy,
                    glyph=enemy.glyph,
                    colour=enemy.color,
                    size=size,
                    cx=cx,
                    row=min(
                        floor_here,
                        max(highest, self._row_for(depth, lift, y0, height)),
                    ),
                    cells=self._span(art, cell_w),
                    chosen=enemy is marked,
                    art=art,
                    phase=index * 1.9,
                )
            )
        hero = self.battle.hero
        size = round(HERO_SIZE * scale)
        art = _picture(hero.name)
        staged.append(
            Staged(
                actor=hero,
                glyph=hero.glyph,
                colour=hero.color,
                size=size,
                cx=(centre + 1) * cell_w,
                row=y0 + height - 1 + HERO_DROP - STAGE_LIFT,
                cells=self._span(art, cell_w),
                art=art,
                # In front of the row and out of step with it: the hero breathes
                # on his own, as somebody standing still in front of a crowd does.
                phase=len(monsters) * 1.9 + 0.9,
            )
        )
        return staged

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
    def _stone(along: int, course: int) -> str:
        """Which stone is at this place in a wall, by name: mostly plain,
        sometimes not.

        Chosen from the place in the wall and not rolled for, so the scattered
        vines stay where they grew: a room that re-dressed itself every frame
        would be a room made of flicker. Named and not loaded -- the same split
        the floor's stones keep -- so a front end with no QPainter can lay the
        same wall.
        """
        return WALL_STONES[_scatter(along, course) % len(WALL_STONES)]

    @staticmethod
    def _floor_stone(along: int, row: int, light: bool) -> str:
        """Which flagstone is here, by name: the tone the checker wants, and
        sometimes what is lying on it.

        Chosen from the place and not rolled for, for the same reason the wall's
        scatter is: bones stay where they were left. Named rather than loaded,
        because *which* stone belongs at a place is the room's rule and loading
        it is the painter's business -- which is what lets a blitter with no
        painter at all lay the same floor.
        """
        tone = "a" if light else "b"
        if _scatter(along, row) % FLOOR_BONES == 0:
            return f"floor_{tone}_bones"
        return f"floor_{tone}"

    @staticmethod
    def _span(art: str | None, cell_w: int) -> int:
        """How many cells wide the pool of shadow under a figure has to be.

        The picture's own width when there is one -- read off the file, because
        how wide a picture is is a fact about the picture -- and two cells when
        there is not: the letter that stands in for it is one cell of the grid,
        and the grid is what this is measured against. Nothing here needs a font,
        which is the point: a shadow belongs to the room and not to the painting.

        And the picture is measured *as it will be drawn*: on a grid whose cells
        are twice as wide, a sprite is drawn twice as big (see ``art_scale``), so a
        ghoul is thirteen cells of shadow on a handheld and thirteen on a desktop
        -- the same composition, which is the whole reason the scale exists.
        """
        measured = art_size(art) if art is not None else None
        if measured is None:
            return 2
        return max(2, round(measured[0] * art_scale(cell_w) / cell_w))

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
        # Rounded, because a figure may stand on half a row and a pixel a
        # painter is handed is a whole one.
        return (figure.cx, int(figure.row * cell_h))

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
    def _tile(depth: float, alt: bool) -> Colour:
        """The floor's colour at ``depth``: 0 at the far edge, 1 at the hero.

        Mixed on the three channels and not through a toolkit: two palette colours
        and a tone between them is arithmetic, and the *grid* floor that wears it
        is the half of this screen that has to work without one.
        """
        near, far = (FLOOR_NEAR, FLOOR_FAR) if alt else (FLOOR_NEAR_ALT, FLOOR_FAR_ALT)
        return Colour(
            int(far.r + (near.r - far.r) * depth),
            int(far.g + (near.g - far.g) * depth),
            int(far.b + (near.b - far.b) * depth),
        )

    def _draw_health(
        self, buffer: PatternBuffer, area: tuple[int, int, int, int]
    ) -> None:
        """Under each monster *that has no picture*, the part of it that is left.

        The fallback and not the bar: a figure the sheets have art for gets its
        stripe over its head in the paste, and a stripe here as well would be a
        second one -- which is what it looked like the moment the two places came
        apart. For a figure with no art the letter is the monster, the floor is the
        only room there is, and this is the sole place its health can be said.
        """
        font = buffer.font
        for figure in self._figures(buffer.cols, buffer.rows, font):
            if figure.actor is self.battle.hero or figure.art is not None:
                continue
            total = max(1, figure.actor.max_hp)
            shown = self._shown.get(id(figure.actor), figure.actor.stats.hp)
            cells = max(8, min(14, figure.cells * 2))
            left = round(figure.cx / font.cell_w) - cells // 2
            # In the figure's own row, which is the one its feet are at the top
            # of: a bar a row lower was a bar floating about on its own. Rounded,
            # because a bar written into the grid lands on whole rows and a figure
            # may be standing on half of one.
            self._bar(buffer, left, round(figure.row), cells, shown / total, thin=True)

    def _draw_log(self, buffer: PatternBuffer, area: tuple[int, int, int, int]) -> None:
        """The lines the fight speaks in, newest last, in the dungeon's colours.

        The same mapping the dungeon log uses, which is the point: a curse is
        the same red here as it is down there, and a kill is the same bad news.

        Behind the words is a strip of the dungeon's own black, the width of the
        frame: this is read over a *painting* now, and a line of prose on stone is
        a line nobody reads. Three rows for three lines and not a row more: a row
        of black under the words was a row of black hanging under them.
        """
        from ..theme import BACKGROUND

        x, y, width, height = area
        if width < 20:
            return
        for row in range(y, y + height):
            buffer.fill_row(row, " ", Style(bg=BACKGROUND))
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
            top = self._plate["top"]
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
            to_go = self._plate["kills"]
            level = self._plate["level"]
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
        # And *now* the plate may say it: the count, the level and the purse all
        # move with the arrow, which is the moment the level happened for the
        # player rather than the moment the rules worked it out.
        self._reading()
        app.play("level_up")

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
        top = self._plate["top"]
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
