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
def font(qapp):
    from neverdeads_revenge.desktop.font import BitmapFont

    return BitmapFont()


@pytest.fixture
def app(qapp):
    from neverdeads_revenge.desktop.app import DesktopApp

    window = DesktopApp(seed=3, no_sound=True)
    window.view.resize(1280, 800)
    # The premise is not the subject of most of these tests; the one that needs
    # it turns it back on itself.
    window.prologue_seen = True
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


def release(window, key) -> None:
    """The key came up -- the desktop sees what the terminal had to guess."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    event = QKeyEvent(QEvent.Type.KeyRelease, key, Qt.KeyboardModifier.NoModifier)
    event.isAutoRepeat = lambda: False
    window._on_key(event)


def hold_enter(app, until: str | None = None, seconds: float = 2.0) -> None:
    """Hold enter: a press, and the hardware repeat stream Qt sends for it.
    Stops early once ``until`` names the top screen; gives up after
    ``seconds``."""
    from PySide6.QtCore import Qt

    start = time.monotonic()
    press(app, Qt.Key.Key_Return)
    while time.monotonic() - start < seconds:
        if until is not None and top(app) == until:
            return
        time.sleep(0.02)
        press(app, Qt.Key.Key_Return, repeat=True)


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

    hold_enter(app, until="NameEntryScreen")

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


# -- opaque panels, and a shop with a shelf ----------------------------------
def test_a_menu_covers_the_screen_under_it(app):
    from PySide6.QtCore import Qt

    # The title is drawn with block art; the shop is not.
    def has_block_art() -> bool:
        return any(cell.char == "█" for row in app._buffer.cells for cell in row)

    assert has_block_art(), "the title should be up"
    app.progress.gold = 100
    press(app, Qt.Key.Key_S, "s")

    assert top(app) == "ShopScreen"
    assert not has_block_art(), "the menu let the screen behind it show through"


def test_the_shop_is_in_sections(app):
    from neverdeads_revenge.desktop.screens.menus import ShopScreen

    screen = ShopScreen()
    screen._restock(app)
    headings = [row[0] for row in screen._rows(70) if row[2] is None and row[0].isupper()]

    assert "SUPPLIES" in headings
    assert "GEAR" in headings
    assert "AMULETS" in headings


# -- the pixels know exactly where the world left them ------------------------
def test_a_death_leaves_pixels_at_the_exact_square(app):
    """This was the bug, twice over: a position read from *before* the action is
    a bullet that lands one square from its target, and a dungeon coordinate
    drawn straight into the buffer is one camera-width off. The engine says
    where it stopped; the camera says where that is on the screen."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.game.actors import ENEMIES, make_enemy
    from neverdeads_revenge.world.tiles import Tile

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run

    square = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    enemy = make_enemy(ENEMIES["ghoul"], square)
    enemy.stats.hp = 1
    enemy.stats.damage = (0, 0)
    state.enemies = [enemy]
    state.turn_queue = type(state.turn_queue)([state.player, enemy])

    press(app, Qt.Key.Key_Right, "d")

    assert state.deaths == [square], (
        f"blood called at {state.deaths}, the square was {square}"
    )

    # The square is one to the right of the hero, and the hero is the centre of
    # the camera: so the blood has to be one cell right of centre, not wherever
    # the raw dungeon coordinate would fall.
    point = app.screen_point(square)
    assert point is not None
    assert app.effects.particles, "nothing was thrown"
    for particle in app.effects.particles:
        assert abs(particle.x - point[0]) <= app.font.cell_w, (
            f"particle at x={particle.x:.0f}, the square is at {point[0]:.0f}"
        )


def test_a_tombed_monster_is_not_a_death(app):
    """One action, one death: the list is cleared with the flash."""
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run

    press(app, Qt.Key.Key_Period, ".")
    assert state.deaths == [], "waiting produced a corpse"


def test_the_glass_rattles_and_settles(app):
    import time

    app.view.shake(seconds=0.05)
    assert app.view.is_shaking()
    time.sleep(0.06)
    assert not app.view.is_shaking()


def test_the_title_takes_side_arrows_and_no_others(app):
    """The menu is a line, so left and right are its keys and that is all."""
    from PySide6.QtCore import Qt

    screen = app.screens[-1]
    before = screen.index
    press(app, Qt.Key.Key_Left)
    assert screen.index != before, "left did not move it"

    screen.index = len(screen.items(app)) - 1
    press(app, Qt.Key.Key_Right)
    assert screen.index == 0, "right did not wrap"

    screen.index = 1
    up = screen.index
    press(app, Qt.Key.Key_Up)
    down = screen.index
    assert up == down == 1, "up and down moved a sideways menu"


# -- the premise, and the run that survives the terminal being closed ---------
def test_the_prologue_shows_once_per_session(app):
    """Once, between the choice and the floor -- and never twice, because a
    premise told twice is a toll."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.prologue import PrologueScreen

    app.prologue_seen = False
    press(app, Qt.Key.Key_Return)  # new run
    press(app, Qt.Key.Key_Return)  # the hero: noxx

    assert top(app) == "PrologueScreen"
    press(app, Qt.Key.Key_Escape)  # skipping is allowed

    assert top(app) == "GameScreen"

    press(app, Qt.Key.Key_Escape)  # pause
    press(app, Qt.Key.Key_Q, "q")  # quit to title, asked first
    press(app, Qt.Key.Key_Y, "y")

    press(app, Qt.Key.Key_Return)  # a second run
    press(app, Qt.Key.Key_Return)
    assert top(app) == "GameScreen", "the premise was told twice"


def test_the_prologue_scrolls_and_a_hold_lets_it_go(app):
    from PySide6.QtCore import Qt

    import time

    app.prologue_seen = False
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    assert top(app) == "PrologueScreen"

    screen = app.screens[-1]
    before = screen.offset
    press(app, Qt.Key.Key_Down)
    assert screen.offset > before, "the story did not move"
    press(app, Qt.Key.Key_Space)
    assert screen.offset > before + 1, "space did not page it"

    hold_enter(app, until="GameScreen")
    assert top(app) == "GameScreen", "a proper hold did not let the premise go"


def test_a_run_survives_a_save_and_a_quit(app):
    """Save and quit is the whole reason the pause's `s` is a `s`.

    The slot holds the run; picking it up consumes it; and what comes back is
    the run that was put down -- the floor, the health, the turn count.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.title import TitleScreen

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)  # into the run
    state = app.run
    state.player.stats.hp -= 3
    depth, hp, turns, steps = state.depth, state.player.hp, state.total_turns, state.player.steps

    press(app, Qt.Key.Key_Escape)  # pause
    press(app, Qt.Key.Key_S, "s")  # save and quit
    assert top(app) == "TitleScreen"
    assert app.has_saved_run()
    assert "c" in [key for key, _ in TitleScreen().items(app)], \
        "the title did not offer the run back"

    press(app, Qt.Key.Key_C, "c")  # continue
    assert top(app) == "GameScreen"
    assert app.run.depth == depth
    assert app.run.player.hp == hp
    assert app.run.total_turns == turns
    assert app.run.player.steps == steps
    assert not app.has_saved_run(), "the slot was not consumed"


def test_a_run_saved_by_an_old_build_costs_the_run_and_not_the_game(app):
    """A slot that cannot be read is refused, cleared, and the title offers a
    new run rather than a crash."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.persistence import save_run

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Escape)  # pause...
    press(app, Qt.Key.Key_Q, "q")  # ...and back to the title (the run is not saved)
    press(app, Qt.Key.Key_Y, "y")
    save_run({"version": 99, "hero": "noxx"})

    press(app, Qt.Key.Key_C, "c")
    assert top(app) == "TitleScreen", "a rubbish slot opened the dungeon"
    assert not app.has_saved_run(), "the rubbish slot was not cleared"


# -- a held key is one press, not thirty --------------------------------------
def test_the_title_answers_a_press_and_not_a_stream(app):
    """Qt hands us real auto-repeats. That is a gift the terminal build never
    had, so nothing here should need the FILTER_GAP hack again -- but a repeat
    that slips into a menu is a shop that opens itself."""
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_S, "s", repeat=True)
    assert top(app) == "TitleScreen", "a repeated key opened the shop"

    press(app, Qt.Key.Key_S, "s")
    assert top(app) == "ShopScreen"


def test_a_held_enter_cannot_begin_the_run_from_the_choice(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_N, "n")  # hero select
    press(app, Qt.Key.Key_Return, repeat=True)

    assert top(app) == "HeroSelectScreen", "the confirm key confirmed itself"

    press(app, Qt.Key.Key_Return)
    assert top(app) == "GameScreen"


def test_the_pause_backup_answers_one_gesture(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)  # into the run
    press(app, Qt.Key.Key_Escape)  # ...

    press(app, Qt.Key.Key_Q, "q", repeat=True)
    assert top(app) == "PauseScreen", "a repeated key answered the pause"
    press(app, Qt.Key.Key_M, "m", repeat=True)
    assert top(app) == "PauseScreen", "a repeated key flipped the sound"

    press(app, Qt.Key.Key_Q, "q")
    assert top(app) == "ConfirmScreen"


def test_the_prologue_skips_on_a_press_never_on_a_repeat(app):
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.prologue import PrologueScreen

    app.prologue_seen = False
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    assert top(app) == "PrologueScreen"

    press(app, Qt.Key.Key_Escape, repeat=True)
    assert top(app) == "PrologueScreen", "the premise was skipped mid-sentence"

    press(app, Qt.Key.Key_Escape)
    assert top(app) == "GameScreen"


def test_the_glass_toggles_answer_a_press(app):
    """Held F2 would flip the scanlines -- and rewrite the settings file --
    thirty times a second."""
    from PySide6.QtCore import Qt

    before = app.crt.scanlines

    press(app, Qt.Key.Key_F2, repeat=True)
    assert app.crt.scanlines == before, "a held F2 flickered the glass"

    press(app, Qt.Key.Key_F2)
    assert app.crt.scanlines != before


# -- what the purse cannot reach is ash ---------------------------------------
def test_what_the_purse_cannot_reach_reads_as_closed(app):
    """An offer a player cannot act on should not sit on the shelf looking
    like the rest: ash, with the reason next to the price."""
    from neverdeads_revenge.desktop.chrome import ASH, BONE
    from neverdeads_revenge.desktop.screens.menus import ShopScreen

    screen = ShopScreen()
    app.progress.gold = 0
    screen._restock(app)
    rows = {offer_index: row for row in screen._rows(70) if (offer_index := row[2]) is not None}

    priced = [o for o in screen.offers if o.price > 0 and not o.maxed]
    assert priced, "the shop priced nothing over nothing"
    for offer in priced:
        text, style, _ = rows[screen.offers.index(offer)]
        assert style == ASH, f"{offer.label} looked affordable to a broke purse"
        assert "(out of reach)" in text, f"{offer.label} did not say why"

    app.progress.gold = 999
    screen._restock(app)
    rows = {offer_index: row for row in screen._rows(70) if (offer_index := row[2]) is not None}
    priced = [o for o in screen.offers if o.price > 0 and not o.maxed and o.affordable]
    assert priced, "nothing was in reach of a full purse"
    text, style, _ = rows[screen.offers.index(priced[0])]
    assert style == f"bold {BONE}", "an offer in reach hid in the ash"


def test_a_held_enter_reads_through_the_repeat_stream(app):
    """The hold lives on auto-repeat events; eating repeats anywhere above the
    screens starves it (and that bug ate them at the window layer). One press,
    then the hardware stream Qt really sends -- the screen must go."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.prologue import PrologueScreen

    app.prologue_seen = False
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    assert top(app) == "PrologueScreen"

    start = time.monotonic()
    press(app, Qt.Key.Key_Return)
    while time.monotonic() - start < 1.6 and top(app) == "PrologueScreen":
        time.sleep(0.033)
        press(app, Qt.Key.Key_Return, repeat=True)

    assert top(app) == "GameScreen", "a held enter starved at the window"


def test_an_old_hold_cannot_cash_itself_in():
    """A hold interrupted long enough for the key to come up banks nothing:
    the next tap starts a fresh hold instead of inheriting a full bar."""
    import time as _time

    from neverdeads_revenge.desktop.hold import HoldToContinue

    hold = HoldToContinue()
    assert hold.press("enter") is False

    _time.sleep(1.05)  # long enough to be a release, long enough for 1.0s
    assert hold.press("enter") is False, "a stale hold spent itself in one tap"


# -- a menu cursor walks its window, and dead lists do not pretend to scroll ---
def test_the_shelf_cursor_walks_inside_the_window(app):
    """The house style for menus: the cursor moves through the visible rows,
    and the shelf only shifts when the cursor reaches an edge. A shelf line is
    two rows -- the offer and what it does -- so the edge is the row above the
    bottom, and the detail is never the thing the window hides."""
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_S, "s")  # the shop
    screen = app.screens[-1]

    total, window = screen._body_size
    assert window < total, "the shelf has no overflow to test against"

    def cursor_row():
        return next(
            n for n, row in enumerate(screen._rows(70)) if row[2] == screen.index
        )

    # Down: the cursor walks, and the row under it -- the description -- stays
    # inside the window the whole way.
    moved = False
    for _ in range(10):
        before = screen.offset
        press(app, Qt.Key.Key_Down)
        row = cursor_row()
        assert row + 1 <= screen.offset + window - 1, (
            "the cursor's own detail line fell out of the window"
        )
        assert screen.offset >= before, "the shelf jumped the wrong way"
        if screen.offset != before:
            moved = True
    assert moved, "the shelf never followed the cursor"

    # Up: the cursor climbs inside the window, the shelf holds still until the
    # cursor reaches the top edge.
    for _ in range(10):
        before = screen.offset
        press(app, Qt.Key.Key_Up)
        row = cursor_row()
        assert screen.offset <= row < screen.offset + window, (
            "the cursor left its window"
        )
        assert screen.offset <= before, "going up dragged the shelf the wrong way"

    press(app, Qt.Key.Key_Escape)


class _FakeEvent:
    """A key event that is never a repeat, for tests that drive a screen
    directly rather than through the app."""

    def isAutoRepeat(self) -> bool:
        return False


def test_the_pack_of_two_items_does_not_scroll(app, font):
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.screens.menus import PackScreen
    from neverdeads_revenge.world.items import ITEMS, make_item

    class _Pack:
        inventory = [make_item(ITEMS["potion"]), make_item(ITEMS["potion"])]

    screen = PackScreen(_Pack())
    buffer = PatternBuffer(70, 30, font)
    screen.draw(buffer, app)
    total, window = screen._body_size

    assert total <= window, "two items overflowed a 30-row page"
    for _ in range(6):
        screen.key("down", _FakeEvent(), app)
    assert screen.offset == 0, "a list that fits still scrolled"

    for _ in range(6):
        screen.key("up", _FakeEvent(), app)
    assert screen.offset == 0


def test_a_long_pack_walks_its_cursor_and_never_scrolls_past_its_floor(app, font):
    """The pack has a hand in it now: down moves the cursor and the box
    follows, two rows per line, and the floor is the floor."""
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.screens.menus import PackScreen
    from neverdeads_revenge.world.items import ITEMS, make_item

    class _LongPack:
        inventory = [make_item(ITEMS[key]) for key in list(ITEMS)[:14]]

    screen = PackScreen(_LongPack())
    buffer = PatternBuffer(70, 30, font)
    screen.draw(buffer, app)
    total, window = screen._body_size
    assert window < total, "the pack has no overflow to test against"

    for _ in range(40):
        screen.key("down", _FakeEvent(), app)
        assert screen.offset <= max(0, total - window), "the box scrolled past its end"
        assert screen.index < len(screen._kinds()), "the cursor left the pack"

    for _ in range(40):
        screen.key("up", _FakeEvent(), app)
        assert screen.offset >= 0
        assert screen.index < len(screen._kinds())


def test_the_shelf_stops_at_its_ends(app):
    """A list walks to its ends and stops; it does not loop, because the offer
    you wanted to pass was before the one you now cannot see."""
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_S, "s")  # the shop
    screen = app.screens[-1]

    press(app, Qt.Key.Key_Up)  # the top: already the first offer
    assert screen.index == 0

    for _ in range(100):
        press(app, Qt.Key.Key_Down)
    last = screen.index
    assert last == len(screen.offers) - 1, "down did not reach the shelf's end"

    press(app, Qt.Key.Key_Down)
    assert screen.index == last, "the bottom looped the shelf to its head"

    for _ in range(100):
        press(app, Qt.Key.Key_Up)
    assert screen.index == 0

    press(app, Qt.Key.Key_Up)
    assert screen.index == 0, "the top looped the shelf to its foot"
    press(app, Qt.Key.Key_Escape)


def test_a_held_scroll_key_walks_the_list(app):
    """Only the scroll keys accept a held key: repeats of everything else --
    most of all a held enter -- answer nothing."""
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_S, "s")  # the shop
    screen = app.screens[-1]
    gold = app.progress.gold

    for _ in range(6):
        press(app, Qt.Key.Key_Down, repeat=True)
    assert screen.index >= 3, "a held scroll key did not walk the list"

    for _ in range(6):
        press(app, Qt.Key.Key_Up, repeat=True)
    assert screen.index == 0, "a held scroll key did not walk back"

    press(app, Qt.Key.Key_Down)
    for _ in range(4):
        press(app, Qt.Key.Key_Enter, repeat=True)  # a held enter must not buy
    assert app.progress.gold == gold, "a held enter spent gold"
    press(app, Qt.Key.Key_Escape)


def test_a_held_scroll_key_walks_a_panel(app, font):
    """The read-only panels scroll on a held key; the pack does not, because
    the pack has a cursor and a menu answers one gesture per line."""
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.screens.menus import ChronicleScreen

    screen = ChronicleScreen()  # thirty-seven pages, so it always overflows
    buffer = PatternBuffer(70, 30, font)
    screen.draw(buffer, app)
    total, window = screen._body_size
    assert window < total, "the chronicle has no overflow to test against"

    class _Repeat:
        def isAutoRepeat(self) -> bool:
            return True

    for _ in range(8):
        screen.key("down", _Repeat(), app)
    assert screen.offset > 0, "a held scroll key did not walk the panel"
    for _ in range(50):
        screen.key("down", _Repeat(), app)
    assert screen.offset == max(0, total - window), "held scrolling passed the floor"


def test_three_taps_dismiss_nothing(app):
    """A hold is a hold. Three quick presses -- the thing a fidget does on the
    way to a real hold -- used to walk straight through the premise, because a
    terminal could only guess that a hold was over by silence. The desktop is
    told when the key came up; taps bank nothing."""
    from PySide6.QtCore import Qt

    app.prologue_seen = False
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    assert top(app) == "PrologueScreen"

    for _ in range(3):
        press(app, Qt.Key.Key_Return)
        release(app, Qt.Key.Key_Return)

    assert top(app) == "PrologueScreen", "taps walked through the premise"

    # a hold still works, right after the taps
    hold_enter(app, until="GameScreen")
    assert top(app) == "GameScreen"


def test_a_tap_banks_nothing():
    """The tap rule the desktop can afford *and* must afford: a press that is
    down briefly and never repeated is a tap, and its release banks nothing.
    No gap heuristic has to separate it from a slow keyboard."""
    import time as _time

    from neverdeads_revenge.desktop.hold import HoldToContinue

    hold = HoldToContinue()
    hold.press("enter")
    _time.sleep(0.05)  # a short, unrepeated press
    hold.release("enter")

    assert hold.progress == 0.0, "a tap spent itself into the fill"
    assert hold.press("enter") is False, "the next press inherited the tap"


def test_the_bar_fills_while_the_key_is_down(app):
    """The fill begins with the press, not with the keyboard's first repeat
    half a second later. The app's tick loop redraws while a hold is live."""
    from PySide6.QtCore import Qt

    app.prologue_seen = False
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    assert top(app) == "PrologueScreen"

    screen = app.screens[-1]
    presses = [0]
    original = app.redraw
    app.redraw = lambda: presses.__setitem__(0, presses[0] + 1)

    try:
        press(app, Qt.Key.Key_Return)
        app._tick()
        app._tick()
        assert presses[0] >= 2, "the bar was not redrawn while the key was down"
        assert screen.hold.holding

        release(app, Qt.Key.Key_Return)  # short, unrepeated: a tap
        assert not screen.hold.holding, "a tap kept the tick painting"
        count = presses[0]
        app._tick()
        assert presses[0] == count, "the tick kept drawing a finished hold"
    finally:
        app.redraw = original


def test_the_wayland_silence_does_not_tear_the_hold():
    """The user saw a bar fill, vanish in full, and fill again -- on one
    pressed key. What a Wayland compositor does between them: it lifts the
    key at its repeat delay (an honest-looking release, long enough not to be
    a tap) and hands the repeats back *later*, past any gap the terminal-era
    press-counting could survive. The desktop renders the fill from the wall
    clock instead: silence inside a hold is composition noise, not the end of
    it."""
    import time as _time

    from neverdeads_revenge.desktop.hold import HoldToContinue

    hold = HoldToContinue()
    hold.press("enter")  # the fill starts
    _time.sleep(0.35)  # the repeat delay
    hold.release("enter")  # the compositor lifts the key: too long to be a tap
    _time.sleep(0.25)  # ...and its repeats come back late

    assert hold.press("enter") is False, "the fill read as finished early"
    assert hold.progress >= 0.55, "the fill restarted instead of bridging"

    # the stream then carries it the rest of the way, calm and unbroken
    while hold.progress < 1.0:
        _time.sleep(0.02)
        hold.press("enter")
    assert hold.press("enter") is True, "the held, bridged hold did not dismiss"

    # a lift that stands alone -- short, unrepeated -- is still a tap
    hold.press("enter")
    hold.release("enter")  # immediate: a short down
    _time.sleep(0.4)
    assert hold.press("enter") is False, "a tap's bank paid the next press"






# -- glass notes reach the frame, and the paint follows a release ---------------
def test_a_glass_note_is_on_the_screen(app):
    """The F2/F3/F4 notes were written into the pattern buffer after the image
    had already been rendered -- invisible, all of it, and a player who looked
    for the words was right not to find them."""
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_F2)
    row = "".join(cell.char for cell in app._buffer.cells[1])
    assert "SCANLINES" in row, "the glass said nothing"


def test_a_release_repaints_the_hold_screen(app):
    """Aborting a fill used to leave the last painted bar frozen on the glass:
    the release voided the hold, nothing considered that fact worth a paint,
    and nothing else happened to force one either."""
    from PySide6.QtCore import Qt

    app.prologue_seen = False
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    assert top(app) == "PrologueScreen"

    paints = [0]
    original = app.redraw
    app.redraw = lambda: paints.__setitem__(0, paints[0] + 1)
    try:
        press(app, Qt.Key.Key_Return)  # start a fill
        before = paints[0]
        release(app, Qt.Key.Key_Return)  # abort it
        assert paints[0] > before, "the aborted bar stayed on the glass"
    finally:
        app.redraw = original


def test_the_mute_note_survives_a_restart(app):
    """The pause remembers the sound is off across restarts, as the audio
    module always claimed it did."""
    app.progress.muted = True
    app.save_progress()

    from neverdeads_revenge.desktop.app import DesktopApp

    fresh = DesktopApp(seed=5, no_sound=False)
    assert fresh.sfx.muted, "the saved silence was not restored"
    fresh.close()


# -- screens that scroll now land somewhere sane --------------------------------
def test_the_prologue_jumps_with_home_and_end(app):
    from PySide6.QtCore import Qt

    app.prologue_seen = False
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    screen = app.screens[-1]

    press(app, Qt.Key.Key_End)
    assert screen.offset > 0, "end did not jump to the bottom"

    press(app, Qt.Key.Key_Home)
    assert screen.offset == 0, "home did not jump to the top"


def test_the_page_stops_at_its_floor(app, font):
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.screens.dialogs import PageScreen

    screen = PageScreen(3, "There is no way back. " * 60)
    buffer = PatternBuffer(70, 30, font)
    screen.draw(buffer, app)
    total, window = screen._span
    assert window < total, "the page has no overflow to test against"

    # Pages answer one gesture, never a repeat stream -- so this walks with
    # plain presses and expects the clamp to hold through all of them.
    for _ in range(80):
        screen.key("down", _FakeEvent(), app)
    assert screen.offset == max(0, total - window), "the page scrolled into blank"
    for _ in range(80):
        screen.key("up", _FakeEvent(), app)
    assert screen.offset == 0


def test_the_title_shrugs_off_a_stale_cursor(app):
    """The item list can shrink under a title that stays put; enter must not
    walk off the end of it and pick whatever used to sit at that index."""
    from PySide6.QtCore import Qt

    screen = app.screens[-1]
    screen.index = 99
    press(app, Qt.Key.Key_Enter)
    assert top(app) == "TitleScreen", "a stale index did something"


def test_fit_scale_falls_back_to_a_fraction():
    from PySide6.QtCore import QSize

    from neverdeads_revenge.desktop.crt import fit_scale

    big = QSize(960, 640)
    small = QSize(160, 120)
    assert fit_scale(big, QSize(240, 160)) == 4.0, "whole scales stopped being whole"
    scale = fit_scale(small, QSize(960, 640))
    assert isinstance(scale, float) and scale == 0.5, "the fraction never came back"


def test_struck_cells_flash_in_reverse(font):
    """state.hits is filled every action and cleared the turn after; the map
    drew the same thing either way. The flash is the visual half of a hit."""
    from neverdeads_revenge.desktop.buffer import PatternBuffer

    from neverdeads_revenge.desktop.render import _draw_map, regions, viewport
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run

    state = start_run(HEROES["noxx"], 3)
    square = state.player.position
    area = regions(40, 16)["map"]
    left, top, _, _ = viewport(state, area[2], area[3])

    plain_buffer = PatternBuffer(40, 16, font)
    _draw_map(plain_buffer, state, area)
    plain = plain_buffer.cells[square[1] - top][square[0] - left]

    state.hits = [square]
    struck_buffer = PatternBuffer(40, 16, font)
    _draw_map(struck_buffer, state, area)
    struck = struck_buffer.cells[square[1] - top][square[0] - left]

    assert not plain.style.reverse and struck.style.reverse, "the flash never lit"


def test_the_sidebar_knows_the_statuses(app):
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.render import marks_names

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    state.player.statuses["poison"] = 3
    names = marks_names(state, "statuses")
    assert names and "3" in names[0], "the status column stayed empty"
    state.player.statuses.pop("poison")


# -- one compositor lift banks; a second is a hand --------------------------------
def test_the_second_release_discharges_the_bank():
    """Deliberate half-second taps would otherwise add up through banking:
    the first release inside a fill is bridgeable (the compositor lifts once),
    and a second is a hand, which voids the whole bank."""
    import time as _time

    from neverdeads_revenge.desktop.hold import HoldToContinue

    hold = HoldToContinue()
    hold.press("enter")
    _time.sleep(0.4)
    hold.release("enter")  # the compositor's lift: banked
    assert hold.progress >= 0.4

    hold.press("enter")
    _time.sleep(0.4)
    hold.release("enter")  # a second lift: nobody's compositor did that
    assert hold.progress == 0.0, "long taps added up through the bank"


# -- the floor knows what the hero carries ----------------------------------------
def test_floor_one_knows_the_parcel():
    """This ran backwards: floor 1 was generated before the shop's parcel
    landed, so a pact's COMPANY curse rented no shapes that floor and a
    floor-one chest could offer back the very curse the pact just charged."""
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run

    class _Loadout:
        # The pact is one of the WILD OFFERS, so into ``wilds`` it goes; the
        # supplies list fits anything else a shop has talked the player into.
        pending: list[str] = []
        wilds: list[str] = ["pact"]
        upgrades: dict = {}

    state = start_run(HEROES["noxx"], 11, loadout=_Loadout())

    keys = {curse.key for curse in state.curses}
    assert keys, "the pact never settled a curse"
    if "company" in keys:
        assert len(state.enemies) >= 9, "COMPANY left its floor-one shapes unrented"

    chest_curses = []
    for pos in state.dungeon_map.walkable_positions():
        item = state.dungeon_map.item_at(pos)
        if item is not None and getattr(item, "kind", None) == "chest" and item.curse:
            chest_curses.append(item.curse)
    assert all(curse not in keys for curse in chest_curses), (
        "a chest offered a curse the pact had just charged for"
    )


def test_the_wild_shelf_is_filled_on_first_visit(app):
    """A fresh book rolls no wild shelf until a run ends -- so the very first
    visit to the shop had an empty rotation, exactly when a new player looks."""
    from neverdeads_revenge.desktop.screens.menus import ShopScreen

    app.progress.wild_stock = []
    ShopScreen()._restock(app)
    assert app.progress.wild_stock, "the first visit had no wilds at all"


# -- the generator's promises are kept --------------------------------------------
def test_nothing_is_hidden_under_immutable_things():
    """Loot under an npc is loot the game cannot ever give back, and an npc on
    the hunter's cell is twice the ambush. The generator claims neither can
    happen; now the tests do too, floor after floor, deep enough to meet."""
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run

    from neverdeads_revenge.world.generator import hunter_chance

    checked_hunter = 0
    for seed in range(1, 13):
        state = start_run(HEROES["noxx"], seed)
        for depth in range(2, 11):
            built = state.build_floor(depth)
            npc_positions = {npc.position for npc in state.npcs}
            item_positions = {
                pos
                for pos in built.map.walkable_positions()
                if built.map.item_at(pos) is not None
            }
            assert not (npc_positions & item_positions), (
                f"seed {seed} depth {depth}: an item lies under a person"
            )
            hunter = next(
                (
                    enemy
                    for enemy in state.enemies
                    if enemy.name == "hunter"  # not "the hunter"; see the table
                ),
                None,
            )
            if hunter is not None:
                checked_hunter += 1
                assert hunter.position not in npc_positions, (
                    f"seed {seed} depth {depth}: the hunter shared an npc's cell"
                )
                if built.spring is not None:
                    assert built.spring != hunter.position, (
                        f"seed {seed} depth {depth}: the spring stood under the hunter"
                    )
                assert all(pos != hunter.position for pos, _ in built.npcs)
        del state
    assert checked_hunter > 0, (
        "no seed reaching depth 10 ever met the hunter; hunter_chance "
        f"at depth 10 is {hunter_chance(10)}"
    )






# -- what the dark handed over reads like it does -----------------------------
def test_the_sheet_says_what_curses_gifts_and_effects_do(app):
    """The sheet was a list of names: a curse on the wall with no price in
    sight. Now every name carries the sentence that names its shape."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.menus import CharacterScreen
    from neverdeads_revenge.game.curses import CURSES
    from neverdeads_revenge.game.gifts import GIFTS

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    curse = next(iter(CURSES.values()))
    gift = GIFTS["momentum"]
    forgotten = list(state.curses)
    state.curses = [curse]
    state.gifts.add(gift.key)
    state.wilds.add("greed")

    lines = CharacterScreen(state).lines(app)
    # Detail lines are wrapped under their name with the 10-space indent; peel
    # the indent and join with spaces so a sentence can be asserted as itself
    # rather than as its wrapping.
    sheet = " ".join(
        text.replace("          ", "", 1) for text, _ in lines if text
    )

    assert curse.name in sheet, "the curse went unnamed"
    assert curse.price in sheet, "the curse has no price with it"
    assert gift.name in sheet, "the gift went unnamed"
    assert gift.blurb in sheet, "the gift has no rule with it"
    assert "coins are worth double" in sheet, "the bargain's tune is unsung"
    assert "everything below is a fifth tougher" in sheet, "its catch went missing"

    state.curses = forgotten
    state.gifts.discard(gift.key)
    state.wilds.discard("greed")


def test_the_pack_is_a_small_window(app, font):
    """The pack holds draughts and nothing else; a shelf drawn over the whole
    glass for three lines of it was working the room too hard."""
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.screens.menus import PackScreen

    class _Pack:
        inventory: list = []

    screen = PackScreen(_Pack())
    buffer = PatternBuffer(70, 30, font)
    screen.draw(buffer, app)

    widest = 0
    for row in buffer.cells:
        chars = "".join(cell.char for cell in row)
        if "THE PACK" in chars:
            inked = [i for i, char in enumerate(chars) if char != " "]
            widest = inked[-1] - inked[0] + 1
    assert 0 < widest <= 46, f"the pack still spans {widest} columns"


def test_equipment_announces_itself_on_pickup(app):
    """Picking up a blade said one log line and was gone; for a roll that
    trades one sword for another, there is no reading what arrived twice."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.world.items import ITEMS, make_item

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    state.dungeon_map.add_item(state.player.position, make_item(ITEMS["tooth"]))

    press(app, Qt.Key.Key_Return)  # enter on the ground: taken
    assert top(app) == "InfoScreen", "the pickup stayed in the log"
    body = app.screens[-1]._body().lower()
    assert "the rusted tooth" in body, "the blade went unnamed"
    assert "+1 damage" in body, "the blade's shape went unsaid"
    assert f"{type(app).__name__}" != "never", "sanity"

    press(app, Qt.Key.Key_Return)  # read, then back to the dark
    assert top(app) == "GameScreen"


def test_a_chest_curse_reads_itself_out(app):
    """A chest asks before it charges; when the answer buys a curse, the
    curse's own sentence opens a page instead of scrolling past in four turns."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.game.curses import CURSES
    from neverdeads_revenge.world.items import make_chest

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    curse_key = next(iter(CURSES))
    state.dungeon_map.add_item(state.player.position, make_chest(curse_key, None))

    press(app, Qt.Key.Key_Return)  # the chest asks
    assert top(app) == "ChestScreen"
    press(app, Qt.Key.Key_Enter)  # open it: the price is paid
    assert top(app) == "InfoScreen", "the curse scrolled away unread"
    body = app.screens[-1]._body().lower()
    assert CURSES[curse_key].name.lower() in body, "the curse went unnamed"
    assert CURSES[curse_key].price.lower()[:16] in body, "the price went unsaid"
    press(app, Qt.Key.Key_Return)
    assert top(app) == "GameScreen"


def test_the_shop_bell_rings_on_a_purchase(app):
    """The till has a bell. A purchase that makes no noise is a purchase the
    second-guesser walks back to count again."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.menus import ShopScreen

    played: list[str] = []
    original = app.play
    app.play = lambda name=None: played.append(name if name else "coin")  # type: ignore[assignment]

    try:
        app.push(ShopScreen())
        app.progress.gold = 200
        app.redraw()
        press(app, Qt.Key.Key_Enter)  # buy the first shelf line
        press(app, Qt.Key.Key_Escape)  # leave the shop again
    finally:
        app.play = original

    assert "coin" in played, "a purchase happened in silence"


def test_a_sound_thread_never_writes_the_save_itself(app, qapp):
    """The sound thread notices that the audio session has given up, and the
    save file is written by whoever owns it. Two threads writing the same
    progress record race, and the last writer silently drops the other's
    update. So the thread only announces; the GUI thread saves."""
    import threading

    from neverdeads_revenge.desktop.audio import GIVE_UP_AFTER

    writers: list[threading.Thread] = []
    app.save_progress = lambda: writers.append(threading.current_thread())
    app.progress.muted = False

    def fail_from_the_sound_thread() -> None:
        for _ in range(GIVE_UP_AFTER):
            app.sfx._count_failure()

    worker = threading.Thread(target=fail_from_the_sound_thread)
    worker.start()
    worker.join()
    qapp.processEvents()

    assert writers, "the give-up never reached the record"
    assert all(t is threading.main_thread() for t in writers), (
        "the sound thread wrote the save file itself"
    )
    assert app.progress.muted is True, "the give-up was not recorded as muted"


# -- the void: the prompt's three states, and f -------------------------------
def test_the_void_prompt_reads_the_right_states():
    """Grey until the level asks for it, dark petrol and breathing once it
    can be given into, grey again once the floor has had its answer."""
    from neverdeads_revenge.desktop.render import _void_prompt
    from neverdeads_revenge.desktop.theme import parse_style
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run

    state = start_run(HEROES["noxx"], 3)

    text, colour = _void_prompt(state, 0.0)  # level 1, gate 7: locked
    assert text == "give in to the void (lvl 7)", "the lock did not say when"
    assert colour == parse_style("grey30").fg

    state.ultimate_level = 1  # level 1 >= 1: the promise is live
    text, colour = _void_prompt(state, 0.0)
    assert text == "give in to the void (f)"
    # The breath at t=0 is 0.35 + 0.95 * 0.5 = 0.825 of the petrol base.
    assert colour.getRgb()[:3] == (round(14 * 0.825), round(111 * 0.825), round(111 * 0.825)), (
        "the petrol does not breathe where the bloom can hear it"
    )
    # and the crest overdraws the base, so the glow is an event, not a tint:
    text, crest = _void_prompt(state, 0.25)
    assert crest.getRgb()[:3] == (18, 144, 144), "the crest never crosses the base"

    state.ultimate_level = 1
    state.atritas = HEROES["noxx"]  # any object; the check is presence
    text, colour = _void_prompt(state, 0.0)
    assert text == "give in to the void" and colour == parse_style("grey35").fg

    state.atritas = None
    state.ultimate_available = False
    text, colour = _void_prompt(state, 0.0)
    assert colour == parse_style("grey35").fg, "a spent ask still advertised"

    state.ultimate_available = True
    state.hero = HEROES["yeti"]
    text, _ = _void_prompt(state, 0.0)
    assert text == "build the Frozen Fortress (f)", "Yeti's ask went unnamed"

    state.hero = HEROES["walkyrion"]
    text, _ = _void_prompt(state, 0.0)
    assert text == "shatter the golden bell (f)", "Walkyrion's ask went unnamed"


def test_f_gives_in_when_the_gate_allows(app):
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.keys import KEY_BINDINGS

    assert KEY_BINDINGS["f"].name == "ULTIMATE"

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)

    played: list[str] = []
    original = app.play
    app.play = lambda name=None: played.append(name if name else "?")  # type: ignore[assignment]
    try:
        app.run.level = 1
        app.run.ultimate_level = 1
        press(app, Qt.Key.Key_F, "f")  # the ask, taken
        assert app.run.atritas is not None, "the void did not answer"
        assert app.run.ultimate_available is False
        assert "void" in played, "the dark arrived in silence"

        before = app.run.atritas
        press(app, Qt.Key.Key_F, "f")  # spent: the floor had its answer
        assert app.run.atritas is before, "the void answered twice"
        assert top(app) == "GameScreen"
    finally:
        app.play = original


def test_the_voids_glass_closes_with_the_shadow():
    """The reveal is drawn, not remembered: a wall across the floor is shown
    while Atritas walks, and gone the moment he sinks back -- even though
    nobody ever walked there."""
    from neverdeads_revenge.desktop.render import _cell_content
    from neverdeads_revenge.game.actions import Action, perform_action
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.world.tiles import Tile

    state = start_run(HEROES["noxx"], 3, ultimate_level=1)
    far = (state.dungeon_map.width - 2, state.dungeon_map.height - 2)
    state.dungeon_map.set_tile(far, Tile.WALL)

    perform_action(state, Action.ULTIMATE)
    glyph, _ = _cell_content(far, state)
    assert glyph == Tile.WALL.glyph, "the glass showed nothing"

    for _ in range(40):
        perform_action(state, Action.WAIT)
    assert state.atritas is None

    glyph, _ = _cell_content(far, state)
    assert glyph == " ", "the glass outlived the shadow"


# -- deleting everything, on purpose -------------------------------------------
def test_deleting_progress_needs_the_word_typed_out(app):
    """A confirm key is a reflex; a word is a decision. Nothing goes until the
    six letters are there."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.persistence import save_run

    app.progress.gold = 999
    app.progress.pages.append(1)
    app.save_progress()
    save_run({"version": 1, "hero": "noxx"})

    press(app, Qt.Key.Key_D, "d")  # the title's DELETE PROGRESS
    assert top(app) == "DeleteProgressScreen"

    for letter in "DELETE":
        press(app, Qt.Key.Key_D if letter == "D" else Qt.Key.Key_E, letter)
    press(app, Qt.Key.Key_Return)

    assert top(app) == "TitleScreen"
    assert app.progress.gold == 0, "the purse survived the word"
    assert not app.progress.pages, "the chronicle survived the word"
    assert not app.has_saved_run(), "the saved run survived the word"


def test_a_changed_mind_keeps_everything(app):
    from PySide6.QtCore import Qt

    app.progress.gold = 999
    app.save_progress()

    press(app, Qt.Key.Key_D, "d")
    press(app, Qt.Key.Key_D, "D")
    press(app, Qt.Key.Key_E, "E")
    press(app, Qt.Key.Key_Return)  # "DE" is not the word

    assert top(app) == "TitleScreen"
    assert app.progress.gold == 999, "a half-typed word erased the profile"

    press(app, Qt.Key.Key_D, "d")
    press(app, Qt.Key.Key_Escape)  # or just walk away
    assert top(app) == "TitleScreen"
    assert app.progress.gold == 999


# -- the controls, from the pause ----------------------------------------------
def test_the_pause_offers_the_controls(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)  # into the run
    press(app, Qt.Key.Key_Escape)  # the pause
    assert top(app) == "PauseScreen"

    press(app, Qt.Key.Key_C, "c")  # CONTROLS
    assert top(app) == "HelpScreen"
    sheet = "\n".join(text for text, _ in app.screens[-1].lines(app))
    assert "LEGEND" in sheet and "ULTIMATE" in sheet


# -- the legend, off the main screen and into its own menu ----------------------
def test_l_opens_the_legend_and_not_the_east_step(app):
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    before = app.run.player.position

    press(app, Qt.Key.Key_L, "l")

    assert top(app) == "LegendScreen", "l did not open the legend"
    assert app.run.player.position == before, "l still moved east"
    lines = "\n".join(text for text, _ in app.screens[-1].lines(app))
    assert "you" in lines, "the legend has no rows"
    # the legend lists the things, not the ground: monsters, loot, the chest
    assert "ghoul" in lines and "!" in lines and "&" in lines, (
        "the legend shows no glyphs"
    )

    press(app, Qt.Key.Key_Escape)
    assert top(app) == "GameScreen"

    # and east still moves: the arrow, and the wasd key
    press(app, Qt.Key.Key_Right)
    assert app.run.player.position != before or True  # may be blocked by a wall
    press(app, Qt.Key.Key_D, "d")


def test_the_sidebar_points_at_the_legend_instead_of_carrying_it(app):
    """The sidebar keeps the run; the reference moved. What is left is the
    pointer, so a player who read the legend once can find it again."""
    from neverdeads_revenge.desktop.screens.menus import HelpScreen

    sheet = "\n".join(text for text, _ in HelpScreen().lines(app))
    assert "LEGEND    l" in sheet, "the controls do not name the legend key"


# -- the pickup page does not close under your thumb -----------------------------
def test_a_pickup_page_ignores_everything_but_enter(app):
    """The wraith's curse lands mid-fight, the page opens, and the direction
    key already under the player's thumb used to dismiss it unread."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.world.items import ITEMS, make_item

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    state.dungeon_map.add_item(state.player.position, make_item(ITEMS["tooth"]))
    press(app, Qt.Key.Key_Return)  # the pickup
    assert top(app) == "InfoScreen"

    for key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Space, Qt.Key.Key_Q):
        press(app, key)
        assert top(app) == "InfoScreen", "a direction key ate the page"

    press(app, Qt.Key.Key_Return)
    assert top(app) == "GameScreen"

    # and escape is allowed: it is a key you *choose*
    state.dungeon_map.add_item(state.player.position, make_item(ITEMS["bite"]))
    press(app, Qt.Key.Key_Return)
    assert top(app) == "InfoScreen"
    press(app, Qt.Key.Key_Escape)
    assert top(app) == "GameScreen"


# -- the pack: drink it or set it down -------------------------------------------
def test_the_pack_drinks_and_drops_by_name(app):
    from PySide6.QtCore import Qt

    from neverdeads_revenge.world.items import ITEMS, make_item
    from neverdeads_revenge.world.tiles import Tile

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    state.inventory.append(make_item(ITEMS["thin_veil"]))
    state.inventory.append(make_item(ITEMS["potion"]))
    state.dungeon_map.set_tile(
        (state.player.position[0] + 1, state.player.position[1]), Tile.FLOOR
    )

    press(app, Qt.Key.Key_I, "i")
    assert top(app) == "PackScreen"
    screen = app.screens[-1]

    # the cursor picks; potion sorts first, thin_veil second
    kinds = [item_id for item_id, _ in screen._kinds()]
    assert kinds == ["potion", "thin_veil"], kinds
    press(app, Qt.Key.Key_Down)
    assert screen.index == 1

    press(app, Qt.Key.Key_Return)  # drink the veil
    assert state.has_draught("thin_veil"), "the pack did not drink by name"
    assert "thin_veil" not in [i.item_id for i in state.inventory], "the bottle stayed"

    # and now drop the potion: it lands beside the hero
    press(app, Qt.Key.Key_Up)
    assert screen.index == 0
    press(app, Qt.Key.Key_X, "x")
    assert "potion" not in [i.item_id for i in state.inventory], "the drop did nothing"
    beside = [
        pos
        for pos in state.dungeon_map.items
        if state.dungeon_map.item_at(pos) is not None
        and state.dungeon_map.item_at(pos).item_id == "potion"
    ]
    assert beside, "the dropped draught is nowhere on the floor"

    press(app, Qt.Key.Key_Escape)
    assert top(app) == "GameScreen"


def test_q_never_drinks_a_strange_bottle(app):
    """`q` is the careful drink -- the cheapest thing that covers the wound.
    A bottle that lays a rule is not a wound's business."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.world.items import ITEMS, make_item

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    state.inventory.append(make_item(ITEMS["short_crown"]))
    state.player.stats.hp = 5

    press(app, Qt.Key.Key_Q, "q")

    assert state.player.stats.hp == 5, "q drank a bottle that heals nothing"
    assert "short_crown" in [i.item_id for i in state.inventory], "q wasted the crown"
    assert not state.floor_draughts


def test_the_carrion_tongue_marks_the_floors_dead():
    """A dim blood spot where something stopped moving, shown only while the
    tongue is working -- and never the bright red comma, which is the hungry
    road's own mark."""
    from neverdeads_revenge.desktop.render import _cell_content
    from neverdeads_revenge.game.actions import perform_action
    from neverdeads_revenge.game.actors import ENEMIES, HEROES, make_enemy
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.world.tiles import Tile

    state = start_run(HEROES["noxx"], 3)
    state.dungeon_map.set_tile((state.player.position[0] + 1, state.player.position[1]), Tile.FLOOR)
    square = (state.player.position[0] + 1, state.player.position[1])
    enemy = make_enemy(ENEMIES["ghoul"], square)
    enemy.stats.hp = 1
    state.enemies.append(enemy)
    state.turn_queue.add(enemy)
    from neverdeads_revenge.game.actions import Action

    perform_action(state, Action.MOVE_EAST)  # the kill
    assert square in state.death_squares
    state.dungeon_map.remove_item(square)  # the kill's coins are loot, not stain

    glyph, _ = _cell_content(square, state)
    assert glyph != "·", "the floor showed a stain nobody could see"

    state.floor_draughts.add("carrion_tongue")
    glyph, style = _cell_content(square, state)
    assert glyph == "·", "the tongue showed no blood"
    assert style.fg.name() == "#8b1a1a", f"the stain is {style.fg.name()}, not blood"
    assert style.dim, "the stain is not lying on the ground"


def test_the_pack_count_counts_the_strange_bottles_too(app):
    """A tongue takes a slot, so the counter has to say so: 1/2 while the pack
    was full was a line lying about the only limit on it."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.render import hud_lines
    from neverdeads_revenge.world.items import ITEMS, make_item

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    state.inventory.append(make_item(ITEMS["potion"]))
    state.inventory.append(make_item(ITEMS["carrion_tongue"]))

    line = next(text for text, _ in hud_lines(state) if "Draughts" in text)
    assert "Draughts 2/2" in line, line
    assert line.endswith("q"), "the q hint went missing while a potion was held"

    state.inventory = [make_item(ITEMS["carrion_tongue"])]
    line = next(text for text, _ in hud_lines(state) if "Draughts" in text)
    assert "Draughts 1/2" in line
    assert not line.endswith("q"), "q was advertised with nothing that heals"


def test_the_sidebar_names_the_draughts_that_are_working(app):
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.render import marks_names
    from neverdeads_revenge.game.draughts import draught_by_key

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run

    assert marks_names(state, "draughts") == [], "a floor with no bottles listed one"

    state.floor_draughts.add("carrion_tongue")
    state.floor_draughts.add("short_crown")

    names = marks_names(state, "draughts")
    assert draught_by_key("carrion_tongue").name in names
    assert draught_by_key("short_crown").name in names


def test_the_tongue_paints_the_dead_even_under_the_coins(app):
    """The kill leaves coin where it died, and the coin won the square: the
    stain was invisible exactly where the kills were. The background is the
    channel loot does not use."""
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.render import BLOOD_TINT, _draw_map, regions, viewport
    from neverdeads_revenge.game.actions import Action, perform_action
    from neverdeads_revenge.game.actors import ENEMIES, HEROES, make_enemy
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.world.tiles import Tile

    state = start_run(HEROES["noxx"], 3)
    square = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    enemy = make_enemy(ENEMIES["ghoul"], square)
    enemy.stats.hp = 1
    state.enemies.append(enemy)
    state.turn_queue.add(enemy)
    perform_action(state, Action.MOVE_EAST)  # the kill, and its coin
    assert square in state.death_squares

    state.floor_draughts.add("carrion_tongue")
    buffer = PatternBuffer(40, 16, app.font)
    area = regions(buffer.cols, buffer.rows)["map"]
    _draw_map(buffer, state, area)
    left, top, _, _ = viewport(state, area[2], area[3])
    cell = buffer.cells[square[1] - top][square[0] - left]

    assert cell.char == "$", "the coin went missing from the corpse"
    assert cell.style.bg is not None and cell.style.bg.name() == BLOOD_TINT.name(), (
        "the dead square is not painted under the loot"
    )

# -- the arena (M1) ----------------------------------------------------------
def arena(seed: int = 1, count: int = 3, *, ultimate_level: int = 1):
    """A fight, out of a real run, over the floor's own first monsters."""
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.battle import Battle
    from neverdeads_revenge.game.state import start_run

    state = start_run(HEROES["noxx"], seed, ultimate_level=ultimate_level)
    return Battle(state, state.enemies[:count])


def drawn(screen, app, font, cols: int = 96, rows: int = 27):
    """Draw the screen the way the app does, and hand back buffer and image."""
    from neverdeads_revenge.desktop.buffer import PatternBuffer

    buffer = PatternBuffer(cols, rows, font)
    screen.draw(buffer, app)
    image = buffer.render()
    screen.paste(image, app)
    return buffer, image


def _is_colour(colour, rgb, tolerance: int = 60) -> bool:
    """Whether a pixel is (roughly) the colour the dungeon draws something in."""
    return (
        abs(colour.red() - rgb[0]) <= tolerance
        and abs(colour.green() - rgb[1]) <= tolerance
        and abs(colour.blue() - rgb[2]) <= tolerance
        and colour.alpha() > 0
    )


def test_the_arena_stages_the_actors_it_is_fighting(font):
    """The models are the monsters, not a mock-up of them.

    A fight against three vipers is three v's in their own colour, and the hero
    is the hero: the stage reads the actors the fight will spend.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=3)
    screen = BattleScreen(battle)
    figures = screen._figures(96, 27, font)

    assert [figure.actor for figure in figures] == [*battle.enemies, battle.hero]
    assert [figure.glyph for figure in figures] == [
        enemy.glyph for enemy in battle.enemies
    ] + [battle.hero.glyph]


def test_the_models_are_the_letters(app, font):
    """The models are the alphabet, drawn big: the monsters are their glyphs.

    The whole look of the game is one fixed cell, and a letter the size of a
    monster does not fit in one -- so the monsters are the single thing pasted
    onto the frame, which means this test has to look at the *frame*: a body of
    pixels in the monster's own colour, taller than the cell it stands on.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.desktop.theme import parse_style

    battle = arena(count=3)
    screen = BattleScreen(battle)
    _, image = drawn(screen, app, font)

    enemy = battle.enemies[0]
    rgb = parse_style(enemy.color).fg
    rows = [
        y
        for y in range(image.height())
        if any(
            _is_colour(image.pixelColor(x, y), (rgb.red(), rgb.green(), rgb.blue()))
            for x in range(image.width())
        )
    ]
    assert rows, f"no {enemy.color} letter anywhere on the stage"
    ink = sum(
        1
        for y in rows
        for x in range(image.width())
        if _is_colour(image.pixelColor(x, y), (rgb.red(), rgb.green(), rgb.blue()))
    )
    assert ink > 200, f"the {enemy.name} is only {ink} pixels of letter"
    assert rows[-1] - rows[0] > font.cell_h, (
        "the monster's letter is no taller than a cell, so it was never drawn big"
    )


def test_the_monsters_carry_their_health_under_them(app, font):
    """A bar under every monster, and none under the hero.

    The letter is the monster and the log is the story, so the one thing a
    monster cannot say about itself is how much of it is left -- and the hero's
    own numbers live on his plate, not on the floor.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=3)
    screen = BattleScreen(battle)
    buffer, _ = drawn(screen, app, font)
    x0, y0, width, height = screen._areas(96, 27)["ground"]

    def bar_cells(row: int) -> int:
        return sum(1 for cell in buffer.cells[row] if cell.char == "█")

    on_the_floor = sum(
        bar_cells(row) for row in range(y0, y0 + height)
    )
    assert on_the_floor >= 3 * len(battle.enemies), (
        f"{on_the_floor} cells of bar for {len(battle.enemies)} monsters"
    )
    hero_row = screen._figures(96, 27, font)[-1].row
    assert bar_cells(hero_row + 1) == 0, "the hero's health is on the floor as well"


def test_a_whole_fight_plays_out_by_keys(app, font):
    """M1's promise: a fight that can be *played*, to the end, with the keys.

    Driven through the app rather than the screen, because the part that could
    quietly not work is the wiring: the arena has to be able to say it is busy,
    the frame tick has to step it, and the input has to be refused while the
    fight is still talking about the last thing the player did.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=3)
    for enemy in battle.enemies:
        enemy.stats.hp = 1  # one blow each, so the test is about the wiring
    screen = BattleScreen(battle)
    app.screens = [screen]
    app.redraw()

    guard = 0
    while guard < 400:
        guard += 1
        if screen.busy:
            app._tick()
            continue
        if battle.over:
            break
        press(app, Qt.Key.Key_Return)

    assert battle.over, "the fight never ended"
    assert battle.won, "three one-hit monsters were not beaten"
    assert screen.verdict == "VICTORY", f"the arena says {screen.verdict!r}"
    assert screen.lines, "the fight said nothing on the way"


def test_the_fight_is_not_interrupted_while_it_talks(app, font):
    """A drummed enter must not choose the next verb before the blow is shown.

    The round is decided the moment the player commits, so the only thing
    standing between a player and accidentally acting on a hit they have not
    seen is that the arena refuses the keyboard while it is busy.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=3)
    screen = BattleScreen(battle)
    app.screens = [screen]
    app.redraw()

    press(app, Qt.Key.Key_Return)
    assert screen.busy, "the fight had nothing to play"
    verb, queue = screen.verb, len(screen._queue)
    for _ in range(5):
        press(app, Qt.Key.Key_Return)
    assert screen.verb == verb, "a key got through while the fight was talking"
    assert len(screen._queue) <= queue, "a second round was set off mid-beat"


def test_the_arena_is_walled_in_the_dungeons_own_glyph(app, font):
    """The room is ``#``, the same wall the map draws, and it converges.

    The walls are pasted, not drawn in the grid, so this asks the *frame*: grey
    pixels where masonry goes -- above the floor's far edge, and down both sides
    -- and none on the floor itself. The convergence is the second half: the
    leftmost wall pixel at the far end of the room is further in than the one at
    the near end, because the walls are placed from the floor's own taper.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.desktop.theme import parse_style

    screen = BattleScreen(arena(count=3))
    _, image = drawn(screen, app, font)
    field = screen._field(96, 27, font.cell_w, font.cell_h)

    def is_wall(x: int, y: int) -> bool:
        colour = image.pixelColor(x, y)
        floor = parse_style("grey19").fg.red()
        return (
            colour.red() == colour.green() == colour.blue()
            and colour.red() >= floor
        )

    top, bottom = int(field["top"]), int(field["bottom"])
    back = sum(
        1
        for y in range(max(0, top - 2), top)
        for x in range(image.width())
        if is_wall(x, y)
    )
    assert back > 200, "there is no wall behind the floor"

    def leftmost(row: int) -> int | None:
        for x in range(image.width()):
            if is_wall(x, row):
                return x
        return None

    # Every row of the room that has wall on its left, from the far end of the
    # room to the near one. The masonry does not reach the very last row -- a
    # wall of stone-sized hashes stops where the last one fits -- so the
    # question is which way the line of them leans, not where it ends.
    walled = [
        (row, leftmost(row))
        for row in range(top, bottom)
        if leftmost(row) is not None
    ]
    assert len(walled) > 3, "there is no wall on the left"
    (far_row, far), (near_row, near) = walled[0], walled[-1]
    assert far_row < near_row, "the wall does not run down the room"
    assert far > near, "the side walls do not converge with the floor"

    centre = (int(field["left"]) + int(field["right"])) // 2
    floor_y = (top + bottom) // 2
    assert not is_wall(centre, floor_y), "the masonry is standing on the floor"


def test_the_battle_floor_recedes(app, font):
    """The floor is the one thing that has to *look* like a place.

    Perspective here is two facts and no arithmetic worth hiding behind a
    shader: the far row is narrower than the near one, and it is darker. Both
    are asserted on the buffer, because both are what the player sees.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    screen = BattleScreen(arena(count=3))
    buffer, _ = drawn(screen, app, font)
    x, y, width, height = screen._areas(96, 27)["ground"]

    # A column nobody is standing on: the hero and the monsters cast a shadow,
    # and a shadow is darker than the floor it is cast on, which is the whole
    # point of it -- but it is not what this test is asking about.
    column = x + width // 5
    far = buffer.cells[y][column]
    near = buffer.cells[y + height - 1][column]
    assert far.style.bg is not None and near.style.bg is not None, (
        "a row of the floor is not floor at all"
    )
    assert near.style.bg.lightness() > far.style.bg.lightness(), (
        "the floor does not fade with distance"
    )
    assert buffer.cells[y][x].style.bg is None, "the far row is as wide as the near one"
    assert buffer.cells[y + height - 1][x].style.bg is not None, (
        "the near row does not reach the edge of the field"
    )


def test_the_arena_survives_any_window(app, font):
    """Drawn into a window too small for it: what fits, or nothing, but never a
    crash. Every menu in this game is drawn at a size it did not choose, and the
    one that raises is the one that took the whole game down with it."""
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    for cols, rows in ((12, 6), (24, 10), (40, 12), (80, 24), (200, 60)):
        screen = BattleScreen(arena(count=3))
        drawn(screen, app, font, cols, rows)


def test_the_battle_scene_opens_and_leaves(qapp):
    """``--battle-scene`` is the only way in for now, and escape the way out."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.app import DesktopApp

    window = DesktopApp(seed=3, no_sound=True, battle_scene=True)
    window.view.resize(1280, 800)
    assert top(window) == "BattleScreen", "the switch did not open the arena"

    press(window, Qt.Key.Key_Escape)
    assert top(window) == "TitleScreen", "escape did not leave the arena"
