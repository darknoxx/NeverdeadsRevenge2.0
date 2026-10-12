"""Saving a run in progress.

One slot, overwritten, and consumed the moment it is read.

"Save and quit" rather than "save and reload", and the difference is the whole
design. The file is deleted when the run is picked up again, so quitting in front
of a monster you do not like the look of and coming back to a fresh roll of the
dice is not a thing you can do twice. What it is for is the terminal being closed
and the laptop running out of battery, and the twenty minutes already spent.

The codec is generic: it walks dataclasses by reflection rather than listing
fields, because a list of fields is a list somebody has to remember to add to.
What makes that safe is the round-trip test -- it builds a run with every field
populated and asserts the reloaded one matches field by field, so a field added
and not handled fails there instead of in somebody's saved game.

Two things are *not* generic, and both for the same reason. The hero is stored by
key rather than by value, because heroes are shared frozen templates and a copy
of one would stop being the hero the roster knows. And the turn queue stores
which actor it means rather than a second copy, because a queue full of copies
would fight with the copies in ``enemies`` and neither would be the real one.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from ..core.direction import Direction
from ..core.rng import Rng
from ..core.turn_queue import TurnQueue
from ..world.map import DungeonMap, GroundItem
from ..world.modifiers import Modifiers
from .lore import PAGE_COUNT
from .actors import Actor, ActorKind, HEROES, Stats, Trait
from .curses import Curse
from .difficulty import BASE_PACK_SLOTS
from .npcs import NPCS
from .state import GameState, LogEntry, LogKind, RunState

__all__ = ["dump", "load", "SaveError", "SCHEMA_VERSION"]

#: Bumped when the shape of a saved run changes in a way the codec cannot read
#: past. A run saved by a different version is thrown away rather than guessed
#: at: a run is twenty minutes, and a half-rebuilt one is worse than none.
SCHEMA_VERSION = 1


class SaveError(Exception):
    """The saved run could not be read. The caller offers a new run instead."""


#: Everything the codec can rebuild, by the name it writes into the file.
_DATACLASSES: dict[str, type] = {
    cls.__name__: cls
    for cls in (
        Stats,
        Modifiers,
        Actor,
        GroundItem,
        DungeonMap,
        LogEntry,
        Curse,
        GameState,
    )
}

#: Every enum it can rebuild, by name. Tiles are absent on purpose: the map keeps
#: them as plain ints, which is what makes a floor cheap to store.
_ENUMS: dict[str, type] = {
    cls.__name__: cls for cls in (ActorKind, Trait, LogKind, RunState, Direction)
}


# -- the codec ---------------------------------------------------------------
def _encode(value: Any) -> Any:
    """Turn a value into JSON-shaped data, tagged with what it was.

    Tagged rather than guessed: ``[1, 2]`` could be a tuple or a list, and a
    position that comes back as a list is a position that compares unequal to
    every other position in the game -- which is the sort of bug that shows up
    as monsters that cannot be found on the map they are standing on.
    """
    if isinstance(value, Enum):
        return {"!enum": type(value).__name__, "value": value.value}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "!type": type(value).__name__,
            "fields": {
                field.name: _encode(getattr(value, field.name))
                for field in fields(value)
            },
        }
    if isinstance(value, tuple):
        return {"!tuple": [_encode(item) for item in value]}
    if isinstance(value, set):
        return {"!set": [_encode(item) for item in sorted(value)]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        # Pairs rather than an object, because the keys are not all strings: the
        # map's items are keyed by position.
        return {"!dict": [[_encode(k), _encode(v)] for k, v in value.items()]}
    return value


def _decode(data: Any) -> Any:
    """Rebuild whatever :func:`_encode` wrote."""
    if isinstance(data, list):
        return [_decode(item) for item in data]
    if not isinstance(data, dict):
        return data

    if "!enum" in data:
        kind = _ENUMS.get(data["!enum"])
        if kind is None:
            raise SaveError(f"unknown enum {data['!enum']!r}")
        return kind(data["value"])
    if "!type" in data:
        kind = _DATACLASSES.get(data["!type"])
        if kind is None:
            raise SaveError(f"unknown type {data['!type']!r}")
        return kind(**{name: _decode(value) for name, value in data["fields"].items()})
    if "!tuple" in data:
        return tuple(_decode(item) for item in data["!tuple"])
    if "!set" in data:
        return {_decode(item) for item in data["!set"]}
    if "!dict" in data:
        return {_decode(k): _decode(v) for k, v in data["!dict"]}
    return data


# -- the queue's references --------------------------------------------------
def _ref(state: GameState, actor: Actor) -> str:
    """Which actor this is, by where it lives in the state.

    By identity, not by value: two ghouls on one floor are equal field for field,
    and ``list.index`` would answer with the first of them.
    """
    if actor is state.player:
        return "player"
    for index, enemy in enumerate(state.enemies):
        if enemy is actor:
            return f"enemy:{index}"
    for index, npc in enumerate(state.npcs):
        if npc is actor:
            return f"npc:{index}"
    return ""


def _by_ref(state: GameState, ref: str) -> Actor | None:
    if ref == "player":
        return state.player
    if ref.startswith("enemy:"):
        index = int(ref.split(":", 1)[1])
        return state.enemies[index] if index < len(state.enemies) else None
    if ref.startswith("npc:"):
        index = int(ref.split(":", 1)[1])
        return state.npcs[index] if index < len(state.npcs) else None
    return None


# -- the run -----------------------------------------------------------------
def dump(state: GameState) -> dict:
    """The whole run, as JSON-shaped data."""
    entries, counter, clock = state.turn_queue.snapshot()
    return {
        "version": SCHEMA_VERSION,
        "hero": state.hero.key,
        "seed": state.seed,
        "rng": _encode(state.rng.state()),
        "depth": state.depth,
        "map": _encode(state.dungeon_map),
        "player": _encode(state.player),
        "enemies": [_encode(enemy) for enemy in state.enemies],
        "npcs": [_encode(npc) for npc in state.npcs],
        "queue": {
            "clock": clock,
            "counter": counter,
            "entries": [[due, order, _ref(state, actor)] for due, order, actor in entries],
        },
        "log": [_encode(entry) for entry in state.log],
        "turn": state.turn,
        "total_turns": state.total_turns,
        "run_state": _encode(state.run_state),
        "kills": state.kills,
        "level": state.level,
        "revenge_stacks": state.revenge_stacks,
        "floors_cleared": state.floors_cleared,
        "inventory": [_encode(item) for item in state.inventory],
        "curses": [_encode(curse) for curse in state.curses],
        "gold": state.gold,
        "fame": state.fame,
        "sight_bonus": state.sight_bonus,
        "coin_multiplier": state.coin_multiplier,
        "enemy_hp_multiplier": state.enemy_hp_multiplier,
        "extra_lives": state.extra_lives,
        "shrouded": state.shrouded,
        "ward_ready": state.ward_ready,
        "momentum": state.momentum,
        "momentum_direction": _encode(state.momentum_direction),
        "blood_debt": state.blood_debt,
        "waits_in_a_row": state.waits_in_a_row,
        "salt_ward": state.salt_ward,
        "void_available": state.ultimate_available,
        "pack_capacity": state.pack_capacity,
        "trail": _encode(state.trail),
        "helped": _encode(state.helped),
        "wilds": _encode(state.wilds),
        "gifts": _encode(state.gifts),
        # Sorted lists rather than sets: the save is JSON. ``missing_pages`` is
        # the one the *generator* reads, so it has to come back exactly as it
        # went in or a run would scatter pages it had already found.
        "found_pages": list(state.found_pages),
        "missing_pages": sorted(state.missing_pages),
    }


def load(payload: dict) -> GameState:
    """Rebuild a run from what :func:`dump` wrote.

    Raises :class:`SaveError` for anything it cannot read. A run is twenty
    minutes and a half-rebuilt one is worse than none, so every failure here is
    a refusal rather than a best effort.
    """
    if not isinstance(payload, dict) or payload.get("version") != SCHEMA_VERSION:
        raise SaveError("this run was saved by a different version")

    try:
        hero = HEROES[payload["hero"]]
        state = GameState(hero=hero, rng=Rng(payload["seed"]), seed=payload["seed"])
        state.rng.restore(_decode(payload["rng"]))
        state.depth = payload["depth"]
        state.dungeon_map = _decode(payload["map"])
        state.player = _decode(payload["player"])
        state.enemies = [_decode(enemy) for enemy in payload["enemies"]]
        state.npcs = [_decode(npc) for npc in payload["npcs"]]

        # The queue last, because it is the only thing that has to look the other
        # actors up again.
        state.turn_queue = TurnQueue()
        state.turn_queue.restore(
            (
                [
                    (due, order, _by_ref(state, ref))
                    for due, order, ref in payload["queue"]["entries"]
                    if _by_ref(state, ref) is not None
                ],
                payload["queue"]["counter"],
                payload["queue"]["clock"],
            )
        )

        state.log = [_decode(entry) for entry in payload["log"]]
        state.turn = payload["turn"]
        state.total_turns = payload["total_turns"]
        state.run_state = _decode(payload["run_state"])
        state.kills = payload["kills"]
        state.level = payload["level"]
        state.revenge_stacks = payload["revenge_stacks"]
        state.floors_cleared = payload["floors_cleared"]
        state.inventory = [_decode(item) for item in payload["inventory"]]
        state.curses = [_decode(curse) for curse in payload["curses"]]
        state.gold = payload["gold"]
        # ``get`` rather than ``[]``, and the version is not bumped for it: a
        # promise of fame is a count that starts at nothing, so a run saved
        # before there was such a thing still resumes -- it simply has none.
        state.fame = payload.get("fame", 0)
        state.sight_bonus = payload["sight_bonus"]
        state.coin_multiplier = payload["coin_multiplier"]
        state.enemy_hp_multiplier = payload["enemy_hp_multiplier"]
        state.extra_lives = payload["extra_lives"]
        state.shrouded = payload["shrouded"]
        state.ward_ready = payload["ward_ready"]
        # ``get`` for all of these, and the version is not bumped: each is a
        # counter or a rule that starts empty, so a run saved before the gift
        # that uses it still resumes -- it simply has none of whatever it was.
        state.momentum = payload.get("momentum", 0)
        state.momentum_direction = _decode(payload.get("momentum_direction"))
        state.blood_debt = payload.get("blood_debt", 0)
        state.waits_in_a_row = payload.get("waits_in_a_row", 0)
        state.salt_ward = payload.get("salt_ward", 0)
        # The floor's one ask. The summoned things themselves are not carried:
        # they belong to the floor they were asked for, and save-and-quit
        # mid-stay lets them fade without ceremony -- only the *spent* flag
        # matters, because that is the part a reload could otherwise have back
        # for nothing. The key is still ``void_available`` so saves written
        # before the other heroes had ultimates still load.
        state.ultimate_available = payload.get(
            "void_available", payload.get("ultimate_available", True)
        )
        # ``get`` like the rest: a run saved before the pack had a size simply
        # gets the base allowance, which is what it was playing with anyway.
        state.pack_capacity = payload.get("pack_capacity", BASE_PACK_SLOTS)
        state.trail = _decode(payload.get("trail", {}))
        state.helped = set(_decode(payload.get("helped", [])))
        # ``set`` around both, because ``_decode`` hands back a list and these
        # are declared as sets -- and ``gifts`` is *added to* when a chest is
        # opened, so a run loaded from disk would have crashed on the first lid
        # that held a rule. ``wilds`` only ever gets read, which is why the same
        # mistake had been sitting there quietly.
        state.wilds = set(_decode(payload["wilds"]))
        # Same reasoning as ``fame``: a set that starts empty, so a run saved
        # before there were gifts still resumes. The borrowed hour is *not*
        # saved -- a run put down and picked up again has lost it, and that is
        # the price of putting it down.
        state.gifts = set(_decode(payload.get("gifts", [])))
        state.found_pages = [int(n) for n in payload.get("found_pages", [])]
        # Every page still out there, for a run saved before there was a
        # chronicle: it had found none, so all of them are missing.
        state.missing_pages = set(
            payload.get("missing_pages", range(1, PAGE_COUNT + 1))
        )
    except SaveError:
        raise
    except Exception as exc:  # a corrupt file is a refusal, not a crash
        raise SaveError(f"this run could not be read: {exc}") from exc

    return state
