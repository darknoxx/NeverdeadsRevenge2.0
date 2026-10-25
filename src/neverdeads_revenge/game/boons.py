"""The three gifts behind every Tenth Door.

A boon is a run-long rule the player chooses at the door. The offers are rolled
on their own dice, so the floor the player is about to walk into does not change
because the door had a different shelf.

The list is deliberately made of *verbs the run already understands*: health,
damage, speed, armour, sight, coin and the kill purse. A boon that needed a new
resource would need a new panel, and the door is already asking enough.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.rng import Rng

__all__ = ["Boon", "BOONS", "offers", "apply"]


@dataclass(frozen=True, slots=True)
class Boon:
    key: str
    name: str
    blurb: str


BOONS: dict[str, Boon] = {
    "iron_heart": Boon(
        "iron_heart",
        "IRON HEART",
        "+8 max health, and the health is there now.",
    ),
    "whetstone": Boon(
        "whetstone",
        "WHETSTONE",
        "+1 damage on every blow, low and high.",
    ),
    "quickstep": Boon(
        "quickstep",
        "QUICKSTEP",
        "+0.08 speed, before REVENGE.",
    ),
    "plated": Boon(
        "plated",
        "PLATED",
        "+1 armour against every hit.",
    ),
    "lantern": Boon(
        "lantern",
        "LANTERN",
        "+1 cell of sight, for the rest of the run.",
    ),
    "long_purse": Boon(
        "long_purse",
        "LONG PURSE",
        "+30 coin, carried through the door.",
    ),
    "blood_price": Boon(
        "blood_price",
        "BLOOD PRICE",
        "+5% critical chance, on every blow.",
    ),
    "deep_purse": Boon(
        "deep_purse",
        "DEEP PURSE",
        "+1 kill point in the purse's ceiling.",
    ),
    "second_wind": Boon(
        "second_wind",
        "SECOND WIND",
        "One more death is refused, once.",
    ),
    "iron_skin": Boon(
        "iron_skin",
        "IRON SKIN",
        "+2 armour against every hit.",
    ),
    "butcher": Boon(
        "butcher",
        "BUTCHER",
        "+2 damage on every blow, low and high.",
    ),
    "hawk": Boon(
        "hawk",
        "HAWK'S EYE",
        "+8% critical chance, on every blow.",
    ),
    "carrier": Boon(
        "carrier",
        "CARRIER",
        "+2 slots in the pack.",
    ),
    "night_eyes": Boon(
        "night_eyes",
        "NIGHT EYES",
        "+2 cells of sight, for the rest of the run.",
    ),
    "coin_hand": Boon(
        "coin_hand",
        "COIN HAND",
        "Every coin is worth a quarter more.",
    ),
}


def offers(seed: int, ring: int) -> tuple[str, ...]:
    """Three different boons for one door, on their own dice."""
    keys = list(BOONS)
    return tuple(Rng(seed * 1021 + ring * 103).shuffled(keys)[:3])


def apply(state, key: str) -> Boon | None:
    """Fold one boon into the run. Returns it, or ``None`` for a bad key."""
    boon = BOONS.get(key)
    if boon is None:
        return None
    player = state.player
    if key == "iron_heart":
        player.stats.max_hp += 8
        player.stats.hp += 8
    elif key == "whetstone":
        low, high = player.stats.damage
        player.stats.damage = (low + 1, high + 1)
    elif key == "quickstep":
        player.stats.speed += 0.08
    elif key == "plated":
        player.stats.armor += 1
    elif key == "lantern":
        state.sight_bonus += 1
    elif key == "long_purse":
        state.gold += 30
    elif key == "blood_price":
        player.stats.crit_chance += 0.05
    elif key == "deep_purse":
        state.kill_points_bonus += 1
    elif key == "second_wind":
        state.extra_lives += 1
    elif key == "iron_skin":
        player.stats.armor += 2
    elif key == "butcher":
        low, high = player.stats.damage
        player.stats.damage = (low + 2, high + 2)
    elif key == "hawk":
        player.stats.crit_chance += 0.08
    elif key == "carrier":
        state.pack_capacity += 2
    elif key == "night_eyes":
        state.sight_bonus += 2
    elif key == "coin_hand":
        state.coin_multiplier *= 1.25
    return boon
