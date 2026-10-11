"""Tests for the gifts added with the status effects.

Each of the three is one rule, so each test is one sentence: a blow leaves
burning, a first blow leaves bleeding, and a twentieth step closes a point.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.game.actions import (
    SLOW_KNITTING_EVERY,
    Action,
    _resolve_player_attack,
    perform_action,
)
from neverdeads_revenge.game.actors import ENEMIES, NOXX, make_enemy
from neverdeads_revenge.game.state import start_run


def _beside(state, key: str = "ghoul"):
    """Put a monster next to the player, with health to spare."""
    enemy = make_enemy(
        ENEMIES[key], (state.player.position[0] + 1, state.player.position[1])
    )
    enemy.stats.hp = enemy.stats.max_hp = 999
    state.enemies = [enemy]
    return enemy


def _until_hit(state, enemy, key: str, tries: int = 300):
    """Swing until the status lands. The dice are the dice."""
    for _ in range(tries):
        _resolve_player_attack(state, enemy)
        if key in enemy.statuses:
            return
    pytest.fail(f"{key} never landed in {tries} swings")


def test_the_ash_mark_leaves_everything_it_hits_burning():
    state = start_run(NOXX, seed=3)
    state.gifts.add("ash_mark")
    enemy = _beside(state)

    _until_hit(state, enemy, "burn")

    assert "burn" in enemy.statuses


def test_without_the_mark_a_plain_blade_leaves_nothing():
    state = start_run(NOXX, seed=3)
    enemy = _beside(state)

    for _ in range(20):
        _resolve_player_attack(state, enemy)

    assert enemy.statuses == {}


def test_the_open_wound_bleeds_the_first_thing_it_touches():
    state = start_run(NOXX, seed=3)
    state.gifts.add("open_wound")
    enemy = _beside(state)

    _until_hit(state, enemy, "bleed")

    assert "bleed" in enemy.statuses


def test_the_slow_knitting_closes_a_point_every_twentieth_step():
    state = start_run(NOXX, seed=3)
    state.gifts.add("slow_knitting")
    state.player.stats.hp = 1

    # Walk in a direction that is open, for exactly the cadence.
    for _ in range(SLOW_KNITTING_EVERY):
        for action in (Action.MOVE_EAST, Action.MOVE_WEST, Action.MOVE_NORTH):
            before = state.player.position
            perform_action(state, action)
            if state.player.position != before:
                break

    assert state.player.hp > 1, "twenty steps closed nothing"


def test_without_the_knitting_walking_closes_nothing():
    state = start_run(NOXX, seed=3)
    state.player.stats.hp = 1

    for _ in range(SLOW_KNITTING_EVERY):
        for action in (Action.MOVE_EAST, Action.MOVE_WEST, Action.MOVE_NORTH):
            before = state.player.position
            perform_action(state, action)
            if state.player.position != before:
                break

    assert state.player.hp == 1
