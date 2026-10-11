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


STATUSES: dict[str, Status] = {
    "bleed": Status(key="bleed", name="bleeding", damage=2, turns=3),
    "poison": Status(key="poison", name="poisoned", damage=1, turns=8),
    "burn": Status(key="burn", name="burning", damage=3, turns=2),
    "chill": Status(key="chill", name="chilled", speed_factor=0.6, turns=4),
}


def status_by_key(key: str | None) -> Status | None:
    """The status with this key, or ``None``."""
    return STATUSES.get(key) if key else None
