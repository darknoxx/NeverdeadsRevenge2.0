"""What a chest takes from you.

A chest is a deal: something worth having, and something owed for it. This is the
owed half. The reward stays hidden until the lid is up -- that is what makes it
daring rather than arithmetic -- so the price has to be stated plainly, and
:attr:`Curse.price` is the sentence the player decides on.

A wide record rather than one class per curse. There are thirteen of these,
each uses one or two of the fields, and one table you can take in at a glance
beats thirteen small classes with one method each. The alternative would be a
hierarchy built to express a dozen different kinds of nothing.

Lives in ``game/`` because a curse changes how a run plays. The chest itself
carries only the curse's *key*, so ``world/`` never has to import this.
"""

from __future__ import annotations

from dataclasses import dataclass

from neverdeads_revenge.world.modifiers import Modifiers

__all__ = ["Curse", "CURSES", "TOUCH_CURSES", "curse_by_key"]


@dataclass(frozen=True, slots=True)
class Curse:
    """One thing a chest can take."""

    key: str
    name: str
    #: The price, in words, as the dialog puts it to the player.
    price: str
    #: Ongoing changes to the hero's stats.
    modifiers: Modifiers = Modifiers()
    #: Fraction of maximum health taken the moment the curse lands, for good.
    wither: float = 0.0
    #: What the wither above actually took, in points, filled in when it lands.
    #: The fraction is of the maximum *at that moment*, so recomputing it later
    #: would hand back a different number -- and a spring that gives back the
    #: wrong amount is a spring nobody trusts twice.
    wither_taken: int = 0
    #: Health lost per this many steps, or 0 for none.
    bleed_every: int = 0
    #: What the sight radius becomes, or ``None`` to leave it alone.
    sight: int | None = None
    #: Multiplier on what a draught restores.
    heal_scale: float = 1.0
    #: Health lost per kill. The price of killing things, which is the one thing
    #: the score now rewards -- so it is the one price that argues with it.
    kill_cost: int = 0
    #: Extra monsters on every floor. More bodies is a different kind of hard
    #: from bigger numbers: it costs turns, and turns are the score.
    extra_enemies: int = 0
    #: Multiplier on what a coin is worth. Below one is the ashen hand.
    coin_scale: float = 1.0
    #: Every this many turns, a step is not taken and the turn is spent anyway.
    #: Zero for none. A price paid in *time*, which is half the score -- and
    #: cadenced on turns rather than on steps because a stumble does not advance
    #: the step count, so a cadence taken from it would never move again.
    step_cost_every: int = 0
    #: How much wider the damage roll swings. Above one is the fever: not less
    #: damage, less *predictable* damage.
    damage_spread: float = 1.0
    #: How many of the monsters left alive follow the player down. Capped, and
    #: the price says so: "what you leave alive" uncapped is a swarm, and a
    #: swarm is not a price, it is the end of the run.
    follows: int = 0


#: Every curse a chest can hold.
#:
#: Prices are written to be read once, in a modal, by somebody who is about to
#: lose something. Short, concrete, no adjectives.
CURSES: dict[str, Curse] = {
    "wither": Curse(
        key="wither",
        name="WITHER",
        price="a quarter of your health, taken now and for good",
        wither=0.25,
    ),
    "bleed": Curse(
        key="bleed",
        name="BLEED",
        price="a drop of blood every tenth step",
        # Ten, not three. Three was a death sentence rather than a price: a
        # floor is sixty turns and half of them are steps, so the old cadence
        # cost thirteen health a floor and finished runs by itself. Ten still
        # costs a real thing -- four or five health a floor, every floor, with
        # no way to get it back but a draught -- and it leaves the player alive
        # to regret it.
        bleed_every=10,
    ),
    "frail": Curse(
        key="frail",
        name="FRAIL",
        price="two points of armour, gone",
        modifiers=Modifiers(armor=-2),
    ),
    "heavy": Curse(
        key="heavy",
        name="HEAVY",
        price="a quarter of your speed",
        modifiers=Modifiers(speed=-0.25),
    ),
    "dim": Curse(
        key="dim",
        name="DIM",
        price="your sight, cut to five paces",
        sight=5,
    ),
    "famine": Curse(
        key="famine",
        name="FAMINE",
        price="half of what every draught is worth",
        heal_scale=0.5,
    ),
    # -- the ones that argue with the other half of the score ----------------
    # The score is distance and speed, and it now pays for killing. These are
    # the prices that take it back: in blood, in turns, and in the coin that is
    # the other currency entirely.
    "tithe": Curse(
        key="tithe",
        name="TITHE",
        price="a drop of blood for every thing you kill",
        kill_cost=1,
    ),
    "company": Curse(
        key="company",
        name="COMPANY",
        price="two more shapes on every floor",
        extra_enemies=2,
    ),
    "hesitation": Curse(
        key="hesitation",
        name="HESITATION",
        price="every fifth turn, the step is not yours",
        step_cost_every=5,
    ),
    "ashen_hand": Curse(
        key="ashen_hand",
        name="ASHEN HAND",
        price="half of what every coin is worth",
        coin_scale=0.5,
    ),
    # -- the ones that change what the dungeon is ----------------------------
    "long_dark": Curse(
        key="long_dark",
        name="LONG DARK",
        price="your sight, cut to one pace",
        sight=1,
    ),
    "fever": Curse(
        key="fever",
        name="FEVER",
        price="your blows swing twice as wide",
        damage_spread=2.0,
    ),
    "crawl": Curse(
        key="crawl",
        name="CRAWL",
        price="three of what you leave alive follows you down",
        follows=3,
    ),
}


#: What a monster's touch can leave behind, by key.
#:
#: Deliberately not the whole table. WITHER takes a quarter of your health for
#: good, and a quarter of your health taken by a random blow in a corridor is
#: not a price, it is a mugging -- that one belongs on a chest, where the player
#: read it and said yes. These four are the ones that feel like something
#: reaching through you: the dark closing in, the guard going slack, the weight,
#: and the slow leak.
TOUCH_CURSES: tuple[str, ...] = ("dim", "frail", "heavy", "bleed")


def curse_by_key(key: str | None) -> Curse | None:
    """The curse with this key, or ``None``."""
    return CURSES.get(key) if key else None
