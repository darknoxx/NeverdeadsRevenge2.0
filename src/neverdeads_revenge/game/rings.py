"""The Tenth Door's rings: one rule each, chosen before the descent.

A ring is ten floors, and the rule is the *weather* of those ten -- not a curse
on the hero and not a reward, a fact about the room. It is read on the door
before the player commits, because a rule discovered halfway down is a rule that
took a run rather than costing one.

The rules are deliberately small and legible. They touch numbers the side panel
already shows (armour, speed, health, sight, coin), so a player can look at a
monster and see what the ring did to it.
"""

from __future__ import annotations

from dataclasses import dataclass


__all__ = ["RingRule", "RING_RULES", "RING_BY_KEY", "rule_for", "enter_ring",
           "apply_to_floor"]


@dataclass(frozen=True, slots=True)
class RingRule:
    """One ring's weather, in words and in a key the game can apply."""

    key: str
    name: str
    blurb: str


RING_RULES: tuple[RingRule, ...] = (
    RingRule(
        "iron",
        "THE IRON RING",
        "Every monster wears one more plate of armour.",
    ),
    RingRule(
        "fever",
        "THE FEVER RING",
        "Every monster moves a little faster through the dark.",
    ),
    RingRule(
        "gloom",
        "THE GLOOM RING",
        "The dark comes closer: two cells of sight are gone.",
    ),
    RingRule(
        "greed",
        "THE GREED RING",
        "Coin is worth a third more, and so is every monster's health.",
    ),
)

RING_BY_KEY: dict[str, RingRule] = {rule.key: rule for rule in RING_RULES}


def rule_for(seed: int, ring: int) -> RingRule | None:
    """The rule of ``ring``. Ring one is the room before the first door.

    Consecutive rings step through the table rather than rolling independently,
    so a run cannot meet the same weather twice in a row and the four rings read
    as a rotation rather than four unrelated dice.
    """
    if ring <= 1:
        return None
    index = (seed // 101 + ring) % len(RING_RULES)
    return RING_RULES[index]


def enter_ring(state, rule: RingRule | None) -> None:
    """Set the ring and apply the parts that happen once, not per floor."""
    if rule is None:
        state.ring_rule = ""
        return
    state.ring_rule = rule.key
    if rule.key == "greed":
        # Once per ring. Applying it on every floor would turn a third into a
        # runaway before the door at the end of the ring.
        state.coin_multiplier *= 1.3
    state.say(f"The ring's rule: {rule.name}. {rule.blurb}")


def apply_to_floor(state) -> None:
    """Put this ring's rule on the monsters and the room of a new floor.

    Called after the floor's monsters exist, and before the warden is chosen, so
    a warden is a warden *of this ring* rather than of the previous one.
    """
    rule = RING_BY_KEY.get(state.ring_rule)
    if rule is None:
        return
    for enemy in state.enemies:
        if rule.key == "iron":
            enemy.stats.armor += 1
        elif rule.key == "fever":
            enemy.stats.speed += 0.10
        elif rule.key == "greed":
            enemy.stats.max_hp = max(1, round(enemy.stats.max_hp * 1.10))
            enemy.stats.hp = enemy.stats.max_hp
    if rule.key == "gloom":
        state.sight_penalty += 2
