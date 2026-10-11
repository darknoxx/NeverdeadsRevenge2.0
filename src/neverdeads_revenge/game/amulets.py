"""What an amulet does.

An amulet is the third equipment slot and the only one that grants an *ability*
rather than a number. The numbers are
:class:`~neverdeads_revenge.world.modifiers.Modifiers` and they are already
handled everywhere a stat is read; these are rules, and a rule needs a place in
the code that asks about it.

So the table here is only the words -- the name a player reads, the sentence that
says what it does, and a tier for the drop tables. The rules themselves live
where the rule happens: a kill, a drink, a blow landed, a floor entered. That is
the same split the curses use: ``world/`` carries the key, ``game/`` knows what it
means, and neither layer has to know what an ember does in order to place one on a
floor.

Some of these are deliberately strange. A slot that only ever added two to a stat
would be a third number, and the game already has two of those.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Passive",
    "AMULETS",
    "FOUND_ON_THE_FLOOR",
    "FROM_THE_STRONG_TIER",
    "amulet_by_key",
    "blurb_for",
]


@dataclass(frozen=True, slots=True)
class Passive:
    """One amulet's ability, and how to talk about it."""

    key: str
    name: str
    #: What it does, in one line. Kept inside the shop's detail column, because
    #: an amulet is sold there like anything else and a line that wraps reads as
    #: a broken row.
    blurb: str
    #: 1 for the ones that turn up lying about, 2 for the strong tier that only
    #: comes out of a chest or the shop.
    tier: int = 1


AMULETS: dict[str, Passive] = {
    # -- found lying about ------------------------------------------------
    "ember": Passive(
        key="ember",
        name="the last ember",
        blurb="every kill puts two health back",
        tier=1,
    ),
    "coin_hand": Passive(
        key="coin_hand",
        name="the coin hand",
        blurb="every coin is worth a quarter more",
        tier=1,
    ),
    "marrow": Passive(
        key="marrow",
        name="the marrow",
        blurb="draughts heal half again as much",
        tier=1,
    ),
    "wayfarer": Passive(
        key="wayfarer",
        name="the wayfarer",
        blurb="you know the way out when you arrive",
        tier=1,
    ),
    # -- out of the strong tier -------------------------------------------
    "rune_heart": Passive(
        key="rune_heart",
        name="the rune heart",
        blurb="+1 max health for every floor down",
        tier=2,
    ),
    "mirror": Passive(
        key="mirror",
        name="the mirror",
        blurb="whatever strikes you takes two back",
        tier=2,
    ),
    "grave_ward": Passive(
        key="grave_ward",
        name="the grave ward",
        blurb="each floor's first blow is halved",
        tier=2,
    ),
    "deathwatch": Passive(
        key="deathwatch",
        name="the deathwatch",
        blurb="three armour under a third health",
        tier=2,
    ),
    "long_hunger": Passive(
        key="long_hunger",
        name="the deep hunger",
        blurb="kills feed REVENGE one more stack",
        tier=2,
    ),
    "patience": Passive(
        key="patience",
        name="the revenant's patience",
        blurb="you hit harder the longer you linger",
        tier=2,
    ),
    "second_mouth": Passive(
        key="second_mouth",
        name="the second mouth",
        blurb="overhealing a draught becomes armour",
        tier=2,
    ),
    "dead_weight": Passive(
        key="dead_weight",
        name="the dead weight",
        blurb="slower; your blows throw them back",
        tier=2,
    ),
    "patient_knife": Passive(
        key="patient_knife",
        name="the patient knife",
        blurb="your first blow on each thing crits",
        tier=2,
    ),
    "borrowed_face": Passive(
        key="borrowed_face",
        name="the borrowed face",
        blurb="the turn after a kill, nothing lands",
        tier=2,
    ),
}


#: Amulets that can be rolled onto a floor. The rest are chest-only, and the two
#: lists have to partition the table -- ``tests/test_shop.py`` checks that they do,
#: because an amulet in neither list is an amulet nobody can ever find.
FOUND_ON_THE_FLOOR: tuple[str, ...] = tuple(
    key for key, passive in AMULETS.items() if passive.tier == 1
)
FROM_THE_STRONG_TIER: tuple[str, ...] = tuple(
    key for key, passive in AMULETS.items() if passive.tier == 2
)


def amulet_by_key(key: str | None) -> Passive | None:
    """The passive with this key, or ``None``."""
    return AMULETS.get(key) if key else None


def blurb_for(amulet_key: str | None) -> str:
    """What the amulet does, or an empty string for something that is not one."""
    passive = amulet_by_key(amulet_key)
    return passive.blurb if passive else ""
