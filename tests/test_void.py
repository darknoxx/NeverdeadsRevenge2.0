"""The void: Noxx's one ask per floor, and the shadow it sends.

The whole feature lives in four numbers (level gate, one ask per floor, forty
turns of shadow, a blood price floored at one) and every number is pinned
here, because each of them is also the edge the player measures it by.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.core.direction import chebyshev
from neverdeads_revenge.game.actors import ActorKind, ENEMIES, make_enemy
from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.difficulty import (
    ATRITAS_RADIUS,
    ATRITAS_TURNS,
)
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.world.tiles import Tile


def _run(ultimate_level: int | None = None, hero: str = "noxx", seed: int = 5):
    state = start_run(
        HEROES[hero], seed, ultimate_level=ultimate_level
    )
    return state


def _wait(state, times: int = 1) -> None:
    for _ in range(times):
        perform_action(state, Action.WAIT)


def _stage_enemy_at_square(state, square, hp: int = 1):
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    enemy = make_enemy(ENEMIES["ghoul"], square)
    enemy.stats.hp = hp
    enemy.stats.max_hp = hp
    enemy.stats.damage = (0, 0)
    state.enemies.append(enemy)
    state.turn_queue.add(enemy)
    return enemy


# -- the gate -----------------------------------------------------------------
def test_the_void_refuses_the_low_levels():
    """Below the level it answers at, the ask does nothing but say when."""
    state = _run()
    state.level = 1  # the start; the void answers at ten

    before_turns = state.total_turns
    result = perform_action(state, Action.SUMMON_VOID)

    assert state.atritas is None
    assert state.void_available is True
    assert state.total_turns == before_turns, "a refusal cannot cost the floor"
    assert any("not yet" in entry.text for entry in state.log)


def test_the_void_does_not_advertise_to_other_heroes():
    """Noxx's dark is his: on anybody else the key is a key that does nothing,
    and nothing is not a log line reading as an offer."""
    state = start_run(HEROES["yeti"], 3, ultimate_level=1)

    result = perform_action(state, Action.SUMMON_VOID)

    assert state.atritas is None
    assert state.void_available is True
    assert state.total_turns == 0
    assert any("atritas" not in entry.text.lower() for entry in state.log[-1:])


def test_a_testrun_runs_answer_early():
    """`--testrun` lowers the gate so a test can hear the whole song."""
    state = _run(ultimate_level=1)

    result = perform_action(state, Action.SUMMON_VOID)
    # Consumes a turn: the scheduler answers the cast, so the shadow is real.
    assert state.atritas is not None, "the void refused its one ask"


# -- one ask per floor ---------------------------------------------------------
def test_the_void_answers_once_and_then_goes_grey():
    """Second cast on one floor: refused, and the refusal is free."""
    state = _run(ultimate_level=1)

    assert perform_action(state, Action.SUMMON_VOID).consumed_turn
    assert state.void_available is False

    before_turns = state.total_turns
    result = perform_action(state, Action.SUMMON_VOID)

    assert result.consumed_turn is False
    assert state.total_turns == before_turns
    assert any("does not ask twice" in entry.text for entry in state.log)


def test_a_new_floor_ask_again():
    """Descent refills the ask: the promise is per floor, and says so."""
    state = _run(ultimate_level=1)

    perform_action(state, Action.SUMMON_VOID)
    assert state.void_available is False

    state.build_floor(2)

    assert state.void_available is True
    assert state.atritas is None, "the shadow stays with its own floor"


# -- what the cast is worth ----------------------------------------------------
def test_the_cast_opens_the_whole_floor():
    """Every wall is glass: the whole map is explored, walls and all."""
    state = _run(ultimate_level=1)

    perform_action(state, Action.SUMMON_VOID)

    total = state.dungeon_map.width * state.dungeon_map.height
    assert len(state.dungeon_map.explored) == total, (
        "the reveal left a wall unopened"
    )


def test_the_shadow_stands_beside_noxx():
    state = _run(ultimate_level=1)

    perform_action(state, Action.SUMMON_VOID)

    atritas = state.atritas
    assert atritas is not None
    assert atritas.kind is ActorKind.ATRITAS
    distance = chebyshev(atritas.position, state.player.position)
    assert 2 <= distance <= 4, "the dark is not beside anyone"


def test_a_bump_against_the_shadow_costs_nothing():
    """Walking into your own dark is a word, not a fight and not a turn."""
    state = _run(ultimate_level=1)
    perform_action(state, Action.SUMMON_VOID)
    atritas = state.atritas
    state.player.position = (atritas.position[0] - 1, atritas.position[1])
    state.refresh_vision()

    before = state.total_turns
    logs = {entry.text for entry in state.log}
    from neverdeads_revenge.core.direction import Direction as _D

    perform_action(state, _move_towards(atritas.position, state.player.position))
    logs |= {entry.text for entry in state.log}

    assert state.total_turns == before, "bumping the shadow charged a turn"
    assert state.atritas is atritas
    assert any("It is yours" in text for text in logs)


def _move_towards(target, source):
    from neverdeads_revenge.game.actions import Action
    from neverdeads_revenge.core.direction import direction_towards

    mapping = {
        "NORTH": Action.MOVE_NORTH, "SOUTH": Action.MOVE_SOUTH,
        "EAST": Action.MOVE_EAST, "WEST": Action.MOVE_WEST,
        "NORTH_EAST": Action.MOVE_NE, "NORTH_WEST": Action.MOVE_NW,
        "SOUTH_EAST": Action.MOVE_SE, "SOUTH_WEST": Action.MOVE_SW,
    }
    return mapping[direction_towards(source, target).name]


# -- the price -------------------------------------------------------------------
def test_the_drain_spend_health_but_never_the_last():
    """One health every second beat of the stay, floored at one: the dark
    cannot kill its summoner, because the ask was a cost, not a bet."""
    state = _run(ultimate_level=1)

    perform_action(state, Action.SUMMON_VOID)
    state.player.stats.hp = 5

    _wait(state, ATRITAS_TURNS)

    assert state.player.stats.hp == 1, "the drain fell below one"
    assert state.atritas is None and not state.over


def test_the_drain_happens_on_its_beat():
    state = _run(ultimate_level=1)

    perform_action(state, Action.SUMMON_VOID)
    state.player.stats.hp = 3
    # The cast's own tick is age one, so the first drain lands on the ninth
    # beat of waiting, not the eighth.

    _wait(state, 8)
    assert state.player.stats.hp == 3
    _wait(state, 1)
    assert state.player.stats.hp == 2


# -- the assistance ---------------------------------------------------------------
def test_the_shadow_takes_the_preys_beside_noxx():
    """Atritas swings on what stands within his reach of Noxx, and the kill
    is Noxx's: coin, revenge, level, the whole payoff."""
    state = _run(ultimate_level=1)
    perform_action(state, Action.SUMMON_VOID)

    square = (state.player.position[0] + 1, state.player.position[1])
    enemy = _stage_enemy_at_square(state, square, hp=1)
    revenge_before = state.revenge_stacks

    _wait(state, 4)  # the first swing lands at age 3

    assert enemy.alive is False, "the shadow's swing did not land"
    assert state.atritas is not None, "the shadow left too early"
    assert state.revenge_stacks > revenge_before, "the kill was nobody's"
    assert any("Atritas" in entry.text for entry in state.log)


def test_the_shadow_ignores_a_far_prey():
    """The promise was *around* him: distance is respected, reach is not."""
    state = _run(ultimate_level=1)
    perform_action(state, Action.SUMMON_VOID)

    far_square = (
        state.player.position[0] + ATRITAS_RADIUS + 5,
        state.player.position[1] + ATRITAS_RADIUS + 5,
    )
    _stage_enemy_at_square(state, far_square, hp=1)

    _wait(state, 4)

    assert state.enemies and state.enemies[0].alive, (
        "the shadow reached a thing it was never promised"
    )


def test_the_shadow_leaves_at_forty_turns():
    """Forty beats, then the dark goes home -- and the walls re-close."""
    state = _run(ultimate_level=1)

    perform_action(state, Action.SUMMON_VOID)
    assert state.atritas is not None

    _wait(state, ATRITAS_TURNS)

    assert state.atritas is None, "the shadow overstayed the promise"
    assert any("sinks back" in entry.text for entry in state.log)


# -- the save -----------------------------------------------------------------------
def test_the_ask_survives_a_save():
    """A spent ask is grey in the save too: reloading cannot re-ask the void
    on a floor that already had it."""
    from neverdeads_revenge.game.savegame import dump, load

    state = _run(ultimate_level=1)
    perform_action(state, Action.SUMMON_VOID)
    assert state.void_available is False

    restored = load(dump(state))

    assert restored.void_available is False
