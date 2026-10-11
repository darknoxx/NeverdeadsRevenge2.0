"""What the dungeon gives back.

A curse is the price. This is the other half of the bargain, and it is *not* the
blade behind the lid -- it is a rule, and it lasts the rest of the run.

The difference matters. A better sword is a bigger number and the player already
has three slots of those. A gift changes what the player can *do*: strike from
two squares away, walk through the wall, take an action back. Which is the same
thing the amulets do, and for the same reason -- the decisions worth stopping
for are the ones that change the shape of a fight rather than its arithmetic.

A gift is meant to be about as good as the curse is bad. Not better: a chest that
is worth opening for free would make the price decoration. And not worse: nobody
would take the bargain twice. The pair is meant to be a *trade of shape*, and the
run afterwards is played differently rather than harder.

They are held in a set on the run, exactly like the wild offers, and the rules
live where they act -- ``game/actions.py`` for the two that change what a step
does, ``game/state.py`` for the one that changes a descent.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Gift", "GIFTS", "gift_by_key"]


@dataclass(frozen=True, slots=True)
class Gift:
    """One rule the dungeon hands over."""

    key: str
    name: str
    #: The sentence the character sheet shows. Written to be read once, next to
    #: a curse's price, by somebody working out what they traded.
    blurb: str


GIFTS: dict[str, Gift] = {
    "long_reach": Gift(
        key="long_reach",
        name="THE LONG REACH",
        blurb="your blow reaches two squares, and nothing solid in between",
    ),
    "step_behind": Gift(
        key="step_behind",
        name="THE STEP BEHIND",
        blurb="every fifth step costs you no time at all",
    ),
    "kind_dark": Gift(
        key="kind_dark",
        name="THE KIND DARK",
        blurb="every floor you descend lifts one curse",
    ),
    "hollow_road": Gift(
        key="hollow_road",
        name="THE HOLLOW ROAD",
        blurb="walk into stone, at two health a square",
    ),
    "borrowed_hour": Gift(
        key="borrowed_hour",
        name="THE BORROWED HOUR",
        blurb="once a floor, take back the last thing you did",
    ),
    "ash_mark": Gift(
        key="ash_mark",
        name="THE ASH MARK",
        blurb="every blow you land leaves it burning",
    ),
    "open_wound": Gift(
        key="open_wound",
        name="THE OPEN WOUND",
        blurb="your first blow on each thing leaves it bleeding",
    ),
    "slow_knitting": Gift(
        key="slow_knitting",
        name="THE SLOW KNITTING",
        blurb="every twentieth step puts one health back",
    ),
    "hungry_road": Gift(
        key="hungry_road",
        name="THE HUNGRY ROAD",
        blurb="every square you leave cuts whatever walks after you",
    ),
    "momentum": Gift(
        key="momentum",
        name="MOMENTUM",
        blurb="the longer you walk one way, the harder your next blow lands",
    ),
    "blood_debt": Gift(
        key="blood_debt",
        name="THE DEBT OF BLOOD",
        blurb="what you are made to bleed is owed back on your next blow",
    ),
    "last_breath": Gift(
        key="last_breath",
        name="THE LAST BREATH",
        blurb="three health or less: you hit twice as hard and are harder to hit",
    ),
    "dark_knows": Gift(
        key="dark_knows",
        name="THE DARK KNOWS",
        blurb="you see every monster on the floor, through the walls",
    ),
    "salt_circle": Gift(
        key="salt_circle",
        name="THE SALT CIRCLE",
        blurb="wait three turns in a row and nothing can reach you",
    ),
    "blood_price": Gift(
        key="blood_price",
        name="THE BLOOD PRICE",
        blurb="every blow you take scatters coin at your feet",
    ),
    "kindness": Gift(
        key="kindness",
        name="THE KINDNESS",
        blurb="whoever you meet hands you something to drink",
    ),
    "nothing_wasted": Gift(
        key="nothing_wasted",
        name="NOTHING WASTED",
        blurb="a draught you drink shatters into everything beside you",
    ),
}


def gift_by_key(key: str | None) -> Gift | None:
    """The gift with this key, or ``None``."""
    return GIFTS.get(key) if key else None
