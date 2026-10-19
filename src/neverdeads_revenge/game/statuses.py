"""What a blow leaves behind.

A status is a rule that runs on the *victim's* own turn rather than on the
attacker's: a wound that keeps bleeding, a poison that keeps working, a chill
that keeps the legs slow. It is the one kind of damage that does not need a
second swing, which is what makes a cheap fast weapon interesting -- and what
makes a monster that inflicts one a different problem from a monster that simply
hits hard.

Bleed and poison are the same shape and deliberately different sizes. A wound is
fast and shallow -- three turns, two a turn -- and a poison is slow and long --
eight turns, one a turn. The first is for a fight you are standing in; the second
is for a fight you are leaving. A weapon that does one is not a weapon that does
the other, and a player who has both has a reason to think about which to swing.

Counted in the victim's turns, not the attacker's. A ghoul that acts every other
turn must not bleed at the player's rate, and this is the same rule the borrowed
face already uses for the turn after a kill.

The table lives in ``game/`` and knows nothing about the world: it says what a
status *is*, and ``actions.py`` says when it runs.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Status", "STATUSES", "status_by_key"]


@dataclass(frozen=True, slots=True)
class Status:
    """One thing a blow can leave running."""

    key: str
    #: How it is said of somebody: "the ghoul is bleeding".
    name: str
    #: Damage at the start of each of the victim's turns.
    damage: int = 0
    #: Multiplies the victim's speed while it lasts. ``1.0`` for the ones that
    #: only hurt -- a slow is a different weapon for a different fight.
    speed_factor: float = 1.0
    #: How many of the victim's turns it lasts.
    turns: int = 3
    #: Whether a second one *deepens* it rather than only refreshing it. Only
    #: the two wounds do: a fast cheap blade is meant to build a cut, and a
    #: poison that stacked would make the viper -- already the monster that
    #: punishes a slow kill -- a damage multiplier instead. A slow stacks
    #: nothing at all; it is a different weapon for a different fight.
    stackable: bool = False


STATUSES: dict[str, Status] = {
    "bleed": Status(
        key="bleed", name="bleeding", damage=2, turns=3, stackable=True
    ),
    #: And the deep one: what Atritas leaves when he brings company. Four a turn
    #: and not two, so "heavy" is heavier and not only longer -- a wound that
    #: costs the same per turn and simply lasts would not be worth a turn of its
    #: own, and the trick is meant to be.
    "maul": Status(
        key="maul", name="bleeding badly", damage=4, turns=4, stackable=True
    ),
    "poison": Status(key="poison", name="poisoned", damage=1, turns=8),
    "burn": Status(key="burn", name="burning", damage=3, turns=2),
    "chill": Status(key="chill", name="chilled", speed_factor=0.6, turns=4),
    #: The deep cold: two fifths of a turn taken away, and only two turns long.
    #: The same trade as chill, told sharper -- which is what THE NUMB is.
    "numb": Status(key="numb", name="numb", speed_factor=0.4, turns=2),
    #: And the longest rot in the game: one a turn for twelve. It is the patient
    #: blade's whole plan; against a crowd it is nothing at all.
    "taint": Status(key="taint", name="tainted", damage=1, turns=12),
}


def status_by_key(key: str | None) -> Status | None:
    """The status with this key, or ``None``."""
    return STATUSES.get(key) if key else None
