"""The screen stack.

A screen draws itself into the pattern buffer and answers a key. That is the
whole contract: the app owns the stack, the run and the progress, and a screen
is a function of the run plus a set of keys.

Modals draw *over* what is under them rather than replacing it, which is how the
dungeon stays visible behind a dialog -- the same thing the terminal did by
dimming a modal's background, done here by simply not clearing what is below.
"""

from __future__ import annotations

from ..pattern import PatternBuffer

__all__ = ["Screen"]


class Screen:
    """One thing on the screen."""

    #: Whether the stack below this screen is drawn first. Dialogs are modals;
    #: the title and the game are not.
    modal = False

    #: Whether a modal *covers* the stack below it. A panel that fills the screen
    #: -- the menus, the roster -- is a room of its own and hides what is under
    #: it; a dialog is a box, and the floor it is standing on stays visible
    #: around it, which is what the terminal build did by dimming a modal's
    #: background instead of clearing it.
    opaque = True

    def draw(self, buffer: PatternBuffer, app) -> None:
        """Draw into ``buffer``. Called top of stack last."""
        raise NotImplementedError

    def key(self, name: str, event, app) -> bool:
        """Handle a key. Returns whether it was used.

        ``name`` is the terminal name -- ``"up"``, ``"enter"``, ``"escape"``,
        ``"k"`` -- so a screen's key handling reads exactly as the terminal
        build's did. ``event`` is the Qt event, for the two things a name cannot
        carry: whether it was an auto-repeat, and the typed character.
        """
        return False

    #: What a key this screen *used* sounds like.
    #:
    #: A cursor click, because a screen is a menu by default -- and the floor
    #: overrides it, because in that one screen the four directions are not a
    #: cursor, they are feet. The sound lives here and not in the screen's own
    #: key handling for the reason the cells live in the grid: fourteen screens
    #: clicking their own cursor is fourteen chances to forget it in the
    #: fifteenth, and this way the answer is a table.
    UI_SOUNDS: dict[str, str] = {
        "up": "cursor_move",
        "down": "cursor_move",
        "left": "cursor_move",
        "right": "cursor_move",
        "pageup": "tab_switch",
        "pagedown": "tab_switch",
        "home": "tab_switch",
        "end": "tab_switch",
        "enter": "cursor_confirm",
        "take": "cursor_confirm",
        "space": "cursor_confirm",
        "escape": "cursor_back",
        "backspace": "cursor_back",
    }

    def key_sound(self, name: str) -> str | None:
        """The sound this screen makes for a key it used, or ``None``."""
        return self.UI_SOUNDS.get(name)

    def key_up(self, name: str, event, app) -> bool:
        """The key went up. Only the hold screens care; everything else
        answers a press, never a release."""
        return False

    def art(self, app) -> list:
        """The pictures this screen wants on the frame, and where.

        Empty for almost every screen, because the grid is the look. Where a
        screen does have art, it says *what* and *where* and the application that
        is drawing puts it down -- so the same roster draws the same hero on a
        frame this build painted and on one a front end with no Qt painted.
        """
        return []

    #: What the controller's buttons mean here: physical button -> key name.
    #: A screen that says nothing gets the default (A confirms, B goes back),
    #: and a screen that says ``None`` for a button means "nothing here".
    from ..padmap import DEFAULT as PAD

    #: Whether the left stick and the D-pad may send the four diagonals. Only
    #: the floor moves in eight directions; a menu that heard ``home`` would
    #: jump to its first row on a diagonal push.
    pad_diagonals = False

    #: Whether the right stick may page the body. Reading screens want it; the
    #: floor must not, because its page keys are movement.
    pad_scroll = False

    #: Whether the screen is in the middle of something it has to finish.
    #: A screen that says yes is stepped once per frame and repainted while it
    #: does, because nothing else in this game needs a heartbeat: the hold bars
    #: read the clock themselves and the particles live in the effects layer.
    @property
    def busy(self) -> bool:
        """Whether a bar is filling on this screen.

        A hold's bar is wall-clock time: between two presses it still has to be
        painted, or it stands still while the key is down. Any screen with a
        ``hold`` answers for it here; the ones with a clock of their own (the
        fight) say so themselves.
        """
        hold = getattr(self, "hold", None)
        return bool(hold is not None and hold.progress)

    #: Whether something on this screen is *moving*, which is not the same as
    #: talking: a fight breathes while the player is deciding what to do, and a
    #: screen that is moving is repainted every frame without taking the keyboard
    #: away. Nothing else in this game moves on its own.
    animating: bool = False

    def step(self, dt: float, app) -> None:
        """A frame went by. Only the screens with something to play override it."""
        return None
