"""Tests for the cleansing spring and for lifting a curse.

A curse used to be permanent by definition -- "a decision made once and lived
with" -- and half of this file is about the part that is easy to get wrong when
that stops being true: giving back *exactly* what was taken. A wither takes a
quarter of the maximum at the moment it lands, so a spring that recomputes the
fraction on the way out hands back a different number, and one that subtracts
modifiers instead of rebuilding them leaves a floating-point residue on the
hero's speed forever.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.game.actions import Action, perform_action, spring_prompt
from neverdeads_revenge.game.actors import NOXX
from neverdeads_revenge.game.curses import CURSES
from neverdeads_revenge.game.state import CLEANSE_COST, start_run
from neverdeads_revenge.world.generator import SPRING_CHANCE, generate_floor
from neverdeads_revenge.world.tiles import Tile


def on_a_spring(seed: int = 3, gold: int = 0, curses: tuple[str, ...] = ()):
    """A run standing in a spring, with the named curses on it."""
    state = start_run(NOXX, seed=seed)
    state.dungeon_map.set_tile(state.player.position, Tile.SPRING)
    for key in curses:
        state.add_curse(CURSES[key])
    state.gold = gold
    return state


# -- the tile ---------------------------------------------------------------
def test_the_spring_is_standable_and_visible_through():
    """You have to stand in it, and a spring you cannot see past is a wall."""
    assert not Tile.SPRING.blocks_movement
    assert not Tile.SPRING.blocks_sight


def test_the_spring_is_not_on_the_first_floor_or_on_the_exit():
    for seed in range(40):
        first = generate_floor(Rng(seed), depth=1, curse_keys=tuple(CURSES))
        assert first.spring is None, "a curse on floor one cannot exist yet"

        for depth in (2, 5, 9):
            floor = generate_floor(Rng(seed), depth=depth, curse_keys=tuple(CURSES))
            if floor.spring is None:
                continue
            assert floor.spring != floor.stairs_down
            assert floor.map.tile_at(floor.spring) is Tile.SPRING


def test_a_spring_is_not_on_every_floor():
    """One at every staircase would make a curse cost a walk, not a decision."""
    floors = [
        generate_floor(Rng(seed), depth=5, curse_keys=tuple(CURSES))
        for seed in range(60)
    ]
    with_spring = sum(1 for floor in floors if floor.spring is not None)
    assert 0 < with_spring < len(floors), f"{with_spring} springs out of 60 floors"
    assert 0 < SPRING_CHANCE < 1


def test_nothing_ever_lands_on_the_spring():
    """The loot's plain-floor rule keeps it clear without a second list."""
    for seed in range(40):
        floor = generate_floor(Rng(seed), depth=6, curse_keys=tuple(CURSES))
        if floor.spring is not None:
            assert floor.spring not in floor.items


# -- lifting a curse --------------------------------------------------------
def test_a_wither_remembers_exactly_what_it_took():
    state = start_run(NOXX, seed=3)
    before = state.player.max_hp

    state.add_curse(CURSES["wither"])

    assert state.curses[0].wither_taken == before - state.player.max_hp
    assert state.curses[0].wither_taken > 0


def test_lifting_a_wither_gives_back_the_health_exactly():
    state = start_run(NOXX, seed=3)
    before = state.player.max_hp

    state.add_curse(CURSES["wither"])
    state.remove_curse(state.curses[0])

    assert state.player.max_hp == before
    assert state.curses == []


def test_lifting_a_wither_twice_over_still_adds_up():
    """Two withers, one lifted: the arithmetic has to survive both."""
    state = start_run(NOXX, seed=3)
    before = state.player.max_hp

    state.add_curse(CURSES["wither"])
    state.add_curse(CURSES["wither"])
    assert state.player.max_hp < before

    state.remove_curse(state.curses[0])
    assert state.player.max_hp < before, "one wither is still on you"

    state.remove_curse(state.curses[0])
    assert state.player.max_hp == before


def test_lifting_a_curse_leaves_no_residue_on_the_stats():
    """Rebuilt, not subtracted: floats do not subtract back where they started."""
    state = start_run(NOXX, seed=3)
    before = state.player.speed

    for key in ("heavy", "frail"):
        state.add_curse(CURSES[key])
    for curse in list(state.curses):
        state.remove_curse(curse)

    assert state.player.speed == before
    assert state.player.armor == NOXX.stats.armor
    assert state.player.modifiers.is_empty


def test_lifting_one_curse_leaves_the_others_working():
    state = start_run(NOXX, seed=3)
    state.add_curse(CURSES["heavy"])
    state.add_curse(CURSES["frail"])

    state.remove_curse(state.curses[0])

    assert state.player.speed == NOXX.stats.speed, "heavy is gone"
    assert state.player.armor == NOXX.stats.armor - 2, "frail is still on"


def test_lifting_bleed_stops_the_bleeding():
    state = start_run(NOXX, seed=3)
    state.add_curse(CURSES["bleed"])
    assert state.bleed_every == CURSES["bleed"].bleed_every

    state.remove_curse(state.curses[0])
    assert state.bleed_every == 0


def test_lifting_dim_gives_the_sight_back():
    state = start_run(NOXX, seed=3)
    before = state.sight_radius

    state.add_curse(CURSES["dim"])
    assert state.sight_radius == 5

    state.remove_curse(state.curses[0])
    assert state.sight_radius == before


def test_lifting_famine_gives_the_draughts_back():
    state = start_run(NOXX, seed=3)
    state.add_curse(CURSES["famine"])
    assert state.heal_scale == 0.5

    state.remove_curse(state.curses[0])
    assert state.heal_scale == 1.0


def test_lifting_a_curse_you_do_not_have_does_nothing():
    state = start_run(NOXX, seed=3)
    state.add_curse(CURSES["heavy"])
    before = state.player.speed

    state.remove_curse(CURSES["frail"])

    assert state.player.speed == before
    assert len(state.curses) == 1


# -- the spring itself ------------------------------------------------------
def test_a_clean_hero_is_told_there_is_nothing_to_wash_off():
    state = on_a_spring(gold=100)
    result = perform_action(state, Action.INTERACT)

    assert result.prompt is None
    assert "nothing on you" in state.log[-1].text


def test_the_spring_states_the_price_rather_than_offering_what_you_cannot_pay():
    """A dialog that ends in "you cannot afford this" wasted the player's time."""
    state = on_a_spring(gold=CLEANSE_COST - 1, curses=("heavy",))
    result = perform_action(state, Action.INTERACT)

    assert result.prompt is None
    assert str(CLEANSE_COST) in state.log[-1].text
    assert str(state.gold) in state.log[-1].text


def test_the_spring_asks_when_it_can_help():
    state = on_a_spring(gold=CLEANSE_COST, curses=("heavy",))
    result = perform_action(state, Action.INTERACT)

    assert result.prompt_kind == "spring", "the UI cannot tell a spring from a chest"
    assert result.prompt is not None
    assert str(CLEANSE_COST) in result.prompt


def test_the_spring_names_the_only_curse_you_have():
    """With one curse there is nothing random about it, so it says which."""
    state = on_a_spring(gold=CLEANSE_COST, curses=("heavy",))
    assert "HEAVY" in spring_prompt(state)


def test_the_spring_does_not_pretend_to_let_you_choose():
    state = on_a_spring(gold=CLEANSE_COST, curses=("heavy", "frail"))
    prompt = spring_prompt(state)

    assert "HEAVY" not in prompt and "FRAIL" not in prompt
    assert "one of your curses" in prompt


def test_washing_a_curse_off_costs_the_coin_and_takes_exactly_one():
    state = on_a_spring(gold=100, curses=("heavy", "frail"))

    perform_action(state, Action.CLEANSE)

    assert state.gold == 100 - CLEANSE_COST
    assert len(state.curses) == 1, "the water took more than it was paid for"


def test_washing_a_curse_off_does_not_cost_a_turn():
    """Being clean is not something the monsters should get to answer."""
    state = on_a_spring(gold=100, curses=("heavy",))
    result = perform_action(state, Action.CLEANSE)

    assert result.consumed_turn is False
    assert state.turn == 0
    assert state.total_turns == 0


def test_the_spring_cannot_be_used_from_anywhere_else():
    """It is not bound to a key, and it does not work by memory."""
    state = start_run(NOXX, seed=3)
    state.gold = 100
    state.add_curse(CURSES["heavy"])

    perform_action(state, Action.CLEANSE)

    assert state.gold == 100
    assert len(state.curses) == 1


def test_washing_a_curse_off_works_whichever_one_the_water_picks():
    """The choice is the water's, and it must be able to make either."""
    picked = set()
    for seed in range(30):
        state = on_a_spring(seed=seed, gold=100, curses=("heavy", "frail"))
        before = {curse.key for curse in state.curses}
        perform_action(state, Action.CLEANSE)
        after = {curse.key for curse in state.curses}
        picked |= before - after

    assert picked == {"heavy", "frail"}, f"the water only ever took {picked}"


def test_the_spring_is_not_the_way_out():
    """Standing in it and pressing enter must not descend or escape."""
    state = on_a_spring(gold=0)
    result = perform_action(state, Action.INTERACT)

    assert result.died is False and result.escaped is False
    assert state.depth == 1
    assert state.run_state.value == "playing"


@pytest.mark.parametrize("key", sorted(CURSES))
def test_every_curse_can_be_lifted(key: str):
    """Every price in the table has to be reversible, not just the easy ones."""
    state = start_run(NOXX, seed=3)
    baseline = (
        state.player.max_hp,
        state.player.speed,
        state.player.armor,
        state.sight_radius,
        state.heal_scale,
        state.bleed_every,
    )

    state.add_curse(CURSES[key])
    state.remove_curse(state.curses[0])

    assert (
        state.player.max_hp,
        state.player.speed,
        state.player.armor,
        state.sight_radius,
        state.heal_scale,
        state.bleed_every,
    ) == baseline


def test_a_spring_is_spent_by_the_wash():
    """One wash per spring.

    Otherwise a curse is not a decision at all: you walk back to the same water
    and pay again, and the only thing standing between you and a clean sheet is
    the size of the purse.
    """
    state = on_a_spring(gold=200, curses=("heavy", "frail"))
    assert state.at_the_spring

    perform_action(state, Action.CLEANSE)

    assert not state.at_the_spring, "the spring is still there"
    assert state.dungeon_map.tile_at(state.player.position) is Tile.FLOOR
    assert state.gold == 200 - CLEANSE_COST


def test_a_spent_spring_does_nothing_the_second_time():
    state = on_a_spring(gold=200, curses=("heavy", "frail"))
    perform_action(state, Action.CLEANSE)

    before_gold = state.gold
    left = len(state.curses)
    result = perform_action(state, Action.INTERACT)
    perform_action(state, Action.CLEANSE)

    assert result.prompt is None, "a spent spring offered another wash"
    assert state.gold == before_gold
    assert len(state.curses) == left
    assert "nothing here" in state.log[-1].text


def test_a_spring_you_walked_away_from_is_still_there():
    """Spent by a wash, not by being looked at."""
    state = on_a_spring(gold=200, curses=("heavy",))
    result = perform_action(state, Action.INTERACT)
    assert result.prompt is not None

    assert state.at_the_spring, "asking spent it"
