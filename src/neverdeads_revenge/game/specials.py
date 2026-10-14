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
    "BETWEEN_BLOWS",
    "LEFT_HAND",
    "OPEN_VEIN",
    "SPECIALS",
    "VOID",
    "ATRITAS",
    "Special",
    "special_by_key",
]

#: The keys, so a caller never has to spell one out.
LEFT_HAND = "left_hand"
ATRITAS = "atritas"
OPEN_VEIN = "open_vein"
BETWEEN_BLOWS = "between_blows"
VOID = "the_void"


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


#: The five, in the order a fight offers them: the small honest ones first, and
#: the void last because it is the end of the argument.
SPECIALS: tuple[Special, ...] = (
    Special(
        key=LEFT_HAND,
        name="THE LEFT HAND",
        blurb="the dagger is the honest one: it stabs where nobody is looking",
        level=2,
    ),
    Special(
        key=ATRITAS,
        name="ATRITAS",
        blurb="the shadow goes on its own, and strikes twice",
        level=4,
    ),
    Special(
        key=OPEN_VEIN,
        name="THE OPEN VEIN",
        blurb="a cut that will not close, and keeps costing him",
        level=5,
    ),
    Special(
        key=BETWEEN_BLOWS,
        name="BETWEEN BLOWS",
        blurb="he is not where they swing, and the cut comes from behind",
        level=6,
    ),
    Special(
        key=VOID,
        name="THE VOID",
        blurb="he gives in, and everything in front of him takes it",
        # The dungeon's own gate: the level the dark answers at, and the once-a-
        # floor price. `--testrun` opens it early, exactly as it does on the map.
        level=0,
        uses_floor=True,
    ),
)

_BY_KEY = {special.key: special for special in SPECIALS}


def special_by_key(key: str) -> Special | None:
    """The special with this key, or ``None`` for a key nobody knows."""
    return _BY_KEY.get(key)
