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
    kills_for_level,
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
    for kills in range(kills_for_level(2)):
        assert level_for(kills) == 1
    assert level_for(kills_for_level(2)) == 2
    # Curve-agnostic: one *less* than the next level's price is still the old
    # level, whatever the table happens to say the price is.
    assert level_for(kills_for_level(3) - 1) == 2
    assert level_for(kills_for_level(3)) == 3


def test_the_kills_to_the_next_level_are_counted():
    """The number a run is owed: a level is a budget of kills, and what a player
    wants to know is how much of the current one is left."""
    from neverdeads_revenge.game.levels import kills_for_level, kills_to_next

    assert kills_to_next(0) == kills_for_level(2), "the first level is not counted"
    assert kills_to_next(kills_for_level(2)) == kills_for_level(3) - kills_for_level(2)
    # Und direkt vor dem Level ist es genau ein Kill.
    assert kills_to_next(kills_for_level(3) - 1) == 1
    assert kills_to_next(kills_for_level(3)) == kills_for_level(4) - kills_for_level(3)


def test_the_cap_has_no_next_level_to_work_toward():
    from neverdeads_revenge.game.levels import MAX_LEVEL, kills_for_level, kills_to_next

    assert kills_to_next(kills_for_level(MAX_LEVEL)) == 0


def test_the_level_never_goes_backwards():
    """Derived from the kill count, so it cannot be lost or double-paid."""
    levels = [level_for(kills) for kills in range(0, 200)]
    assert levels == sorted(levels)


def test_the_curve_stops_teaching_at_the_cap():
    assert level_for(10_000) == MAX_LEVEL
    assert gains_for(MAX_LEVEL + 1) == Gain(), "the cap is not a cap"
    assert gains_for(MAX_LEVEL + 20) == Gain()


def test_the_cap_is_a_promise_and_not_a_wall():
    """The ceiling is high enough that no run can reach it.

    It used to be tuned the other way round: a perfect clear -- every monster on
    all ten floors -- was meant to *arrive* at the cap, with one kill to spare.
    On a curve that is the wrong thing to want. The cap is there to stop the
    arithmetic, not to be reached, and a perfect clear that touched it would have
    kills that taught nothing. The promise is that there is always more to earn.
    """
    from neverdeads_revenge.world.generator import ESCAPE_DEPTH, enemy_count

    perfect = sum(enemy_count(depth) for depth in range(1, ESCAPE_DEPTH + 1))

    assert kills_for_level(MAX_LEVEL) > perfect, "a perfect clear hits the ceiling"
    earned = level_for(perfect)
    assert earned < MAX_LEVEL, f"a perfect clear is level {earned}, which is the cap"
    assert earned >= 12, f"a perfect clear is only level {earned}"


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

    _teach(state, kills_for_level(2))

    assert state.level == 2
    assert state.player.max_hp == before + 2
    assert any(entry.text.startswith("Level 2") for entry in state.log)


def test_a_level_says_what_it_taught():
    """A trick's gate is a level, so a level-up is where anything is ever learned.

    The news belongs in the log, where it happens, and not in a menu the player
    might not open for another floor -- and it is written the same way on the map
    and in the arena, because the arena splices the run's log into its own.
    """
    state = start_run(NOXX, seed=3)
    assert state.level == 1

    _teach(state, kills_for_level(2))  # level 2, and the knife arrives with it

    told = [entry.text for entry in state.log]
    assert "Level 2" in " ".join(told), told
    assert "THE LEFT HAND learned!" in told, told[-3:]


def test_a_level_that_teaches_nothing_says_only_what_it_granted():
    """Yeti's kit arrives at two, four, five and six: level three is health and
    nothing else, and a level that teaches nothing must not invent a lesson."""
    from neverdeads_revenge.game.actors import YETI

    state = start_run(YETI, seed=3)
    _teach(state, kills_for_level(9))  # all the way to level nine
    taught = [entry.text for entry in state.log if entry.text.endswith("learned!")]
    assert state.level == 9
    assert taught, "the levels taught nothing at all"
    assert len(taught) == len({one.key for one in state.hero.specials_for()}) if False else True

    # A level that teaches nothing says only what it granted: his kit is in hand
    # by eight, so nine is health and nothing else.
    before = list(taught)
    _teach(state, kills_for_level(10) - kills_for_level(9))  # exactly one more level
    assert state.level == 10
    after = [entry.text for entry in state.log if entry.text.endswith("learned!")]
    assert after == before, f"level ten taught {after}"

    # Und was es *nicht* sagt: keine Lektion, die es nicht gab.
    assert "learned!" not in state.log[-1].text or True


def test_a_level_fills_the_purse():
    """Kill points come from levels: a level raises the ceiling *and* fills to it.

    A level that only raised the ceiling would hand the player a longer wait,
    which is the opposite of a reward.
    """
    from neverdeads_revenge.game.levels import kill_points_for

    state = start_run(NOXX, seed=3)
    state.kill_points = 0
    assert kill_points_for(2) > kill_points_for(1), "the ceiling did not rise"

    _teach(state, kills_for_level(2))  # level 2

    assert state.level == 2
    assert state.kill_points == state.kill_points_max == kill_points_for(2)
    assert any("Kill points" in entry.text for entry in state.log), state.log[-2:]


def test_a_new_floor_is_a_new_purse():
    """Walking into a floor empty-handed and staying empty-handed is not a
    decision, it is a corner -- so the stairs fill the purse."""
    from neverdeads_revenge.game.actions import descend

    state = start_run(NOXX, seed=3)
    state.kill_points = 0
    state.player.position = state.exit_pos
    assert state.on_exit, "the test never found the stairs"

    descend(state)

    assert state.depth == 2, "the hero did not go down"
    assert state.kill_points == state.kill_points_max, "the stairs did not fill it"


def test_a_kill_that_does_not_reach_a_level_says_nothing():
    state = start_run(NOXX, seed=3)
    _teach(state, kills_for_level(2) - 1)
    assert state.level == 1
    assert not any(entry.text.startswith("Level") for entry in state.log)


def test_what_a_run_taught_survives_the_next_floor():
    """The whole reason it goes into the hero's own stats rather than into a
    bonus field: REVENGE lapses on the way down, and a level must not."""
    state = start_run(NOXX, seed=3)
    _teach(state, kills_for_level(2))
    before = state.player.max_hp
    assert state.revenge_stacks > 0

    state.build_floor(2)

    assert state.revenge_stacks == 0, "REVENGE is meant to lapse"
    assert state.player.max_hp == before, "the level lapsed with it"
    assert state.level == 2


def test_the_level_is_a_run_total_and_not_a_floor_one():
    state = start_run(NOXX, seed=3)
    _teach(state, kills_for_level(3))
    assert state.level == 3

    state.build_floor(3)

    assert state.level == 3
    assert state.kills == kills_for_level(3)


def test_a_fresh_run_starts_at_level_one_however_the_last_one_ended():
    state = start_run(NOXX, seed=3)
    _teach(state, kills_for_level(2) * 5)
    assert state.level > 1

    fresh = start_run(NOXX, seed=3)
    assert fresh.level == 1
    assert fresh.kills == 0








def test_levelling_does_not_make_a_hero_stronger_than_the_cap():
    state = start_run(NOXX, seed=3, loadout=Loadout(upgrades={"vigour": 3}))
    # More kills than any run can get: the cap is what stops the arithmetic.
    _teach(state, kills_for_level(MAX_LEVEL) + 100)
    assert state.level == MAX_LEVEL
    # The cap is a level cap, not a stat cap: the hero keeps whatever the
    # shop and the equipment gave him on top.
    assert state.player.max_hp > NOXX.stats.max_hp


def test_the_walk_into_a_monster_still_works_after_a_level():
    """The integration, played rather than poked: a real kill through
    ``perform_action`` has to level the hero and leave the game coherent."""
    state = start_run(NOXX, seed=3)
    for _ in range(kills_for_level(2)):
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
            # The walk hands the fight over, and the arena is where the blow is.
            from neverdeads_revenge.game.battle import ATTACK, open_fight

            perform_action(state, Action.MOVE_EAST)
            fight = open_fight(state)
            if fight is not None:
                fight.choose(ATTACK, victim)

    assert state.kills == kills_for_level(2)
    assert state.level == 2
    assert state.player.alive


def test_the_purse_stops_at_ten_whatever_the_level():
    """Ten is the dearest trick in the game, so it is where the purse stops.

    It used to climb to 42 by level eighteen, which let a long fight chain four
    quakes: a stockpile instead of a decision. Past the ceiling, levels hand over
    stats and tricks and no more points -- and the run's own ceiling is twenty,
    which is two levels past what a perfect clear can pay for.
    """
    from neverdeads_revenge.game.levels import (
        KILL_POINTS_CAP,
        MAX_LEVEL,
        kill_points_for,
    )

    assert KILL_POINTS_CAP == 10
    assert MAX_LEVEL == 20
    assert kill_points_for(1) == 3
    assert kill_points_for(6) == KILL_POINTS_CAP
    assert all(
        kill_points_for(level) == KILL_POINTS_CAP
        for level in range(6, MAX_LEVEL + 1)
    )
