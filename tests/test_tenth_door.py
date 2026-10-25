"""The Tenth Door: the mode's first slice.

The door is an *answer to a stair*, not a second dungeon. These tests hold the
three facts that make it a mode: it opens only for someone who has escaped once,
the run starts at the tenth floor with the house's credit, and the stair at a
door floor asks a question instead of descending.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.savegame import dump, load
from neverdeads_revenge.game.state import (
    CREDIT_LEVEL,
    RunState,
    start_run,
)
from neverdeads_revenge.persistence import MetaProgress
from neverdeads_revenge.world.tiles import Tile


def _begin(seed: int = 3):
    return start_run(
        HEROES["noxx"],
        seed=seed,
        tenth_door=True,
        start_depth=10,
    )


# -- the unlock -------------------------------------------------------------
def _title_items(app):
    from neverdeads_revenge.desktop.screens.title import TitleScreen

    return [key for key, _label in TitleScreen().items(app)]


def test_the_door_is_not_on_the_title_before_an_escape():
    app = SimpleNamespace(progress=MetaProgress(), has_saved_run=lambda: False)

    assert "t" not in _title_items(app)


def test_the_door_opens_after_one_escape():
    progress = MetaProgress()
    progress.runs_won = 1
    app = SimpleNamespace(progress=progress, has_saved_run=lambda: False)

    assert "t" in _title_items(app)


def test_the_title_line_opens_the_roster_in_door_mode():
    class FakeApp:
        progress = MetaProgress()
        tenth_door = False

        def has_saved_run(self):
            return False

        def open_hero_select(self, *, tenth_door=False):
            self.tenth_door = tenth_door

    app = FakeApp()
    from neverdeads_revenge.desktop.screens.title import TitleScreen

    screen = TitleScreen()
    screen._choose("t", app)

    assert app.tenth_door is True


def test_the_roster_carries_the_mode_into_the_run():
    class FakeApp:
        called = None

        def begin_run(self, key, *, tenth_door=False):
            self.called = (key, tenth_door)

    from neverdeads_revenge.desktop.screens.hero_select import HeroSelectScreen

    screen = HeroSelectScreen(tenth_door=True)
    app = FakeApp()
    screen.key("enter", SimpleNamespace(isAutoRepeat=lambda: False), app)

    assert app.called == ("noxx", True)


# -- the credit -------------------------------------------------------------
def test_the_run_starts_at_the_door_with_the_house_credit():
    state = _begin()

    assert state.depth == 10
    assert state.tenth_door is True
    assert state.level == CREDIT_LEVEL
    assert state.at_a_door
    # Three pieces, worn or carried; the loan is not a single sword.
    gear = [
        item
        for slot in ("weapon", "armour", "amulet")
        if (item := state.player.equipment.get(slot)) is not None
    ]
    assert len(gear) + len(state.inventory) >= 3


def test_the_tenth_floor_has_stairs_and_not_the_rift():
    state = _begin()

    assert state.dungeon_map.tile_at(state.exit_pos) is Tile.STAIRS_DOWN
    assert not state.at_the_rift
    assert not state.dungeon_map.find_tile(Tile.RIFT)


# -- the door ---------------------------------------------------------------
def test_stepping_onto_the_stairs_asks_the_door_question():
    state = _begin()
    state.player.position = state.exit_pos

    result = perform_action(state, Action.DESCEND)

    assert not result.escaped
    assert state.door_pending is True
    assert state.depth == 10, "the door must not descend before it is answered"


def test_pushing_on_multiplies_the_run_and_descends():
    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)

    state.continue_through_the_door()

    assert state.depth == 11
    assert state.door_pending is False
    assert state.risk_multiplier == 1.25
    assert state.door_ring == 2
    assert state.dungeon_map.tile_at(state.exit_pos) is Tile.STAIRS_DOWN


def test_banking_keeps_the_score_it_had_and_does_not_pay_the_rift_bonus():
    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    before = state.score

    state.bank()

    assert state.run_state is RunState.ESCAPED
    assert state.banked is True
    assert state.score == before, "banking must not invent a new score"


def test_the_door_fields_survive_a_save():
    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    state.continue_through_the_door()

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.tenth_door is True
    assert reloaded.door_ring == 2
    assert reloaded.risk_multiplier == 1.25
    assert reloaded.banked is False
    assert reloaded.depth == 11


def test_the_door_screen_banks_or_pushes_on():
    from neverdeads_revenge.desktop.screens.door import DoorScreen

    class FakeApp:
        def __init__(self):
            self.played = []
            self.popped = False
            self.game_over = None

        def play(self, name):
            self.played.append(name)

        def pop(self):
            self.popped = True

        def redraw(self):
            pass

        def show_game_over(self, *, won=False):
            self.game_over = won

    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    app = FakeApp()

    DoorScreen(state)._choose(1, app)

    assert state.depth == 11
    assert app.popped is True
    assert "door_creak" in app.played

    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    app = FakeApp()

    DoorScreen(state)._choose(0, app)

    assert state.banked is True
    assert app.game_over is True
    assert "door_unlock" in app.played


def test_the_summary_says_banked_and_not_escaped():
    from neverdeads_revenge.desktop.screens.game_over import _summary_lines

    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    state.bank()

    text = " ".join(line for line, _style in _summary_lines(state))

    assert "Banked at the door" in text
    assert "Out of the dark" not in text
