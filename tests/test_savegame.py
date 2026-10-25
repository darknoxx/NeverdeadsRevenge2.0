"""Tests for saving a run in progress.

The round trip is the test that matters, and it is written to be *exhaustive*
rather than illustrative: it builds a run with every field the game can put in
one -- equipment, curses, wilds, people, a levelled hero, a half-explored map --
saves it, reads it back and compares the two field by field, recursively.

That is what makes the generic codec safe. It walks dataclasses by reflection
rather than listing fields, so a field added to the game and forgotten by the
codec fails *here* rather than in somebody's saved run twenty minutes in.
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass

import pytest

from neverdeads_revenge.core.direction import Direction
from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.core.turn_queue import TurnQueue
from neverdeads_revenge.game.actors import NOXX, make_npc
from neverdeads_revenge.game.curses import CURSES
from neverdeads_revenge.game.npcs import NPCS
from neverdeads_revenge.game.savegame import SCHEMA_VERSION, SaveError, dump, load
from neverdeads_revenge.game.shop import Loadout
from neverdeads_revenge.game.state import GameState, start_run

from .support import spend_a_turn


def a_busy_run() -> GameState:
    """A run with as much in it as a run can hold."""
    state = start_run(
        NOXX,
        seed=7,
        loadout=Loadout(
            upgrades={
                "vigour": 2,
                "haste": 1,
                "lantern": 1,
                # The two permanent purchases that are numbers rather than
                # items: without them the round-trip never sees the fields.
                "cellar": 1,
                "bleeding_edge": 1,
            },
            pending=("bite", "hide", "patient_knife", "potion", "elixir"),
            wilds=("greed", "second_wind", "borrowed_face"),
        ),
    )
    state.build_floor(4)
    state.add_curse(CURSES["wither"])
    state.add_curse(CURSES["bleed"])
    state.gold = 137
    state.kills = 9
    state.defeated = ["ghoul", "hush"]
    state.found_weapons = ["tooth", "grave"]
    state.level = 3
    state.turn = 12
    state.total_turns = 88
    state.floors_cleared = 3
    state.shrouded = 1
    state.ward_ready = True
    state.revenge_stacks = 2
    state.momentum = 3
    state.momentum_direction = Direction.EAST
    state.blood_debt = 5
    state.salt_ward = 1
    # The floor's own bookkeeping: the ledger blade counts kills here, the rules
    # the strange bottles laid, the squares where things died, the window a
    # fortress took out of the hero's sight -- and the flag that says the hero is
    # in the last breath. None of them used to survive a save.
    state.floor_kills = 4
    state.ravaging = True
    state.sight_penalty = 2
    state.floor_draughts = {"thin_veil", "short_crown"}
    state.death_squares = {
        (state.player.position[0] + 2, state.player.position[1]),
        (state.player.position[0], state.player.position[1] + 2),
    }
    state.trail = {(state.player.position[0] - 1, state.player.position[1]): 5}
    state.helped = {(state.player.position[0] + 1, state.player.position[1])}
    state.npcs = [make_npc(NPCS["tally"], state.player.position)]
    for _ in range(3):
        spend_a_turn(state)
    return state


def assert_same(left, right, path: str = "") -> None:
    """Compare two values field by field, all the way down.

    Two things are not dataclasses and have to be asked the right question:
    ``Rng`` and ``TurnQueue`` both hold their state behind a method rather than
    in fields, and comparing them by identity would fail on every reload.
    """
    if isinstance(left, Rng) or isinstance(right, Rng):
        assert isinstance(left, Rng) and isinstance(right, Rng), path
        assert_same(left.state(), right.state(), f"{path}.rng-state")
        return
    if isinstance(left, TurnQueue) or isinstance(right, TurnQueue):
        assert isinstance(left, TurnQueue) and isinstance(right, TurnQueue), path
        assert_same(left.snapshot(), right.snapshot(), f"{path}.queue")
        return

    if is_dataclass(left) and not isinstance(left, type):
        assert type(left) is type(right), f"{path}: {type(left)} vs {type(right)}"
        for field in fields(left):
            if not field.metadata.get("saved", True):
                # Not in the save, so not in the comparison: a frame's own memory
                # of what a square looks like comes back empty, on purpose.
                continue
            assert_same(
                getattr(left, field.name), getattr(right, field.name),
                f"{path}.{field.name}",
            )
    elif isinstance(left, list):
        assert len(left) == len(right), f"{path}: {len(left)} vs {len(right)}"
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            assert_same(a, b, f"{path}[{index}]")
    elif isinstance(left, dict):
        assert left.keys() == right.keys(), f"{path}: different keys"
        for key in left:
            assert_same(left[key], right[key], f"{path}[{key!r}]")
    elif isinstance(left, tuple):
        assert len(left) == len(right), f"{path}: {len(left)} vs {len(right)}"
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            assert_same(a, b, f"{path}[{index}]")
    else:
        assert left == right, f"{path}: {left!r} != {right!r}"
        assert type(left) is type(right), f"{path}: {type(left)} != {type(right)}"


# -- the round trip ----------------------------------------------------------
def test_a_floor_that_has_been_drawn_still_saves():
    """What a square *looks* like is a fact about a frame, not about the dungeon.

    The map remembers the display tile of every square it has ever drawn -- that
    is what keeps the overworld from asking eight neighbours about two thousand
    squares a frame. That memory is not part of the save: written down it would
    bloat the file and ask the codec to rebuild a tile enum it deliberately does
    not carry. This draws the floor first, so the cache is full when it is saved.
    """
    state = a_busy_run()
    dungeon = state.dungeon_map
    for y in range(dungeon.height):
        for x in range(dungeon.width):
            dungeon.display_tile((x, y))

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert_same(state, reloaded)


def test_the_aspects_a_run_met_come_back():
    """The margin notes are part of the run's record, so they travel with it."""
    state = a_busy_run()
    state.aspects_met = [("ghoul", "fire_kissed"), ("ooze", "frostbound")]

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.aspects_met == [
        ("ghoul", "fire_kissed"),
        ("ooze", "frostbound"),
    ]


def test_the_coats_a_run_wore_come_back():
    """The wardrobe's page is written from the run, so the run remembers it."""
    state = a_busy_run()
    state.found_armours = ["hide", "warden"]

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.found_armours == ["hide", "warden"]


def test_a_whole_run_comes_back_field_for_field():
    """The test that makes the generic codec safe."""
    state = a_busy_run()

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert_same(state, reloaded)


def test_the_round_trip_survives_the_turn_queue():
    """The queue holds *references* to the same actors, not copies.

    A reloaded queue full of copies would fight with the copies in ``enemies``
    and neither would be the real one -- a ghoul you can see and cannot hit.
    """
    state = a_busy_run()
    reloaded = load(json.loads(json.dumps(dump(state))))

    everyone = [reloaded.player, *reloaded.enemies, *reloaded.npcs]
    for _, _, actor in reloaded.turn_queue.snapshot()[0]:
        assert any(actor is one for one in everyone), "the queue holds a copy"


def test_the_queue_keeps_its_order_and_its_clock():
    state = a_busy_run()
    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.turn_queue.clock == state.turn_queue.clock
    assert [entry[0] for entry in reloaded.turn_queue.snapshot()[0]] == [
        entry[0] for entry in state.turn_queue.snapshot()[0]
    ]


def test_the_generator_comes_back_where_it_left_off():
    """The dice are the run. A reloaded run that rolled differently would not be
    the same run, it would be a run with the same map."""
    state = a_busy_run()
    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.rng.between(1, 10**9) == state.rng.between(1, 10**9)


def test_the_almanac_remembers_what_the_run_has_killed():
    """The book asks the *run* what it has met, so a resume that forgot would
    announce a page the player already owns."""
    state = a_busy_run()
    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.defeated == ["ghoul", "hush"]


def test_the_armory_remembers_what_the_run_has_taken_up():
    """The same question as the bestiary's, for the other collection: a resume
    that forgot would write a page the player already owns."""
    state = a_busy_run()
    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.found_weapons == ["tooth", "grave"]


def test_the_map_comes_back_whole():
    state = a_busy_run()
    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.dungeon_map.tiles == state.dungeon_map.tiles
    assert reloaded.dungeon_map.explored == state.dungeon_map.explored
    assert reloaded.dungeon_map.visible == state.dungeon_map.visible
    assert reloaded.dungeon_map.items == state.dungeon_map.items


def test_a_direction_survives_the_codec():
    """``Direction`` is an enum whose *value* is a tuple, and the codec used to
    write that value raw.

    JSON turned ``(1, 0)`` into ``[1, 0]`` and ``Direction([1, 0])`` is not a
    direction, so a run saved with MOMENTUM loaded refused to open. Found by
    removing WAIT -- a saved run could finally be caught mid-charge.
    """
    state = a_busy_run()
    state.momentum = 3
    state.momentum_direction = Direction.EAST

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.momentum_direction is Direction.EAST


def test_a_position_is_still_a_position():
    """The reason everything is tagged: ``[1, 2]`` could be a tuple or a list, and
    a position that comes back as a list compares unequal to every other position
    in the game."""
    state = a_busy_run()
    reloaded = load(json.loads(json.dumps(dump(state))))

    assert isinstance(reloaded.player.position, tuple)
    assert reloaded.player.position == state.player.position
    assert all(isinstance(pos, tuple) for pos in reloaded.dungeon_map.items)


def test_a_wither_still_remembers_what_it_took():
    """The one curse with state of its own, and the spring is what reads it."""
    state = a_busy_run()
    reloaded = load(json.loads(json.dumps(dump(state))))

    taken = [curse.wither_taken for curse in reloaded.curses if curse.wither_taken]
    assert taken, "the wither forgot"
    assert taken == [curse.wither_taken for curse in state.curses if curse.wither_taken]


def test_a_resumed_run_can_be_played():
    """The point of the whole thing: it is not a snapshot, it is a run."""
    state = a_busy_run()
    reloaded = load(json.loads(json.dumps(dump(state))))

    before = reloaded.total_turns
    spend_a_turn(reloaded)

    assert reloaded.total_turns == before + 1
    assert not reloaded.over


# -- refusals ----------------------------------------------------------------
def test_a_file_from_another_version_is_refused():
    """A run is twenty minutes and a half-rebuilt one is worse than none."""
    payload = dump(a_busy_run())
    payload["version"] = SCHEMA_VERSION + 1

    with pytest.raises(SaveError):
        load(payload)


def test_rubbish_is_refused_rather_than_guessed_at():
    with pytest.raises(SaveError):
        load({})
    with pytest.raises(SaveError):
        load({"version": SCHEMA_VERSION, "hero": "nobody"})


def test_a_missing_field_is_refused():
    payload = dump(a_busy_run())
    del payload["gold"]

    with pytest.raises(SaveError):
        load(payload)


def test_an_unknown_type_is_refused():
    payload = dump(a_busy_run())
    payload["player"]["fields"]["stats"]["!type"] = "SomethingElse"

    with pytest.raises(SaveError):
        load(payload)


def test_an_unknown_enum_is_refused():
    payload = dump(a_busy_run())
    payload["run_state"]["!enum"] = "SomethingElse"

    with pytest.raises(SaveError):
        load(payload)


# -- the file ----------------------------------------------------------------
def test_a_run_round_trips_through_the_file():
    from neverdeads_revenge.persistence import clear_run, load_run, run_path, save_run

    state = a_busy_run()
    save_run(dump(state))

    assert run_path().exists()
    assert load_run() is not None

    reloaded = load(load_run())
    assert_same(state, reloaded)

    clear_run()
    assert not run_path().exists()
    assert load_run() is None


def test_the_slot_is_overwritten_not_added_to():
    """One slot. There is no second one, which is why quitting and reloading is
    not a thing a player can do twice."""
    from neverdeads_revenge.persistence import load_run, run_path, save_run

    save_run(dump(a_busy_run()))
    first = load_run()

    other = start_run(NOXX, seed=99)
    save_run(dump(other))

    assert load_run() != first
    assert load_run()["seed"] == 99
    assert len(list(run_path().parent.glob("run*.json"))) == 1


def test_a_corrupt_file_is_not_a_crash():
    from neverdeads_revenge.persistence import load_run, run_path

    run_path().parent.mkdir(parents=True, exist_ok=True)
    run_path().write_text("{ this is not json")

    assert load_run() is None


def test_a_missing_file_is_not_a_crash():
    from neverdeads_revenge.persistence import clear_run, load_run

    clear_run()
    assert load_run() is None
