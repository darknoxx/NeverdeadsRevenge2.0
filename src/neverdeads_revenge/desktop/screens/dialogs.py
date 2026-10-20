"""The dialogs: the four times the game stops and asks, and one it just shows.

Every one of them is the same box, the same frame and the same hint line at the
bottom, because a player who has read one of these should recognise the next.
None of them acts on an auto-repeat: Qt tells us when a key is being held, so a
dialog opened by a held enter cannot be answered by the same hold.
"""

from __future__ import annotations

import math

from ..art import size
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
    """A centred box with a title, a body and a hint.

    A dialog is a *window*, not a room: it draws its own box and leaves the floor
    around it alone, because a card is something the player reads while they are
    still standing somewhere. The menus are the room; this is not.
    """

    modal = True
    #: And it does not cover what is under it. The exception is a room that
    #: paints in pixels -- the arena, the turning -- where the paint lands after
    #: the grid and would cover the box; the app keeps those dialogs solid.
    opaque = False

    title = ""
    hint = ""

    #: The rows a picture may take at the top of the box: six of a twenty-pixel
    #: row is a blade at the size it was painted, so the card shows the drawing
    #: rather than a thumbnail of it.
    PICTURE_ROWS = 6

    #: What the box shows above its words, when it has something to show.
    picture: str | None = None

    #: Whether the box is fitted to what it holds, and its lines centred. The
    #: cards are: six lines in a frame built for thirty is a card that looks like
    #: an empty room. A question is not -- a paragraph wants the room to say
    #: itself, and a centred paragraph is a poem.
    FITTED = False

    def __init__(self, on_done=None) -> None:
        self.on_done = on_done

    def _body(self) -> str:
        return ""

    # -- the geometry, in one place -----------------------------------------
    @staticmethod
    def _cell(buffer) -> tuple[int, int]:
        """How wide a cell is, for a pass that has to know: ten by twenty.

        The grid is drawn by an application that has a face; a frame built in a
        test may not, and the reference cell is what the game is laid out for.
        """
        font = getattr(buffer, "font", None)
        return (getattr(font, "cell_w", 10), getattr(font, "cell_h", 20))

    def _picture_height(self, cell_h: int) -> int:
        """How tall the drawing is in pixels: never bigger than it was painted.

        The rows are sized for a blade, and a bottle is a smaller thing than a
        blade. A picture stretched to fill the frame it was given looks
        resampled, which is the one thing the sheets are drawn to avoid.
        """
        height = self.PICTURE_ROWS * cell_h - 6
        measured = size(self.picture) if self.picture is not None else None
        if measured is not None:
            height = min(height, measured[1])
        return height

    def _picture_rows(self, cell_h: int) -> int:
        """And how many rows of the box that takes, rounded up."""
        if self.picture is None:
            return 0
        return max(1, math.ceil((self._picture_height(cell_h) + 4) / cell_h))

    def _frame(
        self, cols: int, rows: int, cell_w: int = 10, cell_h: int = 20
    ) -> tuple[int, int, int, int]:
        """The box, in cells: the same sums ``draw`` makes, so ``art`` agrees.

        Two passes read this geometry -- the grid pass that lays the words out
        and the picture pass that puts the drawing above them -- and a picture
        that disagreed with the box would sit in the title or on the border.
        """
        lead = self._picture_rows(cell_h)
        padded = 4 if self.FITTED else 6
        if self.FITTED:
            # Wide enough for the longest line it will hold, and for the title
            # and the hint, and not a cell more.
            widest = max(
                [len(line) for line in self._body().split("\n")]
                + [len(self.title) + 2, len(self.hint), 16]
            )
            if self.picture is not None:
                measured = size(self.picture)
                if measured is not None:
                    widest = max(widest, math.ceil(measured[0] / cell_w))
            width = max(16, min(cols - 6, 66, widest + 6))
        else:
            width = min(cols - 6, 66)
        body = wrap(self._body(), width - 6)
        height = min(rows - 2, len(body) + padded + lead)
        return (cols - width) // 2, (rows - height) // 2, width, height

    def draw(self, buffer, app) -> None:
        cell_w, cell_h = self._cell(buffer)
        x, y, width, height = self._frame(buffer.cols, buffer.rows, cell_w, cell_h)
        body = wrap(self._body(), width - 6)
        lead = self._picture_rows(cell_h)
        box(buffer, x, y, width, height, title=self.title, border=BLOOD, fill=True)
        for i, line in enumerate(body[: height - 4 - lead]):
            at = x + 3
            if self.FITTED:
                at = x + max(2, (width - len(line)) // 2)
            buffer.text(at, y + 2 + lead + i, line, parse_style(BONE))
        rule(buffer, x + 1, y + height - 2, width - 2, ASH)
        hint = self.hint[: width - 6]
        at = x + 3
        if self.FITTED:
            at = x + max(2, (width - len(hint)) // 2)
        buffer.text(at, y + height - 1, hint, parse_style(ASH))

    def art(self, app) -> list:
        """The picture above the words, if the dialog has one."""
        if self.picture is None:
            return []
        from ..art import Placed

        cell_w, cell_h = app.font.cell_w, app.font.cell_h
        x, y, width, _height = self._frame(app.cols, app.rows, cell_w, cell_h)
        lead = self._picture_rows(cell_h)
        # Centred in the box and standing on the line above the first of the
        # body's rows, which is what the reserved rows were left for.
        centre = (x + width / 2) * cell_w
        bottom = (y + 1 + lead) * cell_h - 2
        return [Placed(self.picture, centre, bottom, self._picture_height(cell_h))]

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


class KindlyScreen(_Dialog):
    """THE KINDLY ONE, asking.

    It does not attack and it does not block: it stands with a hand out and asks
    for a little. Pay it and it goes; refuse and it is the worst thing on the
    floor. The dialog is the whole of the encounter -- the arena never opens for
    a price that was paid.
    """

    modal = True
    title = "THE KINDLY ONE"
    hint = "enter pay it    esc refuse"

    def __init__(self, price: int, on_done=None) -> None:
        from ..hold import HoldToContinue

        super().__init__(on_done)
        self.price = price
        self.hold = HoldToContinue()

    def _body(self) -> str:
        return (
            "It holds out a hand. It does not want a fight, and it is not asking "
            "for one.\n\n"
            f"It wants {self.price} gold.\n\n"
            "Refuse, and you will find out what it is when it is not asking."
        )

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name == "escape":
            self.finish(app, False)
            return True
        if name in ("enter", "return"):
            self.finish(app, True)
            return True
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
    decoration.

    It closes on enter and escape and on nothing else. Any-key closing was a
    trap: a wraith lands a curse mid-fight, the window opens, and the direction
    key already under the player's thumb dismisses the page before a word of it
    is read. A key you have to *choose* is the difference between reading it
    and losing it.
    """

    FITTED = True

    def __init__(
        self, title: str, name: str, text: str, picture: str | None = None
    ) -> None:
        super().__init__()
        self.title = title
        self._name = name
        self._text = text
        # The blade's own drawing when there is one: the card is where a player
        # first meets a weapon, and a weapon is a thing you recognise by sight.
        self.picture = picture
        # Short, because the card is fitted to its contents and a long hint
        # would be the widest thing in it.
        self.hint = "enter  back"

    def _body(self) -> str:
        return f"{self._name}\n\n{self._text}"

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name in ("enter", "return", "escape"):
            self.finish(app, None)
        # Everything else is swallowed: a direction key, a drink, a wait -- all
        # of them are keys the player was already pressing.
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
