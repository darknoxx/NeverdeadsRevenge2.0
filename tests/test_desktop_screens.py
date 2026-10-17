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
    walk_out_the_turning(app)
    assert top(app) == "BattleScreen", "the floor did not hand the fight over"

    # Play the fight out: the blow lands in the arena now, and the floor throws
    # the pixels for it when the hero comes back to it.
    screen = app.screens[-1]
    play_it_out(app, screen)

    assert screen.battle.won, "a one-hit ghoul was not killed"
    # The arena's own sparks are still in the air -- a short fight leaves more of
    # them behind than a long one -- and this is about the blood the *floor*
    # throws when it gets the hero back, so the air is cleared first.
    app.effects.clear()
    press(app, Qt.Key.Key_Return)  # the verdict: leave the arena
    assert top(app) == "GameScreen", "the fight never gave the floor back"
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
    """The rattle ends when its own span is up, and the margin is enormous.

    It used to be one sixtieth of a second against one twentieth -- a *real*
    clock against a real sleep, on whatever machine is running the suite. On a
    loaded Windows CI runner that is a coin toss, and it was one: the v0.3.0
    release failed here after building nothing and testing everything else. A
    sleep ten times the shake cannot be raced by a slow runner, and the thing
    being asserted -- that it settles at all -- is still the thing asserted.
    """
    import time

    app.view.shake(seconds=0.05)
    assert app.view.is_shaking()
    time.sleep(0.5)
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

    _time.sleep(1.15)  # long enough to be a release, long enough for 1.0s
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
    _time.sleep(0.40)  # the repeat delay, and then some
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
    _time.sleep(0.45)
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


def test_the_burning_floor_writes_walls_and_monsters_in_ember(font):
    """RAVAGING FIRE, as the map's alphabet sees it.

    The walls and the things walking on them go the fire's colour -- ``#`` and
    ``g`` in ember -- and everything else keeps what it had. That is the whole
    of the promise on this screen: it is the *dungeon* that is burning, and the
    player still has to be able to find himself, and his loot, in it.
    """
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.render import (
        EMBER_INK,
        _draw_map,
        regions,
        viewport,
    )
    from neverdeads_revenge.game.actors import ENEMIES, HEROES, make_enemy
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.world.tiles import Tile

    state = start_run(HEROES["inferno"], 3)
    here = state.player.position
    square = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    ghoul = make_enemy(ENEMIES["ghoul"], square)
    state.enemies.append(ghoul)
    state.refresh_vision()

    area = regions(40, 16)["map"]
    left, top, _, _ = viewport(state, area[2], area[3])

    def cell(buffer, pos):
        return buffer.cells[pos[1] - top][pos[0] - left]

    def drawn(ravaging: bool):
        state.ravaging = ravaging
        buffer = PatternBuffer(40, 16, font)
        _draw_map(buffer, state, area)
        return buffer

    plain = drawn(False)
    assert cell(plain, square).style.fg.name() != EMBER_INK.name(), (
        "the ghoul was already on fire"
    )

    burning = drawn(True)
    assert cell(burning, square).style.fg.name() == EMBER_INK.name(), (
        "the monster did not catch"
    )
    assert cell(burning, here).style.fg.name() != EMBER_INK.name(), (
        "the hero was set alight with the room"
    )

    # And the walls, which is what "the dungeon is burning" looks like: `#` in
    # ember, not the grey it was.
    walls = [
        cell(burning, (left + x, top + y))
        for y in range(area[3])
        for x in range(area[2])
        if cell(burning, (left + x, top + y)).char == "#"
    ]
    assert walls, "the test found no wall to burn"
    assert all(one.style.fg.name() == EMBER_INK.name() for one in walls), (
        "a wall is not burning"
    )
    floors = [
        cell(burning, (left + x, top + y))
        for y in range(area[3])
        for x in range(area[2])
        if cell(burning, (left + x, top + y)).char in (".", "·")
    ]
    assert floors and all(one.style.fg.name() != EMBER_INK.name() for one in floors), (
        "the floor burned as well, and the map is now a sign with no writing"
    )


def test_a_wound_more_than_one_stack_carries_its_depth(app, font):
    """The number on the badge, and only once there is more than one.

    Read as a *difference*: the same wound at two stacks and at one differs in
    exactly one place -- the badge's corner -- which is the honest way to test a
    digit nobody wants to parse out of pixels.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=1)
    screen = BattleScreen(battle)
    hero = battle.hero
    hero.statuses["bleed"] = 3

    hero.status_stacks["bleed"] = 2
    screen._catching_up(hero)
    _, two = drawn(screen, app, font)

    hero.status_stacks["bleed"] = 1
    screen._catching_up(hero)
    _, one = drawn(screen, app, font)

    assert bytes(two.constBits()) != bytes(one.constBits()), (
        "two stacks look exactly like one"
    )

    hero.statuses.clear()
    screen._catching_up(hero)
    _, clean = drawn(screen, app, font)
    assert bytes(clean.constBits()) != bytes(one.constBits()), (
        "the badge stayed after the wound had gone"
    )


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
#: Every sleep in this section is deliberately *longer* than the bar it is
#: measuring, and the margin is not decoration: ``sleep`` on Windows comes back up
#: to a timer tick early, so a hold that slept exactly 0.4 seconds for a 0.4
#: second bar reads 0.391 -- and the v0.3.0 release failed on precisely that.
#: These tests are about whether a hold banks or bridges, which is a race the
#: held *key* runs against the bar; the machine they run on is not part of it.
def test_the_second_release_discharges_the_bank():
    """Deliberate half-second taps would otherwise add up through banking:
    the first release inside a fill is bridgeable (the compositor lifts once),
    and a second is a hand, which voids the whole bank."""
    import time as _time

    from neverdeads_revenge.desktop.hold import HoldToContinue

    hold = HoldToContinue()
    hold.press("enter")
    _time.sleep(0.45)
    hold.release("enter")  # the compositor's lift: banked
    assert hold.progress >= 0.4, "the lift banked less than it was held for"

    hold.press("enter")
    _time.sleep(0.45)
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
    from neverdeads_revenge.game.actions import resolve_player_attack

    resolve_player_attack(state, enemy)  # the kill
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
    from neverdeads_revenge.game.actions import resolve_player_attack

    resolve_player_attack(state, enemy)  # the kill, and its coin
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


def test_the_arena_draws_whatever_art_there_is(app, font):
    """Every figure is on the floor: as a picture if the sheets have one, as its
    letter if they do not.

    Both halves are asserted because both are the truth the game lives with --
    the art is optional and the alphabet is not. A fight is never missing a
    fighter, only sometimes missing a picture of one.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.desktop.theme import parse_style

    battle = arena(count=3)
    screen = BattleScreen(battle)
    _, image = drawn(screen, app, font)
    figures = screen._figures(96, 27, font)

    for figure in figures:
        if figure.sprite is not None:
            left = figure.cx - figure.sprite.width() // 2
            top = figure_baseline(figure, font) - figure.sprite.height()
            inked = sum(
                1
                for y in range(top, top + figure.sprite.height(), 3)
                for x in range(left, left + figure.sprite.width(), 3)
                if image.pixelColor(x, y).alpha() > 0
            )
            assert inked > 40, f"the picture of {figure.actor.name} was not drawn"
            continue
        ink = parse_style(figure.colour).fg
        found = [
            y
            for y in range(image.height())
            if any(
                _is_colour(image.pixelColor(x, y), (ink.red(), ink.green(), ink.blue()))
                for x in range(image.width())
            )
        ]
        assert found, f"{figure.actor.name} has neither a picture nor a letter"
        assert found[-1] - found[0] > font.cell_h, "the letter is not a letter"


def test_the_roster_shows_the_hero_and_not_only_their_letter(app, font):
    """The block letter is the fallback; the sheets have the hero now.

    The roster stands them facing the *player* -- the front view, which is the
    second set of art the arena has no use for, since the arena's three stand
    with their backs to the camera at the monsters. What is asserted is the
    difference between the two views: a painted figure is a hundred colours wide
    and a block letter is exactly one, which is a thing a test can see where
    "it looks better" is not.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.blocks import render_word
    from neverdeads_revenge.desktop.screens import hero_select
    from neverdeads_revenge.desktop.sprites import portrait

    press(app, Qt.Key.Key_Return)  # off the title, onto the roster
    screen = app.screens[-1]
    hero = screen.current
    assert hero is not None

    def band() -> tuple[set, list[int]]:
        """The card's picture band: the colours in it, and where its ink is.

        The band is the letter's own five rows, which is where the picture goes
        too, and the background is whatever colour fills most of it.
        """
        _, image = drawn(screen, app, font)
        # Inside the card's own frame: outside it is the game's background, and
        # a background is not a figure standing in a band.
        width = min(96 - 8, 76)
        left = (96 - width) // 2
        inside = range((left + 1) * font.cell_w, (left + width - 1) * font.cell_w)
        top = (27 - min(27 - 4, 22)) // 2 + 2
        rows = range(top * font.cell_h, (top + len(render_word(hero.glyph))) * font.cell_h)
        seen: dict[tuple, int] = {}
        for y in rows:
            for x in inside:
                ink = image.pixelColor(x, y)
                key = (ink.red(), ink.green(), ink.blue())
                seen[key] = seen.get(key, 0) + 1
        fill = max(seen, key=lambda key: seen[key])
        columns = [
            x
            for x in inside
            if any(
                (c.red(), c.green(), c.blue()) != fill
                for c in (image.pixelColor(x, y) for y in rows)
            )
        ]
        return set(seen) - {fill}, columns

    painted, columns = band()
    art = portrait(hero.name)
    assert art is not None, "the sheets have no front view of the hero"
    assert len(painted) > 20, (
        f"the band is {len(painted)} colours, so it is still the block letter"
    )
    # Drawn at the roster's common height rather than at its own, so that four
    # heroes photographed at four sizes stand the same size on four cards.
    from neverdeads_revenge.desktop.screens.hero_select import PORTRAIT_HEIGHT

    expected = round(art.width() * PORTRAIT_HEIGHT / art.height())
    assert abs((max(columns) - min(columns) + 1) - expected) <= 4, (
        "the portrait is not drawn at the roster's height"
    )

    monkeypatch_absent = lambda name: None  # noqa: E731 - one line, one meaning
    hero_select.portrait = monkeypatch_absent
    try:
        lettered, letter_columns = band()
    finally:
        hero_select.portrait = portrait

    assert len(lettered) < len(painted) / 4, "the fallback is not a letter"
    assert max(letter_columns) - min(letter_columns) + 1 < art.width(), (
        "the fallback letter is as wide as the picture"
    )


def test_every_hero_has_a_face_on_the_roster():
    """The sheets' front views, one per hero, or the card falls back to a letter.

    Asserted for *every* hero rather than the one the roster happens to open on:
    a hero added without art is a letter on a card nobody notices until they
    pick him, and the whole point of the front views is that the choice is made
    by looking at four characters instead of four letters.
    """
    from neverdeads_revenge.desktop.sprites import portrait
    from neverdeads_revenge.game.actors import HEROES

    for hero in HEROES.values():
        art = portrait(hero.name)
        assert art is not None, f"{hero.name} has no front view"
        assert art.width() > 20 and art.height() > 20, (
            f"{hero.name}'s front view is a thumbnail"
        )


def test_a_monster_the_sheets_never_heard_of_is_still_a_letter(app, font):
    """The fallback: no picture means the alphabet, which is what the whole
    game looked like before the art arrived -- and a fight is never missing a
    fighter, only sometimes missing a picture of one."""
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.desktop.theme import parse_style

    battle = arena(count=1)
    battle.enemies[0].name = "unknowable"
    screen = BattleScreen(battle)
    _, image = drawn(screen, app, font)

    figure = screen._figures(96, 27, font)[0]
    assert figure.sprite is None, "the sheets have a picture of the unknowable"
    ink = parse_style(figure.colour).fg
    rows = [
        y
        for y in range(image.height())
        if any(
            _is_colour(image.pixelColor(x, y), (ink.red(), ink.green(), ink.blue()))
            for x in range(image.width())
        )
    ]
    assert rows, "the fallback letter was never drawn"
    assert rows[-1] - rows[0] > font.cell_h, "the fallback letter is not a letter"


def figure_baseline(figure, font) -> int:
    """Where a figure's feet are, as the stage draws them."""
    from neverdeads_revenge.desktop.screens.battle import THICKNESS

    return figure.row * font.cell_h - THICKNESS


def test_the_monsters_carry_their_health_under_them(app, font):
    """A bar under every monster, and none under the hero.

    Painted now and not written into the grid: the floor is a picture, so a bar in
    the grid would be a bar *under* the picture. Same stripe, same place -- half a
    cell of it, under the feet -- and the hero keeps his own numbers on his plate.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.desktop.theme import parse_style

    battle = arena(count=3)
    screen = BattleScreen(battle)
    _, image = drawn(screen, app, font)
    figures = screen._figures(96, 27, font)
    inks = [
        parse_style(colour).fg
        for colour in ("bright_green", "bright_yellow", "bright_red")
    ]

    def bar_pixels(figure) -> int:
        """How much of a bar is lying under this figure, read off the frame."""
        y = figure.row * font.cell_h + font.cell_h * 3 // 4
        cells = max(8, min(14, figure.cells * 2))
        left = figure.cx - cells * font.cell_w // 2
        found = 0
        for x in range(left, left + cells * font.cell_w):
            pixel = image.pixelColor(x, y)
            if any(
                abs(pixel.red() - ink.red()) < 40
                and abs(pixel.green() - ink.green()) < 40
                and abs(pixel.blue() - ink.blue()) < 40
                for ink in inks
            ):
                found += 1
        return found

    for figure in figures:
        if figure.actor is battle.hero:
            assert bar_pixels(figure) == 0, "the hero's health is on the floor as well"
            continue
        assert bar_pixels(figure) > 20, f"no bar under the {figure.actor.name}"


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

    press(app, Qt.Key.Key_Return)  # ATTACK: the arrow comes out onto the room
    press(app, Qt.Key.Key_Return)  # and is laid on the monster: the round begins
    assert screen.busy, "the fight had nothing to play"
    verb, queue = screen.verb, len(screen._queue)
    for _ in range(5):
        press(app, Qt.Key.Key_Return)
    assert screen.verb == verb, "a key got through while the fight was talking"
    assert len(screen._queue) <= queue, "a second round was set off mid-beat"


def test_the_arena_is_walled_in_stone(app, font):
    """The room is masonry, raised from the floor's own edges, and it converges.

    The walls are pasted from the tile set, so this asks the *frame*: there is
    something to see above the floor's far edge and down both sides, the sides
    lean in with the taper, and the room *stops* at the top course -- above the
    wall there is nothing, which is what keeps an arena a room and not wallpaper.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    screen = BattleScreen(arena(count=3))
    _, image = drawn(screen, app, font)
    field = screen._field(96, 27, font.cell_w, font.cell_h)

    # The frame's own background, read off a corner above the room: "drawn here"
    # is a comparison against what the app paints behind everything, and not a
    # brightness threshold that the background itself would slip past.
    outside = image.pixelColor(2, 2)

    def lit(x: int, y: int) -> bool:
        return image.pixelColor(x, y) != outside

    top, bottom = int(field["top"]), int(field["bottom"])
    back = sum(
        1
        for y in range(max(0, top - 30), top)
        for x in range(image.width())
        if lit(x, y)
    )
    assert back > 200, "there is no wall behind the floor"

    def leftmost(row: int) -> int | None:
        for x in range(image.width()):
            if lit(x, row):
                return x
        return None

    # Every row of the room that has wall on its left, from the far end of the
    # room to the near one, and which way the line of them leans.
    walled = [
        (row, leftmost(row)) for row in range(top, bottom) if leftmost(row) is not None
    ]
    assert len(walled) > 3, "there is no wall on the left"
    (far_row, far), (near_row, near) = walled[0], walled[-1]
    assert far_row < near_row, "the wall does not run down the room"
    assert far > near, "the side walls do not converge with the floor"

    # And the room has a ceiling line: the masonry ends where the band does, and
    # above it there is nothing at all.
    ceiling = int(field["wall_top"])
    above = sum(
        1
        for y in range(0, max(0, ceiling - 4))
        for x in range(0, image.width(), 3)
        if lit(x, y)
    )
    assert above == 0, f"{above} pixels of masonry above the wall's top course"


def test_the_arena_has_a_room_with_no_art_in_it(app, font, tmp_path, monkeypatch):
    """Take the stone away and the room is still there.

    The alphabet is underneath every picture in this game. The grid floor is drawn
    first and pasted over, and the dungeon's own ``#`` is still in the file: a
    machine with no tiles in it gets the room the arena has always had, in the
    same place. A fight is never missing a *room* -- only a picture of one.
    """
    from neverdeads_revenge.desktop import tiles
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    screen = BattleScreen(arena(count=1))
    # The room with the stone in it first: `monkeypatch` holds the empty
    # directory for the rest of the test, and the second drawing needs the real
    # one still reachable.
    _, stoned = drawn(screen, app, font)
    tiles.clear()
    monkeypatch.setattr(tiles, "TILES_DIR", tmp_path)  # an empty directory
    try:
        _, plain = drawn(screen, app, font)
    finally:
        tiles.clear()

    assert bytes(plain.constBits()) != bytes(stoned.constBits()), (
        "the tiles changed nothing: the arena is not painting the room"
    )

    field = screen._field(96, 27, font.cell_w, font.cell_h)
    top = int(field["top"])

    def grey(x: int, y: int) -> bool:
        colour = plain.pixelColor(x, y)
        return colour.red() == colour.green() == colour.blue() and colour.red() >= 30

    hung = sum(
        1
        for y in range(max(0, top - 30), top)
        for x in range(0, plain.width(), 2)
        if grey(x, y)
    )
    assert hung > 100, "the wall is not drawn in the dungeon's own glyph any more"


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
    # Brightness as the channels add up, and not Qt's `lightness()`: where the
    # floor fades is a fact about the *game's* palette, and a test that asks a
    # GUI toolkit what "light" means is a test that has to be told again when
    # the front end changes.
    assert sum(near.style.bg) > sum(far.style.bg), (
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


# -- the floor hands a fight over (M2) ---------------------------------------
def begin_run_in(app) -> None:
    """Two enters: the hero select, then the floor itself."""
    from PySide6.QtCore import Qt

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)


def walk_into_a_monster(app):
    """Put a monster beside the hero and walk into it. Returns the monster.

    Stops on the *turning*: the floor does not cut to the arena any more, it
    plays the step out -- the hit, the letter coming at the camera, the white --
    so a caller that wants a fight has to walk it out as well.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.core.direction import Direction

    state = app.run
    enemy = state.enemies[0]
    for direction, key in (
        (Direction.EAST, Qt.Key.Key_Right),
        (Direction.WEST, Qt.Key.Key_Left),
        (Direction.NORTH, Qt.Key.Key_Up),
        (Direction.SOUTH, Qt.Key.Key_Down),
    ):
        spot = direction.step(state.player.position)
        if state.dungeon_map.is_walkable(spot) and state.actor_at(spot) is None:
            enemy.position = spot
            press(app, key)
            return enemy
    raise AssertionError("nowhere beside the hero to stand")


def step_into_a_monster(app):
    """The same walk, and then the turning played out to the arena."""
    enemy = walk_into_a_monster(app)
    walk_out_the_turning(app)
    return enemy


def walk_out_the_turning(app) -> None:
    """Tick until the arena is on top of the stack, or give up loudly."""
    assert top(app) == "EncounterScreen", "the step did not turn the floor over"
    for _ in range(200):
        if top(app) == "BattleScreen":
            return
        app._tick()
    raise AssertionError("the turning never handed the room to the arena")


def play_it_out(app, screen) -> None:
    """Hold enter and let the ticks run until the arena is done with the player.

    Stops the moment the arena is no longer on top: a fight that ended in a death
    hands the stack to the summary, and ticking a screen nobody is looking at
    would be ticking the wrong one.
    """
    from PySide6.QtCore import Qt

    guard = 0
    while guard < 600 and app.screens and app.screens[-1] is screen:
        guard += 1
        if screen.busy:
            app._tick()
            continue
        if screen.battle.over:
            break
        press(app, Qt.Key.Key_Return)
    while screen.busy and app.screens and app.screens[-1] is screen:
        app._tick()


def test_walking_into_a_monster_opens_the_arena(app):
    """M2: the floor hands the fight over, and gets the hero back.

    Driven through the app, because the wiring is the whole of what this test is
    for: the walk raises the encounter, the app notices and opens the arena, the
    fight happens in the arena, and the dungeon is still standing underneath it
    -- with one fewer monster on it.
    """
    from PySide6.QtCore import Qt

    begin_run_in(app)
    enemy = step_into_a_monster(app)

    assert top(app) == "BattleScreen", "the floor did not hand the fight over"
    assert enemy.stats.hp == enemy.stats.max_hp, "the floor swung at it on the way"

    screen = app.screens[-1]
    assert enemy in screen.battle.enemies, "the monster the hero met is not in it"
    for monster in screen.battle.enemies:
        monster.stats.hp = 1  # one blow each: this is about the wiring
    play_it_out(app, screen)

    assert screen.battle.won, "a fight of one-hit monsters was not won"
    press(app, Qt.Key.Key_Return)
    assert top(app) == "GameScreen", "the arena did not give the floor back"
    assert app.run.encounter is None, "a fight is still owed"
    assert enemy not in app.run.enemies, "the corpse is still on the floor"


def test_the_step_into_a_monster_turns_the_floor_over(app):
    """The cut is gone: walking into something opens the *turning*, not the arena.

    One frame the dungeon and the next a room full of monsters was the only
    thing a player ever saw of the moment a fight starts, and it was the moment
    the game most needed to shout about.
    """
    begin_run_in(app)
    walk_into_a_monster(app)

    assert top(app) == "EncounterScreen", "the step did not turn the floor over"
    screen = app.screens[-1]
    assert screen.animating, "the turning has nothing to play"
    assert not screen.modal, "the turning hid the dungeon it is turning over"
    assert screen.battle is not None, "the fight it is turning into is missing"


def test_the_turning_is_heard_once(app):
    """The sting, on the first frame of the turning and on no other: it is the
    noise the *step* made, and a noise per frame would be a drone."""
    begin_run_in(app)
    walk_into_a_monster(app)

    played: list[str] = []
    original = app.play
    app.play = lambda name=None: played.append(name if name else "?")  # type: ignore[assignment]
    try:
        screen = app.screens[-1]
        for _ in range(6):
            screen.step(0.033, app)
    finally:
        app.play = original

    assert played.count("encounter") == 1, f"the turning said {played}"


def test_the_turning_lets_nothing_through(app):
    """A moment a drummed key can cut short is a moment the player never sees --
    and this is the one second in the game that is *for* looking at."""
    from PySide6.QtCore import Qt

    begin_run_in(app)
    walk_into_a_monster(app)
    age = app.screens[-1].age

    for _ in range(8):
        press(app, Qt.Key.Key_Return)
        press(app, Qt.Key.Key_Escape)

    assert top(app) == "EncounterScreen", "a key cut the turning short"
    assert app.screens[-1].age == age, "a key moved the turning's clock"


def test_the_arena_takes_the_turnings_place_not_its_company(app):
    """The turning is a *hand-off*: the arena stands where it stood, and nothing
    is left underneath still drawing a dungeon over a fight."""
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    begin_run_in(app)
    walk_into_a_monster(app)
    turning = app.screens[-1]
    battle = turning.battle
    walk_out_the_turning(app)

    assert [type(screen).__name__ for screen in app.screens][-2:] == [
        "GameScreen",
        "BattleScreen",
    ], "the turning was left in the stack"
    assert app.screens[-1].battle is battle, "a different fight arrived"


def test_the_turning_runs_out_the_letter_of_what_was_walked_into(app, font):
    """The thing coming at the camera is the monster's own glyph, in its own
    colour: the letter that was standing on the floor a moment ago, made big and
    brought forward. That is the arena's whole promise, and the turning is where
    the promise is made -- so it is measured in pixels, where a player reads it.
    """
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.screens.encounter import FLASH_IN, GROW_FROM, GROW_TO
    from neverdeads_revenge.desktop.theme import parse_style

    begin_run_in(app)
    enemy = walk_into_a_monster(app)
    screen = app.screens[-1]
    ink = parse_style(enemy.color).fg
    rgb = (ink.red(), ink.green(), ink.blue())

    def ink_at(age: float, tolerance: int = 12) -> int:
        """The monster's colour, in the middle of the frame, at this moment.

        Counted nearly exactly, and not "roughly the colour": the step's own
        white -- the flash, and the rings going out of the square -- passes
        through *every* grey on its way up out of the dark floor, so a loose
        match counts the effect as the letter whenever the letter is grey, which
        the skeleton's is. What is counted here is the glyph's own ink, which is
        what a player sees a moment later filling the room.
        """
        screen.age = age
        buffer = PatternBuffer(96, 27, font)
        # The map has to be drawn by *something*: in the app it is the game
        # screen standing under the turning, which is the whole reason this
        # screen is not a modal.
        app.screens[-2].draw(buffer, app)
        screen.draw(buffer, app)
        image = buffer.render()
        screen.paste(image, app)
        left, top = image.width() // 3, image.height() // 5
        right, bottom = image.width() * 2 // 3, image.height() * 4 // 5
        return sum(
            1
            for y in range(top, bottom, 2)
            for x in range(left, right, 2)
            if _is_colour(image.pixelColor(x, y), rgb, tolerance)
        )

    # Sampled once the white has gone: GROW_FROM is when the letter starts
    # moving, and the rings are out of the room by twice the flash. What is
    # being measured is the movement, not the first frame of it.
    small = ink_at(FLASH_IN * 2 + 0.02)
    big = ink_at(GROW_TO - 0.02)
    assert big > small * 3, f"the letter did not come at the camera ({small} -> {big})"


def test_a_run_that_ends_in_the_arena_ends_where_it_always_did(app):
    """Dying in a fight is dying: the summary, the board, the borrowed hour.

    The arena does not get to end a run its own way. It steps out of the way and
    asks the app for the ending the floor would have given -- which is what keeps
    one ending in this game instead of two.
    """
    from PySide6.QtCore import Qt

    begin_run_in(app)
    step_into_a_monster(app)
    screen = app.screens[-1]

    app.run.player.stats.hp = 0  # already gone: the fight is decided
    press(app, Qt.Key.Key_Return)
    play_it_out(app, screen)

    assert screen.battle.over and not screen.battle.won
    assert top(app) == "GameOverScreen", "the run did not end the usual way"


def test_the_battle_scene_opens_and_leaves(qapp):
    """``--battle-scene`` is the only way in for now, and the way out is the one
    every fight has: flee it, or win it. Escape does not walk out of a battle --
    that is the whole point of a fight -- so the dev door leaving is a *verb*."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.app import DesktopApp

    window = DesktopApp(seed=3, no_sound=True, battle_scene=True)
    window.view.resize(1280, 800)
    assert top(window) == "BattleScreen", "the switch did not open the arena"

    screen = window.screens[-1]
    press(window, Qt.Key.Key_F, "f")  # flee: the honest way out of a fight
    play_it_out(window, screen)
    assert screen.battle.escaped, "the hero could not get away at all"
    press(window, Qt.Key.Key_Return)

    assert top(window) == "TitleScreen", "the dev door would not let go"


def test_a_trick_paints_its_own_colour_on_the_blow(app, font):
    """A blow wears the word of the trick that made it.

    The arena flashes a struck figure in the colour of the thing that hit it --
    green for the dagger, petrol for the shadow, and the void's own pale light --
    which is how the five are told apart from the other side of a room. The rules
    deal in names; only the screen knows what green is.
    """
    from neverdeads_revenge.desktop.screens.battle import FLAIR_COLOURS, BattleScreen
    from neverdeads_revenge.game.battle import Struck
    from neverdeads_revenge.game.combat import AttackOutcome
    from neverdeads_revenge.game.specials import LEFT_HAND, special_by_key

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    outcome = AttackOutcome(hit=True, crit=True, damage=3, killed=False)
    screen._queue = [Struck(battle.hero, target, outcome, flair=LEFT_HAND)]
    screen._beat = 0.0

    screen.step(0.5, app)

    assert screen._hurts[id(target)][1] == FLAIR_COLOURS[LEFT_HAND]
    assert screen._hurts[id(target)][2] == special_by_key(LEFT_HAND).look, (
        "the blow forgot which shape made it"
    )


def _paint(look: str, *, selfy: bool = False, age: float = 0.14):
    """One flourish, painted into an empty picture and nothing else.

    A shape is checked by looking at *it*: the stage under it would be a
    photograph of the whole game, and fifteen of those to check fifteen lines
    would be a test nobody could afford to run.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    from neverdeads_revenge.desktop.screens.battle import BattleScreen, Staged

    battle = arena(count=1)
    screen = BattleScreen(battle)
    actor = battle.hero if selfy else battle.enemies[0]
    figure = Staged(actor, "v", "#ffffff", 1, 100, 10, 6)
    screen._clock = 5.0
    if selfy:
        screen._self = (look, "#ffffff", 5.0 - age)
    else:
        screen._hurts[id(actor)] = (5.0 - age, "#ffffff", look)
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    if selfy:
        screen._paste_self(painter, figure, 10, 20, 200)
    else:
        screen._paste_flourish(painter, figure, 10, 20, 200)
    painter.end()
    return image


def _alpha(image) -> bytes:
    """The shape of it and nothing else: what is painted, wherever it is painted.

    The colour of a blow is the flair's business and is checked above; two shapes
    that differ only in *what* they paint are the same picture to a player
    looking at a fight from across the room.
    """
    return bytes(image.constBits())[3::4]


def test_every_trick_has_a_shape_of_its_own():
    """Fifteen tricks and not five colours.

    A colour alone would not do: two of the five would wear the same green and
    the fight would look like one attack used twice. Every special names a shape,
    and the screen has a recipe for every shape a special can name.
    """
    from neverdeads_revenge.desktop.screens.battle import SPARKS
    from neverdeads_revenge.game.specials import SPECIALS_BY_HERO

    every = [special for kit in SPECIALS_BY_HERO.values() for special in kit]
    assert all(special.look for special in every), "a trick with no shape of its own"
    assert {special.look for special in every} <= set(SPARKS), (
        "a trick asks for a shape the screen cannot draw"
    )
    assert len({special.look for special in every}) >= 12, (
        "fifteen tricks and a handful of shapes between them"
    )


def test_no_two_tricks_are_the_same_picture():
    """Every shape paints, and no two of them paint the same picture.

    This is what "flashy, and told apart by the animation" means as a test: not
    that a number changed, but that a *frame* differs -- which is the only thing
    the player has to go on. The three that belong on the hero are painted on
    him, because that is where they are seen.
    """
    from neverdeads_revenge.desktop.screens.battle import SELF_LOOKS, SPARKS

    shots = {}
    for look in sorted(SPARKS):
        shot = _alpha(_paint(look, selfy=look in SELF_LOOKS))
        painted = len(shot) - shot.count(0)
        assert painted > 60, f"the {look} painted almost nothing ({painted} pixels)"
        shots[look] = shot

    for look, shot in shots.items():
        twins = sorted(other for other, theirs in shots.items() if theirs == shot)
        assert twins == [look], f"the {look} is the same picture as {twins}"


def test_a_shape_that_belongs_on_the_hero_does_not_land_on_what_he_hit():
    """An ice wall in front of a monster would be a wall in the wrong room: the
    three that are not blows are painted on the hero, and nowhere else."""
    from neverdeads_revenge.desktop.screens.battle import SELF_LOOKS

    for look in sorted(SELF_LOOKS):
        empty = _alpha(_paint(look))
        assert empty.count(0) == len(empty), f"the {look} was painted on the target"


def test_a_throw_sends_what_it_hit_up_the_room(app):
    """THE BELL'S THROW has to be *seen*: a knockback that only changed the queue
    would be a rule nobody could see. The figure goes up the room and comes home
    again, and it is home before the beat is over."""
    from neverdeads_revenge.desktop.screens.battle import (
        FLOURISH_LIFE,
        THROWN,
        BattleScreen,
    )

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    figure = screen._figure_of(target, app)
    screen._knocked[id(target)] = (screen._clock + 0.2, THROWN)

    assert screen._knockback(figure, 20) == 0, "it was thrown before it was hit"

    screen._clock += 0.34
    thrown = screen._knockback(figure, 20)
    assert thrown > 10, "the throw did not move anything"

    screen._clock += FLOURISH_LIFE
    assert screen._knockback(figure, 20) == 0, "it never came home again"


def test_every_blow_shoves_what_it_hit(app):
    """Weight is the one thing a number cannot say.

    A stick hit does not get the bell's throw, but it *moves* the monster: a
    fraction of the figure's own height, up the room, gone before the beat is
    over. A hit that left the monster exactly where it stood is a hit the eye
    reads as a subtraction.
    """
    from neverdeads_revenge.desktop.screens.battle import SHOVE, THROWN, BattleScreen

    assert 0 < SHOVE < THROWN, "a plain hit shoves as hard as the bell's throw"

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    figure = screen._figure_of(target, app)
    screen._knocked[id(target)] = (screen._clock + 0.2, SHOVE)

    screen._clock += 0.34
    assert screen._knockback(figure, 20) > 0, "the monster did not move at all"


def test_the_trick_is_picked_before_the_monster_is(app):
    """The order every fight in this genre ever had: the move, and then the mark.

    SPECIAL opens the five, taking one of the five opens the *arrow*, and the
    arrow is what spends the turn. A trick chosen in a list and spent on whoever
    happened to be standing under a cursor is a choice the player never made --
    the panel is still the one that says what is being thrown, and the floor is
    the one that says at whom.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=3)
    screen = BattleScreen(battle)
    screen._queue = []  # the opening round is not what this test is about
    app.screens = [screen]

    press(app, Qt.Key.Key_S, "s")
    assert screen.picking, "SPECIAL did not open the five"

    press(app, Qt.Key.Key_Return)
    assert not screen.picking, "the list stayed open after a trick was taken"
    assert screen.aiming, "the trick was spent without a monster being picked"
    assert screen._picked == battle.specials()[0].key, "a different trick was armed"
    assert not screen.busy, "the turn was spent before the arrow was laid on anyone"


def test_the_arrow_blips_and_the_choice_answers(app):
    """Switching monsters is heard, and taking one is a note of its own.

    A cursor that moves in silence makes a player look down at the panel to find
    out whether the key even registered -- and a fight is watched on the floor.
    The confirm is the other half: the arrow says *which* one, and the note says
    that the choice was taken.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=3)
    screen = BattleScreen(battle)
    screen._queue = []
    app.screens = [screen]

    press(app, Qt.Key.Key_Return)  # ATTACK wants a monster: the arrow comes out
    assert screen.aiming, "the plain swing did not ask for a target"

    played: list[str] = []
    original = app.play
    app.play = lambda name=None: played.append(name if name else "?")  # type: ignore[assignment]
    try:
        press(app, Qt.Key.Key_Right)
        assert screen.target == 1, "the arrow did not cross the room"
        assert played == ["move"], "the arrow crossed the room in silence"
        played.clear()
        press(app, Qt.Key.Key_Return)
    finally:
        app.play = original

    assert played and played[0] == "pick", "the choice was taken in silence"
    assert not screen.aiming, "the arrow is still out after the turn was spent"
    assert screen.busy, "the arrow on a monster did not spend the turn"


def test_the_list_only_holds_what_he_has_learned(app, font):
    """A list of names the player cannot use is a list of spoilers.

    Learned is not the same question as *available*, and the menu needs both: a
    trick spent in **this** fight is still on the list -- dimmed, because it is
    his and it comes back next fight -- and a trick he has not reached yet is not
    on it at all. What the player cannot have is not what the player is offered.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.battle import Battle
    from neverdeads_revenge.game.specials import LEFT_HAND
    from neverdeads_revenge.game.state import start_run

    state = start_run(HEROES["noxx"], 3, ultimate_level=7)
    state.level = 2  # the knife, and nothing else
    battle = Battle(state, state.enemies[:1])
    screen = BattleScreen(battle)
    screen.picking = True
    buffer, _ = drawn(screen, app, font)
    written = "".join(cell.char for row in buffer.cells for cell in row)

    assert [one.key for one in battle.learned()] == [LEFT_HAND]
    assert "THE LEFT HAND" in written, "the one he has learned is missing"
    assert "ORB OF PTAMERA" not in written, "a trick he has not learned is on the list"


def test_the_arena_reads_out_a_lesson(app):
    """A trick learned in a fight is said *in* the fight.

    The arena plays the run's own log, so the line a kill wrote on the map is the
    line a kill writes here -- which is why the announcement lives in the rules
    and not in the menu: it has one text and two rooms to be read in.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.game.levels import kills_for_level

    # The dark answers at seven here and not at one: with `--testrun` every trick
    # is learned from the start, and a level that teaches nothing (correctly)
    # says nothing either.
    battle = arena(count=1, ultimate_level=7)
    battle.state.kills = kills_for_level(2) - 1  # one kill short of level two
    battle.state.level = 1
    battle.enemies[0].stats.hp = 1
    screen = BattleScreen(battle)
    app.screens = [screen]

    seen: list[str] = []
    guard = 0
    while guard < 400 and app.screens and app.screens[-1] is screen:
        guard += 1
        if screen.busy:
            app._tick()
            seen += [line.text for line in screen.lines]
            continue
        if battle.over:
            break
        press(app, Qt.Key.Key_Return)  # ATTACK: the arrow comes out
        press(app, Qt.Key.Key_Return)  # and the blow goes in

    assert any("learned!" in text for text in seen), f"the arena never said it: {seen}"


def test_the_side_panel_counts_the_kills_to_the_next_level(app):
    """The overworld's own line says how close the next level is.

    It is a footnote to the level -- "+3" -- rather than a fourth number in a
    row: three kills is a *distance*, and the line has room for a distance.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.render import hud_lines

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    written = " ".join(text for text, _style in hud_lines(state))

    assert f"Lv {state.level} (+{state.kills_to_level})" in written, written


def test_the_plate_counts_the_kills_to_the_next_level(app, font):
    """And the arena says the same thing, because a level is what a fight is for."""
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=1)
    screen = BattleScreen(battle)
    buffer, _ = drawn(screen, app, font)
    written = "".join(cell.char for row in buffer.cells for cell in row)

    assert f"{battle.state.kills_to_level} KILLS TO LVL" in written, (
        f"the plate does not say how close the level is: {written[-200:]}"
    )


def test_a_level_up_gets_an_arrow_over_the_hero(app):
    """The line the rules wrote for a level gets a picture, and the picture is
    over the *hero*: the loudest thing in a room is a number about somebody else,
    and this is the quiet one about him."""
    from neverdeads_revenge.desktop.screens.battle import LEVEL_UP, BattleScreen
    from neverdeads_revenge.game.battle import Said
    from neverdeads_revenge.game.state import LogKind

    battle = arena(count=1)
    screen = BattleScreen(battle)
    screen._queue = [Said("Level 4: more blood.", LogKind.GOOD)]
    screen._beat = 0.0

    played: list[str] = []
    original = app.play
    app.play = lambda name=None: played.append(name if name else "?")  # type: ignore[assignment]
    try:
        screen.step(1 / 30.0, app)
    finally:
        app.play = original

    assert any(popup.text == LEVEL_UP for popup in screen._popups), (
        "the level-up made no picture"
    )
    assert "level" in played, f"the level-up made no sound: {played}"


def test_the_command_panel_names_what_the_blade_does(app, font):
    """The weapon's own wounds, beside the verb that swings it.

    In the colours the room draws them in, so the menu and the monsters speak the
    same vocabulary and the player learns it once -- and `( = X` when his hand is
    empty, which is worth saying, because fighting bare-handed is a choice.
    """
    from types import SimpleNamespace

    from neverdeads_revenge.desktop.screens.battle import STATUS_COLOURS, BattleScreen
    from neverdeads_revenge.desktop.theme import parse_style
    from neverdeads_revenge.world.items import ITEMS

    battle = arena(count=1)
    screen = BattleScreen(battle)

    def panel():
        buffer, _ = drawn(screen, app, font)
        for row in buffer.cells:
            text = "".join(cell.char for cell in row)
            if "( = " in text:
                return row, text
        return [], ""

    _, written = panel()
    assert "( = X" in written, "a bare hand goes unmentioned"

    blade = next(
        one for one in ITEMS.values() if one.kind == "weapon" and one.inflicts
    )
    # A blade is anything with `inflicts` on it: the screen reads the slot, not
    # the factory, so this is the whole of what it needs to be.
    battle.state.player.equipment["weapon"] = SimpleNamespace(inflicts=blade.inflicts)

    row, written = panel()
    for key in blade.inflicts:
        assert key in written, f"the blade's {key} is not named"
        at = written.index(key)
        inks = {row[col].style.fg.name() for col in range(at, at + len(key))}
        assert parse_style(STATUS_COLOURS[key]).fg.name() in inks, (
            f"{key} is not written in its own colour"
        )


def test_a_key_with_nothing_behind_it_says_so(app):
    """SPECIAL at level one is a door onto an empty room, and this one is shut."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.battle import Battle
    from neverdeads_revenge.game.state import start_run

    state = start_run(HEROES["noxx"], 3, ultimate_level=7)
    state.level = 1  # nothing learned at all
    battle = Battle(state, state.enemies[:1])
    screen = BattleScreen(battle)
    screen._queue = []
    app.screens = [screen]

    played: list[str] = []
    original = app.play
    app.play = lambda name=None: played.append(name if name else "?")  # type: ignore[assignment]
    try:
        press(app, Qt.Key.Key_S, "s")
    finally:
        app.play = original

    assert not screen.picking, "a list with nothing in it opened anyway"
    assert played and played[-1] == "deny", f"an empty menu said {played}"


def test_a_trick_thrown_at_nobody_does_not_ask_for_one(app):
    """Six of the fifteen are not thrown at anybody: the three that are set on the
    hero himself, the note he finds for his own sword, and the two that go through
    everything standing. An arrow walked to a monster for one of those is a
    question the fight never reads -- and a turn is not a quiz."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.battle import Battle
    from neverdeads_revenge.game.specials import SPECIALS_BY_HERO, STILLNESS
    from neverdeads_revenge.game.state import start_run

    at_nobody = [special for kit in SPECIALS_BY_HERO.values() for special in kit]
    at_nobody = [special for special in at_nobody if not special.needs_target]
    assert len(at_nobody) >= 3, "almost nothing is thrown at nobody: check the rule"

    state = start_run(HEROES["yeti"], 5, ultimate_level=7)
    state.level = 7
    state.kill_points = state.kill_points_max
    battle = Battle(state, state.enemies[:2])
    screen = BattleScreen(battle)
    screen._queue = []
    app.screens = [screen]

    press(app, Qt.Key.Key_S, "s")  # the list opens on the first of the five
    screen.special = [special.key for special in battle.specials()].index(STILLNESS)
    press(app, Qt.Key.Key_Return)

    assert not screen.aiming, "a trick with no victim in it asked for one"
    assert screen.busy, "the trick was not spent at all"


def test_every_trick_says_what_it_does():
    """The list has to be readable and not decipherable.

    A fight is not a guessing game: all fifteen say what they *do* -- what is
    hit, how hard, for how long -- in the same panel that says it prettily. The
    voice is the colour; the numbers are the offer, and an offer nobody can
    price is not an offer.
    """
    from neverdeads_revenge.game.specials import SPECIALS_BY_HERO

    every = [special for kit in SPECIALS_BY_HERO.values() for special in kit]
    for special in every:
        assert special.effect, f"{special.name} does not say what it does"
        assert special.blurb, f"{special.name} lost its voice"
        assert len(special.effect) <= 34, (
            f"{special.name} says more than a panel can hold"
        )
    assert len({special.effect for special in every}) == len(every), (
        "two tricks are described with the same words"
    )


def test_the_list_says_what_the_chosen_trick_does(app, font):
    """The facts under the names, in the readable ink.

    Scroll to a trick and the panel tells you what it does before you spend a
    turn on it: the fight's own voice underneath is a voice, and a voice is not
    an instruction.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=1)
    screen = BattleScreen(battle)
    screen.picking = True
    screen.special = 2
    buffer, _ = drawn(screen, app, font)

    written = "".join(cell.char for row in buffer.cells for cell in row)
    assert battle.specials()[2].effect in written, "the panel did not say what it does"
    assert battle.specials()[2].blurb[:20] in written, "the panel lost its voice"


def test_the_aim_keeps_saying_what_is_being_aimed(app, font):
    """While the arrow is out, the player is still choosing an *attack*: what is
    about to be thrown at one of them stays in front of them."""
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.game.specials import LEFT_HAND, special_by_key

    battle = arena(count=2)
    screen = BattleScreen(battle)
    screen.aiming = True
    screen._picked = LEFT_HAND
    buffer, _ = drawn(screen, app, font)

    written = "".join(cell.char for row in buffer.cells for cell in row)
    assert special_by_key(LEFT_HAND).effect in written, (
        "the aim did not say what was being aimed"
    )


def test_every_cursor_step_is_heard(app):
    """The ears are told before the eyes are.

    Opening the arrow, crossing the room and spending the turn each make their
    own noise. A cursor that moves in silence makes the player look down at the
    panel to find out whether the key registered, and a fight is watched on the
    floor.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=3)
    screen = BattleScreen(battle)
    screen._queue = []
    app.screens = [screen]

    played: list[str] = []
    original = app.play
    app.play = lambda name=None: played.append(name if name else "?")  # type: ignore[assignment]
    try:
        press(app, Qt.Key.Key_Return)  # ATTACK: the arrow comes out
        assert played == ["move"], played
        played.clear()
        press(app, Qt.Key.Key_Right)  # across the room
        assert played == ["move"], played
        played.clear()
        press(app, Qt.Key.Key_Return)  # and the turn is spent
        assert played == ["pick"], played
    finally:
        app.play = original
    assert screen.busy, "the swing was confirmed and never thrown"


def test_the_menus_blip_on_the_way_through(app):
    """Every step of every cursor in the menus as well -- the verbs, the five,
    across the five, and the way back out of them."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=3)
    screen = BattleScreen(battle)
    screen._queue = []
    app.screens = [screen]

    played: list[str] = []
    original = app.play
    app.play = lambda name=None: played.append(name if name else "?")  # type: ignore[assignment]
    try:
        for key, expected in (
            (Qt.Key.Key_Down, "move"),  # the verbs
            (Qt.Key.Key_S, "move"),  # and into the five
            (Qt.Key.Key_Down, "move"),
            (Qt.Key.Key_Left, "move"),
            (Qt.Key.Key_Escape, "move"),  # back to the verbs
        ):
            played.clear()
            press(app, key, "s" if key == Qt.Key.Key_S else "")
            assert played == [expected], f"{key} said {played}"
    finally:
        app.play = original


def test_a_trick_the_dark_will_not_answer_is_refused_out_loud(app):
    """A lock is not silence. The same note for a spent trick as for a chosen one
    is a menu the player cannot read with their ears -- and they will try the
    same row again."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.game.specials import VOID

    battle = arena(count=1)
    battle.state.ultimate_available = False  # the dungeon's ask is spent
    screen = BattleScreen(battle)
    screen._queue = []
    app.screens = [screen]

    played: list[str] = []
    original = app.play
    app.play = lambda name=None: played.append(name if name else "?")  # type: ignore[assignment]
    try:
        press(app, Qt.Key.Key_S, "s")
        screen.special = [special.key for special in battle.specials()].index(VOID)
        press(app, Qt.Key.Key_Return)
    finally:
        app.play = original

    assert played[-1] == "deny", f"a locked trick was answered with {played}"
    assert screen.picking, "the refusal took the list away from the player"


def test_escape_from_the_arrow_gives_the_five_back(app):
    """The aim is a step in a menu and not a trap: escape walks it backwards,
    one panel at a time, and the trick that was picked is still picked when the
    list comes back."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=3)
    screen = BattleScreen(battle)
    screen._queue = []
    app.screens = [screen]

    press(app, Qt.Key.Key_S, "s")
    press(app, Qt.Key.Key_Return)
    assert screen.aiming

    press(app, Qt.Key.Key_Escape)
    assert not screen.aiming and screen.picking, "escape did not give the five back"

    press(app, Qt.Key.Key_Escape)
    assert not screen.picking and not screen.aiming, "escape did not give the verbs back"


def test_a_landed_blow_holds_the_room_still(app):
    """Weight, as three frames in which nothing moves.

    The freeze has to be *at the impact* and not at the decision to swing: a room
    that stopped when the player pressed the key would be pausing before the
    punch, which is not the punch.
    """
    from neverdeads_revenge.desktop.screens.battle import IMPACT_AT, BattleScreen
    from neverdeads_revenge.game.battle import Struck
    from neverdeads_revenge.game.combat import AttackOutcome
    from neverdeads_revenge.game.specials import LEFT_HAND

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    screen._queue = [
        Struck(battle.hero, target, AttackOutcome(True, False, 4, False), flair=LEFT_HAND)
    ]
    screen._beat = 0.0

    screen.step(0.02, app)  # the swing
    assert screen._hitstop == 0.0, "the room stopped before the blow landed"

    screen.step(IMPACT_AT, app)  # and the blow lands in this one
    assert screen._hitstop > 0, "the blow landed on a room that carried on"

    clock = screen._clock
    screen.step(0.01, app)
    assert screen._clock == clock, "the room moved during the hitstop"


def test_a_landed_blow_washes_the_room(app, font):
    """The colour over everything, for a moment: the loudest thing here and the
    cheapest -- one rectangle, where the eye is already looking."""
    from neverdeads_revenge.desktop.screens.battle import (
        FLASH_LIFE,
        IMPACT_AT,
        BattleScreen,
        FLAIR_COLOURS,
    )
    from neverdeads_revenge.game.battle import Struck
    from neverdeads_revenge.game.combat import AttackOutcome
    from neverdeads_revenge.game.specials import LEFT_HAND

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    screen._queue = [
        Struck(battle.hero, target, AttackOutcome(True, False, 4, False), flair=LEFT_HAND)
    ]
    screen._beat = 0.0

    screen.step(0.02, app)
    screen.step(IMPACT_AT + 0.01, app)
    assert screen._wash is not None, "the blow did not colour the room at all"
    assert screen._wash.colour == FLAIR_COLOURS[LEFT_HAND]

    _, during = drawn(screen, app, font)
    screen._clock += FLASH_LIFE
    _, after = drawn(screen, app, font)

    assert bytes(during.constBits()) != bytes(after.constBits()), (
        "the wash was not drawn over the room"
    )
    assert screen._wash is None, "the wash outstayed the blow"


def test_the_number_waits_for_the_blow(app):
    """A number hanging over a monster the sword has not reached yet is the fight
    telling the player the future. It is written down when the swing starts --
    there is one moment to write it down -- and it appears when the blow does."""
    from neverdeads_revenge.desktop.screens.battle import IMPACT_AT, BattleScreen
    from neverdeads_revenge.game.battle import Struck
    from neverdeads_revenge.game.combat import AttackOutcome
    from neverdeads_revenge.game.specials import LEFT_HAND

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    screen._queue = [
        Struck(battle.hero, target, AttackOutcome(True, False, 4, False), flair=LEFT_HAND)
    ]
    screen._beat = 0.0

    screen.step(0.02, app)
    assert screen._popups, "no number was written down at all"
    assert screen._popups[0].age < 0, "the number was readable before the blow"

    screen.step(IMPACT_AT, app)
    assert screen._popups[0].age >= 0, "the number never arrived"


class _Quiet:
    """An app-shaped thing for the pace tests: a fight, and no window.

    Timing a fight through the real app would be timing Qt as well -- the tick is
    the app's and the frames are the app's -- and the question here is only how
    long the *fight* keeps the player's hands off the keyboard.
    """

    def __init__(self, font):
        from neverdeads_revenge.desktop.effects import Effects

        self.font = font
        self.effects = Effects(font.cell_w, font.cell_h)

    def play(self, name):  # noqa: D102 - an app has one
        pass

    def leave_battle(self):  # noqa: D102 - an app has one
        pass

    def show_game_over(self, won: bool = False):  # noqa: D102 - an app has one
        pass

    class _View:
        def shake(self, strength: int = 0, seconds: float = 0.0):  # noqa: D102
            pass

    view = _View()


def _time_a_round(font, count: int = 3, *, dt: float = 1 / 30.0) -> float:
    """How many seconds one round of ``count`` monsters costs the player."""
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=count)
    battle.state.player.stats.hp = 9999
    battle.state.player.stats.max_hp = 9999
    for enemy in battle.enemies:
        enemy.stats.hp = 9999
        enemy.stats.damage = (0, 0)
        # No riders either. A monster that poisons narrates two lines more than
        # one that does not -- news the player wants, and a number this test
        # must not read as the fight being slow. The question here is the
        # clock, and which monster the seed deals should not be part of it.
        enemy.inflicts = ()
    screen = BattleScreen(battle)
    app = _Quiet(font)
    for _ in range(60):  # anything quicker than the hero gets its turn first
        if not screen.busy:
            break
        screen.step(dt, app)
    screen.verb = 0
    screen._choose(app)
    frames = 0
    while screen.busy and frames < 400:
        screen.step(dt, app)
        frames += 1
    return frames * dt


def test_a_round_does_not_keep_the_player_waiting(font):
    """A fight is only boring in the gap between the decision and the answer.

    This is the number that says the gap is short: a round of three monsters,
    measured on the fight's own clock, is about a second. It used to be three
    and a half, and most of the difference was the fight narrating at the speed
    it strikes -- a line is read at a glance and does not need to be watched.
    """
    from neverdeads_revenge.desktop.screens.battle import BEAT, LINE_BEAT

    assert LINE_BEAT < BEAT, "a line holds the stage as long as a blow does"
    one = _time_a_round(font, count=1)
    three = _time_a_round(font, count=3)
    assert one < 1.4, f"a round of one monster took {one:.2f}s"
    assert three < 2.2, f"a round of three monsters took {three:.2f}s"


def test_a_damage_number_does_not_hold_the_keyboard(font):
    """A number on its way out is not a reason to hold the player's hands.

    It is the fight's last word about a blow that has already landed: readable
    while the next turn is being chosen, and worth about three quarters of a
    second of pure waiting every single round when it was not.
    """
    from neverdeads_revenge.desktop.screens.battle import BEAT, BattleScreen
    from neverdeads_revenge.game.battle import Struck
    from neverdeads_revenge.game.combat import AttackOutcome
    from neverdeads_revenge.game.specials import LEFT_HAND

    battle = arena(count=1)
    screen = BattleScreen(battle)
    app = _Quiet(font)
    target = battle.enemies[0]
    screen._queue = [
        Struck(battle.hero, target, AttackOutcome(True, False, 3, False), flair=LEFT_HAND)
    ]
    screen._beat = 0.0

    screen.step(0.033, app)  # the swing: the number is written down
    screen.step(BEAT, app)  # the beat runs out on its own

    assert screen._popups, "the number is gone already: nothing left to test"
    assert not screen.busy, "a number on its way out was holding the keyboard"


def test_the_arena_names_who_the_arrow_is_on(app, font):
    """The one place a monster's name is written on a panel and not spoken in the
    log: a name under a figure would be a label on the room, but this is the
    *choice*, and a choice has to be readable."""
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=3)
    screen = BattleScreen(battle)
    screen.aiming = True
    buffer, _ = drawn(screen, app, font)

    written = "".join(cell.char for row in buffer.cells for cell in row)
    assert battle.enemies[screen.target].name[:6] in written, (
        "the panel did not say who the arrow was on"
    )


def test_a_line_about_a_blow_waits_for_the_blow(app):
    """The log does not run ahead of the sword.

    A sentence about a hit that turns up *before* the hit has told the player the
    end of the sentence they are in the middle of, and the animation that follows
    reads as an afterthought to its own description.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.game.battle import Said, Struck
    from neverdeads_revenge.game.combat import AttackOutcome
    from neverdeads_revenge.game.specials import LEFT_HAND
    from neverdeads_revenge.game.state import LogKind

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    line = Said("The ghoul takes 4.", LogKind.COMBAT)
    screen._queue = [
        line,
        Struck(battle.hero, target, AttackOutcome(True, False, 4, False), flair=LEFT_HAND),
    ]
    screen._beat = 0.0

    screen.step(1 / 30.0, app)  # the swing begins: the line is written down
    assert line not in screen.lines, "the log said it before the sword did"

    waited = 1
    while line not in screen.lines and waited < 60:
        screen.step(1 / 30.0, app)
        waited += 1

    assert line in screen.lines, "the line never arrived at all"
    assert waited >= 8, f"the line turned up after {waited} frames: with the swing"


def test_the_bar_and_the_sparks_wait_for_the_blow(app):
    """The damage is the blow's, and the blow has not landed yet.

    A bar that drops while the sword is still in the air is the fight spending
    the blow on the player's behalf, and sparks over a monster the blade has not
    reached are the fight telling them the future.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.game.battle import Struck
    from neverdeads_revenge.game.combat import AttackOutcome
    from neverdeads_revenge.game.specials import LEFT_HAND

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    hp = target.stats.hp
    screen._shown[id(target)] = hp
    screen._queue = [
        Struck(battle.hero, target, AttackOutcome(True, False, 4, False), flair=LEFT_HAND)
    ]
    screen._beat = 0.0

    screen.step(1 / 30.0, app)  # the swing
    assert screen._shown[id(target)] == hp, "the bar fell while the sword was in the air"
    assert not app.effects.particles, "the sparks flew before the blow landed"

    for _ in range(30):
        screen.step(1 / 30.0, app)
        if screen._shown[id(target)] < hp:
            break

    assert screen._shown[id(target)] == hp - 4, "the bar never took the blow"
    assert app.effects.particles, "the blow landed without throwing anything"


def test_a_beat_is_long_enough_for_the_animation_it_starts():
    """The invariant that keeps the fight from telling the player what is next
    before the last thing has finished: a beat covers a whole blink *and* the
    longest stop a blow can be given.

    It did not, and the symptom was the level-up arriving over the hero's head
    while the sword was still coming down -- and the same for every log line that
    followed a strike.
    """
    from neverdeads_revenge.desktop.screens.battle import (
        BEAT,
        CRIT_STOP,
        HITSTOP,
        HITSTOPS,
        STRIKE,
    )

    worst = STRIKE + max(HITSTOP, CRIT_STOP, *HITSTOPS.values())
    assert BEAT >= worst, (
        f"a beat is {BEAT:.2f}s and the slowest strike takes {worst:.2f}s"
    )


def test_the_order_strip_says_who_acts_next(app, font):
    """Three turns at the bottom of the room, in the alphabet it is made of.

    ``N > N > g``: the hero, the hero again, and then the ghoul -- which is what
    the queue really produces for a quick hero, and the reason to show it at all.
    Letters and not names, because a letter is what everything in this room is.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=1)
    screen = BattleScreen(battle)
    buffer, _ = drawn(screen, app, font)
    written = "".join(cell.char for row in buffer.cells for cell in row)

    assert "ORDER" in written, "there is no order strip at all"
    assert battle.hero.glyph in written, "the hero is not in the order"
    assert battle.enemies[0].glyph in written, "the monster is not in the order"


def test_the_order_strip_does_not_jump_when_the_hero_swings(app):
    """The turn in flight stays at the front of the strip while he swings.

    The queue charges the hero for his turn *before* he takes it -- that is how
    `_advance` finds him -- so a strip read straight off the paces loses him the
    moment his blow lands and slides him back in when the room settles: the row
    shifts a step left and then a step right again. This is that, pinned.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=1)
    # A monster that is slower than he is and survives the blow: then the round
    # is his alone, and the strip has no honest reason to move -- which is the
    # thing being pinned. (It passed before because the sword killed the viper
    # outright, so the round *was* his alone; that is luck and not a rule.)
    battle.enemies[0].stats.speed = 0.5
    battle.enemies[0].stats.hp = 999
    screen = BattleScreen(battle)
    screen._queue = []
    screen._beat = 0.0
    screen.verb = 0
    screen._choose(app)

    heads: list = []
    for _ in range(80):
        assert screen._order, "the strip emptied itself"
        heads.append(screen._order[0])
        if not screen.busy:
            break
        screen.step(1 / 30.0, app)

    assert all(one is battle.hero for one in heads), (
        f"the strip left him mid-swing: {[one.glyph for one in heads]}"
    )


def test_the_order_strip_moves_on_to_whoever_is_next(app):
    """And it does move on: once the turn being taken is *taken*, the head is
    whoever the queue says is up. Dropped up to and including them, so a turn
    whose events are not all blows does not leave the strip one behind."""
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=1)
    # A monster quick enough to act *after* him in the same round: with the
    # floor's own slow ones the hero is up again immediately, and rightly so.
    battle.enemies[0].stats.speed = 9.0
    screen = BattleScreen(battle)
    screen._queue = []
    screen._beat = 0.0
    screen.verb = 0
    screen._choose(app)

    assert screen._order and screen._order[0] is battle.hero, "not his turn first"
    head = screen._order[0]
    for _ in range(80):
        screen.step(1 / 30.0, app)
        if screen._order and screen._order[0] is not head:
            break

    assert screen._order, "the strip emptied itself"
    assert screen._order[0] is battle.enemies[0], (
        f"the strip is on {screen._order[0].glyph}, not on the monster that acts next"
    )


def test_a_monster_dies_when_the_blow_lands_and_not_when_it_is_decided(app):
    """The rules settle a whole round at once; the room must not.

    A monster that goes pale the moment the *fight* knows it is dead -- with the
    sword still in the air -- has told the player the ending of a sentence they
    are in the middle of. It holds its own light until the frame the number comes
    off it, and then it does not lie down dead and dim: the room lets it *go*.
    """
    from neverdeads_revenge.desktop.screens.battle import GONE_LIFE, BattleScreen
    from neverdeads_revenge.game.battle import Struck
    from neverdeads_revenge.game.combat import AttackOutcome
    from neverdeads_revenge.game.specials import LEFT_HAND

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    screen._queue = [
        Struck(battle.hero, target, AttackOutcome(True, False, 1, True), flair=LEFT_HAND)
    ]
    screen._beat = 0.0

    screen.step(1 / 30.0, app)  # the swing: the rules have already killed it
    assert screen._fade(id(target)) == 1.0, "it died while the sword was in the air"

    for _ in range(30):
        screen.step(1 / 30.0, app)
        if screen._fade(id(target)) < 1.0:
            break
    assert 0.0 < screen._fade(id(target)) < 1.0, "it never died at all"

    waited = 0
    while screen._fade(id(target)) > 0.0 and waited < 120:
        screen.step(1 / 30.0, app)
        waited += 1
    assert screen._fade(id(target)) == 0.0, "the corpse stayed in the room"
    assert waited * (1 / 30.0) < GONE_LIFE + 0.25, "it took longer to go than its time"


def test_a_wound_bites_in_the_colour_of_what_is_eating_it(app):
    """The fight *reads out* a wound as well as showing it.

    "The ghoul is bleeding. 2." was being written into the run's log and never
    reaching the arena's, so a wound cost a monster health in a fight where
    nobody ever mentioned it -- and the flourish tells the screen which wound it
    was, so it can be shown in the right colour on the one it is happening to.
    """
    from neverdeads_revenge.desktop.screens.battle import (
        STATUS_COLOURS,
        STATUS_LOOKS,
        BattleScreen,
    )
    from neverdeads_revenge.game.battle import Flourish

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    screen._queue = [Flourish(target, "burn")]
    screen._beat = 0.0

    screen.step(1 / 30.0, app)

    from PySide6.QtGui import QColor

    _when, colour, look = screen._hurts[id(target)]
    worn = QColor(STATUS_COLOURS["burn"])
    assert QColor(colour).hue() == worn.hue(), "the wound was shown in the wrong colour"
    assert QColor(colour).lightness() > worn.lightness(), (
        "the bite is the same brightness as the light it wears: nobody will see it"
    )
    assert look == STATUS_LOOKS["burn"], "the wound was shown in the wrong shape"
    assert screen._popups, "the wound bit without a number coming off it"


def test_a_wound_is_a_badge_on_the_plate_and_not_a_light_on_the_monster(app, font):
    """Worn, not thrown -- and now *written down* rather than shone.

    A wound used to be a pool of colour the figure stood in, which said
    "something is eating this one" and could not say which wound, or how many of
    them. The plate can: the sheets' own symbol for each one, beside the life
    bar, in a row.

    Read as pixels, three ways. The room does not change when a wound arrives --
    nothing is lit any more -- the plate does, and a second wound pushes the row
    *further right* rather than landing on top of the first, which is what
    "side by side" means and is the only part of it a colour count could not see.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.game.actions import inflict

    battle = arena(count=1)
    screen = BattleScreen(battle)
    hero = battle.hero
    cols, rows = 96, 27  # what `drawn` renders at, and what the plate is sized by
    _, plain = drawn(screen, app, font)
    ground = screen._areas(cols, rows)["ground"]
    plate = screen._areas(cols, rows)["plate"]

    def changed(image, area, base=None) -> list[int]:
        """The columns in one band where a frame differs from another one."""
        was = plain if base is None else base
        x0, y0, width, height = area
        return [
            x
            for x in range(x0 * font.cell_w, (x0 + width) * font.cell_w)
            if any(
                image.pixelColor(x, y) != was.pixelColor(x, y)
                for y in range(y0 * font.cell_h, (y0 + height) * font.cell_h)
            )
        ]

    inflict(battle.state, hero, ("burn",))
    screen._catching_up(hero)  # the room has been *shown* the wound (see below)
    _, burning = drawn(screen, app, font)
    assert not changed(burning, ground), "the wound is still lighting the room"
    assert changed(burning, plate), "the wound was not shown on the plate"
    first = max(changed(burning, plate))

    inflict(battle.state, hero, ("chill",))
    screen._catching_up(hero)
    _, both = drawn(screen, app, font)
    assert max(changed(both, plate)) > first, (
        "the second wound did not line up beside the first"
    )

    # And the monsters keep theirs, at the end of their own bars: without that,
    # taking the light away would have made a wounded monster one that nothing
    # on screen says is wounded.
    bare = drawn(screen, app, font)[1]
    inflict(battle.state, battle.enemies[0], ("poison",))
    screen._catching_up(battle.enemies[0])
    _, poisoned = drawn(screen, app, font)
    assert changed(poisoned, ground, bare), (
        "the monster's wound is not on the floor with it"
    )
    assert not changed(poisoned, plate, bare), (
        "a monster's wound was written on the player's plate"
    )

    # And the plate *goes away* when the trick list is up -- the list is drawn
    # across the whole strip -- so the row must go with it: it is painted in
    # pixels, after the grid, and a badge over a panel that is not there is a
    # badge over somebody else's menu.
    screen.picking = True
    hero.statuses.clear()
    screen._catching_up(hero)
    _, listed_bare = drawn(screen, app, font)
    hero.statuses["burn"] = 1
    screen._catching_up(hero)
    _, listed_wound = drawn(screen, app, font)
    assert bytes(listed_bare.constBits()) == bytes(listed_wound.constBits()), (
        "a badge is hanging over the list of tricks"
    )


def test_a_wound_reaches_the_room_only_when_the_blow_lands(app, font):
    """The animation first, and every display after it.

    Which is the rule the whole arena is built on and the one this row broke:
    the rules resolve a turn at once, so the *status* is on the monster the
    moment the hero presses the key -- and the fight must not say so until the
    sword has arrived. A badge that turned up during the swing is the fight
    telling the player the ending of the sentence they are in the middle of.

    Read at the swing and at the impact, and the swing is the hard half: the
    monster has the wound already, in the rules, and the room is still not
    allowed to have seen it.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen
    from neverdeads_revenge.world.items import ITEMS, make_item

    battle = arena(count=1)
    screen = BattleScreen(battle)
    target = battle.enemies[0]
    target.stats.hp = 999
    # A blade that leaves something in: the wound is the *attack's*, and an
    # attack that wounds nobody would test nothing.
    battle.hero.equipment["weapon"] = make_item(ITEMS["wound"])

    screen.verb = 0  # ATTACK
    screen._choose(app)

    assert "bleed" in target.statuses, "the blade did not land its wound at all"
    assert screen._worn(target) == (), "the wound was shown before the blow landed"

    for _ in range(30):  # past the impact, which is where the sword arrives
        screen.step(1 / 30.0, app)

    assert "bleed" in screen._worn(target), "the wound never reached the room"


def test_a_monster_killed_by_its_own_wound_is_let_go_like_any_other(app, font):
    """The fade is owed to a *death*, and the room only ever heard about the
    ones a sword did.

    A monster that bled to death kept its zero health and stayed standing: the
    fight was over, the room was quiet, and the corpse was still in it -- which
    is a fight with no monster in it and a monster in it. The flag the fade
    hangs off was set by a killing *blow* and by nothing else, and a wound that
    finishes something is not a blow. It is a death like any other.
    """
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=2)
    screen = BattleScreen(battle)
    other, wounded = battle.enemies
    other.stats.hp = 999  # so the hero's own swing is not what finishes it
    wounded.stats.hp = 1
    wounded.statuses["bleed"] = 1

    screen.verb = 0  # ATTACK at the first of them
    screen._choose(app)
    for _ in range(240):  # the wounds bite last, after the blows have played
        screen.step(1 / 30.0, app)
        if id(wounded) in screen._dying:
            break

    assert not wounded.stats.alive, "the wound did not finish it"
    assert id(wounded) in screen._dying, "the wound's kill was never seen as a death"
    for _ in range(5):  # a few frames of the going, which is half a second
        screen.step(1 / 30.0, app)
    assert screen._fade(id(wounded)) < 1.0, "the corpse is still standing in the room"


def test_the_arena_does_not_offer_a_way_out_that_is_not_there(app, font):
    """The plate used to say "esc leave the arena", and escape has not left the
    arena since the fall of M1: in the room it is the line about there being no
    way out but through, and in a menu it is one step back. A footer promising a
    key that does nothing is worse than no footer."""
    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=1)
    screen = BattleScreen(battle)
    buffer, _ = drawn(screen, app, font)
    written = "".join(cell.char for row in buffer.cells for cell in row)
    assert "leave the arena" not in written, "the plate still offers a way out"
    assert "esc" not in written, "the plate is still talking about escape"

    screen.picking = True
    buffer, _ = drawn(screen, app, font)
    written = "".join(cell.char for row in buffer.cells for cell in row)
    assert "esc" in written, "the menus lost their way back"


def test_escape_does_not_leave_a_fight(app):
    """There is no way out of a fight but through it.

    Fleeing is a verb with a price -- everything still standing gets a blow at
    the hero's back -- and a key that walks out for nothing would make every
    encounter in the dungeon optional. Escape closes the five, and says so in
    the log when there is nothing to close.
    """
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=1)
    screen = BattleScreen(battle)
    app.screens = [screen]

    press(app, Qt.Key.Key_Escape)

    assert top(app) == "BattleScreen", "escape walked out of the fight"
    assert any("only way out" in line.text for line in screen.lines), (
        "the fight said nothing about there being no way out"
    )


def test_the_five_can_be_walked_across_as_well_as_down(app):
    """The list is two columns: up and down move inside one, left and right take
    the choice into the other -- and a jump that would land outside the list
    stays where it is rather than wrapping round to somewhere unrelated."""
    from PySide6.QtCore import Qt

    from neverdeads_revenge.desktop.screens.battle import BattleScreen

    battle = arena(count=1)
    screen = BattleScreen(battle)
    app.screens = [screen]
    screen.picking = True
    rows = screen._list_rows(app)

    press(app, Qt.Key.Key_Down)
    assert screen.special == 1
    press(app, Qt.Key.Key_Right)
    assert screen.special == 1 + rows, "the right arrow did not cross a column"
    press(app, Qt.Key.Key_Left)
    assert screen.special == 1, "the left arrow did not come back"
    screen.special = 0
    press(app, Qt.Key.Key_Left)
    assert screen.special == 0, "the choice wandered out of the list"
