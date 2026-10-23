"""The controller: a fake pad, driven by hand.

The real thing is an SDL game controller, and no test machine has one -- which is
exactly why the pad is a class that takes its devices. A fake stick is a stick:
ten buttons, two sticks and a hat, and the same names the screens already answer.
"""

from __future__ import annotations

import json

import pytest

from neverdeads_revenge.core.direction import Direction
from neverdeads_revenge.desktop.pattern import PatternBuffer, pad_words
from neverdeads_revenge.sdl_front.app import SdlApp
from neverdeads_revenge.sdl_front.pad import Pad


class FakeStick:
    """A pad with no hands: set a button, set an axis, tick the app."""

    def __init__(self) -> None:
        self.buttons: set[int] = set()
        self.axes: dict[int, float] = {}
        self.hat = (0, 0)
        self.rumble_calls: list[tuple[float, float, int]] = []

    def get_button(self, number: int) -> bool:
        return number in self.buttons

    def get_axis(self, number: int) -> float:
        return self.axes.get(number, 0.0)

    def get_numhats(self) -> int:
        return 1

    def get_hat(self, number: int) -> tuple[int, int]:
        return self.hat

    def rumble(self, low: float, high: float, ms: int) -> None:
        self.rumble_calls.append((low, high, ms))


def _app_with_pad(seed: int = 3, **kwargs) -> tuple[SdlApp, FakeStick]:
    app = SdlApp(seed=seed, no_sound=True, **kwargs)
    stick = FakeStick()
    app.pad = Pad([stick])
    return app, stick


def _press(app: SdlApp, stick: FakeStick, button: int, frames: int = 2) -> None:
    """One press and its release: the screens answer a press, not a hold."""
    stick.buttons.add(button)
    app.tick(1 / 30.0)
    stick.buttons.discard(button)
    for _ in range(frames):
        app.tick(1 / 30.0)


# -- the pad as a source of key names --------------------------------------
def test_a_held_direction_walks_at_the_keyboards_pace():
    """SDL gives a keyboard its repeats; a pad has none, so the pad invents them."""
    stick = FakeStick()
    stick.axes[0] = 1.0  # full east
    pad = Pad([stick])

    first = pad.poll(0.016, {}, diagonals=True, scroll=False)
    assert first == [("right", "key", False)], first

    heard = []
    for _ in range(60):  # a second of holding
        heard += pad.poll(0.016, {}, diagonals=True, scroll=False)
    assert ("right", "key", True) in heard, "a held direction never repeated"


def test_a_diagonal_is_eight_directions_on_the_floor_and_four_in_a_menu():
    stick = FakeStick()
    stick.axes[0] = 0.6
    stick.axes[1] = -1.0
    pad = Pad([stick])

    floor = pad.poll(0.016, {}, diagonals=True, scroll=False)
    assert floor == [("pageup", "key", False)], floor  # north-east

    pad.forget()
    menu = pad.poll(0.016, {}, diagonals=False, scroll=False)
    # The stronger axis is the one the player meant, and it is the *same* push.
    assert menu == [("up", "key", False)], menu


def test_a_button_held_through_a_screen_change_has_to_be_pressed_again():
    stick = FakeStick()
    stick.buttons.add(0)
    pad = Pad([stick])
    mapping = {"south": "enter"}
    assert pad.poll(0.016, mapping, diagonals=False, scroll=False)

    pad.forget()
    for _ in range(40):
        assert pad.poll(0.016, mapping, diagonals=False, scroll=False) == []

    stick.buttons.discard(0)
    pad.poll(0.016, mapping, diagonals=False, scroll=False)
    stick.buttons.add(0)
    assert pad.poll(0.016, mapping, diagonals=False, scroll=False), "a fresh press was eaten"


def test_a_release_is_reported_so_a_hold_bar_knows():
    stick = FakeStick()
    stick.buttons.add(0)
    pad = Pad([stick])
    mapping = {"south": "enter"}
    pad.poll(0.016, mapping, diagonals=False, scroll=False)

    stick.buttons.discard(0)
    assert ("enter", "up", False) in pad.poll(
        0.016, mapping, diagonals=False, scroll=False
    )


# -- the app ---------------------------------------------------------------
def test_a_on_the_title_starts_a_run_and_start_opens_the_settings():
    app, stick = _app_with_pad()
    _press(app, stick, 0)  # A -> enter -> NEW RUN
    assert type(app.screens[-1]).__name__ == "HeroSelectScreen"

    app.return_to_title()
    stick.buttons.discard(0)
    _press(app, stick, 7)  # Start -> the settings, on the title
    assert type(app.screens[-1]).__name__ == "SettingsScreen"


def test_b_on_the_floor_is_the_bag():
    app, stick = _app_with_pad()
    _press(app, stick, 0)  # A: new run
    _press(app, stick, 0)  # A: the first hero
    _press(app, stick, 1)  # B: the prologue, skipped? no -- the prologue holds
    # The prologue is a hold; its B is escape and it leaves at once.
    assert type(app.screens[-1]).__name__ == "GameScreen"

    _press(app, stick, 1)  # B -> the bag
    assert type(app.screens[-1]).__name__ == "PackScreen"


def test_the_stick_walks_the_hero():
    app, stick = _app_with_pad()
    _press(app, stick, 0)
    _press(app, stick, 0)
    _press(app, stick, 1)
    state = app.run
    start = state.player.position

    for direction, axis in (
        (Direction.EAST, (1.0, 0.0)),
        (Direction.SOUTH, (0.0, 1.0)),
        (Direction.WEST, (-1.0, 0.0)),
        (Direction.NORTH, (0.0, -1.0)),
    ):
        target = direction.step(start)
        if state.dungeon_map.is_walkable(target) and state.actor_at(target) is None:
            stick.axes[0], stick.axes[1] = axis
            app.tick(1 / 30.0)
            assert state.player.position == target
            return
    pytest.skip("the starting square is walled in on all four sides")


def test_back_opens_the_almanac_in_a_fight_and_b_backs_out_of_the_aim():
    app, stick = _app_with_pad(battle_scene=True)
    arena = app.screens[-1]
    living = arena.battle.living_enemies()
    if not living:
        pytest.skip("the battle scene came up empty")
    _press(app, stick, 0)  # A -> attack, and the arrow comes out
    assert arena.arena.aiming, "the arrow did not come out"
    _press(app, stick, 1)  # B -> back to the verbs, and nothing else
    assert not arena.arena.aiming, "B did not back out of the aim"
    assert not arena.battle.over, "B fled the fight"
    assert not any("only way out" in line.text for line in arena.arena.lines), (
        "B printed the flee refusal"
    )

    _press(app, stick, 6)  # Back -> the book
    book = app.screens[-1]
    assert type(book).__name__ == "AlmanacScreen"
    assert book.tab == 1, "the book did not open at the bestiary"


def test_r3_inspects_what_is_being_fought():
    app, stick = _app_with_pad(battle_scene=True)
    arena = app.screens[-1]
    living = arena.battle.living_enemies()
    if not living:
        pytest.skip("the battle scene came up empty")

    _press(app, stick, 9)  # R3 -> inspect

    book = app.screens[-1]
    assert type(book).__name__ == "AlmanacScreen"
    index = arena.arena.target % len(living)
    assert book._selected().key == living[index].key
    assert book.focus == "page", "inspect landed in the index and not on the page"
    _press(app, stick, 1)  # B closes it
    assert type(app.screens[-1]).__name__ == "SdlArena"


def test_the_settings_screen_toggles_the_glass_and_writes_it_down():
    app, stick = _app_with_pad()
    _press(app, stick, 7)  # Start -> settings
    screen = app.screens[-1]
    assert type(screen).__name__ == "SettingsScreen"

    before = app.crt.scanlines
    stick.hat = (0, -1)  # one row down: scanlines
    app.tick(1 / 30.0)
    stick.hat = (0, 0)
    app.tick(1 / 30.0)
    _press(app, stick, 0)  # A toggles it

    assert app.crt.scanlines is (not before), "the switch did not flip"
    from neverdeads_revenge.desktop.settings import load_settings

    assert load_settings()["scanlines"] == app.crt.scanlines, "the switch was not written"


def test_the_settings_menu_is_reachable_from_the_title_row():
    app, stick = _app_with_pad()
    app.key("e")  # the SETTINGS row
    assert type(app.screens[-1]).__name__ == "SettingsScreen"

    screen = app.screens[-1]

    def row_down() -> None:
        stick.hat = (0, -1)
        app.tick(1 / 30.0)
        stick.hat = (0, 0)
        app.tick(1 / 30.0)

    def choose(label: str) -> None:
        # By name, not by counting rows: a row added to the list is not a broken
        # test. Only down, because every row the test wants is below the first.
        while screen.rows(app)[screen.index][0] != label:
            row_down()

    # The scanlines: A flips them, and the file keeps the answer.
    choose("scanlines")
    before = app.crt.scanlines
    _press(app, stick, 0)
    assert app.crt.scanlines is (not before), "the glass switch did not flip"

    from neverdeads_revenge.desktop.settings import load_settings

    assert load_settings()["scanlines"] == app.crt.scanlines, "the switch was not written"

    # And further down the list, the sound.
    choose("sound")
    before = app.sfx.muted
    _press(app, stick, 0)
    assert app.sfx.muted is (not before)
    assert app.progress.muted is app.sfx.muted, "the sound setting was not kept"


def test_the_shoulders_turn_the_almancs_tab_page():
    app, stick = _app_with_pad()
    app.open_almanac()
    assert app.screens[-1].tab == 0

    app.key("]")
    assert app.screens[-1].tab == 1
    app.key("]")
    assert app.screens[-1].tab == 2, "the last tab was not reachable"
    app.key("]")
    assert app.screens[-1].tab == 2, "the tab page wrapped past the end"
    app.key("[")
    assert app.screens[-1].tab == 1


def test_m_opens_and_closes_the_book_on_the_floor():
    app, stick = _app_with_pad()
    _press(app, stick, 0)  # new run
    _press(app, stick, 0)  # the first hero
    _press(app, stick, 1)  # the prologue, skipped
    assert type(app.screens[-1]).__name__ == "GameScreen"

    app.key("m")
    assert type(app.screens[-1]).__name__ == "AlmanacScreen"
    app.key("m")
    assert type(app.screens[-1]).__name__ == "GameScreen", "m did not close the book"


def test_the_right_stick_pages_only_where_a_screen_reads_pages():
    stick = FakeStick()
    stick.axes[3] = 0.9
    pad = Pad([stick])

    # A floor does not read pages: its page keys are *movement*, so the stick is
    # silent there.
    assert pad.poll(0.016, {}, diagonals=True, scroll=False) == []

    heard = []
    for _ in range(30):
        heard += pad.poll(0.016, {}, diagonals=False, scroll=True)
    assert ("pagedown", "key", False) in heard, "the reading stick never paged"


def test_the_name_is_spelled_on_the_pad():
    """The alphabet is on the card: the d-pad walks it, A takes the letter.

    A pad cannot type, and rolling a name was the only way to finish a run with
    a name of its own. The board is on the card now, so five letters are five
    presses and five steps -- and the dice are still there for a player who
    would rather not spell.
    """
    from neverdeads_revenge.desktop.screens.game_over import PAD_NAMES, NameEntryScreen

    app, stick = _app_with_pad()
    kept: list[str] = []
    screen = NameEntryScreen(1234, on_done=kept.append)
    app.push(screen)

    def step(direction: tuple[int, int]) -> None:
        stick.hat = direction
        app.tick(1 / 30.0)
        stick.hat = (0, 0)
        for _ in range(2):
            app.tick(1 / 30.0)

    _press(app, stick, 0)  # A: the cursor is on A
    assert screen.name == "A"

    step((1, 0))  # right: B
    step((1, 0))  # right: C
    _press(app, stick, 0)  # A: C
    assert screen.name == "AC", "the d-pad did not walk the alphabet"

    step((0, -1))  # down six cells: I
    _press(app, stick, 0)
    assert screen.name == "ACI", screen.name

    _press(app, stick, 1)  # B takes one back
    assert screen.name == "AC", "B did not erase a letter"

    _press(app, stick, 2)  # X rolls one
    assert screen.name in PAD_NAMES, "the dice rolled nothing"
    rolled = screen.name
    _press(app, stick, 1)  # and the roll can be taken back
    assert screen.name == rolled[:-1]

    _press(app, stick, 7)  # Start keeps the name
    assert type(app.screens[-1]).__name__ != "NameEntryScreen", "the card stayed up"
    assert kept and kept[0] == screen.name


def test_b_with_nothing_typed_still_leaves_the_board():
    """A player who does not want their name on the board is not trapped by it."""
    from neverdeads_revenge.desktop.screens.game_over import NameEntryScreen

    app, stick = _app_with_pad()
    kept: list[str] = []
    app.push(NameEntryScreen(0, on_done=kept.append))

    _press(app, stick, 1)  # B on an empty name

    assert kept == ["???"], kept
    assert type(app.screens[-1]).__name__ != "NameEntryScreen"


def test_the_alphabet_on_the_card_does_not_take_the_keyboard_away():
    """A desk is a desk: typing still writes the name, letter by letter."""
    from neverdeads_revenge.desktop.screens.game_over import NameEntryScreen

    app, _ = _app_with_pad()
    screen = NameEntryScreen(0)
    app.push(screen)

    for char in "nox":
        app.key(char, text=char)
    assert screen.name == "NOX"

    app.key("backspace")
    assert screen.name == "NO"

    app.key("enter")
    assert type(app.screens[-1]).__name__ != "NameEntryScreen", "enter did not keep it"


def test_x_sets_a_bottle_down_from_the_pack():
    """The pack's one other verb had no button. X is the drop, as `x` is."""
    from neverdeads_revenge.desktop.padmap import PACK
    from neverdeads_revenge.desktop.screens.menus import PackScreen
    from neverdeads_revenge.world.items import ITEMS, make_item

    assert PACK["west"] == "x", "the pad's X is not the pack's drop"

    app, stick = _app_with_pad()
    app.begin_run("noxx")
    if type(app.screens[-1]).__name__ == "PrologueScreen":
        app.key("escape")
    app.key("i")
    screen = app.screens[-1]
    assert isinstance(screen, PackScreen), type(screen).__name__

    app.run.inventory.append(make_item(ITEMS["potion"]))
    before = len(app.run.inventory)
    assert before, "the pack started empty"
    _press(app, stick, 2)  # X: set the bottle down
    assert len(app.run.inventory) == before - 1, "X did not set the bottle down"
    assert screen.message, "the pack said nothing about it"


# -- the hints --------------------------------------------------------------
def test_hints_speak_the_pads_language_when_the_pad_spoke_last():
    grid = PatternBuffer(80, 10)
    grid.text(0, 0, "enter take   esc quit", None)
    assert "enter" in "".join(cell.char or " " for cell in grid.cells[0])

    grid.clear()
    grid.pad = True
    grid.text(0, 0, "enter take   esc quit", None)
    said = "".join(cell.char or " " for cell in grid.cells[0])
    assert "A take" in said and "B quit" in said, said
    assert "sentence" == pad_words("sentence"), "a word inside a word was rewritten"


def test_the_pad_says_it_in_the_hand_when_a_blow_lands():
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy
    from neverdeads_revenge.world.tiles import Tile

    app, stick = _app_with_pad()
    _press(app, stick, 0)
    _press(app, stick, 0)
    _press(app, stick, 1)
    state = app.run
    beside = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(beside, Tile.FLOOR)
    monster = make_enemy(ENEMIES["ghoul"], beside)
    monster.stats.hp = 1
    state.enemies.append(monster)
    state.turn_queue.add(monster)
    state.refresh_vision()

    app.key("right")  # walk into it, on the keyboard: the rumble is the room's
    for _ in range(400):
        if type(app.screens[-1]).__name__ == "SdlArena":
            break
        app.tick(1 / 30.0)
    app.key("a")
    app.key("enter")  # the killing blow
    for _ in range(120):
        app.tick(1 / 30.0)
        if stick.rumble_calls:
            break

    assert stick.rumble_calls, "a killing blow said nothing in the hand"
