"""The screen stack.

A screen draws itself into the pattern buffer and answers a key. That is the
whole contract: the app owns the stack, the run and the progress, and a screen
is a function of the run plus a set of keys.

Modals draw *over* what is under them rather than replacing it, which is how the
dungeon stays visible behind a dialog -- the same thing the terminal did by
dimming a modal's background, done here by simply not clearing what is below.
"""

from __future__ import annotations

from ..buffer import PatternBuffer

__all__ = ["Screen"]


class Screen:
    """One thing on the screen."""

    #: Whether the stack below this screen is drawn first. Dialogs are modals;
    #: the title and the game are not.
    modal = False

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

    def key_up(self, name: str, event, app) -> bool:
        """The key went up. Only the hold screens care; everything else
        answers a press, never a release."""
        return False
