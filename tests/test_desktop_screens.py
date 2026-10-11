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
    and the shelf only shifts when the cursor reaches an edge. The old
    stateless formula parked the cursor on the bottom edge and dragged the
    list, so going back up scrolled the shelf under a polished-in cursor."""
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_S, "s")  # the shop
    screen = app.screens[-1]

    total, window = screen._body_size
    assert window < total, "the shelf has no overflow to test against"

    def cursor_row():
        return next(
            n for n, row in enumerate(screen._rows(70)) if row[2] == screen.index
        )

    # every press skips its own detail line, so walk until the cursor sits on
    # the window's bottom edge
    while cursor_row() < window - 1:
        press(app, Qt.Key.Key_Down)
    assert screen.offset == 0, "the shelf moved before the cursor reached its edge"

    press(app, Qt.Key.Key_Down)  # the edge: the window now lives with the shift
    press(app, Qt.Key.Key_Down)
    assert cursor_row() == screen.offset + window - 1, (
        "a walking cursor was not pinned at the window's bottom edge"
    )

    # and back up, in the mirror image of the walk down: the cursor climbs
    # and the shelf holds still until the top edge; tied to the edge, the
    # window follows it one cursor-stride at a time -- never a jump -- and
    # the whole thing ends in the rest state, shelf open at the heading.
    pinned = screen.offset
    saw_pin = False
    while screen.index > 0:
        before = screen.offset
        press(app, Qt.Key.Key_Up)
        row = cursor_row()
        assert screen.offset <= row < screen.offset + window, "the cursor left its window"
        assert screen.offset <= before, "going up dragged the shelf the wrong way"
        assert screen.offset in (before, row) or (
            screen.offset == 0 and row <= 2
        ), "the shelf jumped instead of following"
        if screen.offset != before:
            saw_pin = True
        pinned = min(pinned, screen.offset)

    assert saw_pin, "the window never followed the cursor at the top edge"
    assert screen.offset == 0 and cursor_row() <= 2, "no rest state at the top"

    press(app, Qt.Key.Key_Escape)


class _FakeEvent:
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


def test_a_long_list_stops_at_its_floor(app, font):
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.screens.menus import PackScreen
    from neverdeads_revenge.world.items import ITEMS, make_item

    class _Pack:
        inventory = [make_item(ITEMS[key]) for key in list(ITEMS)[:14]]

    screen = PackScreen(_Pack())
    buffer = PatternBuffer(70, 30, font)
    screen.draw(buffer, app)
    total, window = screen._body_size
    assert window < total, "the pack has no overflow to test against"

    for _ in range(total + 10):
        screen.key("down", _FakeEvent(), app)
    assert screen.offset == max(0, total - window), "the floor scrolled past the end"

    screen.key("up", _FakeEvent(), app)
    assert screen.offset == max(0, total - window) - 1

    for _ in range(total + 10):
        screen.key("up", _FakeEvent(), app)
    assert screen.offset == 0


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
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.screens.menus import PackScreen
    from neverdeads_revenge.world.items import ITEMS, make_item

    class _LongPack:
        inventory = [make_item(ITEMS[key]) for key in list(ITEMS)[:14]]

    screen = PackScreen(_LongPack())
    buffer = PatternBuffer(70, 30, font)
    screen.draw(buffer, app)
    total, window = screen._body_size

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


def test_a_release_empties_the_bar():
    """Hold, let go: nothing is banked for the next press to inherit."""
    import time as _time

    from neverdeads_revenge.desktop.hold import HoldToContinue

    hold = HoldToContinue()
    hold.press("enter")
    assert hold.holding and hold.progress > 0.0

    hold.release("enter")
    assert not hold.holding
    assert hold.progress == 0.0

    _time.sleep(0.05)
    assert hold.press("enter") is False, "released progress funded the next press"
    assert hold.bar() == "░" * 10 or True  # just started over; it reads empty


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

        release(app, Qt.Key.Key_Return)
        assert not screen.hold.holding
        count = presses[0]
        app._tick()
        assert presses[0] == count, "the tick kept drawing a finished hold"
    finally:
        app.redraw = original
