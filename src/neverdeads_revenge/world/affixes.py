"""The aspects: what the dark does to a thing that has been down here too long.

An affix is one adjective, one rule, one colour. It is deliberately not a new
monster and not a new weapon: the ghoul is the same ghoul, and the blade is the
same blade -- the dark has been at it. That is why the vocabulary is shared: a
`fire-kissed` ghoul burns what it touches, and a `fire-kissed` depthless leaves
the same fire in a wound.

The registry is data. The rules live with the systems that already own them
(the fight's statuses, the weapon's inflicts), so an aspect cannot invent a
second opinion about what burning is.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Affix",
    "AFFIXES",
    "AFFIX_FROM_DEPTH",
    "enemy_affixes",
    "name_with",
]


@dataclass(frozen=True, slots=True)
class Affix:
    """One aspect, as data: the word, the colour, and what it costs."""

    key: str
    #: What is written in front of the name: "fire-kissed ghoul".
    adjective: str
    #: The name's ink and the aura's light.
    colour: str
    #: Which particle the painter should keep around it.
    particle: str
    #: What it is made of. Opposing tags are never rolled onto one thing.
    tags: frozenset[str]
    #: What it adds to a monster's threat, in the generator's own budget.
    threat: float
    #: One line for the book, when the player first meets it.
    blurb: str


AFFIXES: dict[str, Affix] = {
    "fire_kissed": Affix(
        key="fire_kissed",
        adjective="fire-kissed",
        colour="#ff7a2a",
        particle="ember",
        tags=frozenset({"fire"}),
        threat=1.0,
        blurb="It burns what it touches.",
    ),
    "darkness_touched": Affix(
        key="darkness_touched",
        adjective="darkness-touched",
        colour="#8b5cf6",
        particle="smoke",
        tags=frozenset({"dark"}),
        threat=1.2,
        blurb="The dark it carries does not leave when it does.",
    ),
    "frostbound": Affix(
        key="frostbound",
        adjective="frostbound",
        colour="#8fd8ff",
        particle="snow",
        tags=frozenset({"frost"}),
        threat=1.0,
        blurb="It freezes the hand that reaches for it.",
    ),
}

#: The first floor an aspect can be met on. The early floors stay clean: an
#: aspect is a *second* rule to read, and a player who is still learning what a
#: ghoul does should not also be learning what the dark did to it.
AFFIX_FROM_DEPTH = 6


def name_with(name: str, affixes: tuple[str, ...]) -> str:
    """The name a player reads: the aspects, then the thing they are on.

    A weapon's name already starts with "the", and the aspect goes *after* it:
    "the darkness-touched depthless", never "darkness-touched the depthless".
    """
    words = [AFFIXES[key].adjective for key in affixes if key in AFFIXES]
    if not words:
        return name
    # A template may already spell the whole name (a named deep find); the rule
    # must not put the adjective on it twice.
    if name.startswith(f"the {words[0]} ") or name.startswith(f"{words[0]} "):
        return name
    if name.startswith("the "):
        return "the " + " ".join([*words, name[4:]])
    return " ".join([*words, name])


def enemy_affixes(rng, depth: int) -> tuple[str, ...]:
    """Which aspects this floor's monsters are wearing, if any.

    One roll per monster, on a *separate* generator: the floor's own dice must
    not move because a monster got a name, or every seeded floor below the old
    one would come out different.
    """
    if depth < AFFIX_FROM_DEPTH:
        return ()
    # Ten per cent at the first deep floor, and a little more as the house takes
    # an interest. Capped so a floor is still a floor and not an exhibition.
    chance = min(0.28, 0.10 + 0.02 * (depth - AFFIX_FROM_DEPTH))
    if not rng.chance(chance):
        return ()
    keys = tuple(AFFIXES)
    return (rng.pick(keys),)
