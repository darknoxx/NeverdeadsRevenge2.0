"""Tests for directions and the energy-based turn queue."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from neverdeads_revenge.core.direction import (
    CARDINALS,
    DIAGONALS,
    DIRECTIONS,
    Direction,
    chebyshev,
    direction_towards,
    manhattan,
)
from neverdeads_revenge.core.turn_queue import ENERGY_PER_TURN, TurnQueue


@dataclass
class Dummy:
    """Minimal stand-in for an actor."""

    name: str
    speed: float


# -- directions ------------------------------------------------------------
def test_there_are_eight_real_directions():
    assert len(DIRECTIONS) == 8
    assert len(CARDINALS) == 4
    assert len(DIAGONALS) == 4


def test_every_direction_has_an_opposite():
    for direction in DIRECTIONS:
        assert direction.opposite.opposite is direction
    assert Direction.NONE.opposite is Direction.NONE


def test_diagonal_detection():
    assert Direction.NORTH_EAST.is_diagonal
    assert not Direction.NORTH.is_diagonal
    assert not Direction.NONE.is_diagonal


def test_rotate_cycles_clockwise():
    # One turn is 90 degrees, so the compass is stepped in 45 degree increments.
    assert Direction.NORTH.rotate(1) is Direction.EAST
    assert Direction.NORTH.rotate(2) is Direction.SOUTH
    assert Direction.NORTH.rotate(4) is Direction.NORTH
    assert Direction.NORTH.rotate(-1) is Direction.WEST
    assert Direction.NONE.rotate(1) is Direction.NONE


def test_rotate_is_invertible():
    for direction in DIRECTIONS:
        for turns in range(-4, 5):
            assert direction.rotate(turns).rotate(-turns) is direction


def test_step_moves_position():
    assert Direction.NORTH.step((5, 5)) == (5, 4)
    assert Direction.SOUTH_WEST.step((5, 5)) == (4, 6)
    assert Direction.NONE.step((5, 5)) == (5, 5)


def test_distances():
    assert chebyshev((0, 0), (3, 4)) == 4
    assert manhattan((0, 0), (3, 4)) == 7
    assert chebyshev((2, 2), (2, 2)) == 0


def test_direction_towards():
    assert direction_towards((0, 0), (0, -5)) is Direction.NORTH
    assert direction_towards((0, 0), (5, 5)) is Direction.SOUTH_EAST
    assert direction_towards((3, 3), (3, 3)) is Direction.NONE


# -- turn queue ------------------------------------------------------------
def test_interval_is_inverse_to_speed():
    assert TurnQueue.interval(Dummy("noxx", 1.5)) == pytest.approx(ENERGY_PER_TURN / 1.5)
    assert TurnQueue.interval(Dummy("ghoul", 0.7)) == pytest.approx(ENERGY_PER_TURN / 0.7)


def test_non_positive_speed_rejected():
    with pytest.raises(ValueError):
        TurnQueue.interval(Dummy("dead", 0.0))
    with pytest.raises(ValueError):
        TurnQueue.interval(Dummy("dead", -1.0))


def test_empty_queue_pops_none():
    assert TurnQueue().pop() is None


def test_fast_actor_acts_more_often():
    """The whole point of the game: speed turns into action count."""
    noxx = Dummy("noxx", 1.5)
    ghoul = Dummy("ghoul", 0.7)
    queue = TurnQueue([noxx, ghoul])

    order = queue.take(200)
    assert order.count(noxx) > order.count(ghoul) * 2
    # 1.5 / 0.7 = 2.14, so allow some slack but not too much.
    ratio = order.count(noxx) / order.count(ghoul)
    assert 2.0 < ratio < 2.3


def test_equal_speed_alternates_evenly():
    a, b = Dummy("a", 1.0), Dummy("b", 1.0)
    order = TurnQueue([a, b]).take(100)
    assert order.count(a) == order.count(b) == 50
    assert order[0] is a and order[1] is b  # insertion order breaks ties


def test_speed_one_is_exactly_one_action_per_100_energy():
    a = Dummy("a", 1.0)
    queue = TurnQueue([a])
    for _ in range(5):
        queue.pop()
    assert queue.clock == pytest.approx(500.0)


def test_clock_monotonically_advances():
    queue = TurnQueue([Dummy("a", 0.3), Dummy("b", 2.0)])
    clocks = []
    for _ in range(50):
        queue.pop()
        clocks.append(queue.clock)
    assert clocks == sorted(clocks)


def test_remove_stops_future_turns():
    doomed = Dummy("doomed", 1.0)
    other = Dummy("other", 1.0)
    queue = TurnQueue([doomed, other])

    assert queue.remove(doomed)
    assert doomed not in queue
    assert not queue.remove(doomed)  # second removal is a no-op

    assert doomed not in queue.take(50)


def test_add_schedules_relative_to_now():
    """A latecomer is scheduled from the current clock, not from time zero."""
    first = Dummy("first", 1.0)
    latecomer = Dummy("late", 0.5)
    queue = TurnQueue([first])

    queue.take(3)
    assert queue.clock == pytest.approx(300.0)

    # Scheduled while the clock stands at 300: due at 300 + 200 = 500.
    # If it were wrongly scheduled from zero it would be due at 200 and go first.
    queue.add(latecomer)
    assert queue.pop() is first  # first is due at 400
    assert queue.pop() is latecomer  # ...so latecomer follows at 500
    assert queue.clock == pytest.approx(500.0)


def test_insertion_order_breaks_ties():
    """Two actors due at the same time act in the order they were added."""
    first = Dummy("first", 1.0)
    second = Dummy("second", 1.0)
    queue = TurnQueue([first, second])
    assert [a.name for a in queue.take(4)] == ["first", "second", "first", "second"]


def test_snapshot_restore_reproduces_order():
    def build():
        actors = [Dummy(f"a{i}", 0.5 + i * 0.25) for i in range(6)]
        return actors, TurnQueue(actors)

    actors, queue = build()
    queue.take(13)
    snapshot = queue.snapshot()
    expected = [a.name for a in queue.take(30)]

    queue.restore(snapshot)
    assert [a.name for a in queue.take(30)] == expected


def test_no_drift_over_long_run():
    """Fast actors must keep their exact ratio over thousands of turns."""
    noxx, ghoul = Dummy("noxx", 1.5), Dummy("ghoul", 0.7)
    order = TurnQueue([noxx, ghoul]).take(20000)
    ratio = order.count(noxx) / order.count(ghoul)
    assert ratio == pytest.approx(1.5 / 0.7, rel=0.01)
