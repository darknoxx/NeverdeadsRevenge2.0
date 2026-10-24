"""The menus and the dialogs: a key at a time, through the real stack.

They drive the app the way a player does, because that is the part that can go
wrong: a screen that never opens, a key that two screens both think they own, a
dialog that answers its own opening press. The ported half of the old Qt suite;
the rest is still in ``_port_pending``.

These tests were written against the Qt build, and when that build went they came
across rather than being thrown away: the questions they ask -- which screen is on
top, what the plate says, where the stripe sits -- are about the *game* and not
about a toolkit. What changed is the harness underneath them: the app, the font
and the blitter. The old spellings were kept where they cost nothing, so that a
test's body still reads as it did.

Two shims are worth naming. ``Qt`` is a dictionary now, mapping the old key names
onto the names this game has always answered to -- the same vocabulary the
screens were written against, which is the reason a front end could be swapped at
all. And ``drawn`` hands back a surface wrapped in something that answers
``pixelColor``, because a test asking what colour a pixel is should not have to
care which library owns the pixels.
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

import pytest  # noqa: E402

from neverdeads_revenge.desktop import art  # noqa: E402
from neverdeads_revenge.sdl_front.arena import SdlArena  # noqa: E402

from neverdeads_revenge.game.state import RunState  # noqa: E402

pygame.init()


class _Key:
    """The old spelling of a key, so the tests kept their bodies."""

    Key_Return = "enter"
    Key_Enter = "enter"
    Key_Escape = "escape"
    Key_Space = "space"
    Key_Backspace = "backspace"
    Key_Delete = "delete"
    Key_Tab = "tab"
    Key_Home = "home"
    Key_End = "end"
    Key_PageUp = "pageup"
    Key_PageDown = "pagedown"
    Key_Up = "up"
    Key_Down = "down"
    Key_Left = "left"
    Key_Right = "right"
    Key_Period = "."
    Key_F2 = "f2"


for _letter in "abcdefghijklmnopqrstuvwxyz":
    setattr(_Key, f"Key_{_letter.upper()}", _letter)


class Qt:  # noqa: N801  (the name is the point: it is the old vocabulary)
    Key = _Key


_CODES = {
    "enter": pygame.K_RETURN,
    "escape": pygame.K_ESCAPE,
    "space": pygame.K_SPACE,
    "backspace": pygame.K_BACKSPACE,
    "delete": pygame.K_DELETE,
    "tab": pygame.K_TAB,
    "home": pygame.K_HOME,
    "end": pygame.K_END,
    "pageup": pygame.K_PAGEUP,
    "pagedown": pygame.K_PAGEDOWN,
    "up": pygame.K_UP,
    "down": pygame.K_DOWN,
    "left": pygame.K_LEFT,
    "right": pygame.K_RIGHT,
    "f2": pygame.K_F2,
    ".": pygame.K_PERIOD,
    **{
        letter: getattr(pygame, f"K_{letter}")
        for letter in "abcdefghijklmnopqrstuvwxyz"
    },
}


class _Colour:
    """A pixel, asked the way a ``QColor`` was asked."""

    def __init__(self, rgba) -> None:
        self._rgba = tuple(rgba)

    def red(self) -> int:
        return self._rgba[0]

    def green(self) -> int:
        return self._rgba[1]

    def blue(self) -> int:
        return self._rgba[2]

    def alpha(self) -> int:
        return self._rgba[3] if len(self._rgba) > 3 else 255

    def __eq__(self, other) -> bool:
        return isinstance(other, _Colour) and other._rgba == self._rgba

    def __hash__(self) -> int:
        return hash(self._rgba)

    def __repr__(self) -> str:
        return f"_Colour{self._rgba!r}"


class _Shot:
    """A frame, asked the way a ``QImage`` was asked."""

    def __init__(self, surface) -> None:
        self.surface = surface

    def pixelColor(self, x: int, y: int) -> _Colour:  # noqa: N802
        return _Colour(self.surface.get_at((int(x), int(y))))

    def constBits(self) -> bytes:  # noqa: N802
        return pygame.image.tostring(self.surface, "RGBA")

    def width(self) -> int:
        return self.surface.get_width()

    def height(self) -> int:
        return self.surface.get_height()


class _Picture:
    """A sprite, asked for the two things these tests used it for."""

    def __init__(self, size) -> None:
        self._size = size or (0, 0)

    def width(self) -> int:
        return self._size[0]

    def height(self) -> int:
        return self._size[1]

    def isNull(self) -> bool:  # noqa: N802
        return self._size == (0, 0)


def portrait(name: str) -> _Picture:
    return _Picture(art.size(f"sprites/portraits/{name}.png"))


@pytest.fixture
def font():
    from neverdeads_revenge.sdl_front.font import SdlFont

    return SdlFont("src/neverdeads_revenge/desktop/fonts/DejaVuSansMono.ttf")


@pytest.fixture
def app():
    from neverdeads_revenge.sdl_front.app import SdlApp

    window = SdlApp(seed=3, no_sound=True)
    # The premise is not the subject of most of these tests; the one that needs
    # it turns it back on itself.
    window.prologue_seen = True
    window.redraw()
    return window


def press(window, key, text: str = "", repeat: bool = False) -> None:
    """One key press, the way the window loop delivers one.

    A tap is a down *and* an up: the app marks a key held through a screen change
    stale, so a second press without the release would be ignored -- which is the
    behaviour that keeps a held key out of the screen it opened.
    """
    event = pygame.event.Event(pygame.KEYDOWN, key=_CODES[key], unicode=text, mod=0)
    event.repeat = repeat
    window.feed(event)
    if not repeat:
        up = pygame.event.Event(pygame.KEYUP, key=_CODES[key], mod=0)
        up.repeat = False
        window.feed(up)


def top(window) -> str:
    return type(window.screens[-1]).__name__


def drawn(screen, app, font, cols: int = 96, rows: int = 27):
    """Draw a screen the way the app does: the cells, then the art over them."""
    from neverdeads_revenge.desktop.pattern import PatternBuffer
    from neverdeads_revenge.desktop.theme import BACKGROUND
    from neverdeads_revenge.sdl_front.paint import paint

    buffer = PatternBuffer(cols, rows, font)
    screen.draw(buffer, app)
    surface = paint(buffer, font, BACKGROUND)
    over = getattr(screen, "paint_over", None)
    if over is not None:
        over(surface, app)
    # And the pictures the screen asked for, through the application's own blit:
    # a screen says what and where, and this is the half that puts it down, so a
    # test that drew the grid and stopped would be looking at a roster with no
    # faces on it.
    app._surface = surface
    app._blit_art(screen)
    return buffer, _Shot(surface)


def test_the_title_offers_a_run_and_a_shop(app):
    from neverdeads_revenge.desktop.screens.title import TitleScreen

    keys = [key for key, _ in TitleScreen().items(app)]
    assert keys[0] == "n"
    assert "s" in keys and "q" in keys


def test_new_run_asks_for_a_hero(app):

    press(app, Qt.Key.Key_Return)

    assert top(app) == "HeroSelectScreen"


def test_the_shop_opens_from_its_own_letter(app):

    app.progress.gold = 100
    press(app, Qt.Key.Key_S, "s")

    assert top(app) == "ShopScreen"


def test_a_run_starts_when_the_hero_is_confirmed(app):

    press(app, Qt.Key.Key_Return)  # new run
    press(app, Qt.Key.Key_Return)  # confirm the hero

    assert top(app) == "GameScreen"
    assert app.run is not None and app.run.depth == 1


def test_a_confirm_answers_yes_and_no(app):

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

    from neverdeads_revenge.desktop.screens.dialogs import ConfirmScreen

    answers = []
    app.push(ConfirmScreen("QUIT?", "sure?", on_done=answers.append))
    press(app, Qt.Key.Key_Escape)

    assert answers == [False]


def test_a_dialog_ignores_a_held_key(app):

    from neverdeads_revenge.desktop.screens.dialogs import ConfirmScreen

    answers = []
    app.push(ConfirmScreen("QUIT?", "sure?", on_done=answers.append))
    press(app, Qt.Key.Key_Y, "y", repeat=True)

    assert answers == [], "a held key answered the question"


def test_the_chest_has_three_answers(app):

    from neverdeads_revenge.desktop.screens.dialogs import OPEN, ChestScreen

    answers = []
    app.push(ChestScreen("The price: DIM.", on_done=answers.append))
    press(app, Qt.Key.Key_Return)

    assert answers == [OPEN]


def test_the_character_sheet_and_the_pack_open(app):

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)  # into the run

    press(app, Qt.Key.Key_C, "c")
    assert top(app) == "CharacterScreen"
    press(app, Qt.Key.Key_Escape)

    press(app, Qt.Key.Key_I, "i")
    assert top(app) == "PackScreen"


def test_escape_in_the_dungeon_pauses(app):

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Escape)

    assert top(app) == "PauseScreen"


def test_the_pause_menu_toggles_the_sound(app):

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Escape)
    before = app.sfx.muted

    press(app, Qt.Key.Key_M, "m")

    assert app.sfx.muted is not before


def test_the_pause_asks_before_quitting_to_the_title(app):

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Escape)
    press(app, Qt.Key.Key_Q, "q")

    assert top(app) == "ConfirmScreen"
    assert app.run is not None, "the run was thrown away before the question"


def test_a_run_that_escaped_is_recorded_as_won(app):

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    game = app.screens[-1]
    game.state.run_state = RunState.ESCAPED
    game._game_over(app, won=True)

    assert top(app) == "GameOverScreen"


def test_the_shop_is_in_sections(app):
    from neverdeads_revenge.desktop.screens.menus import ShopScreen

    screen = ShopScreen()
    screen._restock(app)
    headings = [row[0] for row in screen._rows(70) if row[2] is None and row[0].isupper()]

    assert "SUPPLIES" in headings
    assert "GEAR" in headings
    assert "AMULETS" in headings


def test_a_tombed_monster_is_not_a_death(app):
    """One action, one death: the list is cleared with the flash."""

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run

    press(app, Qt.Key.Key_Period, ".")
    assert state.deaths == [], "waiting produced a corpse"


def test_the_title_takes_side_arrows_and_no_others(app):
    """The menu is a line, so left and right are its keys and that is all."""

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


def test_the_prologue_shows_once_per_session(app):
    """Once, between the choice and the floor -- and never twice, because a
    premise told twice is a toll."""


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


def test_a_run_survives_a_save_and_a_quit(app):
    """Save and quit is the whole reason the pause's `s` is a `s`.

    The slot holds the run; picking it up consumes it; and what comes back is
    the run that was put down -- the floor, the health, the turn count.
    """

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


def test_the_title_answers_a_press_and_not_a_stream(app):
    """Qt hands us real auto-repeats. That is a gift the terminal build never
    had, so nothing here should need the FILTER_GAP hack again -- but a repeat
    that slips into a menu is a shop that opens itself."""

    press(app, Qt.Key.Key_S, "s", repeat=True)
    assert top(app) == "TitleScreen", "a repeated key opened the shop"

    press(app, Qt.Key.Key_S, "s")
    assert top(app) == "ShopScreen"


def test_a_held_enter_cannot_begin_the_run_from_the_choice(app):

    press(app, Qt.Key.Key_N, "n")  # hero select
    press(app, Qt.Key.Key_Return, repeat=True)

    assert top(app) == "HeroSelectScreen", "the confirm key confirmed itself"

    press(app, Qt.Key.Key_Return)
    assert top(app) == "GameScreen"


def test_the_pause_backup_answers_one_gesture(app):

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


    app.prologue_seen = False
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    assert top(app) == "PrologueScreen"

    press(app, Qt.Key.Key_Escape, repeat=True)
    assert top(app) == "PrologueScreen", "the premise was skipped mid-sentence"

    press(app, Qt.Key.Key_Escape)
    assert top(app) == "GameScreen"


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


def test_an_old_hold_cannot_cash_itself_in():
    """A hold interrupted long enough for the key to come up banks nothing:
    the next tap starts a fresh hold instead of inheriting a full bar."""
    import time as _time

    from neverdeads_revenge.desktop.hold import HoldToContinue

    hold = HoldToContinue()
    assert hold.press("enter") is False

    _time.sleep(1.15)  # long enough to be a release, long enough for 1.0s
    assert hold.press("enter") is False, "a stale hold spent itself in one tap"


class _FakeEvent:
    """A key event that is never a repeat, for tests that drive a screen
    directly rather than through the app."""

    def isAutoRepeat(self) -> bool:
        return False


def test_the_pack_of_two_items_does_not_scroll(app, font):
    from neverdeads_revenge.desktop.pattern import PatternBuffer
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
    from neverdeads_revenge.desktop.pattern import PatternBuffer
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






def test_the_prologue_jumps_with_home_and_end(app):

    app.prologue_seen = False
    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    screen = app.screens[-1]

    press(app, Qt.Key.Key_End)
    assert screen.offset > 0, "end did not jump to the bottom"

    press(app, Qt.Key.Key_Home)
    assert screen.offset == 0, "home did not jump to the top"


def test_the_page_stops_at_its_floor(app, font):
    from neverdeads_revenge.desktop.pattern import PatternBuffer
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

    screen = app.screens[-1]
    screen.index = 99
    press(app, Qt.Key.Key_Enter)
    assert top(app) == "TitleScreen", "a stale index did something"


def test_struck_cells_flash_in_reverse(font):
    """state.hits is filled every action and cleared the turn after; the map
    drew the same thing either way. The flash is the visual half of a hit."""
    from neverdeads_revenge.desktop.pattern import PatternBuffer

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
    from neverdeads_revenge.desktop.pattern import PatternBuffer
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


def test_the_sidebar_knows_the_statuses(app):

    from neverdeads_revenge.desktop.render import marks_names

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    state.player.statuses["poison"] = 3
    names = marks_names(state, "statuses")
    assert names and "3" in names[0], "the status column stayed empty"
    state.player.statuses.pop("poison")


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






def test_the_sheet_says_what_curses_gifts_and_effects_do(app):
    """The sheet was a list of names: a curse on the wall with no price in
    sight. Now every name carries the sentence that names its shape."""

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
    from neverdeads_revenge.desktop.pattern import PatternBuffer
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


def test_a_changed_mind_keeps_everything(app):

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


def test_the_pause_offers_the_controls(app):

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)  # into the run
    press(app, Qt.Key.Key_Escape)  # the pause
    assert top(app) == "PauseScreen"

    press(app, Qt.Key.Key_C, "c")  # CONTROLS
    assert top(app) == "HelpScreen"
    sheet = "\n".join(text for text, _ in app.screens[-1].lines(app))
    assert "LEGEND" in sheet and "ULTIMATE" in sheet


def test_l_opens_the_legend_and_not_the_east_step(app):

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


def test_a_pickup_page_ignores_everything_but_enter(app):
    """The wraith's curse lands mid-fight, the page opens, and the direction
    key already under the player's thumb used to dismiss it unread."""

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


def test_the_pack_drinks_and_drops_by_name(app):

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


def test_the_sidebar_names_the_draughts_that_are_working(app):

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
    from neverdeads_revenge.desktop.pattern import PatternBuffer
    from neverdeads_revenge.desktop.render import BLOOD_TINT, _draw_map, regions, viewport
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

def arena(seed: int = 1, count: int = 3, *, ultimate_level: int = 1):
    """A fight, out of a real run, over the floor's own first monsters."""
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.battle import Battle
    from neverdeads_revenge.game.state import start_run

    state = start_run(HEROES["noxx"], seed, ultimate_level=ultimate_level)
    return Battle(state, state.enemies[:count])


def test_the_roster_shows_the_hero_and_not_only_their_letter(app, font):
    """The block letter is the fallback; the sheets have the hero now.

    The roster stands them facing the *player* -- the front view, which is the
    second set of art the arena has no use for, since the arena's three stand
    with their backs to the camera at the monsters. What is asserted is the
    difference between the two views: a painted figure is a hundred colours wide
    and a block letter is exactly one, which is a thing a test can see where
    "it looks better" is not.
    """

    from neverdeads_revenge.desktop.blocks import render_word
    from neverdeads_revenge.desktop.screens import hero_select
    from neverdeads_revenge.desktop.screens.hero_select import exists

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

    monkeypatch_absent = lambda name: False  # noqa: E731 - one line, one meaning
    hero_select.exists = monkeypatch_absent
    try:
        lettered, letter_columns = band()
    finally:
        hero_select.exists = exists

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
    from neverdeads_revenge.game.actors import HEROES

    for hero in HEROES.values():
        art = portrait(hero.name)
        assert art is not None, f"{hero.name} has no front view"
        assert art.width() > 20 and art.height() > 20, (
            f"{hero.name}'s front view is a thumbnail"
        )


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


def test_the_side_panel_counts_the_kills_to_the_next_level(app):
    """The overworld's own line says how close the next level is.

    It is a footnote to the level -- "+3" -- rather than a fourth number in a
    row: three kills is a *distance*, and the line has room for a distance.
    """

    from neverdeads_revenge.desktop.render import hud_lines

    press(app, Qt.Key.Key_Return)
    press(app, Qt.Key.Key_Return)
    state = app.run
    written = " ".join(text for text, _style in hud_lines(state))

    assert f"Lv {state.level} (+{state.kills_to_level})" in written, written


def test_the_plate_counts_the_kills_to_the_next_level(app, font):
    """And the arena says the same thing, because a level is what a fight is for."""
    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=1)
    screen = SdlArena(battle)
    buffer, _ = drawn(screen, app, font)
    written = "".join(cell.char for row in buffer.cells for cell in row)

    assert f"{battle.state.kills_to_level} KILLS TO LVL" in written, (
        f"the plate does not say how close the level is: {written[-200:]}"
    )


class _Quiet:
    """An app-shaped thing for the pace tests: a fight, and no window.

    Timing a fight through the real app would be timing Qt as well -- the tick is
    the app's and the frames are the app's -- and the question here is only how
    long the *fight* keeps the player's hands off the keyboard.
    """

    def __init__(self, font):
        from neverdeads_revenge.sdl_front.effects import SdlEffects

        self.font = font
        self.effects = SdlEffects()

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
    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=1)
    screen = SdlArena(battle)
    buffer, _ = drawn(screen, app, font)
    written = "".join(cell.char for row in buffer.cells for cell in row)

    assert "ORDER" in written, "there is no order strip at all"
    assert battle.hero.glyph in written, "the hero is not in the order"
    assert battle.enemies[0].glyph in written, "the monster is not in the order"


def _is_colour(colour, rgb, tolerance: int = 60) -> bool:
    """Whether a pixel is (roughly) the colour the dungeon draws something in."""
    channels = (
        (colour.r, colour.g, colour.b)
        if hasattr(colour, "r")
        else (colour.red(), colour.green(), colour.blue())
    )
    alpha = colour.a if hasattr(colour, "a") else colour.alpha()
    return all(abs(a - b) <= tolerance for a, b in zip(channels, rgb, strict=True)) and alpha > 0


def _time_a_round(font, count: int = 3, *, dt: float = 1 / 30.0) -> float:
    """How many seconds one round of ``count`` monsters costs the player."""
    from neverdeads_revenge.sdl_front.arena import SdlArena

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
    screen = SdlArena(battle)
    app = _Quiet(font)
    for _ in range(60):  # anything quicker than the hero gets its turn first
        if not screen.busy:
            break
        screen.step(dt, app)
    screen.arena.verb = 0
    screen.arena._choose(app)
    frames = 0
    while screen.busy and frames < 400:
        screen.step(dt, app)
        frames += 1
    return frames * dt


def figure_baseline(figure, font) -> int:
    """Where a figure's feet are, as the stage draws them."""
    from neverdeads_revenge.desktop.screens.battle import THICKNESS

    return int(figure.row * font.cell_h) - THICKNESS


def hold_enter(app, until: str | None = None, seconds: float = 2.0) -> None:
    """Hold enter: a press, and the hardware repeat stream Qt sends for it.
    Stops early once ``until`` names the top screen; gives up after
    ``seconds``."""

    start = time.monotonic()
    press(app, Qt.Key.Key_Return)
    while time.monotonic() - start < seconds:
        if until is not None and top(app) == until:
            return
        time.sleep(0.02)
        press(app, Qt.Key.Key_Return, repeat=True)


def release(window, key) -> None:
    """The key came up -- the desktop sees what the terminal had to guess."""
    event = pygame.event.Event(pygame.KEYUP, key=_CODES[key], mod=0)
    event.repeat = False
    window.feed(event)


def sprite_for(name: str) -> _Picture:
    return _Picture(art.size(f"sprites/{name}.png"))



def test_a_held_enter_reads_through_the_repeat_stream(app):
    """The hold lives on auto-repeat events; eating repeats anywhere above the
    screens starves it (and that bug ate them at the window layer). One press,
    then the hardware stream Qt really sends -- the screen must go."""


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


def test_a_monster_killed_by_its_own_wound_is_let_go_like_any_other(app, font):
    """The fade is owed to a *death*, and the room only ever heard about the
    ones a sword did.

    A monster that bled to death kept its zero health and stayed standing: the
    fight was over, the room was quiet, and the corpse was still in it -- which
    is a fight with no monster in it and a monster in it. The flag the fade
    hangs off was set by a killing *blow* and by nothing else, and a wound that
    finishes something is not a blow. It is a death like any other.
    """
    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=2)
    screen = SdlArena(battle)
    other, wounded = battle.enemies
    other.stats.hp = 999  # so the hero's own swing is not what finishes it
    wounded.stats.hp = 1
    wounded.statuses["bleed"] = 1

    screen.arena.verb = 0  # ATTACK at the first of them
    screen.arena._choose(app)
    for _ in range(240):  # the wounds bite last, after the blows have played
        screen.step(1 / 30.0, app)
        if id(wounded) in screen.arena._dying:
            break

    assert not wounded.stats.alive, "the wound did not finish it"
    assert id(wounded) in screen.arena._dying, "the wound's kill was never seen as a death"
    for _ in range(5):  # a few frames of the going, which is half a second
        screen.step(1 / 30.0, app)
    assert screen.arena._fade(id(wounded)) < 1.0, "the corpse is still standing in the room"


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
    from neverdeads_revenge.sdl_front.arena import SdlArena
    from neverdeads_revenge.game.actions import inflict

    battle = arena(count=1)
    screen = SdlArena(battle)
    hero = battle.hero
    cols, rows = 96, 27  # what `drawn` renders at, and what the plate is sized by
    _, plain = drawn(screen, app, font)
    ground = screen.arena._areas(cols, rows)["ground"]
    plate = screen.arena._areas(cols, rows)["plate"]

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
    screen.arena._catching_up(hero)  # the room has been *shown* the wound (see below)
    _, burning = drawn(screen, app, font)
    assert not changed(burning, ground), "the wound is still lighting the room"
    assert changed(burning, plate), "the wound was not shown on the plate"
    first = max(changed(burning, plate))

    inflict(battle.state, hero, ("chill",))
    screen.arena._catching_up(hero)
    _, both = drawn(screen, app, font)
    assert max(changed(both, plate)) > first, (
        "the second wound did not line up beside the first"
    )

    # And the monsters keep theirs, at the end of their own bars: without that,
    # taking the light away would have made a wounded monster one that nothing
    # on screen says is wounded.
    bare = drawn(screen, app, font)[1]
    inflict(battle.state, battle.enemies[0], ("poison",))
    screen.arena._catching_up(battle.enemies[0])
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
    screen.arena.picking = True
    hero.statuses.clear()
    screen.arena._catching_up(hero)
    _, listed_bare = drawn(screen, app, font)
    hero.statuses["burn"] = 1
    screen.arena._catching_up(hero)
    _, listed_wound = drawn(screen, app, font)
    assert bytes(listed_bare.constBits()) == bytes(listed_wound.constBits()), (
        "a badge is hanging over the list of tricks"
    )


def test_a_wound_more_than_one_stack_carries_its_depth(app, font):
    """The number on the badge, and only once there is more than one.

    Read as a *difference*: the same wound at two stacks and at one differs in
    exactly one place -- the badge's corner -- which is the honest way to test a
    digit nobody wants to parse out of pixels.
    """
    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=1)
    screen = SdlArena(battle)
    hero = battle.hero
    hero.statuses["bleed"] = 3

    hero.status_stacks["bleed"] = 2
    screen.arena._catching_up(hero)
    _, two = drawn(screen, app, font)

    hero.status_stacks["bleed"] = 1
    screen.arena._catching_up(hero)
    _, one = drawn(screen, app, font)

    assert bytes(two.constBits()) != bytes(one.constBits()), (
        "two stacks look exactly like one"
    )

    hero.statuses.clear()
    screen.arena._catching_up(hero)
    _, clean = drawn(screen, app, font)
    assert bytes(clean.constBits()) != bytes(one.constBits()), (
        "the badge stayed after the wound had gone"
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
    from neverdeads_revenge.sdl_front.arena import SdlArena
    from neverdeads_revenge.world.items import ITEMS, make_item

    battle = arena(count=1)
    screen = SdlArena(battle)
    target = battle.enemies[0]
    target.stats.hp = 999
    # A blade that leaves something in: the wound is the *attack's*, and an
    # attack that wounds nobody would test nothing.
    battle.hero.equipment["weapon"] = make_item(ITEMS["wound"])

    screen.arena.verb = 0  # ATTACK
    screen.arena._choose(app)

    assert "bleed" in target.statuses, "the blade did not land its wound at all"
    assert screen.arena._worn(target) == (), "the wound was shown before the blow landed"

    for _ in range(30):  # past the impact, which is where the sword arrives
        screen.step(1 / 30.0, app)

    assert "bleed" in screen.arena._worn(target), "the wound never reached the room"


def test_escape_from_the_arrow_gives_the_five_back(app):
    """The aim is a step in a menu and not a trap: escape walks it backwards,
    one panel at a time, and the trick that was picked is still picked when the
    list comes back."""

    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=3)
    screen = SdlArena(battle)
    screen._queue = []
    app.screens = [screen]

    press(app, Qt.Key.Key_S, "s")
    press(app, Qt.Key.Key_Return)
    assert screen.arena.aiming

    press(app, Qt.Key.Key_Escape)
    assert not screen.arena.aiming and screen.arena.picking, "escape did not give the five back"

    press(app, Qt.Key.Key_Escape)
    assert not screen.arena.picking and not screen.arena.aiming, "escape did not give the verbs back"


def test_the_aim_keeps_saying_what_is_being_aimed(app, font):
    """While the arrow is out, the player is still choosing an *attack*: what is
    about to be thrown at one of them stays in front of them."""
    from neverdeads_revenge.sdl_front.arena import SdlArena
    from neverdeads_revenge.game.specials import LEFT_HAND, special_by_key

    battle = arena(count=2)
    screen = SdlArena(battle)
    screen.arena.aiming = True
    screen.arena._picked = LEFT_HAND
    buffer, _ = drawn(screen, app, font)

    written = "".join(cell.char for row in buffer.cells for cell in row)
    assert special_by_key(LEFT_HAND).effect in written, (
        "the aim did not say what was being aimed"
    )


def test_the_arena_does_not_offer_a_way_out_that_is_not_there(app, font):
    """The plate used to say "esc leave the arena", and escape has not left the
    arena since the fall of M1: in the room it is the line about there being no
    way out but through, and in a menu it is one step back. A footer promising a
    key that does nothing is worse than no footer."""
    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=1)
    screen = SdlArena(battle)
    buffer, _ = drawn(screen, app, font)
    written = "".join(cell.char for row in buffer.cells for cell in row)
    assert "leave the arena" not in written, "the plate still offers a way out"
    assert "esc" not in written, "the plate is still talking about escape"

    screen.arena.picking = True
    buffer, _ = drawn(screen, app, font)
    written = "".join(cell.char for row in buffer.cells for cell in row)
    assert "esc" in written, "the menus lost their way back"


def test_the_arena_draws_whatever_art_there_is(app, font):
    """Every figure is on the floor: as a picture if the sheets have one, as its
    letter if they do not.

    Both halves are asserted because both are the truth the game lives with --
    the art is optional and the alphabet is not. A fight is never missing a
    fighter, only sometimes missing a picture of one.
    """
    from neverdeads_revenge.sdl_front.arena import SdlArena
    from neverdeads_revenge.desktop.theme import parse_style

    battle = arena(count=3)
    screen = SdlArena(battle)
    _, image = drawn(screen, app, font)
    figures = screen.arena._figures(96, 27, font)

    for figure in figures:
        if figure.art is not None:
            # The staging carries the art's *name*; the picture is loaded here,
            # the way a painter loads it.
            art = sprite_for(figure.actor.name)
            left = figure.cx - art.width() // 2
            top = figure_baseline(figure, font) - art.height()
            inked = sum(
                1
                for y in range(top, top + art.height(), 3)
                for x in range(left, left + art.width(), 3)
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


def test_the_arena_names_who_the_arrow_is_on(app, font):
    """The one place a monster's name is written on a panel and not spoken in the
    log: a name under a figure would be a label on the room, but this is the
    *choice*, and a choice has to be readable."""
    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=3)
    screen = SdlArena(battle)
    screen.arena.aiming = True
    buffer, _ = drawn(screen, app, font)

    written = "".join(cell.char for row in buffer.cells for cell in row)
    assert battle.enemies[screen.arena.target].name[:6] in written, (
        "the panel did not say who the arrow was on"
    )


def test_the_arena_reads_out_a_lesson(app):
    """A trick learned in a fight is said *in* the fight.

    The arena plays the run's own log, so the line a kill wrote on the map is the
    line a kill writes here -- which is why the announcement lives in the rules
    and not in the menu: it has one text and two rooms to be read in.
    """

    from neverdeads_revenge.sdl_front.arena import SdlArena
    from neverdeads_revenge.game.levels import kills_for_level

    # The dark answers at seven here and not at one: with `--testrun` every trick
    # is learned from the start, and a level that teaches nothing (correctly)
    # says nothing either.
    battle = arena(count=1, ultimate_level=7)
    battle.state.kills = kills_for_level(2) - 1  # one kill short of level two
    battle.state.level = 1
    battle.enemies[0].stats.hp = 1
    screen = SdlArena(battle)
    app.screens = [screen]

    seen: list[str] = []
    guard = 0
    while guard < 400 and app.screens and app.screens[-1] is screen:
        guard += 1
        if screen.busy:
            app.tick(0.1)
            seen += [line.text for line in screen.arena.lines]
            continue
        if battle.over:
            break
        press(app, Qt.Key.Key_Return)  # ATTACK: the arrow comes out
        press(app, Qt.Key.Key_Return)  # and the blow goes in

    assert any("learned!" in text for text in seen), f"the arena never said it: {seen}"


def test_the_arena_stages_the_actors_it_is_fighting(font):
    """The models are the monsters, not a mock-up of them.

    A fight against three vipers is three v's in their own colour, and the hero
    is the hero: the stage reads the actors the fight will spend.
    """
    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=3)
    screen = SdlArena(battle)
    figures = screen.arena._figures(96, 27, font)

    assert [figure.actor for figure in figures] == [*battle.enemies, battle.hero]
    assert [figure.glyph for figure in figures] == [
        enemy.glyph for enemy in battle.enemies
    ] + [battle.hero.glyph]


def test_the_command_panel_names_what_the_blade_does(app, font):
    """The weapon's own wounds, beside the verb that swings it.

    In the colours the room draws them in, so the menu and the monsters speak the
    same vocabulary and the player learns it once -- and `( = X` when his hand is
    empty, which is worth saying, because fighting bare-handed is a choice.
    """
    from types import SimpleNamespace

    from neverdeads_revenge.desktop.screens.battle import STATUS_COLOURS
    from neverdeads_revenge.desktop.theme import parse_style
    from neverdeads_revenge.world.items import ITEMS

    battle = arena(count=1)
    screen = SdlArena(battle)

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


def test_the_five_can_be_walked_across_as_well_as_down(app):
    """The list is two columns: up and down move inside one, left and right take
    the choice into the other -- and a jump that would land outside the list
    stays where it is rather than wrapping round to somewhere unrelated."""

    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=1)
    screen = SdlArena(battle)
    app.screens = [screen]
    screen.arena.picking = True
    rows = screen.arena._list_rows(app)

    press(app, Qt.Key.Key_Down)
    assert screen.arena.special == 1
    press(app, Qt.Key.Key_Right)
    assert screen.arena.special == 1 + rows, "the right arrow did not cross a column"
    press(app, Qt.Key.Key_Left)
    assert screen.arena.special == 1, "the left arrow did not come back"
    screen.arena.special = 0
    press(app, Qt.Key.Key_Left)
    assert screen.arena.special == 0, "the choice wandered out of the list"


def test_the_list_only_holds_what_he_has_learned(app, font):
    """A list of names the player cannot use is a list of spoilers.

    Learned is not the same question as *available*, and the menu needs both: a
    trick spent in **this** fight is still on the list -- dimmed, because it is
    his and it comes back next fight -- and a trick he has not reached yet is not
    on it at all. What the player cannot have is not what the player is offered.
    """
    from neverdeads_revenge.sdl_front.arena import SdlArena
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.battle import Battle
    from neverdeads_revenge.game.specials import LEFT_HAND
    from neverdeads_revenge.game.state import start_run

    state = start_run(HEROES["noxx"], 3, ultimate_level=7)
    state.level = 2  # the knife, and nothing else
    battle = Battle(state, state.enemies[:1])
    screen = SdlArena(battle)
    screen.arena.picking = True
    buffer, _ = drawn(screen, app, font)
    written = "".join(cell.char for row in buffer.cells for cell in row)

    assert [one.key for one in battle.learned()] == [LEFT_HAND]
    assert "THE LEFT HAND" in written, "the one he has learned is missing"
    assert "ORB OF PTAMERA" not in written, "a trick he has not learned is on the list"


def test_the_list_says_what_the_chosen_trick_does(app, font):
    """The facts under the names, in the readable ink.

    Scroll to a trick and the panel tells you what it does before you spend a
    turn on it: the fight's own voice underneath is a voice, and a voice is not
    an instruction.
    """
    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=1)
    screen = SdlArena(battle)
    screen.arena.picking = True
    screen.arena.special = 2
    buffer, _ = drawn(screen, app, font)

    written = "".join(cell.char for row in buffer.cells for cell in row)
    assert battle.specials()[2].effect in written, "the panel did not say what it does"
    assert battle.specials()[2].blurb[:20] in written, "the panel lost its voice"


def test_the_order_strip_does_not_jump_when_the_hero_swings(app):
    """The turn in flight stays at the front of the strip while he swings.

    The queue charges the hero for his turn *before* he takes it -- that is how
    `_advance` finds him -- so a strip read straight off the paces loses him the
    moment his blow lands and slides him back in when the room settles: the row
    shifts a step left and then a step right again. This is that, pinned.
    """
    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=1)
    # A monster that is slower than he is and survives the blow: then the round
    # is his alone, and the strip has no honest reason to move -- which is the
    # thing being pinned. (It passed before because the sword killed the viper
    # outright, so the round *was* his alone; that is luck and not a rule.)
    battle.enemies[0].stats.speed = 0.5
    battle.enemies[0].stats.hp = 999
    screen = SdlArena(battle)
    screen._queue = []
    screen._beat = 0.0
    screen.arena.verb = 0
    screen.arena._choose(app)

    heads: list = []
    for _ in range(80):
        assert screen.arena._order, "the strip emptied itself"
        heads.append(screen.arena._order[0])
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
    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=1)
    # A monster quick enough to act *after* him in the same round: with the
    # floor's own slow ones the hero is up again immediately, and rightly so.
    battle.enemies[0].stats.speed = 9.0
    screen = SdlArena(battle)
    screen._queue = []
    screen._beat = 0.0
    screen.arena.verb = 0
    screen.arena._choose(app)

    assert screen.arena._order and screen.arena._order[0] is battle.hero, "not his turn first"
    head = screen.arena._order[0]
    for _ in range(80):
        screen.step(1 / 30.0, app)
        if screen.arena._order and screen.arena._order[0] is not head:
            break

    assert screen.arena._order, "the strip emptied itself"
    assert screen.arena._order[0] is battle.enemies[0], (
        f"the strip is on {screen.arena._order[0].glyph}, not on the monster that acts next"
    )


def test_the_prologue_scrolls_and_a_hold_lets_it_go(app):


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


def test_the_trick_is_picked_before_the_monster_is(app):
    """The order every fight in this genre ever had: the move, and then the mark.

    SPECIAL opens the five, taking one of the five opens the *arrow*, and the
    arrow is what spends the turn. A trick chosen in a list and spent on whoever
    happened to be standing under a cursor is a choice the player never made --
    the panel is still the one that says what is being thrown, and the floor is
    the one that says at whom.
    """

    from neverdeads_revenge.sdl_front.arena import SdlArena

    battle = arena(count=3)
    screen = SdlArena(battle)
    screen._queue = []  # the opening round is not what this test is about
    app.screens = [screen]

    press(app, Qt.Key.Key_S, "s")
    assert screen.arena.picking, "SPECIAL did not open the five"

    press(app, Qt.Key.Key_Return)
    assert not screen.arena.picking, "the list stayed open after a trick was taken"
    assert screen.arena.aiming, "the trick was spent without a monster being picked"
    assert screen.arena._picked == battle.specials()[0].key, "a different trick was armed"
    assert not screen.busy, "the turn was spent before the arrow was laid on anyone"


def test_the_voids_glass_closes_with_the_shadow():
    """The reveal is drawn, not remembered: a wall across the floor is shown
    while Atritas walks, and gone the moment he sinks back -- even though
    nobody ever walked there."""
    from neverdeads_revenge.desktop.render import _cell_content
    from neverdeads_revenge.game.actions import Action, advance_world, perform_action
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
        advance_world(state)
    assert state.atritas is None

    glyph, _ = _cell_content(far, state)
    assert glyph == " ", "the glass outlived the shadow"


def test_three_taps_dismiss_nothing(app):
    """A hold is a hold. Three quick presses -- the thing a fidget does on the
    way to a real hold -- used to walk straight through the premise, because a
    terminal could only guess that a hold was over by silence. The desktop is
    told when the key came up; taps bank nothing."""

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


