"""Tests for the menus and dialogs.

They drive the app the way a player does -- a key at a time, through the real
stack -- because that is the part that can go wrong: a screen that never opens,
a key that two screens both think they own, a dialog that answers its own
opening press.
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from neverdeads_revenge.game.state import RunState  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def app(qapp):
    from neverdeads_revenge.desktop.app import DesktopApp

    window = DesktopApp(seed=3, no_sound=True)
    window.view.resize(1280, 800)
    window.redraw()
    return window


def press(window, key, text: str = "", repeat: bool = False) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)
    event.isAutoRepeat = lambda: repeat
    window._on_key(event)


def top(window) -> str:
    return type(window.screens[-1]).__name__


# -- the title ----------------------------------------------------------------
def test_the_title_offers_a_run_and_a_shop(app):
    from neverdeads_revenge.desktop.screens.title import TitleScreen

    keys = [key for key, _ in TitleScreen().items(app)]
    assert keys[0] == "n"
    assert "s" in keys and "q" in keys


def test_new_run_asks_for_a_hero(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)

    assert top(app) == "HeroSelectScreen"


def test_the_shop_opens_from_its_own_letter(app):
    from PySide6.QtCore import Qt

    app.progress.gold = 100
    press(app, Qt.Key.Key_S, "s")

    assert top(app) == "ShopScreen"


def test_a_run_starts_when_the_hero_is_confirmed(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)  # new run
    press(app, Qt.Key.Key_Return)  # confirm the hero

    assert top(app) == "GameScreen"
    assert app.run is not None and app.run.depth == 1


# -- the dialogs --------------------------------------------------------------
def test_a_confirm_answers_yes_and_no(app):
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.dialogs import ConfirmScreen

    answers = []
    app.push(ConfirmScreen("QUIT?", "sure?", on_done=answers.append))

    press(app, Qt.Key.Key_N, "n")
    assert answers == [False]
    assert top(app) != "ConfirmScreen"

    app.push(ConfirmScreen("QUIT?", "sure?", on_done=answers.append))
    press(app, Qt.Key.Key_Y, "y")
    assert answers == [False, True]


def test_escape_answers_a_confirm_with_no(app):
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.dialogs import ConfirmScreen

    answers = []
    app.push(ConfirmScreen("QUIT?", "sure?", on_done=answers.append))
    press(app, Qt.Key.Key_Escape)

    assert answers == [False]


def test_a_dialog_ignores_a_held_key(app):
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.dialogs import ConfirmScreen

    answers = []
    app.push(ConfirmScreen("QUIT?", "sure?", on_done=answers.append))
    press(app, Qt.Key.Key_Y, "y", repeat=True)

    assert answers == [], "a held key answered the question"


def test_the_chest_has_three_answers(app):
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.dialogs import OPEN, ChestScreen

    answers = []
    app.push(ChestScreen("The price: DIM.", on_done=answers.append))
    press(app, Qt.Key.Key_Return)

    assert answers == [OPEN]


def test_a_page_scrolls_and_then_closes(app):
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.dialogs import PageScreen

    app.push(PageScreen(1, "line\n" * 60))
    page = app.screens[-1]
    press(app, Qt.Key.Key_Down, "")
    press(app, Qt.Key.Key_Down, "")
    assert page.offset == 2

    press(app, Qt.Key.Key_Space)
    assert top(app) != "PageScreen"


# -- the run's own screens ----------------------------------------------------
def test_the_character_sheet_and_the_pack_open(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)  # into the run

    press(app, Qt.Key.Key_C, "c")
    assert top(app) == "CharacterScreen"
    press(app, Qt.Key.Key_Escape)

    press(app, Qt.Key.Key_I, "i")
    assert top(app) == "PackScreen"


def test_escape_in_the_dungeon_pauses(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Escape)

    assert top(app) == "PauseScreen"


def test_the_pause_menu_toggles_the_sound(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Escape)
    before = app.sfx.muted

    press(app, Qt.Key.Key_M, "m")

    assert app.sfx.muted is not before


def test_the_pause_asks_before_quitting_to_the_title(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Escape)
    press(app, Qt.Key.Key_Q, "q")

    assert top(app) == "ConfirmScreen"
    assert app.run is not None, "the run was thrown away before the question"


def test_the_summary_takes_a_hold_and_the_name_goes_on_the_board(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    game = app.screens[-1]
    game.state.kills = 4
    game._game_over(app, won=False)
    assert top(app) == "GameOverScreen"

    for _ in range(3):
        press(app, Qt.Key.Key_Return)
        time.sleep(0.3)

    assert top(app) == "NameEntryScreen"
    press(app, Qt.Key.Key_N, "N")
    press(app, Qt.Key.Key_X, "X")
    press(app, Qt.Key.Key_Return)

    assert top(app) == "TitleScreen"
    assert app.progress.scores[-1].name == "NX"


def test_a_run_that_escaped_is_recorded_as_won(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    game = app.screens[-1]
    game.state.run_state = RunState.ESCAPED
    game._game_over(app, won=True)

    assert top(app) == "GameOverScreen"
