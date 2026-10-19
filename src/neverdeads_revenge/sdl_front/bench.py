"""The pad, shown raw.

A bench, not a menu: it answers one question, and only a device in hand can
answer it -- what does *this* pad actually send? A mapping written from a spec
sheet is a mapping that gets debugged twice, so this shows every axis, button and
hat the way SDL reports them, beside the name the game gives each one.

That is why it exists at all on a front end with a keyboard: on the handheld
there is no command line to pass a flag to, and the pause menu is the only door
left. It changes nothing while it is open -- B (or escape) leaves -- and it is
the screen that turned "the d-pad does nothing" into "the d-pad is four buttons
and nobody was reading them".
"""

from __future__ import annotations

from ..desktop.chrome import ASH, BLOOD, BONE, PURPLE, box
from ..desktop.screens.base import Screen
from ..desktop.theme import parse_style
from .pad import DPAD_BUTTONS, button_name, describe_pad, dpad_direction, stick_direction

__all__ = ["PadBench"]

#: How many raw events to keep on show. Enough to see a sequence -- a stick
#: sweeping, a button pressed and released -- without becoming a log.
MAX_EVENTS = 10


class PadBench(Screen):
    """Every axis, button and hat, live, with the game's name for each."""

    modal = True

    def __init__(self) -> None:
        self.events: list[str] = []

    # -- what the app feeds it ----------------------------------------------
    def note(self, event, app) -> None:
        """Record one raw event, before any screen has read it.

        Called by the app for *every* event, which is the point: the question
        here is what arrives, not what survived a mapping.
        """
        line = describe_event(event)
        if line is not None:
            self.events.append(line)
            del self.events[: -MAX_EVENTS]

    # -- drawing -------------------------------------------------------------
    def draw(self, buffer, app) -> None:
        pads = getattr(app, "joysticks", [])
        width, height = buffer.cols - 4, buffer.rows - 2
        x, y = 2, 1
        box(buffer, x, y, width, height, border=BLOOD, fill=True)
        buffer.text(x + 2, y + 1, "PAD BENCH", parse_style(f"bold {PURPLE}"))
        buffer.text(
            x + 2,
            y + 2,
            "raw from SDL, beside the name the game gives it",
            parse_style(ASH),
        )
        buffer.text(
            x + 2,
            y + 3,
            f"{app.frames:5.1f} fps      escape (or B) leaves",
            parse_style(ASH),
        )
        row = y + 5
        if not pads:
            buffer.text(
                x + 2, row, "no pad seen -- a keyboard is all there is",
                parse_style(ASH),
            )
        for index, stick in enumerate(pads):
            row = self._pad_rows(buffer, stick, index, x + 2, row, width - 4)
        row = min(row + 1, y + height - MAX_EVENTS - 2)
        buffer.text(x + 2, row, "last events", parse_style(f"bold {BONE}"))
        for offset, line in enumerate(self.events[-MAX_EVENTS:]):
            buffer.text(x + 2, row + 1 + offset, line[: width - 4], parse_style(ASH))

    def _pad_rows(self, buffer, stick, index: int, x: int, row: int, width: int) -> int:
        """One pad's own rows: what it is, where it is pushed, and what is down."""
        buffer.text(x, row, f"{index}: {describe_pad(stick)}", parse_style(f"bold {BONE}"))
        pushed = dpad_direction(stick) or "rest"
        leaning = stick_direction(stick) or "rest"
        buffer.text(
            x,
            row + 1,
            f"   d-pad {pushed:<6} stick {leaning}",
            parse_style(BONE),
        )
        axes = ", ".join(
            f"{stick.get_axis(axis):+.2f}" for axis in range(stick.get_numaxes())
        )
        buffer.text(x, row + 2, f"   axes {axes}"[:width], parse_style(ASH))
        if stick.get_numhats():
            hat = ", ".join(str(stick.get_hat(hat)) for hat in range(stick.get_numhats()))
            buffer.text(x, row + 3, f"   hat {hat}"[:width], parse_style(ASH))
        down = "  ".join(
            f"{number}:{shown_name(number)}"
            for number in range(stick.get_numbuttons())
            if stick.get_button(number)
        )
        buffer.text(x, row + 4, f"   down {down or 'none'}"[:width], parse_style(ASH))
        return row + 6

    # -- keys ----------------------------------------------------------------
    def key(self, name, event, app) -> bool:
        """Escape leaves, and *only* escape.

        A is "enter" and enter would be the obvious second way out -- and it is
        exactly the button a player presses first while looking for a way out.
        On a bench that is the wrong button to lose: every press is data here, so
        the one key that closes it is the one the pad spells "back".
        """
        if name == "escape":
            app.pop()
        return True

    def key_sound(self, name: str) -> str | None:
        return None


def shown_name(button: int) -> str:
    """The name to show for a button, the d-pad included.

    A d-pad button has no name the *game* answers to -- it is read as a direction
    and never as a button -- and a bench that printed ``12:?`` for the very
    button it was written to find would be hiding its own result.
    """
    return button_name(button) or DPAD_BUTTONS.get(button) or "?"


def describe_event(event) -> str | None:
    """One raw event as a line of text, or ``None`` for one that is not the pad.

    The keys are shown too: the question "did the button even arrive?" is
    answered by seeing whether the line before it is a ``KEY`` line, and on a
    handheld a pad button that Android turns into a keycode looks exactly like
    one.
    """
    import pygame

    kind = event.type
    if kind == pygame.JOYBUTTONDOWN:
        return f"BUTTON DOWN {event.button:>3}  -> {shown_name(event.button)}"
    if kind == pygame.JOYBUTTONUP:
        return f"BUTTON UP   {event.button:>3}  -> {shown_name(event.button)}"
    if kind == pygame.JOYHATMOTION:
        return f"HAT {event.hat} -> {event.value}"
    if kind == pygame.JOYAXISMOTION:
        return f"AXIS {event.axis:>2}  {event.value:+.3f}"
    if kind == pygame.KEYDOWN:
        return f"KEY DOWN    {pygame.key.name(event.key)}"
    return None
