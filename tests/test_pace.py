"""Tests for how fast a held direction acts.

Not a game rule -- the turn queue decides who acts how often and a tap is never
throttled -- so this is the one place a hero's speed is felt under the finger
rather than read off a number. Which is why it is worth having and worth
showing, and why it gets its own file.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.game.actors import HEROES, NOXX, WALKYRION, YETI
from neverdeads_revenge.game.pace import (
    ACTIONS_PER_SECOND,
    MAX_ACTIONS_PER_SECOND,
    MIN_ACTIONS_PER_SECOND,
    action_gap,
    actions_per_second,
)


def test_six_a_second_is_a_hero_of_speed_one():
    assert actions_per_second(1.0) == pytest.approx(ACTIONS_PER_SECOND)


def test_a_faster_hero_acts_faster():
    """The one place speed is felt rather than read."""
    noxx = actions_per_second(NOXX.stats.speed)
    walk = actions_per_second(WALKYRION.stats.speed)
    yeti = actions_per_second(YETI.stats.speed)

    assert noxx > walk > yeti


def test_every_hero_starts_under_the_ceiling():
    """The ceiling exists so that speed bought later has somewhere to go. A hero
    who started at it would have nothing left to buy."""
    for hero in HEROES.values():
        assert actions_per_second(hero.stats.speed) < MAX_ACTIONS_PER_SECOND, hero.key


def test_the_ceiling_is_high_enough_to_be_worth_reaching():
    """It was eight, and Noxx starts at nine -- so the hero whose whole identity
    is speed was the one hero the ceiling was flattening."""
    assert MAX_ACTIONS_PER_SECOND > 1.5 * ACTIONS_PER_SECOND
    assert actions_per_second(NOXX.stats.speed) < MAX_ACTIONS_PER_SECOND


def test_the_rate_is_capped():
    assert actions_per_second(99.0) == pytest.approx(MAX_ACTIONS_PER_SECOND)
    assert actions_per_second(1e6) == pytest.approx(MAX_ACTIONS_PER_SECOND)


def test_the_rate_is_floored():
    """A hero heavy enough to be slow should be heavy, not unusable."""
    assert actions_per_second(0.01) == pytest.approx(MIN_ACTIONS_PER_SECOND)
    assert actions_per_second(0.0) == pytest.approx(MIN_ACTIONS_PER_SECOND)


def test_a_negative_speed_does_not_invert_the_curve():
    """A curse or a heavy blade could in principle take a hero below zero, and a
    negative rate would be a negative gap, which is a throttle that lets
    everything through."""
    assert actions_per_second(-5.0) == pytest.approx(MIN_ACTIONS_PER_SECOND)


def test_the_gap_is_the_inverse_of_the_rate():
    for speed in (0.5, 1.0, 1.5, 3.0):
        assert action_gap(speed) == pytest.approx(1.0 / actions_per_second(speed))


def test_bought_speed_has_somewhere_to_go():
    """Speed from equipment and upgrades raises the rate until the ceiling, which
    is the whole reason the ceiling moved."""
    base = actions_per_second(NOXX.stats.speed)
    kitted = actions_per_second(NOXX.stats.speed + 0.45)

    assert kitted > base
    assert kitted <= MAX_ACTIONS_PER_SECOND
