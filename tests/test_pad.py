"""The pad: what a handheld's buttons are called, and how a held one repeats.

Three things are held down here, and all three of them cost a session on the
device this front end was written for:

* **the button numbers are Android's**, not a PC's -- SDL maps every Android
  keycode onto an ``SDL_CONTROLLER_BUTTON_*`` index and *that* is what pygame
  reports, so the shoulders are 9 and 10 and the stick clicks 7 and 8;
* **a d-pad is read as a hat *and* as four buttons**, because on that device it
  reported itself as buttons and the face buttons worked while the d-pad did
  nothing;
* **the analog stick is never walked with**, because a resting one reported
  itself as "down" forever and ran the menus off the bottom of the screen.

And one thing that is *made* here rather than reported: a pad sends nothing
between a button going down and coming up, so a held direction and a held button
are turned into the repeat stream the screens already answer -- with the delays
that keep a tap a tap.
"""

from __future__ import annotations

import os

import pytest

FONT = "src/neverdeads_revenge/desktop/fonts/DejaVuSansMono.ttf"

from neverdeads_revenge.desktop.screens.base import Screen  # noqa: E402


def _sdl():
    """SDL, up and initialised, the way every test in this suite does it."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    pygame.init()
    return pygame


class FakePad:
    """A pad that is not plugged in: the only way a mapping can be held still.

    Every number is a fact about the handheld this comes from -- the d-pad is
    *buttons* (11 up, 12 down, 13 left, 14 right) because that is what the device
    reports, and the stick is a stick that can be left leaning.
    """

    def __init__(
        self,
        *,
        hat: tuple[int, int] = (0, 0),
        hats: int = 1,
        buttons: tuple[int, ...] = (),
        axes: tuple[float, ...] = (0.0, 0.0),
        name: str = "Fake Pad",
    ) -> None:
        self.hat = hat
        self.hats = hats
        self.buttons = set(buttons)
        self.axes = list(axes)
        self.name = name

    def get_name(self) -> str:
        return self.name

    def get_numhats(self) -> int:
        return self.hats

    def get_hat(self, index: int) -> tuple[int, int]:
        return self.hat

    def get_numbuttons(self) -> int:
        return 17

    def get_button(self, index: int) -> int:
        return 1 if index in self.buttons else 0

    def get_numaxes(self) -> int:
        return len(self.axes)

    def get_axis(self, index: int) -> float:
        return self.axes[index]


class Recorder(Screen):
    """A screen that writes down what it was told, and nothing else."""

    def __init__(self) -> None:
        self.presses: list[tuple[str, bool]] = []
        self.releases: list[str] = []
        self.hold = None

    def draw(self, buffer, app) -> None:  # pragma: no cover - never drawn
        return None

    def key(self, name, event, app) -> bool:
        self.presses.append((name, bool(event.isAutoRepeat())))
        return True

    def key_up(self, name, event, app) -> bool:
        self.releases.append(name)
        return True

    def key_sound(self, name: str) -> str | None:
        return None


def _app(screen=None, **kwargs):
    """An application, headless, with the pads handed in by the test."""
    _sdl()
    from neverdeads_revenge.sdl_front.app import SdlApp

    return SdlApp(seed=3, no_sound=True, screen=screen, **kwargs)


# -- the table ---------------------------------------------------------------
def test_the_shoulders_are_nine_and_ten_because_android_numbers_them():
    """The one mistake this table exists to prevent.

    On a PC's SDL a pad's L1/R1/L2/R2 are 4, 5, 6 and 7. On Android they are not:
    SDL maps the keycodes onto controller-button indices first, and the result is
    that the shoulders are 9 and 10, the stick clicks 7 and 8, Start 6 and Select
    4. Assuming the PC layout -- which is what the first version of this did --
    puts "escape" on L1 and leaves R1 with nothing at all.
    """
    from neverdeads_revenge.sdl_front.pad import BUTTONS

    assert BUTTONS[9] == "r", "L1 is the borrowed hour"
    assert BUTTONS[10] == "space", "R1 waits"
    assert BUTTONS[7] == BUTTONS[8] == "f", "either stick click is the ultimate"
    assert BUTTONS[4] == BUTTONS[6] == "select", "Select and Start both pause"
    # And the PC numbering, said out loud: 4 is *not* the left shoulder here, and
    # 5 -- which a PC would call the right one -- is not a button at all.
    assert BUTTONS[4] != "r"
    assert 5 not in BUTTONS


def test_the_face_buttons_are_the_game_s_own_verbs():
    """A, B, X, Y: take, back, drink, pack."""
    from neverdeads_revenge.sdl_front.pad import button_name

    assert button_name(0) == "enter"
    assert button_name(1) == "escape"
    assert button_name(2) == "q"
    assert button_name(3) == "i"
    assert button_name(99) is None


def test_a_d_pad_is_read_as_a_hat_and_as_four_buttons():
    """Both, because the device reported the second and the code read the first.

    The bench said it plainly: the face buttons worked and the d-pad did nothing,
    because only the hat was being read. So a hat is tried first -- the usual way
    -- and the four buttons SDL reserves for a d-pad after it.
    """
    from neverdeads_revenge.sdl_front.pad import dpad_direction

    assert dpad_direction(FakePad(hat=(-1, 0))) == "left"
    assert dpad_direction(FakePad(hat=(1, 1))) == "se"
    assert dpad_direction(FakePad(hat=(0, 0))) is None
    # No hat at all: the four buttons, and a diagonal out of two of them.
    assert dpad_direction(FakePad(hats=0, buttons=(12,))) == "down"
    assert dpad_direction(FakePad(hats=0, buttons=(11, 13))) == "nw"
    assert dpad_direction(FakePad(hats=0)) is None


def test_a_direction_is_the_key_the_dungeon_already_walks_on():
    """Eight positions, and the game's own eight keys.

    The dungeon walks diagonally on ``y``/``u``/``b``/``n`` -- the terminal's
    numpad letters -- so a pad pushed north-west is that key and no screen had to
    learn a second word for a direction.
    """
    from neverdeads_revenge.sdl_front.pad import DIRECTION_KEYS

    assert DIRECTION_KEYS == {
        "up": "up",
        "down": "down",
        "left": "left",
        "right": "right",
        "nw": "y",
        "ne": "u",
        "sw": "b",
        "se": "n",
    }
    app = _app(Recorder())
    app.joysticks = [FakePad(hats=0, buttons=(11, 14))]  # up + right
    assert app.pad_direction() == "u"


def test_the_stick_is_shown_but_never_walked_with():
    """A drifting stick is not a metaphor: it walked the menus by itself.

    The bench still shows it raw -- that is what the bench is for -- but the game
    asks the d-pad and nothing else, so a thumb resting on a stick is not a
    decision.
    """
    from neverdeads_revenge.sdl_front.pad import DEADZONE, stick_direction

    assert stick_direction(FakePad(axes=(DEADZONE - 0.01, 0.0))) is None
    assert stick_direction(FakePad(axes=(0.9, -0.9))) == "ne"
    app = _app(Recorder())
    app.joysticks = [FakePad(hats=0, axes=(0.0, 0.95))]  # a stick pushed down
    assert app.pad_direction() is None, "the stick is not walked with"


# -- events ------------------------------------------------------------------
def test_a_button_arrives_as_the_name_the_screens_answer():
    """A press is an event, exactly like a key: one press, one action."""
    pygame = _sdl()
    screen = Recorder()
    app = _app(screen)

    app.feed(pygame.event.Event(pygame.JOYBUTTONDOWN, {"button": 0}))
    app.feed(pygame.event.Event(pygame.JOYBUTTONUP, {"button": 0}))
    assert screen.presses == [("enter", False)]
    assert screen.releases == ["enter"]

    app.feed(pygame.event.Event(pygame.JOYBUTTONDOWN, {"button": 5}))
    assert len(screen.presses) == 1, "an unnamed button is not a key"


def test_a_button_held_from_the_screen_before_does_not_choose_here():
    """The house rule: a screen answers a *press*, and a stale one is not one."""
    pygame = _sdl()
    first = Recorder()
    app = _app(first)
    app.feed(pygame.event.Event(pygame.JOYBUTTONDOWN, {"button": 0}))
    assert first.presses == [("enter", False)]

    second = Recorder()
    app.push(second)  # the button is still down while this one arrives
    app.feed(pygame.event.Event(pygame.JOYBUTTONDOWN, {"button": 0}))
    assert second.presses == [], "a held button chose on a screen it never saw"
    app.feed(pygame.event.Event(pygame.JOYBUTTONUP, {"button": 0}))
    app.feed(pygame.event.Event(pygame.JOYBUTTONDOWN, {"button": 0}))
    assert second.presses == [("enter", False)], "and it works when pressed again"


# -- the made-up repeats -----------------------------------------------------
def test_a_held_direction_walks_once_and_then_repeats():
    """One step at once, then repeats -- and the *pace* is not decided here.

    A keyboard repeats by itself; a pad sends nothing between a button going down
    and coming up, so the stream is made here or a held direction moves exactly
    one square. It is fed and flagged as a repeat, and the floor throttles those
    by the hero's own pace, exactly as it does for a held key.
    """
    from neverdeads_revenge.sdl_front.app import PAD_WALK_DELAY

    screen = Recorder()
    app = _app(screen)
    app.joysticks = [FakePad(hats=0, buttons=(12,))]  # the d-pad pushed down

    app._poll_pad(1000.0)
    assert screen.presses == [("down", False)], "a push is a press"
    app._poll_pad(1000.0 + PAD_WALK_DELAY / 2)
    assert len(screen.presses) == 1, "a tap of any ordinary length is one square"
    app._poll_pad(1000.0 + PAD_WALK_DELAY + 0.01)
    assert screen.presses[-1] == ("down", True), "and a hold repeats"

    app.joysticks = [FakePad(hats=0)]  # the pad rests
    app._poll_pad(1001.0)
    app._poll_pad(1002.0)
    assert len(screen.presses) == 2, "a resting pad says nothing"


def test_the_pad_s_own_a_holds_a_hold_screen():
    """The prologue, the death tally and the profile erase wait for a *stream*.

    They advance on the presses that arrive, and a pad does not send any: the
    first repeat waits longer than a tap, so a tap still banks nothing, and then
    it comes at the rate the bar is painted at.
    """
    from neverdeads_revenge.desktop.hold import HoldToContinue
    from neverdeads_revenge.sdl_front.app import PAD_HOLD_DELAY

    screen = Recorder()
    screen.hold = HoldToContinue()
    app = _app(screen)
    app._buttons_down.add(0)  # the pad's A

    app._poll_pad(2000.0)
    app._poll_pad(2000.0 + PAD_HOLD_DELAY / 2)
    assert screen.presses == [], "a tap must never bank a hold"
    app._poll_pad(2000.0 + PAD_HOLD_DELAY + 0.01)
    assert screen.presses == [("enter", True)]

    # And the keyboard is left exactly as it was: SDL repeats those itself, and
    # feeding a second stream would double every hold on a desktop.
    app._buttons_down.clear()
    app._poll_pad(2001.0)
    app._poll_pad(2002.0)
    assert len(screen.presses) == 1


def test_a_hold_screen_with_another_key_is_left_alone():
    """The stream is fed for the key the hold is waiting for, and no other."""
    from neverdeads_revenge.desktop.hold import HoldToContinue
    from neverdeads_revenge.sdl_front.app import PAD_HOLD_DELAY

    screen = Recorder()
    screen.hold = HoldToContinue(keys=("space",))
    app = _app(screen)
    app._buttons_down.add(0)  # A is "enter", which this hold is not waiting for

    app._poll_pad(3000.0)
    app._poll_pad(3000.0 + PAD_HOLD_DELAY + 0.01)
    assert screen.presses == []


# -- the bench ---------------------------------------------------------------
def test_the_bench_shows_the_pad_raw_and_leaves_on_escape():
    """What *this* pad sends, before any mapping has read it.

    It is the screen that turned "the d-pad does nothing" into "the d-pad is four
    buttons and nobody was reading them", so what it shows is the raw event --
    the button number and the name the game gives it, side by side.
    """
    pygame = _sdl()
    app = _app(sniff=True)
    bench = app.screens[-1]
    assert type(bench).__name__ == "PadBench"

    app.joysticks = [FakePad(name="Retroid Pad")]
    app.feed(pygame.event.Event(pygame.JOYBUTTONDOWN, {"button": 0}))
    app.feed(pygame.event.Event(pygame.JOYHATMOTION, {"hat": 0, "value": (-1, 0)}))
    assert any("BUTTON DOWN" in line and "enter" in line for line in bench.events)
    assert any("HAT" in line for line in bench.events)

    app.redraw()  # it draws, with a pad and with the events on it
    app.key("escape")
    assert type(app.screens[-1]).__name__ != "PadBench", "escape leaves the bench"


def test_the_pause_menu_offers_the_bench_only_when_a_pad_is_plugged_in():
    """A menu line that does nothing is a line that teaches distrust.

    On a handheld there is no command line to pass ``--sniff`` to, so the pause
    menu is the only door left -- and on a desktop with no pad plugged in there
    is nothing to bench, so the line is not offered at all.
    """
    from neverdeads_revenge.desktop.screens.pause import PauseScreen

    app = _app(Recorder())
    assert not app.joysticks
    assert "THE PAD" not in [label for _key, label in PauseScreen().items(app)]

    app.joysticks = [FakePad()]
    labels = [label for _key, label in PauseScreen().items(app)]
    assert "THE PAD" in labels
    app.push(PauseScreen())
    app.key("p")
    assert type(app.screens[-1]).__name__ == "PadBench"


def test_the_android_back_key_is_escape():
    """The one key a handheld has that a keyboard does not."""
    from neverdeads_revenge.sdl_front import keys

    assert keys.NAMES["K_AC_BACK"] == "escape"
    pygame = _sdl()
    if hasattr(pygame, "K_AC_BACK"):
        event = pygame.event.Event(
            pygame.KEYDOWN, {"key": pygame.K_AC_BACK, "unicode": ""}
        )
        assert keys.name_of(event) == "escape"
