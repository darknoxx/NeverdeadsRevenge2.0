"""How fast a held direction acts.

Not a game rule. The turn queue decides who acts how often, and a *tap* is never
throttled -- so this changes nothing about the balance. It is how a hero's speed
is felt under the finger rather than read off a number, which is worth having and
worth showing, so it lives where the game and the screen can both read it.

A terminal repeats a held key about thirty-three times a second, which is a rate
nobody chose: it made a fight an unreadable blur and it dropped two sounds in
three. This is the rate somebody chose.
"""

from __future__ import annotations

__all__ = [
    "ACTIONS_PER_SECOND",
    "MAX_ACTIONS_PER_SECOND",
    "MIN_ACTIONS_PER_SECOND",
    "actions_per_second",
    "action_gap",
]

#: Actions a second for a hero of speed 1.0.
ACTIONS_PER_SECOND = 6.0

#: The fastest a held key may ever act, however fast the hero is.
#:
#: A ceiling rather than a target: it exists so that speed bought with equipment
#: and upgrades has somewhere to go, and it is high enough that no hero reaches
#: it by accident. Noxx starts at nine.
#:
#: The *sound* has its own budget, in ``ui.audio``, because a device that can play
#: twenty notes a second does not exist and pretending otherwise is how a backlog
#: grows.
MAX_ACTIONS_PER_SECOND = 20.0

#: The slowest, so a hero carrying grave iron is heavy and not unusable.
MIN_ACTIONS_PER_SECOND = 3.0


def actions_per_second(speed: float) -> float:
    """How often a held direction acts for a hero of this speed."""
    rate = ACTIONS_PER_SECOND * max(0.0, speed)
    return max(MIN_ACTIONS_PER_SECOND, min(MAX_ACTIONS_PER_SECOND, rate))


def action_gap(speed: float) -> float:
    """The shortest gap between two actions from a held key, in seconds."""
    return 1.0 / actions_per_second(speed)
