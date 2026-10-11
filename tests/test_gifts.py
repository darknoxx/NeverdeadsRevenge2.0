"""Tests for what the dungeon gives back.

A gift is the other half of a curse: the chest charges a price and hands over a
*rule* instead of a blade. Each one changes what a step does, so each one is
tested where it acts -- a step, a descent, a death -- rather than by reading a
number off a table.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import ENEMIES, NOXX, make_enemy
from neverdeads_revenge.game.curses import CURSES
from neverdeads_revenge.game.gifts import GIFTS, gift_by_key
from neverdeads_revenge.game.savegame import dump, load
from neverdeads_revenge.game.state import RunState, start_run
from neverdeads_revenge.world.items import make_chest
from neverdeads_revenge.world.tiles import Tile


# -- helpers ------------------------------------------------------------------
def holding(*keys: str):
    """A run with these gifts already in hand, and room around the player."""
    state = start_run(NOXX, seed=3)
    state.gifts |= set(keys)
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            pos = (state.player.position[0] + dx, state.player.position[1] + dy)
            state.dungeon_map.set_tile(pos, Tile.FLOOR)
    return state


def brute_at(state, offset: int):
    """A monster that cannot miss and cannot be missed, ``offset`` squares east."""
    enemy = make_enemy(
        ENEMIES["bone"], (state.player.position[0] + offset, state.player.position[1])
    )
    enemy.stats.hp = 500
    enemy.stats.accuracy = 99
    enemy.stats.evasion = 0
    enemy.stats.damage = (0, 0)
    state.enemies = [enemy]
    state.turn_queue = type(state.turn_queue)([state.player, enemy])
    state.refresh_vision()
    return enemy


def steps(state, count: int) -> list[int]:
    """Walk ``count`` steps and report the turns each one cost."""
    spent: list[int] = []
    for _ in range(count):
        before = state.total_turns
        for direction in (
            Action.MOVE_EAST,
            Action.MOVE_WEST,
            Action.MOVE_NORTH,
            Action.MOVE_SOUTH,
        ):
            if perform_action(state, direction).acted:
                spent.append(state.total_turns - before)
                break
    return spent


# -- the table ----------------------------------------------------------------
def test_every_gift_says_what_it_does():
    for key, gift in GIFTS.items():
        assert gift.key == key
        assert gift.name.isupper(), key
        assert gift.blurb and gift.blurb[0].islower(), key
        assert gift_by_key(key) is gift


def test_a_chest_holds_a_gift_or_a_reward_and_never_both():
    """Two rewards for one price is not a bargain, it is a sale."""
    gift = make_chest("dim", None, gift="long_reach")
    assert gift.gift == "long_reach" and gift.contents is None

    loot = make_chest("dim", None)
    assert loot.gift is None and loot.contents is None


def test_a_run_is_never_offered_a_gift_it_already_holds():
    """Two of the same rule is not twice the rule."""
    state = start_run(NOXX, seed=3)
    assert set(state.unheld_gifts) == set(GIFTS)

    state.gifts.add("long_reach")
    assert "long_reach" not in state.unheld_gifts
    assert len(state.unheld_gifts) == len(GIFTS) - 1


# -- THE LONG REACH -----------------------------------------------------------
def test_a_long_reach_strikes_two_squares_away():
    """The gift is that a *direction* reaches, not that a key does.

    Walking into a monster still attacks it. With the reach, a direction with
    something hostile one square beyond an empty square is a blow instead of a
    step -- which is the whole of the rule, and it means the player never has to
    learn a second attack key.
    """
    state = holding("long_reach")
    enemy = brute_at(state, 2)
    before = (state.player.position, enemy.stats.hp)

    perform_action(state, Action.MOVE_EAST)

    assert state.player.position == before[0], "the player walked instead of striking"
    assert enemy.stats.hp < before[1], "nothing was hit"


def test_without_the_gift_a_square_two_away_is_just_a_step():
    state = holding()
    enemy = brute_at(state, 2)
    before = (state.player.position, enemy.stats.hp)

    perform_action(state, Action.MOVE_EAST)

    assert state.player.position != before[0], "the player refused to move"
    assert enemy.stats.hp == before[1]


def test_stone_stops_the_reach():
    """It is a reach and not a bow: what is in between is what decides."""
    state = holding("long_reach")
    enemy = brute_at(state, 2)
    state.dungeon_map.set_tile(
        (state.player.position[0] + 1, state.player.position[1]), Tile.WALL
    )
    before = (state.player.position, enemy.stats.hp)

    perform_action(state, Action.MOVE_EAST)

    assert enemy.stats.hp == before[1], "the blow went through a wall"


def test_the_reach_does_not_swing_at_people():
    """A person standing two squares away is still not something to hit."""
    from neverdeads_revenge.game.actors import make_npc
    from neverdeads_revenge.game.npcs import NPCS

    state = holding("long_reach")
    npc = make_npc(NPCS[next(iter(NPCS))], (state.player.position[0] + 2, state.player.position[1]))
    state.npcs = [npc]
    state.enemies = []
    state.refresh_vision()
    before = state.player.position

    perform_action(state, Action.MOVE_EAST)

    assert state.player.position != before, "the player struck at a person"


# -- THE STEP BEHIND ----------------------------------------------------------
def test_every_fifth_step_costs_nothing():
    """The one gift that touches the score, because turns *are* the score.

    And the player still moves: a step that reported "nothing happened" would
    leave them standing still on screen, which is why acting and spending are
    two flags and not one.
    """
    state = holding("step_behind")
    spent = steps(state, 6)

    assert spent == [1, 1, 1, 1, 0, 1]
    assert state.player.steps == 6, "the free step did not happen"


def test_without_the_gift_every_step_costs_a_turn():
    assert steps(holding(), 6) == [1] * 6


# -- THE KIND DARK ------------------------------------------------------------
def test_the_kind_dark_lifts_one_curse_per_descent():
    state = holding("kind_dark")
    for key in ("dim", "heavy", "frail"):
        state.add_curse(CURSES[key])

    state.player.position = state.stairs
    perform_action(state, Action.DESCEND)

    assert len(state.curses) == 2, "it took none, or more than one"
    assert state.depth == 2


def test_without_the_gift_a_descent_is_not_a_cure():
    state = holding()
    state.add_curse(CURSES["dim"])
    state.player.position = state.stairs

    perform_action(state, Action.DESCEND)

    assert [c.key for c in state.curses] == ["dim"]


def test_the_kind_dark_does_nothing_on_the_first_floor():
    """There is nothing to give back before anything has been taken."""
    state = holding("kind_dark")
    state.add_curse(CURSES["dim"])

    state.build_floor(1)

    assert [c.key for c in state.curses] == ["dim"]


# -- THE HOLLOW ROAD ----------------------------------------------------------
def test_the_hollow_road_walks_into_stone_and_charges_for_it():
    state = holding("hollow_road")
    target = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(target, Tile.WALL)
    before = state.player.hp

    perform_action(state, Action.MOVE_EAST)

    assert state.player.position == target
    assert state.player.hp == before - 2


def test_without_the_gift_a_wall_is_a_wall():
    state = holding()
    target = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(target, Tile.WALL)
    before = state.player.position

    perform_action(state, Action.MOVE_EAST)

    assert state.player.position == before


def test_the_hollow_road_can_finish_you():
    """A gift with no floor is a gift that is not a decision."""
    state = holding("hollow_road")
    target = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(target, Tile.WALL)
    state.player.stats.hp = 1

    perform_action(state, Action.MOVE_EAST)

    assert state.run_state is RunState.DEAD


# -- THE BORROWED HOUR --------------------------------------------------------
def test_the_borrowed_hour_gives_a_death_back():
    """The one verb that works after the run is over, because undoing a death is
    the whole of what the gift is for."""
    state = holding("borrowed_hour")
    state.build_floor(1)  # arms the hour, the way a descent does
    assert state.rewind_ready

    enemy = brute_at(state, 1)
    enemy.stats.damage = (99, 99)
    for _ in range(20):
        perform_action(state, Action.WAIT)
        if state.over:
            break
    assert state.run_state is RunState.DEAD

    result = perform_action(state, Action.REWIND)

    assert result.acted
    assert state.run_state is RunState.PLAYING
    assert state.player.alive


def test_the_hour_is_spent_when_it_is_used():
    state = holding("borrowed_hour")
    state.build_floor(1)
    perform_action(state, Action.WAIT)

    assert perform_action(state, Action.REWIND).acted
    assert not state.rewind_ready
    assert not perform_action(state, Action.REWIND).acted, "it was spent twice"


def test_without_the_gift_there_is_no_hour():
    state = holding()
    perform_action(state, Action.WAIT)

    assert not perform_action(state, Action.REWIND).acted
    assert state.run_state is RunState.PLAYING


def test_the_hour_comes_back_on_the_next_floor():
    state = holding("borrowed_hour")
    state.build_floor(1)
    perform_action(state, Action.WAIT)
    perform_action(state, Action.REWIND)

    state.player.position = state.stairs
    perform_action(state, Action.DESCEND)

    assert state.rewind_ready, "the hour did not refill"


def test_a_rewind_puts_the_run_back_the_way_it_was():
    """Not just health: the monster, the map and the purse go back too."""
    state = holding("borrowed_hour")
    state.build_floor(1)
    state.gold = 50
    enemy = brute_at(state, 1)
    enemy.stats.damage = (99, 99)
    perform_action(state, Action.WAIT)

    perform_action(state, Action.REWIND)

    assert state.gold == 50
    assert state.player.stats.hp == state.player.max_hp
    assert state.depth == 1


def test_a_rewind_leaves_the_queue_holding_the_real_actors():
    """The hour gives the run back, not a wax copy of it.

    The turn queue has to be rebuilt around the *same* objects state.player and
    state.enemies point at, or the restored queue schedules a set of phantom
    copies that nobody outside the queue can see or kill. Rebuilding the
    snapshot field by field did exactly that: the player and every monster fell
    out of the queue on the first rewind, dead monsters kept taking turns, and
    the hero's own status ticks went to a duplicate that was never rendered.
    """
    state = holding("borrowed_hour")
    state.build_floor(1)
    perform_action(state, Action.WAIT)
    perform_action(state, Action.REWIND)

    # ``in`` is identity on the queue, which is the whole point of this test.
    assert state.player in state.turn_queue
    assert len(state.enemies) > 0
    for enemy in state.enemies:
        assert enemy in state.turn_queue


def test_a_monster_rewritten_after_the_rewind_is_rewritten_in_the_queue():
    """The rewind's bodies and the queue's bodies are one and the same.

    The restored actors are fresh copies by design -- the whole run is put
    back -- so the test pins the property that matters: whatever the state
    fields hold after the rewind, the queue holds that same thing. Killing
    serves as the sharpest probe, because it is the one thing that touches the
    queue by identity.
    """
    state = holding("borrowed_hour")
    state.build_floor(1)
    enemy = brute_at(state, 1)
    perform_action(state, Action.WAIT)
    perform_action(state, Action.REWIND)

    restored = [e for e in state.enemies if e.position == enemy.position]
    assert len(restored) == 1, "the brute did not come back to life at its post"
    restored = restored[0]

    removed = state.turn_queue.remove(restored)
    assert removed, "the restored queue was scheduling a stranger"
    assert restored not in state.turn_queue


# -- the save ----------------------------------------------------------------
def test_gifts_survive_a_save_and_an_old_save_does_not_have_them():
    state = start_run(NOXX, seed=3)
    state.gifts = {"long_reach", "kind_dark"}
    assert load(dump(state)).gifts == {"long_reach", "kind_dark"}

    payload = dump(state)
    payload.pop("gifts")
    assert load(payload).gifts == set()
