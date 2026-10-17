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

    def paste(self, image, app) -> None:
        """Draw straight onto the rendered frame, in pixels.

        The exception, not the rule: everything else writes characters into the
        grid, and the grid is the look. This exists for the two cases that need
        a size the grid cannot give them -- the log and the sidebar, which are a
        smaller face of the same font, and the battle's monsters, which are the
        alphabet of the dungeon drawn big enough to fight.
        """
        return None

    def art(self, app) -> list:
        """The pictures this screen wants on the frame, and where.

        Empty for almost every screen, because the grid is the look. Where a
        screen does have art, it says *what* and *where* and the application that
        is drawing puts it down -- so the same roster draws the same hero on a
        frame this build painted and on one a front end with no Qt painted.
        """
        return []

    #: Whether the screen is in the middle of something it has to finish.
    #: A screen that says yes is stepped once per frame and repainted while it
    #: does, because nothing else in this game needs a heartbeat: the hold bars
    #: read the clock themselves and the particles live in the effects layer.
    busy: bool = False

    #: Whether something on this screen is *moving*, which is not the same as
    #: talking: a fight breathes while the player is deciding what to do, and a
    #: screen that is moving is repainted every frame without taking the keyboard
    #: away. Nothing else in this game moves on its own.
    animating: bool = False

    def step(self, dt: float, app) -> None:
        """A frame went by. Only the screens with something to play override it."""
        return None
