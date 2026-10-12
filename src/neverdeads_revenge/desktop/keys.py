"""What a key means in the dungeon.

The terminal build's table, kept as the same dictionary of human key names to
domain verbs, in its own module so the app and the game screen can both read it
without importing each other.
"""

from __future__ import annotations

from neverdeads_revenge.game.actions import Action

__all__ = ["KEY_BINDINGS"]

KEY_BINDINGS: dict[str, Action] = {
    "up": Action.MOVE_NORTH,
    "k": Action.MOVE_NORTH,
    "w": Action.MOVE_NORTH,
    "down": Action.MOVE_SOUTH,
    "j": Action.MOVE_SOUTH,
    "s": Action.MOVE_SOUTH,
    "left": Action.MOVE_WEST,
    "h": Action.MOVE_WEST,
    "a": Action.MOVE_WEST,
    "right": Action.MOVE_EAST,
    # ``l`` used to move east; it opens the legend now, and east is the arrow,
    # ``d`` and the numpad. The help screen says so.
    "d": Action.MOVE_EAST,
    "y": Action.MOVE_NW,
    "u": Action.MOVE_NE,
    "b": Action.MOVE_SW,
    "n": Action.MOVE_SE,
    "home": Action.MOVE_NW,
    "pageup": Action.MOVE_NE,
    "end": Action.MOVE_SW,
    "pagedown": Action.MOVE_SE,
    ".": Action.WAIT,
    "space": Action.WAIT,
    "i": Action.INVENTORY,
    "q": Action.QUAFF,
    "r": Action.REWIND,
    ">": Action.DESCEND,
    "f": Action.ULTIMATE,
    "enter": Action.INTERACT,
}
