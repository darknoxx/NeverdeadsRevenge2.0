"""The daily door: one day, one seed, one answer."""

from __future__ import annotations

import json
from types import SimpleNamespace

from neverdeads_revenge.game import daily
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.savegame import dump, load
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.persistence import MetaProgress, load_meta, save_meta


def test_the_daily_seed_is_the_date_and_not_the_process():
    first = daily.seed_for("2026-10-25")

    assert first == daily.seed_for("2026-10-25")
    assert first != daily.seed_for("2026-10-26")


def test_the_door_needs_an_escape_and_has_not_been_answered():
    progress = MetaProgress()
    assert not daily.available(progress, "2026-10-25")
    assert "answered" in daily.label(progress, "2026-10-25")

    progress.runs_won = 1
    assert daily.available(progress, "2026-10-25")
    assert "y to enter" in daily.label(progress, "2026-10-25")

    progress.daily_date = "2026-10-25"
    assert not daily.available(progress, "2026-10-25")
    assert "answered" in daily.label(progress, "2026-10-25")


def test_the_title_key_opens_the_door_in_daily_mode():
    class FakeApp:
        def __init__(self):
            self.progress = MetaProgress(runs_won=1)
            self.called = None

        def open_hero_select(self, *, tenth_door=False, daily_mode=False):
            self.called = (tenth_door, daily_mode)

    from neverdeads_revenge.desktop.screens.title import TitleScreen

    app = FakeApp()
    event = SimpleNamespace(isAutoRepeat=lambda: False)

    assert TitleScreen().key("y", event, app)
    assert app.called == (True, True)


def test_a_daily_run_carries_its_date_and_survives_a_save():
    state = start_run(
        HEROES["noxx"],
        daily.seed_for("2026-10-25"),
        tenth_door=True,
        start_depth=10,
        daily="2026-10-25",
    )

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.daily == "2026-10-25"
    assert reloaded.seed == daily.seed_for("2026-10-25")
    assert reloaded.tenth_door is True


def test_the_meta_keeps_the_day_it_answered(tmp_path):
    path = tmp_path / "meta.json"
    progress = MetaProgress(runs_won=1)
    progress.daily_date = "2026-10-25"
    save_meta(progress, path)

    loaded = load_meta(path)

    assert loaded.daily_date == "2026-10-25"
    assert not daily.available(loaded, "2026-10-25")
    assert daily.available(loaded, "2026-10-26")


def test_a_daily_run_is_marked_on_the_board():
    from neverdeads_revenge.desktop.screens.menus import ScoreboardScreen
    from neverdeads_revenge.persistence import ScoreEntry

    progress = MetaProgress()
    progress.scores = [
        ScoreEntry(
            name="ASH",
            score=1234,
            depth=10,
            hero="noxx",
            won=True,
            daily="2026-10-25",
        )
    ]
    app = SimpleNamespace(progress=progress)

    text = " ".join(line for line, _style in ScoreboardScreen().lines(app))

    assert " D" in text


def test_the_daily_marker_survives_the_meta_file(tmp_path):
    path = tmp_path / "meta.json"
    progress = MetaProgress()
    progress.record_run(
        depth=10,
        score=500,
        kills=3,
        won=True,
        name="ASH",
        hero="noxx",
        daily="2026-10-25",
    )
    save_meta(progress, path)

    loaded = load_meta(path)

    assert loaded.scores[0].daily == "2026-10-25"
