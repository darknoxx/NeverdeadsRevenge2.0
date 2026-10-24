"""One part of the turn: take."""

from __future__ import annotations

from ..state import GameState


from .core import (
    Action,
    ActionResult,
    _outcome,
)
from .movement import (
    _try_move,
)
from .pack import (
    _inventory,
    _pick_up,
    _quaff,
    _try_descend,
)
from .turn import (
    advance_world,
)
from .ultimates import (
    _take_fame,
    _ultimate,
)
from .world import (
    _cleanse,
    _interact,
    _open_chest,
    _rewind,
    _snapshot,
)


def perform_action(state: GameState, action: Action) -> ActionResult:
    """Apply a player action, then let the world answer.

    Returns whether the action consumed a turn, so the UI knows whether to run
    enemy turns.
    """
    # The borrowed hour is allowed while the run is over, and it is the only
    # thing that is. Everything else has stopped being possible, because there
    # is nobody left to do it.
    if state.over and action is not Action.REWIND:
        return _outcome(state, consumed_turn=False, acted=False)

    state.refresh_passives()
    # Everything struck from here on is this action's. Cleared here rather than
    # by the screen, so the flash cannot outlive the turn it belongs to.
    state.hits.clear()
    state.deaths.clear()

    if action is Action.REWIND:
        return _rewind(state)

    # The run as it is, taken before anything happens, so the hour has somewhere
    # to go back to. Only while one is in hand: a deep copy of a floor is not
    # free, and most runs never take one.
    if state.rewind_ready:
        state.snapshot = _snapshot(state)

    match action:
        case Action.INTERACT:
            return _interact(state)
        case Action.PICK_UP:
            return _pick_up(state)
        case Action.OPEN_CHEST:
            return _open_chest(state)
        case Action.TAKE_FAME:
            return _take_fame(state)
        case Action.CLEANSE:
            return _cleanse(state)
        case Action.ULTIMATE:
            return _ultimate(state)
        case Action.QUAFF:
            return _quaff(state)
        case Action.INVENTORY:
            return _inventory(state)
        case Action.DESCEND:
            return _try_descend(state)
        case _:
            pass

    # Everything left is a step. There is no longer a verb for standing still:
    # the world only answers something the hero *does*, and a turn that did
    # nothing but let the room move was a key nobody pressed.
    acted, spent = _try_move(state, action.direction)

    if state.over:
        return _outcome(state, consumed_turn=spent, acted=acted)

    # Only a real action advances the clock. Bumping a wall must not tick the
    # turn counter, or the displayed turn number drifts away from the world --
    # and a step taken for free must not either, which is why the two are not
    # the same flag.
    if spent:
        state.turn += 1
        state.total_turns += 1
        advance_world(state)
    state.refresh_vision()
    return _outcome(state, consumed_turn=spent, acted=acted)


