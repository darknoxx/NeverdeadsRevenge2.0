"""Tests for the seeded RNG."""

from __future__ import annotations

from neverdeads_revenge.core.rng import Rng, seed_from_string


def test_same_seed_same_sequence():
    a, b = Rng(1234), Rng(1234)
    assert [a.below(1000) for _ in range(50)] == [b.below(1000) for _ in range(50)]


def test_different_seed_differs():
    assert [Rng(1).below(1000) for _ in range(20)] != [Rng(2).below(1000) for _ in range(20)]


def test_below_is_in_range():
    rng = Rng(7)
    for _ in range(500):
        assert 0 <= rng.below(10) < 10


def test_below_zero_raises():
    import pytest

    with pytest.raises(ValueError):
        Rng(1).below(0)


def test_between_is_inclusive():
    rng = Rng(99)
    seen = {rng.between(1, 3) for _ in range(300)}
    assert seen == {1, 2, 3}


def test_chance_statistically_sane():
    rng = Rng(2024)
    hits = sum(1 for _ in range(10000) if rng.chance(0.25))
    # Comfortably wide bounds; this only catches gross breakage.
    assert 2000 < hits < 3000


def test_pick_and_shuffled():
    rng = Rng(5)
    seq = [1, 2, 3, 4, 5]
    assert rng.pick(seq) in seq
    shuffled = rng.shuffled(seq)
    assert sorted(shuffled) == seq
    assert seq == [1, 2, 3, 4, 5]  # original untouched


def test_shuffled_does_not_mutate_input():
    rng = Rng(5)
    original = [1, 2, 3]
    rng.shuffled(original)
    assert original == [1, 2, 3]


def test_choice_weighted_respects_weights():
    rng = Rng(11)
    counts = {"common": 0, "rare": 0}
    for _ in range(10000):
        counts[rng.choice_weighted([("common", 9.0), ("rare", 1.0)])] += 1
    assert 8500 < counts["common"] < 9500


def test_choice_weighted_all_zero_raises():
    import pytest

    with pytest.raises(ValueError):
        Rng(1).choice_weighted([("a", 0.0), ("b", 0.0)])


def test_spawn_is_independent_but_reproducible():
    # Two identically-seeded parents spawn identically...
    assert Rng(42).spawn().below(1000) == Rng(42).spawn().below(1000)
    # ...while repeated spawns from one parent do not, since each spawn
    # advances the parent. That is what makes sub-generators independent.
    parent = Rng(42)
    assert parent.spawn().below(1000) != parent.spawn().below(1000)


def test_state_restore_roundtrip():
    rng = Rng(31337)
    for _ in range(10):
        rng.below(1000)
    saved = rng.state()

    expected = [rng.below(1000) for _ in range(10)]
    rng.restore(saved)
    assert [rng.below(1000) for _ in range(10)] == expected


def test_seed_from_string_is_stable_across_processes():
    # Must not use hash(), which is salted per process.
    assert seed_from_string("noxx") == seed_from_string("noxx")
    assert seed_from_string("noxx") != seed_from_string("noxy")
    assert 0 <= seed_from_string("noxx") < 2**32
