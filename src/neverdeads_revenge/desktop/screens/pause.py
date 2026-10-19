"""The pause menu.

Thin on purpose: resume, save and quit, quit to title, and the sound. The sound
toggle lives here because this is the only menu in the game and a sound you
cannot turn off is a sound that stops you playing.
"""

from __future__ import annotations

from ..chrome import ASH, BLOOD, box, menu
from ..theme import parse_style
from .base import Screen

__all__ = ["PauseScreen"]


class PauseScreen(Screen):
    """The dungeon, held still."""

    modal = True

    def __init__(self) -> None:
        self.index = 0

    def items(self, app) -> list[tuple[str, str]]:
        items = [
            ("r", "RESUME"),
            ("c", "CONTROLS"),
            ("s", "SAVE AND QUIT"),
            ("q", "QUIT TO TITLE"),
            ("m", f"SOUND: {'on' if not app.sfx.muted else 'off'}"),
        ]
        # The sheet and the legend are on the keys c and l in the dungeon, and a
        # handheld has no c -- so they are here, where every player can reach
        # them with a d-pad.
        items.insert(2, ("t", "THE SHEET"))
        items.insert(3, ("g", "THE LEGEND"))
        if getattr(app, "joysticks", None):
            # The bench, and only when there is something to bench. On a desktop
            # with no pad plugged in it would be a line answering a question
            # nobody asked, and a menu line that does nothing is a line that
            # teaches a player to distrust the menu.
            items.insert(4, ("p", "THE PAD"))
        return items

    def draw(self, buffer, app) -> None:
        items = self.items(app)
        width = 34
        height = len(items) + 4
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title="PAUSED", border=BLOOD, fill=True)
        menu(buffer, x + 3, y + 2, items, self.index)

    def key(self, name, event, app) -> bool:
        # One gesture per menu line: a held r would pop, a held m would flip the
        # sound thirty times a second.
        if event.isAutoRepeat():
            return True
        items = self.items(app)
        if name in ("up", "k"):
            self.index = (self.index - 1) % len(items)
            return True
        if name in ("down", "j"):
            self.index = (self.index + 1) % len(items)
            return True
        if name == "enter":
            self._choose(items[self.index][0], app)
            return True
        if name in ("escape", "r"):
            app.pop()
            return True
        if name in ("s", "q", "m", "c", "p", "t", "g"):
            self._choose(name, app)
            return True
        return True

    def _choose(self, key: str, app) -> None:
        if key == "r":
            app.pop()
        elif key == "c":
            # The reference, from the one menu that has room to offer it.
            from .menus import HelpScreen

            app.push(HelpScreen())
        elif key == "t":
            from .menus import CharacterScreen

            if app.run is not None:
                app.push(CharacterScreen(app.run))
        elif key == "g":
            from .menus import LegendScreen

            if app.run is not None:
                app.push(LegendScreen(app.run))
        elif key == "p":
            # What the pad actually sends. Here rather than only on the command
            # line because a handheld has no command line: this is the only door
            # left once the game is installed.
            app.open_bench()
        elif key == "s":
            app.save_and_quit()
        elif key == "q":
            app.confirm_quit_to_title()
        elif key == "m":
            app.toggle_sound()
            self.index = min(self.index, len(self.items(app)) - 1)
