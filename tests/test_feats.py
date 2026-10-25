"""Feats: what a finished run proves, and the page that remembers it."""

from __future__ import annotations

from types import SimpleNamespace

from neverdeads_revenge.game import feats
from neverdeads_revenge.game.actions import _on_death
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.persistence import MetaProgress, load_meta, save_meta


def _state(**kwargs):
    return start_run(
        HEROES["noxx"],
        kwargs.pop("seed", 3),
        tenth_door=kwargs.pop("tenth_door", False),
        start_depth=kwargs.pop("start_depth", 1),
        **kwargs,
    )


def test_every_feat_has_one_key_and_a_sentence():
    keys = [feat.key for feat in feats.FEATS]

    assert len(keys) == len(set(keys))
    assert feats.FEAT_BY_KEY.keys() == set(keys)
    assert all(feat.name and feat.blurb for feat in feats.FEATS)


def test_a_finished_run_proves_the_first_blood_and_the_door():
    progress = MetaProgress(runs_won=1, runs_started=1)
    state = _state(tenth_door=True, start_depth=10, daily="2026-10-25")

    found = feats.earned(state, progress)

    assert "first_blood" in found
    assert "escaped" in found
    assert "door_opened" in found
    assert "daily" in found


def test_the_keeper_and_the_bank_are_proved_only_by_the_run_that_did_it():
    state = _state(tenth_door=True, start_depth=15)
    progress = MetaProgress(runs_started=1)
    state.wardens_slain = 1
    state.banked = True
    state.door_ring = 2
    state.depth = 20

    found = feats.earned(state, progress)

    assert {"keeper", "banked", "second_ring", "deep_twenty"} <= set(found)


def test_award_writes_each_feat_once_and_sorts_the_book():
    progress = MetaProgress(runs_started=1, runs_won=1)
    state = _state()

    first = feats.award(progress, state)
    second = feats.award(progress, state)

    assert "first_blood" in first
    assert "escaped" in first
    assert second == []
    assert progress.feats == sorted(progress.feats)


def test_feats_outlive_the_run(tmp_path):
    path = tmp_path / "meta.json"
    progress = MetaProgress(feats=["first_blood", "daily"])
    save_meta(progress, path)

    assert load_meta(path).feats == ["first_blood", "daily"]


def test_the_warden_is_counted_when_it_dies():
    state = _state(tenth_door=True, start_depth=15)
    state.build_floor(15)
    warden = next(enemy for enemy in state.enemies if enemy.warden)

    _on_death(state, warden)

    assert state.wardens_slain == 1


def test_the_almanac_marks_what_is_earned_and_leaves_the_rest_open():
    from neverdeads_revenge.desktop.screens.almanac import AlmanacScreen

    progress = MetaProgress(feats=["first_blood"])
    app = SimpleNamespace(progress=progress)

    text = " ".join(
        line for line, _style in AlmanacScreen(tab=4).feats_lines(app, 60)
    )

    assert "[x] FIRST BLOOD" in text
    assert "[ ] OUT OF THE DARK" in text
    assert "Finish a run" in text
