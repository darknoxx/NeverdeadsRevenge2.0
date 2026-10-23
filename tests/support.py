"""A step, for a test that only needs a turn.

There is no "wait" verb any more: the world answers what the hero *does*, and a
key that only let the room move was a key nobody pressed. A test that wants one
turn to pass therefore takes one -- in the first direction there is room in, so
the shape of a particular floor never becomes part of what the test measures.
"""

from __future__ import annotations

from neverdeads_revenge.game.actions import Action, perform_action

__all__ = ["spend_a_turn", "STEPS"]

#: Tried in this order. A test should not care which one it got, only that the
#: turn was spent.
STEPS = (
    Action.MOVE_EAST,
    Action.MOVE_SOUTH,
    Action.MOVE_WEST,
    Action.MOVE_NORTH,
)


def spend_a_turn(state) -> None:
    """Take one real step. Raises if the hero is walled in on all four sides."""
    for action in STEPS:
        if perform_action(state, action).consumed_turn:
            return
    raise AssertionError("the hero had nowhere to step")
