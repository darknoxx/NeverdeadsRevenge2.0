"""Tests for what outlives a run.

The save file is the one thing in the project that can lose a player's work, so
it gets its own file rather than a corner of ``test_game``.
"""

from __future__ import annotations

import json
from pathlib import Path

from neverdeads_revenge.persistence import (
    SCOREBOARD_SIZE,
    MetaProgress,
    ScoreEntry,
    load_meta,
    save_meta,
)


# -- the scoreboard ---------------------------------------------------------
def test_the_board_keeps_the_best_first():
    progress = MetaProgress()
    for name, score in (("AAA", 100), ("BBB", 900), ("CCC", 500)):
        progress.record_run(depth=1, score=score, kills=0, name=name)

    assert [entry.name for entry in progress.scores] == ["BBB", "CCC", "AAA"]


def test_the_board_is_capped():
    """The file is rewritten on every ending; a list that grows forever is a
    file that grows forever."""
    progress = MetaProgress()
    for score in range(SCOREBOARD_SIZE + 8):
        progress.record_run(depth=1, score=score, kills=0, name="AAA")

    assert len(progress.scores) == SCOREBOARD_SIZE
    assert progress.scores[0].score == SCOREBOARD_SIZE + 7


def test_a_worse_run_does_not_lower_the_best():
    progress = MetaProgress()
    progress.record_run(depth=1, score=900, kills=0, name="AAA")
    progress.record_run(depth=1, score=10, kills=0, name="BBB")

    assert progress.best_score == 900
    assert len(progress.scores) == 2, "a bad run is still a run worth listing"


def test_gold_is_added_and_the_score_is_kept_at_its_best():
    """Coin is a currency; a score is a record. They behave differently."""
    progress = MetaProgress()
    progress.record_run(depth=1, score=100, kills=0, gold=40, name="AAA")
    progress.record_run(depth=1, score=50, kills=0, gold=25, name="BBB")

    assert progress.gold == 65
    assert progress.best_score == 100


def test_a_run_without_a_name_is_not_listed():
    """The totals still count it -- a run that was abandoned is still a run."""
    progress = MetaProgress()
    progress.record_run(depth=3, score=200, kills=2)

    assert progress.scores == []
    assert progress.runs_started == 1
    assert progress.best_score == 200


def test_the_last_name_is_remembered():
    """So the next run costs one keypress rather than five."""
    progress = MetaProgress()
    progress.record_run(depth=1, score=1, kills=0, name="NXX")

    assert progress.last_name == "NXX"


def test_an_entry_says_how_the_run_ended():
    won = ScoreEntry(name="AAA", score=1, depth=10, hero="noxx", won=True)
    lost = ScoreEntry(name="BBB", score=1, depth=4, hero="yeti", won=False)
    assert won.outcome == "escaped"
    assert lost.outcome == "died"


# -- the file ---------------------------------------------------------------
def test_progress_round_trips_through_the_file(tmp_path: Path):
    path = tmp_path / "meta.json"
    progress = MetaProgress(gold=250)
    progress.record_run(
        depth=10, score=4200, kills=17, gold=80, won=True, name="NOXX", hero="yeti"
    )

    save_meta(progress, path)
    loaded = load_meta(path)

    assert loaded.gold == 250 + 80
    assert loaded.best_score == 4200
    assert loaded.last_name == "NOXX"
    assert len(loaded.scores) == 1
    assert loaded.scores[0].name == "NOXX"
    assert loaded.scores[0].hero == "yeti"
    assert loaded.scores[0].won is True


def test_a_save_from_an_older_build_is_kept_not_discarded(tmp_path: Path):
    """The version check used to throw the file away for a missing key.

    Which would have cost a player their high score in exchange for adding a
    coin counter -- the sort of thing that makes somebody stop trusting saves.
    """
    path = tmp_path / "meta.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "unlocked_heroes": ["noxx"],
                "upgrades": {},
                "runs_started": 4,
                "runs_won": 1,
                "best_depth": 9,
                "best_score": 12345,
                "total_kills": 40,
            }
        )
    )

    loaded = load_meta(path)

    assert loaded.best_score == 12345, "the high score was thrown away"
    assert loaded.runs_started == 4
    assert loaded.gold == 0, "a field the old file never had"
    assert loaded.scores == []
    assert loaded.last_name == ""


def test_a_corrupt_file_costs_progress_and_not_the_game(tmp_path: Path):
    path = tmp_path / "meta.json"
    path.write_text("{ this is not json")

    loaded = load_meta(path)

    assert loaded.best_score == 0
    assert loaded.gold == 0


def test_a_future_version_is_not_guessed_at(tmp_path: Path):
    """A file from a newer build is not ours to interpret."""
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"version": 99, "best_score": 99999}))

    assert load_meta(path).best_score == 0


def test_a_missing_file_is_just_a_fresh_start(tmp_path: Path):
    assert load_meta(tmp_path / "nothing-here.json").best_score == 0


# -- settings ----------------------------------------------------------------
def test_the_sound_setting_survives_the_file(tmp_path: Path):
    """A setting rather than a session flag: somebody who turns the sound off in
    a library means it for the next time too."""
    path = tmp_path / "meta.json"
    save_meta(MetaProgress(muted=True), path)

    assert load_meta(path).muted is True


def test_an_old_save_without_the_setting_means_the_sound_is_on(tmp_path: Path):
    """The default, and the least surprising thing for a file that never said."""
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"version": 1, "unlocked_heroes": ["noxx"]}))

    assert load_meta(path).muted is False


# -- the test save -----------------------------------------------------------
def test_a_test_save_fills_the_book_and_the_purse(tmp_path: Path):
    from neverdeads_revenge.game.lore import PAGE_COUNT
    from neverdeads_revenge.persistence import TEST_GOLD, grant_test_save

    path = tmp_path / "meta.json"
    save_meta(MetaProgress(gold=3), path)

    grant_test_save(path)

    loaded = load_meta(path)
    assert loaded.gold == TEST_GOLD
    assert loaded.pages == list(range(1, PAGE_COUNT + 1))


def test_a_test_save_merges_rather_than_replaces(tmp_path: Path):
    """A cheat should cost you nothing but the thing it cheats at. The
    scoreboard, the heroes and the name are not what it came for."""
    from neverdeads_revenge.persistence import grant_test_save

    path = tmp_path / "meta.json"
    progress = MetaProgress(last_name="Noxx", unlocked_heroes=["noxx", "yeti"])
    progress.record_run(depth=7, score=1234, kills=55, name="Noxx", hero="noxx")
    save_meta(progress, path)

    grant_test_save(path)

    loaded = load_meta(path)
    assert [entry.score for entry in loaded.scores] == [1234]
    assert loaded.unlocked_heroes == ["noxx", "yeti"]
    assert loaded.last_name == "Noxx"
    assert loaded.runs_started == 1


def test_a_test_save_keeps_the_file_from_before_the_first_time(tmp_path: Path):
    """Run the flag twice and the second run must not overwrite the original
    with the first test state -- there has to be one file to go back to, and it
    has to be the one from before you ever asked."""
    from neverdeads_revenge.persistence import grant_test_save

    path = tmp_path / "meta.json"
    save_meta(MetaProgress(gold=42), path)

    _, first_backup = grant_test_save(path)
    _, second_backup = grant_test_save(path)

    assert first_backup is not None
    assert second_backup is None, "the backup was overwritten by a test state"
    assert load_meta(first_backup).gold == 42


def test_a_test_save_on_a_machine_with_nothing_saved_has_nothing_to_keep(tmp_path: Path):
    from neverdeads_revenge.persistence import grant_test_save

    _, backup = grant_test_save(tmp_path / "meta.json")

    assert backup is None
    assert not (tmp_path / "meta.json.bak").exists()
