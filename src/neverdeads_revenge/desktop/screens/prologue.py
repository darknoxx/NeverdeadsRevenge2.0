"""The premise, told once.

Between the hero choice and floor one: the one piece of prose in the game, and
the only moment the mechanics are allowed to be quiet. It closes on a *held*
enter -- a stray press cost the first player this text, and nobody has read it
by accident since.

The story scrolls in place (the arrows and space), because a screen this full
does not fit a small grid, and a text nobody can finish reading is a text they
will hold past. Under the rule is the hold bar and the hint line, and escape
skips: this is a premise, not a toll.
"""

from __future__ import annotations

from neverdeads_revenge.game.prologue import PROLOGUE, PROLOGUE_HINT, PROLOGUE_TITLE

from ..chrome import ASH, BONE, BLOOD, PURPLE, box, rule
from ..hold import HoldToContinue
from ..theme import parse_style
from .base import Screen
from .dialogs import wrap

__all__ = ["PrologueScreen"]

#: Keys that move the story in place, and how far. Nothing here closes; closing
#: is the hold's business and escape's.
_SCROLL_STEP: dict[str, int | None] = {
    "down": 2,
    "pagedown": 6,
    "space": 6,
    "up": -2,
    "pageup": -6,
    "home": None,
    "end": None,
}

_FILLED = PURPLE
_EMPTY = "#4a4a4a"


class PrologueScreen(Screen):
    """The premise. Once per session; the app remembers having shown it."""

    modal = True

    def __init__(self, on_done=None) -> None:
        self.on_done = on_done
        self.hold = HoldToContinue()
        self.offset = 0

    # -- what is on the page -------------------------------------------------
    def _page(self, width: int) -> list[tuple[str, str]]:
        """The story, wrapped, as ``(text, style)`` -- title, prose, and the one
        line it is meant to leave a reader with."""
        lines: list[tuple[str, str]] = [(PROLOGUE_TITLE, f"bold {PURPLE}")]
        for paragraph in PROLOGUE:
            lines.append(("", ""))
            lines.extend((piece, BONE) for piece in wrap(paragraph, width - 10))
        lines.append(("", ""))
        lines.append((PROLOGUE_HINT, "dim"))
        return lines

    def _window(self, app) -> tuple[int, int]:
        """``(page length, lines shown)`` -- the clamp and the draw agree on it."""
        cols, rows = app.cells
        height = min(rows - 2, 21)
        return len(self._page(min(cols - 8, 66))), height - 5

    # -- drawing -------------------------------------------------------------
    def draw(self, buffer, app) -> None:
        buffer.clear()
        width = min(buffer.cols - 8, 66)
        height = min(buffer.rows - 2, 21)
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, border=BLOOD, fill=True)

        page = self._page(width)
        window = page[self.offset : self.offset + height - 5]
        for i, (text, style) in enumerate(window):
            buffer.text(x + 4, y + 2 + i, text[: width - 8], parse_style(style))
        rule(buffer, x + 1, y + height - 3, width - 2, ASH)
        buffer.text(x + 4, y + height - 2, "arrows read   hold enter to begin", parse_style(ASH))
        bar_style = f"bold {_FILLED}" if self.hold.progress else _EMPTY
        buffer.text(x + width - 4 - 10, y + height - 2, self.hold.bar(), parse_style(bar_style))

    # -- input --------------------------------------------------------------
    #: The hold key has no click of its own.
    #:
    #: A press that *starts* a hold has decided nothing -- that is the whole
    #: design of the bar, and a tap goes nowhere -- so the only sound this screen
    #: makes for ``enter`` is the one at the end of the fill, played by the
    #: screen itself. Everything else about the interface still clicks through
    #: the table it inherits.
    UI_SOUNDS = {
        key: sound
        for key, sound in Screen.UI_SOUNDS.items()
        if key not in ("enter", "space")
    }

    def key(self, name: str, event, app) -> bool:
        if name in _SCROLL_STEP:
            if event.isAutoRepeat():
                return True
            total, shown = self._window(app)
            step = _SCROLL_STEP[name]
            if step is None:  # home and end: named by where they go
                self.offset = total - shown if name == "end" else 0
            else:
                self.offset = max(0, min(self.offset + step, max(0, total - shown)))
            return True
        if name == "escape":
            # Skipping is allowed -- on a press, not on a thirtieth of a
            # second. The hold's own repeats stay: they *are* the hold.
            if not event.isAutoRepeat():
                self.finish(app)
            return True
        if name in ("enter", "return"):
            # Repeats are the hold's food; nothing else here acts on them.
            if self.hold.press(name, event.isAutoRepeat()):
                # One sound, at the end of the hold and not on every repeat:
                # this is one decision however many frames it took to make.
                app.play("cursor_confirm")
                self.finish(app)
            return True
        return True

    def key_up(self, name: str, event, app) -> bool:
        # The desktop can *see* the key come up, so a tap is a tap: nothing is
        # banked, and the next press starts an unfilled bar. Platforms that
        # synthesise repeats as press/release pairs pair the release too;
        # those are not a key coming up.
        if not event.isAutoRepeat():
            self.hold.release(name)
        return True

    def finish(self, app) -> None:
        app.pop()
        if self.on_done is not None:
            self.on_done()