"""The heroes' own tricks: the ways to spend a turn that are theirs alone.

Nothing in here is an **ultimate**. An ultimate is the overworld's -- one ask
per floor, bound to ``f``, and its effect walks into the fight with you (Atritas
comes and helps, the wall stands, the floor burns). A trick is what the *room*
offers: paid out of kill points, listed in the battle menu, and never once a
floor.

Every hero's kit has a shape, and the shape is the hero. Noxx is a shadowy
assassin whose petrol-coloured shadow has a life of its own, whose right hand
holds a rapier and whose left holds a green dagger: the honest little knife, the
shadow that goes on its own, a cut that will not close, a step so quick that
nothing finds him, and the room painted red with what he opened.

Nothing here resolves anything. Each entry names *what* a special is and what it
costs; `game/battle.py` runs them through the same blow every other attack in
this game goes through, which is what keeps a special from being a second game
hidden inside the first.

**One trick a level**, and that is a rule rather than a habit: seven tricks, the
levels two to eight, so every level a run earns hands over exactly one new way to
spend a turn. Two of them arriving together was a level that felt like a list.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AVALANCHE",
    "BELLS_THROW",
    "CHORD",
    "BETWEEN_BLOWS",
    "DEVOURING_DARKNESS",
    "EMBER_FIST",
    "GUT_PUNCH",
    "HAYMAKER",
    "HEADBUTT",
    "INFERNO_SPECIALS",
    "JAB",
    "RED_MIST",
    "ROUNDHOUSE",
    "ECHOING_CUT",
    "FIRST_NOTE",
    "FLEETING_SHADOW",
    "PAINT_THE_WALLS_RED",
    "HOARFROST",
    "LEFT_HAND",
    "LONG_WINTER",
    "OPEN_VEIN",
    "ORB_OF_PTAMERA",
    "OVERTURE",
    "RIME",
    "SILENCE",
    "SNOW_BLIND",
    "SPECIALS",
    "SPECIALS_BY_HERO",
    "STILLNESS",
    "TRUE_NOTE",
    "QUAKE",
    "Special",
    "learned_at",
    "special_by_key",
    "specials_for",
]

#: The keys, so a caller never has to spell one out.
LEFT_HAND = "left_hand"
ORB_OF_PTAMERA = "orb_of_ptamera"
FLEETING_SHADOW = "fleeting_shadow"
DEVOURING_DARKNESS = "devouring_darkness"
PAINT_THE_WALLS_RED = "paint_the_walls_red"
OPEN_VEIN = "open_vein"
BETWEEN_BLOWS = "between_blows"
AVALANCHE = "avalanche"
SNOW_BLIND = "snow_blind"
QUAKE = "quake"
LONG_WINTER = "long_winter"
RIME = "rime"
HOARFROST = "hoarfrost"
STILLNESS = "stillness"
FIRST_NOTE = "first_note"
OVERTURE = "overture"
CHORD = "ringing_chord"
SILENCE = "silence_after"
BELLS_THROW = "bells_throw"
TRUE_NOTE = "true_note"
ECHOING_CUT = "echoing_cut"
JAB = "jab"
GUT_PUNCH = "gut_punch"
EMBER_FIST = "ember_fist"
HEADBUTT = "headbutt"
RED_MIST = "red_mist"
ROUNDHOUSE = "roundhouse"
HAYMAKER = "haymaker"


@dataclass(frozen=True, slots=True)
class Special:
    """One of Noxx's tricks: what it is called, and what it asks for."""

    key: str
    name: str
    #: What it *does*, in plain words and with the numbers in it: what is hit,
    #: how hard, and for how long. The player has to be able to read this and
    #: know, because a fight is not a guessing game -- and the voice below is a
    #: voice, not an instruction. Kept short enough to fit one line of a panel.
    effect: str
    #: One line about it, in the fight's own voice, for the menu to show under
    #: the facts: colour, not information.
    blurb: str
    #: The level it arrives at. Zero means "the dark's own gate" -- see below.
    level: int
    #: What it costs, in kill points. One purse for the whole kit, so the price
    #: is the decision: the cheap wound twice, or the big thing once, or nothing
    #: and wait for the purse to fill. Priced against `levels.KILL_POINTS`, which
    #: is what a hero of the level that learns it can *hold* -- so a trick is
    #: affordable the moment it arrives.
    cost: int = 0
    #: How it should *look*, for whoever is doing the showing. A look and not a
    #: colour, because a colour is not enough to tell fifteen tricks apart:
    #: ``"slash"`` cuts, ``"shatter"`` showers shards, ``"frost"`` leaves crystals,
    #: ``"pulse"`` rings out from the hero, ``"aura"`` glows on him, ``"ring"``
    #: travels, ``"wave"`` goes through the room, ``"throw"`` sends what it hit
    #: back, ``"shadow"`` sends a second figure, ``"trail"`` leaves echoes,
    #: ``"bleed"`` drips, ``"dissolve"`` takes the hero out of the room and
    #: ``"wall"`` stands in front of him. Two heroes can share one.
    look: str = ""
    #: Whether it is thrown at *somebody*. Six of the fifteen are not: the three
    #: that are set on the hero himself, the note he finds for his own sword, and
    #: the two that go through everything standing -- and a fight that made the
    #: player walk an arrow to a monster for one of those would be asking a
    #: question whose answer it was never going to read.
    needs_target: bool = True
    #: Whether it hits *everyone* standing. ``needs_target`` says whether the
    #: player has to walk an arrow to somebody; this says how many take it, and
    #: the arena draws its marker over all of them while one of these is chosen
    #: -- the cursor is a promise about who the attack is for.
    all_enemies: bool = False


#: The five, in the order a fight offers them: the small honest ones first, and
#: the void last because it is the end of the argument.
SPECIALS: tuple[Special, ...] = (
    Special(
        key=LEFT_HAND,
        cost=2,
        effect="a plain cut; poison 1 a turn for 8",
        look="slash",
        name="THE LEFT HAND",
        blurb="the dagger is the honest one: it cuts, and leaves something in",
        level=2,
    ),
    Special(
        key=ORB_OF_PTAMERA,
        cost=3,
        effect="a dark orb: nearly always a crit",
        look="orb",
        name="ORB OF PTAMERA",
        blurb="the black of it is thrown, and it goes for the throat",
        level=3,
    ),
    Special(
        key=FLEETING_SHADOW,
        cost=5,
        effect="out at once; nothing gets a swing",
        needs_target=False,
        look="fleet",
        name="FLEETING SHADOW",
        blurb="he was never in the room; the room was in him",
        level=4,
    ),
    Special(
        key=OPEN_VEIN,
        cost=4,
        effect="small cut, then 2 a turn for 3",
        look="bleed",
        name="THE OPEN VEIN",
        blurb="a cut that will not close, and keeps costing him",
        level=5,
    ),
    Special(
        key=DEVOURING_DARKNESS,
        cost=6,
        effect="a bite; half the damage comes back",
        look="drain",
        name="DEVOURING DARKNESS",
        blurb="it eats him, and he keeps what it ate",
        level=6,
    ),
    Special(
        key=BETWEEN_BLOWS,
        cost=6,
        effect="untouched this round, and it cuts",
        look="trail",
        name="BETWEEN BLOWS",
        blurb="he is not where they swing, and the cut comes from behind",
        level=7,
    ),
    Special(
        key=PAINT_THE_WALLS_RED,
        cost=8,
        effect="all of them: the deepest wound, five stacks",
        needs_target=False,
        look="shadow",
        name="PAINT THE WALLS RED",
        blurb="the room is the canvas, and the paint is theirs",
        level=8,
        all_enemies=True,
    ),
)

#: Yeti, "the unmoved": slow as a glacier and about as easy to move, and
#: everything that reaches him gets through the armour first. His kit is the
#: glacier and the wall -- a hammer that comes down, a cold that gets into the
#: legs, and the one thing he is famous for: standing there.
YETI_SPECIALS: tuple[Special, ...] = (
    Special(
        key=AVALANCHE,
        cost=4,
        effect="the blow lands 80% heavier",
        look="shatter",
        name="THE AVALANCHE",
        blurb="the hammer comes down with the mountain behind it",
        level=2,
    ),
    Special(
        key=SNOW_BLIND,
        cost=3,
        effect="a cut, and it loses its place",
        look="throw",
        name="THE SNOW BLIND",
        blurb="the mountain does not shout; it puts out the light",
        level=3,
    ),
    Special(
        key=RIME,
        cost=3,
        effect="small cut, slows them 4 turns",
        look="frost",
        name="THE RIME",
        blurb="a shallow cut, and the cold gets into the legs",
        level=4,
    ),
    Special(
        key=HOARFROST,
        cost=5,
        effect="the cold answers whoever hits you",
        needs_target=False,
        look="pulse",
        name="THE HOARFROST",
        blurb="he does not swing: whoever strikes him takes the cold home",
        level=5,
    ),
    Special(
        key=STILLNESS,
        cost=6,
        effect="half damage this round, +2 armour for the fight",
        needs_target=False,
        name="THE STILLNESS",
        blurb="he sets his feet, and the ice does not care what hits it",
        level=6,
        look="aura",
    ),
    Special(
        key=QUAKE,
        cost=10,
        effect="all of them at 70%, and shoved",
        needs_target=False,
        look="shatter",
        name="THE QUAKE",
        blurb="he puts the mountain into the floor, and the floor answers",
        level=7,
        all_enemies=True,
    ),
    Special(
        key=LONG_WINTER,
        cost=9,
        effect="all of them: a cut, and chilled",
        needs_target=False,
        look="frost",
        name="THE LONG WINTER",
        blurb="the cold comes in and stays; the legs are the first to go",
        level=8,
        all_enemies=True,
    ),
)

#: Walkyrion, whose sword gives off a note and whose note throws what it lands
#: on. His kit is the sound of the thing: a cut that is heard behind him, a ring
#: that throws what it lands on, and finally the bell itself.
WALKYRION_SPECIALS: tuple[Special, ...] = (
    Special(
        key=FIRST_NOTE,
        cost=3,
        effect="a cut, and a second at 60%",
        look="ring",
        name="THE FIRST NOTE",
        blurb="one cut, and the note of it carries to what is behind him",
        level=2,
    ),
    Special(
        key=OVERTURE,
        cost=4,
        effect="a note on all of them, at 60%",
        needs_target=False,
        look="wave",
        name="THE OVERTURE",
        blurb="the first bar is for everyone in the room",
        level=3,
        all_enemies=True,
    ),
    Special(
        key=BELLS_THROW,
        cost=5,
        effect="thrown to the back of the queue",
        look="throw",
        name="THE BELL'S THROW",
        blurb="the ring of it throws what it lands on to the back of the round",
        level=4,
    ),
    Special(
        key=TRUE_NOTE,
        cost=6,
        effect="+3 damage on every blow after",
        needs_target=False,
        name="THE TRUE NOTE",
        blurb="he finds the note the sword is for, and keeps it",
        level=5,
        look="aura",
    ),
    Special(
        key=ECHOING_CUT,
        cost=8,
        effect="full cut on one, half the rest",
        look="slash",
        name="THE ECHOING CUT",
        blurb="the cut lands once and is heard three times",
        level=6,
    ),
    Special(
        key=CHORD,
        cost=10,
        effect="a heavy blow, and thrown back",
        look="throw",
        name="THE RINGING CHORD",
        blurb="three notes at once, and the last of them is the floor",
        level=7,
    ),
    Special(
        key=SILENCE,
        cost=9,
        effect="all of them, and all thrown back",
        needs_target=False,
        look="wave",
        name="THE SILENCE AFTER",
        blurb="he stops playing, and the room has lost its place",
        level=8,
        all_enemies=True,
    ),
)

#: Whose kit is whose, by the hero's own key.
#: Inferno's eight, and they are one idea told eight ways: *the next one lands*.
#:
#: He has no kit in the sense the other three do -- there is nothing here that
#: avoids a blow, absorbs one, or changes the shape of a fight. What he has is
#: damage in escalating amounts, and the prices climb with it: the jab is the
#: cheapest thing anybody in this game can do, and the haymaker is the heaviest
#: single blow in it. Two of them cost him blood, which is his own currency,
#: because the answer to "he has 34 hit points" is not to give him more.
#:
#: The last one is a *place*: he builds a fire in the room out of himself and
#: everything in it burns, which is the one thing a fist cannot do.
INFERNO_SPECIALS: tuple[Special, ...] = (
    Special(
        key=JAB,
        cost=2,
        effect="a fast hand: light, and two more",
        look="pulse",
        name="THE JAB",
        blurb="he does not wind up; he just starts",
        level=2,
    ),
    Special(
        key=GUT_PUNCH,
        cost=3,
        effect="a body blow: heavy; it bleeds",
        look="bleed",
        name="GUT PUNCH",
        blurb="somewhere inside gives way, and keeps on giving",
        level=3,
    ),
    Special(
        key=EMBER_FIST,
        cost=4,
        effect="a burning hand: heavy, and fire",
        look="burn",
        name="EMBER FIST",
        blurb="the fist is not on fire; he is",
        level=4,
    ),
    Special(
        key=HEADBUTT,
        cost=5,
        effect="his hardest blow; it costs blood",
        look="shatter",
        name="THE HEADBUTT",
        blurb="he opens his own brow to put it in yours",
        level=5,
    ),
    Special(
        key=RED_MIST,
        cost=6,
        effect="hurt harder, swing harder",
        look="aura",
        name="RED MIST",
        blurb="the red comes down and he stops counting",
        level=6,
    ),
    Special(
        key=HAYMAKER,
        cost=6,
        effect="the heaviest single blow he has",
        look="shatter",
        name="THE HAYMAKER",
        blurb="the whole floor goes into it, and then so does the monster",
        level=7,
    ),
    Special(
        key=ROUNDHOUSE,
        cost=8,
        effect="one spin: everything takes it",
        needs_target=False,
        look="wave",
        name="THE ROUNDHOUSE",
        blurb="he turns once, and the room is in the way",
        level=8,
        all_enemies=True,
    ),
)


SPECIALS_BY_HERO: dict[str, tuple[Special, ...]] = {
    "noxx": SPECIALS,
    "yeti": YETI_SPECIALS,
    "walkyrion": WALKYRION_SPECIALS,
    "inferno": INFERNO_SPECIALS,
}

_ALL = (*SPECIALS, *YETI_SPECIALS, *WALKYRION_SPECIALS, *INFERNO_SPECIALS)
_BY_KEY = {special.key: special for special in _ALL}


def specials_for(hero_key: str) -> tuple[Special, ...]:
    """The hero's own five, or an empty kit for a hero nobody has written for.

    A hero with no kit is not a broken fight: the menu simply has nothing in it
    and the dark says so, which is the same courtesy a monster with no picture
    gets.
    """
    return SPECIALS_BY_HERO.get(hero_key, ())


def learned_at(special: Special, ultimate_level: int) -> int:
    """The level this trick arrives at, in a run where the dark answers at this one.

    Every trick is its own printed level, capped by the dark's gate -- the level
    the *ultimate* answers at, which ``--testrun`` moves down: a run the dark
    talks through has the whole kit early, and one it does not has the kit at the
    levels it was written for.

    One function for it, because two callers need the answer and they must not
    disagree: the menu asks *what is on it*, and a level-up asks *what was just
    learned*.
    """
    return min(special.level, ultimate_level)


def special_by_key(key: str) -> Special | None:
    """The special with this key, or ``None`` for a key nobody knows."""
    return _BY_KEY.get(key)
