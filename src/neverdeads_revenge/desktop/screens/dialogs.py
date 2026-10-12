"""The dialogs: the four times the game stops and asks, and one it just shows.

Every one of them is the same box, the same frame and the same hint line at the
bottom, because a player who has read one of these should recognise the next.
None of them acts on an auto-repeat: Qt tells us when a key is being held, so a
dialog opened by a held enter cannot be answered by the same hold.
"""

from __future__ import annotations

from ..chrome import ASH, BONE, BLOOD, box, rule
from ..theme import parse_style
from .base import Screen
from .game_over import clean_name

__all__ = [
    "ConfirmScreen",
    "ChestScreen",
    "SpringScreen",
    "NpcScreen",
    "PageScreen",
    "InfoScreen",
    "DeleteProgressScreen",
    "OPEN",
    "FAME",
]

OPEN = "open"
FAME = "fame"


def wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap. A word longer than the line is left to overflow."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        line = ""
        for word in paragraph.split():
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width:
                line += " " + word
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


class _Dialog(Screen):
    """A centred box with a title, a body and a hint."""

    modal = True
    title = ""
    hint = ""

    def __init__(self, on_done=None) -> None:
        self.on_done = on_done

    def _body(self) -> str:
        return ""

    def draw(self, buffer, app) -> None:
        width = min(buffer.cols - 6, 66)
        body = wrap(self._body(), width - 6)
        height = min(buffer.rows - 2, len(body) + 6)
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title=self.title, border=BLOOD, fill=True)
        for i, line in enumerate(body[: height - 4]):
            buffer.text(x + 3, y + 2 + i, line, parse_style(BONE))
        rule(buffer, x + 1, y + height - 2, width - 2, ASH)
        buffer.text(x + 3, y + height - 1, self.hint[: width - 6], parse_style(ASH))

    def finish(self, app, value) -> None:
        app.pop()
        if self.on_done is not None:
            self.on_done(value)


class ConfirmScreen(_Dialog):
    """A yes/no question. Escape answers no, the way it does everywhere."""

    def __init__(self, title: str, body: str, on_done=None) -> None:
        super().__init__(on_done)
        self.title = title
        self._text = body
        self.hint = "y  yes        n / esc  no"

    def _body(self) -> str:
        return self._text

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name == "y":
            self.finish(app, True)
        elif name in ("n", "escape"):
            self.finish(app, False)
        return True


class ChestScreen(_Dialog):
    """The price, and nothing else. The reward stays behind the lid."""

    title = "AN OMINOUS CHEST"

    def __init__(self, price: str, on_done=None) -> None:
        super().__init__(on_done)
        self.price = price
        self.hint = "enter open it    f the curse, for fame    esc walk away"

    def _body(self) -> str:
        return (
            "It glows. Whatever is inside is worth having, and it is not free."
            f"\n\n{self.price}\n\n"
            "Pay it and take what is in it. Or pay it and take nothing at all -- "
            "and the dark will remember your name."
        )

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name == "enter":
            self.finish(app, OPEN)
        elif name == "f":
            self.finish(app, FAME)
        elif name in ("escape", "n"):
            self.finish(app, None)
        return True


class SpringScreen(_Dialog):
    """Ask before the water takes a curse."""

    title = "A SPRING"

    def __init__(self, prompt: str, on_done=None) -> None:
        super().__init__(on_done)
        self.prompt = prompt
        self.hint = "enter wash it off    esc leave it"

    def _body(self) -> str:
        return self.prompt

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name == "enter":
            self.finish(app, True)
        elif name in ("escape", "n"):
            self.finish(app, False)
        return True


class DeleteProgressScreen(_Dialog):
    """Erasing everything, on purpose, with the word typed out.

    A confirm key is a reflex; a word is a decision. Nothing goes until the
    six letters are there, and escape always walks away. The alternative --
    a two-key dialog -- is the one that gets answered by a hand that was
    already moving.
    """

    modal = True
    title = "DELETE EVERYTHING"
    hint = "type DELETE   enter to erase   esc to keep"

    def __init__(self, on_done=None) -> None:
        super().__init__(on_done)
        self.typed = ""

    def _body(self) -> str:
        return (
            "This erases every score on the board, the chronicle, the purse, "
            "every upgrade bought, and the run you put down. There is no undo "
            "and no copy.\n\n"
            f"Type DELETE to be sure:   {self.typed or '_'}"
        )

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name == "escape":
            self.finish(app, False)
            return True
        if name == "backspace":
            self.typed = self.typed[:-1]
            return True
        if name == "enter":
            self.finish(app, self.typed.upper() == "DELETE")
            return True
        char = clean_name(event.text() or "")
        if char and len(self.typed) < len("DELETE"):
            self.typed += char.upper()
        return True


class NpcScreen(_Dialog):
    """Somebody has something to say. Any key closes it."""

    def __init__(self, speaker: str, line: str, on_done=None) -> None:
        super().__init__(on_done)
        self.title = speaker.upper()
        self.line = line
        self.hint = "any key"

    def _body(self) -> str:
        return self.line

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        self.finish(app, None)
        return True


class InfoScreen(_Dialog):
    """What the dark just handed over: a name, and what it does.

    Everything a run catches whose shape is its own price -- a blade picked
    up, a curse left in you, a gift the dark decided you need -- gets one of
    these, because a log line scrolls away and a note in the sidebar is a
    decoration. One box, one page, read with one press.
    """

    def __init__(self, title: str, name: str, text: str) -> None:
        super().__init__()
        self.title = title
        self._name = name
        self._text = text
        self.hint = "enter  back to the dark"

    def _body(self) -> str:
        return f"{self._name}\n\n{self._text}"

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        self.finish(app, None)
        return True


class PageScreen(_Dialog):
    """A page of the chronicle, opened the moment it is found."""

    def __init__(self, number: int, text: str, on_done=None) -> None:
        super().__init__(on_done)
        from neverdeads_revenge.game.lore import numeral

        self.title = f"THE CHRONICLE  ·  PAGE {numeral(number)}"
        self.text = text
        self.offset = 0
        self.hint = "↑↓ scroll    any other key closes"

    def _body(self) -> str:
        return self.text

    def draw(self, buffer, app) -> None:
        width = min(buffer.cols - 6, 72)
        body = wrap(self._body(), width - 6)
        height = min(buffer.rows - 2, 22)
        self._span = (len(body), height - 4)
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title=self.title, border=BLOOD, fill=True)
        window = body[self.offset : self.offset + height - 4]
        for i, line in enumerate(window):
            buffer.text(x + 3, y + 2 + i, line, parse_style(BONE))
        rule(buffer, x + 1, y + height - 2, width - 2, ASH)
        more = "  ▼ more" if self.offset + height - 4 < len(body) else ""
        buffer.text(x + 3, y + height - 1, (self.hint + more)[: width - 6], parse_style(ASH))

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        total, window = getattr(self, "_span", (0, 0))
        floor = max(0, total - window)
        if name in ("down", "j", "s"):
            if floor:
                self.offset = min(self.offset + 1, floor)
            return True
        if name in ("up", "k", "w"):
            self.offset = max(0, self.offset - 1)
            return True
        self.finish(app, None)
        return True
