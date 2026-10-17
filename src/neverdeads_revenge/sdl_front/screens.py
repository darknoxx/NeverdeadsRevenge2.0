"""Screens that exist because a session ended before the real one did.

The port order is chosen by what the game needs *next*, and one thing it needs is
a way to say "this part is not here yet" without lying about it. A front end that
silently swallowed a fight would be a front end that lost a fight; one that
opened an empty arena would be worse.

So this is the honest placeholder: it names what was about to happen, and it goes
away when the player says so. It is the only screen in the second front end that
the first one does not have, and the plan is for it to have nothing to do.
"""

from __future__ import annotations

from ..desktop.chrome import ASH, BONE, box
from ..desktop.theme import parse_style

__all__ = ["NotYetScreen"]


class NotYetScreen:
    """One paragraph of truth, centred, and a key to close it."""

    modal = True

    def __init__(self, headline: str, already: str = "", on_close=None) -> None:
        self.headline = headline
        self.already = already
        self.on_close = on_close

    def draw(self, buffer, app) -> None:
        width = min(buffer.cols - 8, 62)
        height = 9
        x = (buffer.cols - width) // 2
        y = (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title="NOT IN THIS BUILD", border=ASH, fill=True)
        buffer.text(x + 3, y + 2, self.headline[: width - 6], parse_style(f"bold {BONE}"))
        for index, line in enumerate(_wrap(self.already, width - 6)[:3]):
            buffer.text(x + 3, y + 4 + index, line, parse_style(ASH))
        buffer.text(x + 3, y + height - 2, "enter  close", parse_style(ASH))

    def key(self, name, event, app) -> bool:
        if name in ("enter", "space", "escape"):
            app.pop()
            if self.on_close is not None:
                self.on_close()
            return True
        return False


def _wrap(text: str, width: int) -> list[str]:
    """Greedy wrapping, because a paragraph in a panel should not run off it."""
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines
