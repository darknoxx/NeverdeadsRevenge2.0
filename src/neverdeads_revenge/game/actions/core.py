"""The vocabulary of a turn: actions, results, and the constants they use."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from neverdeads_revenge.core.direction import (
    Direction,
)
from ..state import GameState, RunState


EMBER_HEAL = 2

MIRROR_REFLECTION = 2

COUNTS_FAVOUR_EVERY = 13

SECOND_MOUTH_BASE = 3


class Action(Enum):
    """Everything the player can do."""

    MOVE_NORTH = "north"
    MOVE_SOUTH = "south"
    MOVE_EAST = "east"
    MOVE_WEST = "west"
    MOVE_NE = "ne"
    MOVE_NW = "nw"
    MOVE_SE = "se"
    MOVE_SW = "sw"
    #: Do whatever is under the player: take it, or take the stairs. This is the
    #: verb a key is bound to. The two specific actions below stay because they
    #: are meaningful on their own -- ``>`` is the classic "go down" and does not
    #: need to guess, and a test that wants to pick something up should not have
    #: to arrange a floor first.
    INTERACT = "interact"
    PICK_UP = "pickup"
    DESCEND = "descend"
    #: Open the chest underfoot. Never bound to a key: it only happens after the
    #: player has been shown the price and said yes, so the dialog is the only
    #: thing that issues it.
    OPEN_CHEST = "open_chest"
    #: Pay the price and leave the reward: a curse bought for a bigger score
    #: rather than for the thing behind the lid. Never bound to a key, like
    #: OPEN_CHEST, because it is a third answer to the same question.
    TAKE_FAME = "take_fame"
    #: Take back the last thing that happened. Only possible with THE BORROWED
    #: HOUR, and the only verb in the game that may be used after the run is
    #: over -- undoing a death is the whole of what it is for.
    REWIND = "rewind"
    #: Wash a curse off in the spring. Like OPEN_CHEST, never bound to a key:
    #: it only happens after the player has been shown the price and said yes.
    CLEANSE = "cleanse"
    QUAFF = "quaff"
    INVENTORY = "inventory"
    #: The hero's ultimate. Once a floor, from a level, and different for every
    #: hero: Noxx calls his friends, Yeti builds the Frozen Fortress,
    #: Walkyrion shatters the golden bell. Bound to `f`, because an ultimate is
    #: not a navigation verb and deserved a key of its own.
    ULTIMATE = "ultimate"

    @property
    def direction(self) -> Direction:
        """The movement direction, or ``NONE`` for non-movement actions."""
        return _ACTION_DIRECTIONS.get(self, Direction.NONE)


_ACTION_DIRECTIONS: dict[Action, Direction] = {
    Action.MOVE_NORTH: Direction.NORTH,
    Action.MOVE_SOUTH: Direction.SOUTH,
    Action.MOVE_EAST: Direction.EAST,
    Action.MOVE_WEST: Direction.WEST,
    Action.MOVE_NE: Direction.NORTH_EAST,
    Action.MOVE_NW: Direction.NORTH_WEST,
    Action.MOVE_SE: Direction.SOUTH_EAST,
    Action.MOVE_SW: Direction.SOUTH_WEST,
}


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Outcome of a player action."""

    consumed_turn: bool
    acted: bool
    died: bool = False
    escaped: bool = False
    #: Set when the player has to decide something before the action can happen.
    #:
    #: The domain never draws a dialog. It says one is needed, and the UI asks --
    #: which is what keeps the whole decision tree testable without a terminal.
    prompt: str | None = None
    #: Which dialog the prompt belongs to. The domain never draws one; it says
    #: one is needed and which question it is asking. Three kinds now -- a chest,
    #: a spring, somebody talking -- and a fourth would want an enum.
    prompt_kind: str = "chest"
    #: Set when the prompt is somebody talking, so the dialog can title itself.
    speaker: str = ""
    #: Set when the game *refused* something the player asked for -- a full pack,
    #: a bottle that is not there. The log says why in words; the front end says
    #: it in the one language an eye on the map does not read, and beeps.
    denied: bool = False


FIRST_BLOW = 7
COWARD_EDGE = 4
LEDGER_CAP = 5


KINDLY_PRICE = 8


COIN_SCALE = 0.5


LONG_REACH = 2

STEP_BEHIND_EVERY = 5

SLOW_KNITTING_EVERY = 20

HOLLOW_ROAD_COST = 2

MOMENTUM_MAX = 5

LAST_BREATH_EVASION = 2

HUNGRY_ROAD_DAMAGE = 5
HUNGRY_ROAD_TRAIL = 10

STACK_LIMIT = 3

NOTHING_WASTED_DAMAGE = 4

ENEMY_BITE = 0.75


MAX_ENEMY_ACTIONS_PER_PLAYER_TURN = 64


def second_mouth_cap(depth: int) -> int:
    """The most armour the second mouth will hold on ``depth``."""
    return SECOND_MOUTH_BASE + max(0, depth)


def _the(name: str) -> str:
    """``the`` before a name that needs one, and not before one that has it.

    Half the equipment is called "the something" -- every amulet is, and the
    strongest blades are -- and "You start with the the patient knife" is the
    sort of thing that makes a whole screen look unfinished.
    """
    return name if name.startswith("the ") else f"the {name}"


def _outcome(state: GameState, consumed_turn: bool, acted: bool) -> ActionResult:
    """Wrap a result, reading the ending off the state rather than assuming it.

    Worth the two lines: ``died=state.over`` was true after an escape too, and
    the game over screen would have announced a death to a player who had just
    won.
    """
    return ActionResult(
        consumed_turn=consumed_turn,
        acted=acted,
        died=state.run_state is RunState.DEAD,
        escaped=state.run_state is RunState.ESCAPED,
    )


