"""The title.

A grim little menu: the name in the block font, a line under it that says what
the game is about, and five things to do. The stack is a list of ``(key, label)``
so the menu, the keys and the drawing cannot disagree about what is on it.
"""

from __future__ import annotations

from ..blocks import render_word
from ..chrome import ASH, BONE, BLOOD, PURPLE, box, menu
from ..theme import parse_style
from .base import Screen

__all__ = ["TitleScreen", "TAGLINE"]

#: The line under the name. The premise, not the genre.
TAGLINE = "death was not granted to him"


class TitleScreen(Screen):
    """Where a run starts, and where one ends up."""

    def __init__(self) -> None:
        self.index = 0

    def items(self, app) -> list[tuple[str, str]]:
        items = [("n", "NEW RUN")]
        if app.has_saved_run():
            items.append(("c", "CONTINUE"))
        items += [
            ("s", "SHOP"),
            ("h", "SCORES"),
            ("l", "CHRONICLE"),
            ("q", "QUIT"),
        ]
        return items

    def draw(self, buffer, app) -> None:
        from ..render import draw_title

        buffer.clear()
        art = render_word("NEVERDEAD'S") + render_word("REVENGE")
        top = max(1, (buffer.rows - (len(art) + 14)) // 2)
        y = top
        for line in art:
            x = max(0, (buffer.cols - len(line)) // 2)
            buffer.text(x, y, line, parse_style(f"bold {PURPLE}"))
            y += 1
        y += 1
        self._centre(buffer, y, TAGLINE, "bold " + BONE)
        y += 1
        best = app.progress.best_score
        if best:
            self._centre(buffer, y, f"best {best}", ASH)
        y += 2

        items = self.items(app)
        width = max(len(label) for _, label in items) + 12
        x = max(0, (buffer.cols - width) // 2)
        box(buffer, x, y, width, len(items) + 2, border=BLOOD)
        menu(buffer, x + 3, y + 1, items, self.index)

        hint = "↑↓ choose   enter take   esc quit"
        self._centre(buffer, buffer.rows - 2, hint, ASH)

    @staticmethod
    def _centre(buffer, y: int, text: str, style: str) -> None:
        x = max(0, (buffer.cols - len(text)) // 2)
        buffer.text(x, y, text, parse_style(style))

    # -- input --------------------------------------------------------------
    def key(self, name: str, event, app) -> bool:
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
        # A letter picks its line outright, the way the terminal title did.
        for key, _label in items:
            if name == key:
                self._choose(key, app)
                return True
        if name == "escape":
            app.quit_requested()
            return True
        return False

    def _choose(self, key: str, app) -> None:
        if key == "n":
            app.open_hero_select()
        elif key == "c":
            app.continue_run()
        elif key == "s":
            app.open_shop()
        elif key == "h":
            app.open_scoreboard()
        elif key == "l":
            app.open_chronicle()
        elif key == "q":
            app.quit_requested()
