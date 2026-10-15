"""Noxx's own tricks: five ways to spend a turn that are his and no one else's.

Every hero's ask is one thing -- the dark answers -- and the shape it takes is
the hero. Noxx is a shadowy assassin whose petrol-coloured shadow has a life of
its own, whose right hand holds a rapier and whose left holds a green dagger, and
these are the five that follow from that: the honest little knife, the shadow
that goes on its own, a cut that will not close, a step so quick that nothing
finds him, and finally the void itself.

Nothing here resolves anything. Each entry names *what* a special is and what it
costs; `game/battle.py` runs them through the same blow every other attack in
this game goes through, which is what keeps a special from being a second game
hidden inside the first.

The gates are levels, spread across the first three floors: kills teach one level
each four of them, so the knife arrives on floor one, the shadow and the vein by
the middle of floor two, the step and the void by floor three.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ATRITAS",
    "AVALANCHE",
    "BELLS_THROW",
    "BETWEEN_BLOWS",
    "ECHOING_CUT",
    "FIRST_NOTE",
    "HOARFROST",
    "LEFT_HAND",
    "OPEN_VEIN",
    "RIME",
    "SHATTERED_BELL",
    "SPECIALS",
    "SPECIALS_BY_HERO",
    "STILLNESS",
    "TRUE_NOTE",
    "VOID",
    "Special",
    "special_by_key",
    "specials_for",
]

#: The keys, so a caller never has to spell one out.
LEFT_HAND = "left_hand"
ATRITAS = "atritas"
OPEN_VEIN = "open_vein"
BETWEEN_BLOWS = "between_blows"
VOID = "the_void"
AVALANCHE = "avalanche"
RIME = "rime"
HOARFROST = "hoarfrost"
STILLNESS = "stillness"
FORTRESS = "frozen_fortress"
FIRST_NOTE = "first_note"
BELLS_THROW = "bells_throw"
TRUE_NOTE = "true_note"
ECHOING_CUT = "echoing_cut"
SHATTERED_BELL = "shattered_bell"


@dataclass(frozen=True, slots=True)
class Special:
    """One of Noxx's tricks: what it is called, and what it asks for."""

    key: str
    name: str
    #: One line about it, in the fight's own voice, for the menu to show.
    blurb: str
    #: The level it arrives at. Zero means "the dark's own gate" -- see below.
    level: int
    #: Whether the cost is the *floor* rather than the fight. Only the void is
    #: that expensive, and it is the ask the dungeon already prices.
    uses_floor: bool = False
    #: How it should *look*, for whoever is doing the showing. A look and not a
    #: colour, because a colour is not enough to tell fifteen tricks apart:
    #: ``"slash"`` cuts, ``"shatter"`` showers shards, ``"frost"`` leaves crystals,
    #: ``"pulse"`` rings out from the hero, ``"aura"`` glows on him, ``"ring"``
    #: travels, ``"wave"`` goes through the room, ``"throw"`` sends what it hit
    #: back, ``"shadow"`` sends a second figure, ``"trail"`` leaves echoes,
    #: ``"bleed"`` drips, ``"dissolve"`` takes the hero out of the room and
    #: ``"wall"`` stands in front of him. Two heroes can share one.
    look: str = ""


#: The five, in the order a fight offers them: the small honest ones first, and
#: the void last because it is the end of the argument.
SPECIALS: tuple[Special, ...] = (
    Special(
        key=LEFT_HAND,
        look="slash",
        name="THE LEFT HAND",
        blurb="the dagger is the honest one: it stabs where nobody is looking",
        level=2,
    ),
    Special(
        key=ATRITAS,
        look="shadow",
        name="ATRITAS",
        blurb="the shadow goes on its own, and strikes twice",
        level=4,
    ),
    Special(
        key=OPEN_VEIN,
        look="bleed",
        name="THE OPEN VEIN",
        blurb="a cut that will not close, and keeps costing him",
        level=5,
    ),
    Special(
        key=BETWEEN_BLOWS,
        look="trail",
        name="BETWEEN BLOWS",
        blurb="he is not where they swing, and the cut comes from behind",
        level=6,
    ),
    Special(
        key=VOID,
        look="dissolve",
        name="THE VOID",
        blurb="he gives in, and everything in front of him takes it",
        # The dungeon's own gate: the level the dark answers at, and the once-a-
        # floor price. `--testrun` opens it early, exactly as it does on the map.
        level=0,
        uses_floor=True,
    ),
)

#: Yeti, "the unmoved": slow as a glacier and about as easy to move, and
#: everything that reaches him gets through the armour first. His kit is the
#: glacier and the wall -- a hammer that comes down, a cold that gets into the
#: legs, and the one thing he is famous for: standing there.
YETI_SPECIALS: tuple[Special, ...] = (
    Special(
        key=AVALANCHE,
        look="shatter",
        name="THE AVALANCHE",
        blurb="the hammer comes down with the mountain behind it",
        level=2,
    ),
    Special(
        key=RIME,
        look="frost",
        name="THE RIME",
        blurb="a shallow cut, and the cold gets into the legs",
        level=4,
    ),
    Special(
        key=HOARFROST,
        look="pulse",
        name="THE HOARFROST",
        blurb="he does not swing: whoever strikes him takes the cold home",
        level=5,
    ),
    Special(
        key=STILLNESS,
        name="THE STILLNESS",
        blurb="he sets his feet, and the ice does not care what hits it",
        level=6,
        look="aura",
    ),
    Special(
        key=FORTRESS,
        name="THE FROZEN FORTRESS",
        blurb="the wall with twice his blood in it, and the floor's whole teeth",
        level=0,
        uses_floor=True,
        look="wall",
    ),
)

#: Walkyrion, whose sword gives off a note and whose note throws what it lands
#: on. His kit is the sound of the thing: a cut that is heard behind him, a ring
#: that throws what it lands on, and finally the bell itself.
WALKYRION_SPECIALS: tuple[Special, ...] = (
    Special(
        key=FIRST_NOTE,
        look="ring",
        name="THE FIRST NOTE",
        blurb="one cut, and the note of it carries to what is behind him",
        level=2,
    ),
    Special(
        key=BELLS_THROW,
        look="throw",
        name="THE BELL'S THROW",
        blurb="the ring of it throws what it lands on to the back of the round",
        level=4,
    ),
    Special(
        key=TRUE_NOTE,
        name="THE TRUE NOTE",
        blurb="he finds the note the sword is for, and keeps it",
        level=5,
        look="aura",
    ),
    Special(
        key=ECHOING_CUT,
        look="slash",
        name="THE ECHOING CUT",
        blurb="the cut lands once and is heard three times",
        level=6,
    ),
    Special(
        key=SHATTERED_BELL,
        look="wave",
        name="THE SHATTERED BELL",
        blurb="he shatters the bell, and the note goes down through the floor",
        level=0,
        uses_floor=True,
    ),
)

#: Whose kit is whose, by the hero's own key.
SPECIALS_BY_HERO: dict[str, tuple[Special, ...]] = {
    "noxx": SPECIALS,
    "yeti": YETI_SPECIALS,
    "walkyrion": WALKYRION_SPECIALS,
}

_ALL = (*SPECIALS, *YETI_SPECIALS, *WALKYRION_SPECIALS)
_BY_KEY = {special.key: special for special in _ALL}


def specials_for(hero_key: str) -> tuple[Special, ...]:
    """The hero's own five, or an empty kit for a hero nobody has written for.

    A hero with no kit is not a broken fight: the menu simply has nothing in it
    and the dark says so, which is the same courtesy a monster with no picture
    gets.
    """
    return SPECIALS_BY_HERO.get(hero_key, ())


def special_by_key(key: str) -> Special | None:
    """The special with this key, or ``None`` for a key nobody knows."""
    return _BY_KEY.get(key)
