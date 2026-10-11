"""Tests for the curve a run climbs.

The whole thing is a function of the kill count, so most of this file reads the
curve off rather than playing it: thresholds, the rotation of what each level
grants, and the arithmetic of a jump of several levels at once. The last few
tests are the integration -- that a kill actually teaches, that what it teaches
survives a descent, and that nothing can take it back.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import ENEMIES, NOXX, make_enemy, make_hero
from neverdeads_revenge.game.combat import AttackOutcome
from neverdeads_revenge.game.levels import (
    KILLS_PER_LEVEL,
    MAX_LEVEL,
    Gain,
    apply_gain,
    gains_between,
    gains_for,
    level_for,
)
from neverdeads_revenge.game.shop import Loadout
from neverdeads_revenge.game.state import start_run


# -- the curve ---------------------------------------------------------------
def test_a_run_starts_at_level_one_and_earns_one_every_few_kills():
    assert level_for(0) == 1
    for kills in range(KILLS_PER_LEVEL):
        assert level_for(kills) == 1
    assert level_for(KILLS_PER_LEVEL) == 2
    assert level_for(KILLS_PER_LEVEL * 2) == 3


def test_the_level_never_goes_backwards():
    """Derived from the kill count, so it cannot be lost or double-paid."""
    levels = [level_for(kills) for kills in range(0, 200)]
    assert levels == sorted(levels)


def test_the_curve_stops_teaching_at_the_cap():
    assert level_for(10_000) == MAX_LEVEL
    assert gains_for(MAX_LEVEL + 1) == Gain(), "the cap is not a cap"
    assert gains_for(MAX_LEVEL + 20) == Gain()


def test_the_cap_sits_where_a_run_can_still_be_working_toward_it():
    """A cap below the ceiling is a wall a thorough run can feel without ever
    being told it is there, which is what twenty was.

    A perfect clear is every monster on all ten floors. The cap has to be
    reachable, and it must not leave more than the last level unearned -- a
    whole level of kills that teach nothing would be the same wall again.
    """
    from neverdeads_revenge.world.generator import ESCAPE_DEPTH, enemy_count

    perfect = sum(enemy_count(depth) for depth in range(1, ESCAPE_DEPTH + 1))
    # Uncapped, because level_for clamps and would make this test vacuous.
    ceiling = 1 + perfect // KILLS_PER_LEVEL

    assert ceiling >= MAX_LEVEL, f"a perfect clear is level {ceiling}, below the cap"
    assert ceiling - MAX_LEVEL <= 1, (
        f"a perfect clear is level {ceiling}, so the cap wastes {ceiling - MAX_LEVEL} "
        f"of them"
    )


def test_every_level_after_the_first_grants_something():
    for level in range(2, MAX_LEVEL + 1):
        assert not gains_for(level).is_empty, level


def test_the_first_level_grants_nothing():
    """You start at one. A level-one gain would be a gain every hero starts with,
    which is the same as no gain and one more number to read."""
    assert gains_for(1) == Gain()


def test_health_every_level_and_the_rest_on_a_rotation():
    for level in range(2, MAX_LEVEL + 1):
        assert gains_for(level).max_hp == 2, level
    assert [level for level in range(2, 20) if gains_for(level).damage] == [3, 6, 9, 12, 15, 18]
    assert [level for level in range(2, 20) if gains_for(level).armor] == [4, 8, 12, 16]
    assert [level for level in range(2, 20) if gains_for(level).speed] == [5, 10, 15]


def test_the_rotations_do_not_all_land_together():
    """Coprime lengths on purpose: if two of them shared a period the run would
    feel like a staircase instead of a curve."""
    together = [
        level
        for level in range(2, 60)
        if gains_for(level).damage and gains_for(level).armor and gains_for(level).speed
    ]
    assert len(together) <= 1, f"everything arrives at once on {together}"


def test_a_jump_of_several_levels_adds_up():
    """A single kill can be worth two levels if the last one was close."""
    assert gains_between(1, 4) == gains_for(2) + gains_for(3) + gains_for(4)
    assert gains_between(4, 4) == Gain()


def test_a_gain_says_what_it_is():
    assert "max health" in Gain(max_hp=2).describe()
    assert "damage" in Gain(damage=1).describe()
    assert "speed" in Gain(speed=0.05).describe()
    assert Gain().describe(), "an empty gain should still be a sentence"


# -- what it does to a hero --------------------------------------------------
def test_a_gain_writes_into_the_hero_and_not_into_a_bonus():
    """A level is not a bonus and does not lapse. It is the hero."""
    hero = make_hero(NOXX, (0, 0))
    before = (hero.max_hp, hero.damage_range, hero.armor)

    apply_gain(hero, Gain(max_hp=2, damage=1, armor=1))

    assert hero.max_hp == before[0] + 2
    assert hero.damage_range == (before[1][0] + 1, before[1][1] + 1)
    assert hero.armor == before[2] + 1
    assert hero.stats.armor == before[2] + 1, "it went into a bonus, not the hero"


def test_the_new_health_is_health_you_have():
    """A level that raised the ceiling and left you at the old number would be a
    level you have to drink your way back to."""
    hero = make_hero(NOXX, (0, 0))
    hero.stats.hp = 10
    apply_gain(hero, Gain(max_hp=2))
    assert hero.hp == 12


def test_a_gain_never_heals_past_the_new_ceiling():
    hero = make_hero(NOXX, (0, 0))
    apply_gain(hero, Gain(max_hp=2))
    assert hero.hp == hero.max_hp


def test_a_speed_gain_moves_the_hero():
    hero = make_hero(NOXX, (0, 0))
    before = hero.speed
    apply_gain(hero, Gain(speed=0.05))
    assert hero.speed == pytest.approx(before + 0.05)


# -- in the game -------------------------------------------------------------
def _teach(state, times: int = 1) -> None:
    """Kill something, without arranging a fight for each one."""
    from neverdeads_revenge.game.actions import _kill_message

    for _ in range(times):
        victim = make_enemy(ENEMIES["ghoul"], state.player.position)
        victim.stats.hp = 1
        state.enemies = [victim]
        state.turn_queue = type(state.turn_queue)([state.player, victim])
        _kill_message(
            state, victim, AttackOutcome(hit=True, crit=False, damage=1, killed=True)
        )


def test_a_kill_teaches_the_hero():
    state = start_run(NOXX, seed=3)
    before = state.player.max_hp

    _teach(state, KILLS_PER_LEVEL)

    assert state.level == 2
    assert state.player.max_hp == before + 2
    assert any(entry.text.startswith("Level 2") for entry in state.log)


def test_a_kill_that_does_not_reach_a_level_says_nothing():
    state = start_run(NOXX, seed=3)
    _teach(state, KILLS_PER_LEVEL - 1)
    assert state.level == 1
    assert not any(entry.text.startswith("Level") for entry in state.log)


def test_what_a_run_taught_survives_the_next_floor():
    """The whole reason it goes into the hero's own stats rather than into a
    bonus field: REVENGE lapses on the way down, and a level must not."""
    state = start_run(NOXX, seed=3)
    _teach(state, KILLS_PER_LEVEL)
    before = state.player.max_hp
    assert state.revenge_stacks > 0

    state.build_floor(2)

    assert state.revenge_stacks == 0, "REVENGE is meant to lapse"
    assert state.player.max_hp == before, "the level lapsed with it"
    assert state.level == 2


def test_the_level_is_a_run_total_and_not_a_floor_one():
    state = start_run(NOXX, seed=3)
    _teach(state, KILLS_PER_LEVEL * 2)
    assert state.level == 3

    state.build_floor(3)

    assert state.level == 3
    assert state.kills == KILLS_PER_LEVEL * 2


def test_a_fresh_run_starts_at_level_one_however_the_last_one_ended():
    state = start_run(NOXX, seed=3)
    _teach(state, KILLS_PER_LEVEL * 5)
    assert state.level > 1

    fresh = start_run(NOXX, seed=3)
    assert fresh.level == 1
    assert fresh.kills == 0








def test_levelling_does_not_make_a_hero_stronger_than_the_cap():
    state = start_run(NOXX, seed=3, loadout=Loadout(upgrades={"vigour": 3}))
    _teach(state, KILLS_PER_LEVEL * 40)
    assert state.level == MAX_LEVEL
    # The cap is a level cap, not a stat cap: the hero keeps whatever the
    # shop and the equipment gave him on top.
    assert state.player.max_hp > NOXX.stats.max_hp


def test_the_walk_into_a_monster_still_works_after_a_level():
    """The integration, played rather than poked: a real kill through
    ``perform_action`` has to level the hero and leave the game coherent."""
    state = start_run(NOXX, seed=3)
    for _ in range(KILLS_PER_LEVEL):
        victim = make_enemy(
            ENEMIES["ghoul"], (state.player.position[0] + 1, state.player.position[1])
        )
        victim.stats.hp = 1
        state.enemies = [victim]
        state.turn_queue = type(state.turn_queue)([state.player, victim])
        state.refresh_vision()
        for _ in range(30):
            if not victim.alive:
                break
            perform_action(state, Action.MOVE_EAST)

    assert state.kills == KILLS_PER_LEVEL
    assert state.level == 2
    assert state.player.alive
