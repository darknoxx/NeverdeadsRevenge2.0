"""The title.

A grim little menu: the name in the block font, a line under it that says what
the game is about, and five things to do. The stack is a list of ``(key, label)``
so the menu, the keys and the drawing cannot disagree about what is on it.
"""

from __future__ import annotations

from ..blocks import render_word
from ..chrome import ASH, BONE, BLOOD, PURPLE, rule
from ..theme import parse_style
from .base import Screen

__all__ = ["TitleScreen"]


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
        buffer.clear()
        art = render_word("NEVERDEAD'S") + render_word("REVENGE")
        version = render_word("2.0", scale=2)
        items = self.items(app)

        # Everything the title has to hold, laid out from the top so the big
        # version number cannot push the menu off the bottom of a 27-row grid.
        best = app.progress.best_score
        block = len(art) + len(version) + 2 + (1 if best else 0) + 3
        y = max(0, (buffer.rows - block) // 2)

        for line in art:
            self._centre(buffer, y, line, f"bold {PURPLE}")
            y += 1
        for line in version:
            self._centre(buffer, y, line, "bold #8b1a1a")
            y += 1
        y += 1
        if best:
            self._centre(buffer, y, f"best {best}", ASH)
            y += 1
        y += 1

        rule(buffer, 2, y, buffer.cols - 4, BLOOD)
        y += 1
        self._menu_line(buffer, y, items, self.index)
        self._centre(buffer, buffer.rows - 2, "↑↓ choose   enter take   esc quit", ASH)

    def _menu_line(self, buffer, y, items, index) -> None:
        """The menu as one line, the chosen entry lit and bracketed.

        A line rather than a box, because the title's own art is ten rows and
        the version number is ten more: on a 27-row grid a boxed menu is a menu
        that falls off the screen. The choices are all still one keypress away.
        """
        texts = [
            f"[{label}]" if i == index else label for i, (_key, label) in enumerate(items)
        ]
        x = max(0, (buffer.cols - len("   ".join(texts))) // 2)
        for i, (_key, _label) in enumerate(items):
            chosen = i == index
            style = parse_style(f"bold {BONE}") if chosen else parse_style(ASH)
            buffer.text(x, y, texts[i], style)
            x += len(texts[i]) + 3

    @staticmethod
    def _centre(buffer, y: int, text: str, style: str) -> None:
        x = max(0, (buffer.cols - len(text)) // 2)
        buffer.text(x, y, text, parse_style(style))

    # -- input --------------------------------------------------------------
    def key(self, name: str, event, app) -> bool:
        items = self.items(app)
        # Strictly a line read sideways: left and right move it. Up and down say
        # nothing, which is the whole point of "only the keys a line understands"
        # -- before this, every arrow was welcome and the answer was chaos.
        if name == "left":
            self.index = (self.index - 1) % len(items)
            return True
        if name == "right":
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
