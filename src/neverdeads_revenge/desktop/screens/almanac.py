"""The Almanac: the chronicle, and the monsters that wrote it.

One book with two halves, because they answer the same question from two sides.
The chronicle is what the old lords left behind; the bestiary is what is still
down there, written down the moment it is first killed. A player who opens the
Almanac is asking "what is this place", and the answer is a page of the book or
a page of the dungeon.

The bestiary is *earned*: a monster's page is blank until the run has killed
one, so the book fills as the player survives. That is the whole reason it is a
collection and not a manual -- a manual would have told them what the hush does,
and finding out is the game.

Order is alphabetical by the name on the page. Not by floor (nobody looks a
monster up by the floor it stood on) and not by when it was met (that is the
shelf of a collector, not a book).
"""

from __future__ import annotations

from ...game.actors import ENEMIES
from ...game.bestiary import ENTRIES, Entry, stat_lines, title_of
from ...game.lore import PAGE_COUNT, TITLE, numeral, page
from ..art import Placed, exists as art_exists, size as art_size
from ..chrome import ASH, BONE, BLOOD, PURPLE, box, rule
from ..theme import parse_style
from .base import Screen
from .dialogs import wrap

__all__ = ["AlmanacScreen"]


def _wrap(text: str, width: int) -> list[str]:
    return wrap(text, max(8, width))


def _clip(text: str, width: int) -> str:
    """One line, shortened to fit -- with an ellipsis, never mid-letter.

    The index has a fixed width and one name is longer than it: cutting with
    ``text[:width]`` leaves "one who did not come bac", which reads as a bug
    rather than as an abbreviation.
    """
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


class AlmanacScreen(Screen):
    """Two tabs, one cover."""

    modal = True

    #: The two halves, in the order they are read: the story first, the monsters
    #: second. The other order would open the book on a list of things that have
    #: not happened yet.
    TABS = ("CHRONICLE", "BESTIARY")

    #: How wide the bestiary's index is, in cells -- a third of the page and no
    #: wider, so the page never gets the narrow half. The longest name ("one who
    #: did not come back") is shortened on the index and whole on the page: an
    #: index is for finding a thing, the page is for reading it.
    LIST_WIDTH = 30

    #: Rows of a twenty-pixel line the monster's picture may take. Six is the
    #: height the sheets were painted at, so the page shows the figure at 1:1
    #: rather than as a thumbnail of it.
    PICTURE_ROWS = 6

    #: The column the figure stands in, in cells, when the page is wide enough to
    #: afford one. Beside the words and not above them: a page whose lore has to
    #: give up its last lines so an illustration can breathe is a page that has
    #: its priorities backwards.
    FIGURE_COLUMN = 14

    #: How far a page-up moves the body, in lines: the chronicle's scroll and a
    #: long page's, because both are prose a player reads downward.
    PAGE_SCROLL = 9

    def __init__(self) -> None:
        self.tab = 0
        #: The chronicle's scroll, and the bestiary's cursor and page scroll.
        self.offset = 0
        self.index = 0
        self.list_offset = 0
        self.detail_offset = 0
        #: The size of the body as of the last draw: the key handler needs it to
        #: refuse scrolling a list that does not overflow, and to page a body
        #: that does.
        self._body = (0, 0)

    # -- what the book knows ------------------------------------------------
    @staticmethod
    def known(app) -> set[str]:
        return set(getattr(app.progress, "bestiary", ()))

    def _selected(self, app) -> Entry:
        return ENTRIES[max(0, min(self.index, len(ENTRIES) - 1))]

    # -- the frame ----------------------------------------------------------
    def _frame(self, buffer) -> tuple[int, int, int, int]:
        width = min(buffer.cols - 4, 92)
        height = min(buffer.rows - 2, 30)
        return width, height, (buffer.cols - width) // 2, (buffer.rows - height) // 2

    def draw(self, buffer, app) -> None:
        width, height, x, y = self._frame(buffer)
        box(buffer, x, y, width, height, title="THE ALMANAC", border=BLOOD, fill=True)
        body_rows = height - 6
        self._body = (body_rows, width)
        self._more = False
        self._tabs(buffer, app, x, y, width)
        rule(buffer, x + 1, y + 2, width - 2, ASH)
        if self.tab == 0:
            self._chronicle(buffer, app, x, y, width, body_rows)
        else:
            self._bestiary(buffer, app, x, y, width, body_rows)
        rule(buffer, x + 1, y + height - 2, width - 2, ASH)
        hint = (
            "←→ tab   ↑↓ scroll   esc close"
            if self.tab == 0
            else "←→ tab   ↑↓ choose   pgup/pgdn page   esc close"
        )
        # The arrow is the same "there is more below" the reading panels use: a
        # page that is quietly missing its last paragraph is a page that lied.
        more = "  ▼" if self._more else ""
        buffer.text(x + 3, y + height - 1, (hint + more)[: width - 6], parse_style(ASH))

    def _tabs(self, buffer, app, x: int, y: int, width: int) -> None:
        cursor = x + 2
        for number, name in enumerate(self.TABS):
            chosen = number == self.tab
            label = f"[ {name} ]" if chosen else f"  {name}  "
            style = parse_style(f"bold {BONE}" if chosen else ASH)
            buffer.text(cursor, y + 1, label, style)
            cursor += len(label) + 1
        if self.tab == 0:
            count = f"{len(app.progress.pages)} of {PAGE_COUNT} pages"
        else:
            count = f"{len(self.known(app))} of {len(ENTRIES)} written"
        buffer.text(x + width - 3 - len(count), y + 1, count, parse_style(ASH))

    # -- tab one: the chronicle --------------------------------------------
    def chronicle_lines(self, app) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for number in range(1, PAGE_COUNT + 1):
            if number in app.progress.pages:
                rows.append((f"PAGE {numeral(number)}", f"bold {BONE}"))
                for line in _wrap((page(number) or "").strip(), 64):
                    rows.append((f"      {line}", BONE))
                rows.append(("", ""))
            else:
                rows.append((f"PAGE {numeral(number):<8} ——— unread", ASH))
        rows.insert(0, (TITLE, PURPLE))
        rows.insert(1, ("", ""))
        return rows

    def _chronicle(self, buffer, app, x, y, width, body_rows) -> None:
        rows = self.chronicle_lines(app)
        #: How long the book is, for the key handler: it pages what is drawn,
        #: and a scroll that counted anything else would stop short of the end.
        self._chronicle_total = len(rows)
        self.offset = max(0, min(self.offset, max(0, len(rows) - body_rows)))
        self._more = self.offset + body_rows < len(rows)
        for i, (text, style) in enumerate(rows[self.offset : self.offset + body_rows]):
            buffer.text(x + 3, y + 3 + i, text[: width - 6], parse_style(style))

    # -- tab two: the bestiary ---------------------------------------------
    def _bestiary(self, buffer, app, x, y, width, body_rows) -> None:
        known = self.known(app)
        self._list_window(body_rows, len(ENTRIES), self.index)
        left = x + 2
        # Never more than a third of the inside, never less than a name that
        # cannot be read: the index is a column, not the page.
        list_w = max(22, min(self.LIST_WIDTH, (width - 4) // 3))
        for row in range(body_rows):
            number = self.list_offset + row
            if number >= len(ENTRIES):
                break
            entry = ENTRIES[number]
            chosen = number == self.index
            marker = "►" if chosen else " "
            if entry.key in known:
                text = f"{marker} {entry.name}"
                style = f"bold {BONE}" if chosen else BONE
            else:
                # A page that is not written yet recedes: the names the player
                # *has* are the index, and eighteen rows of question marks at the
                # same weight as the names would be a list of holes.
                text = f"{marker} ???"
                style = f"bold {ASH}" if chosen else "grey23"
            buffer.text(left, y + 3 + row, _clip(text, list_w), parse_style(style))
        # The divider: one cell of "│" from the tab rule to the hint rule, so
        # the index and the page read as two columns and not as one column that
        # stops halfway.
        divider = left + list_w
        for row in range(body_rows):
            buffer.put(divider, y + 3 + row, "│", parse_style(ASH))
        self._page(buffer, app, x, y, width, body_rows, divider + 2)

    def _list_window(self, body_rows: int, total: int, index: int) -> None:
        """Keep the cursor inside the window, the way the shop does."""
        self.list_offset = max(0, min(self.list_offset, max(0, total - body_rows)))
        if index < self.list_offset:
            self.list_offset = index
        elif index >= self.list_offset + body_rows:
            self.list_offset = index - body_rows + 1

    def _page(self, buffer, app, x, y, width, body_rows, left) -> None:
        """The right-hand page: who it is, its picture, its numbers, its rule."""
        right = x + width - 3
        room = right - left
        # The figure stands in its own column, beside the words -- and the words
        # keep what they need first. The widest line on a page is the armour
        # line, and a column that squeezed it into "accura" would be an
        # illustration that cost the page its numbers. A narrow window drops the
        # column instead: fourteen cells out of forty is a page with no room to
        # read.
        figure = self.FIGURE_COLUMN if room >= self.FIGURE_COLUMN + 40 else 0
        text_left = left + (figure + 2 if figure else 0)
        text_room = room - (figure + 2 if figure else 0)
        #: What ``art`` needs to put the figure down: the column, its width, and
        #: where the page starts. Kept in cells, and multiplied out by whichever
        #: front end is painting.
        self._figure = (left, figure, y + 3)
        entry = self._selected(app)
        if entry.key not in self.known(app):
            self.detail_offset = 0
            buffer.text(text_left, y + 3, "NOT YET WRITTEN", parse_style(f"bold {ASH}"))
            note = _wrap("Kill one and the page writes itself.", text_room)
            for i, line in enumerate(note):
                buffer.text(text_left, y + 5 + i, line, parse_style(ASH))
            buffer.text(
                text_left,
                y + 7 + len(note),
                f"{len(self.known(app))} of {len(ENTRIES)} met.",
                parse_style(ASH),
            )
            return
        rows = self.page_lines(entry, text_room)
        self.detail_offset = max(0, min(self.detail_offset, max(0, len(rows) - body_rows)))
        self._more = self.detail_offset + body_rows < len(rows)
        for i, (text, style) in enumerate(
            rows[self.detail_offset : self.detail_offset + body_rows]
        ):
            buffer.text(text_left, y + 3 + i, text[:text_room], parse_style(style))

    def page_lines(self, entry: Entry, room: int) -> list[tuple[str, str]]:
        """One monster's page as lines, top to bottom.

        The figure is *not* in here: it is painted in pixels beside these words
        by the application, so a placeholder row would be ink under a sprite --
        the same rule the arena's staging keeps.
        """
        colour = ENEMIES[entry.key].color
        rows: list[tuple[str, str]] = [
            (title_of(entry), f"bold {BONE}"),
            (f"{entry.glyph}   {entry.where}", colour),
        ]
        rows += [(line, BONE if i == 0 else ASH) for i, line in enumerate(stat_lines(entry))]
        rows.append(("", ""))
        rows.append(("THE RULE", f"bold {PURPLE}"))
        rows += [(line, BONE) for line in _wrap(entry.rule, room)]
        rows.append(("", ""))
        rows.append(("HOW IT IS ANSWERED", f"bold {PURPLE}"))
        rows += [(line, BONE) for line in _wrap(entry.answer, room)]
        rows.append(("", ""))
        # The lore is the part of the page a player reads for pleasure, so it is
        # grey rather than ash: dim enough to sit under the rule and the numbers,
        # light enough to be read by choice and not by effort.
        rows += [(line, "grey60") for line in _wrap(entry.lore, room)]
        return rows

    # -- the picture --------------------------------------------------------
    def art(self, app) -> list[Placed]:
        """The monster's own drawing, in the column its page keeps for it.

        The column is the picture's *own*, so the words can scroll beside it
        without ever printing over it -- which is the reason it is a column and
        not a band across the top of the page.
        """
        if self.tab != 1:
            return []
        entry = self._selected(app)
        if entry.key not in self.known(app):
            return []
        left, column, top = getattr(self, "_figure", (0, 0, 0))
        if column <= 0:
            return []
        picture = entry.picture
        if not art_exists(picture):
            return []
        measured = art_size(picture)
        cell_w, cell_h = app.font.cell_w, app.font.cell_h
        tall = min(
            measured[1] if measured else 0,
            self.PICTURE_ROWS * cell_h - 6,
        )
        if tall <= 0:
            return []
        return [
            Placed(
                picture,
                (left + column / 2) * cell_w,
                (top + self.PICTURE_ROWS) * cell_h - 6,
                tall,
            )
        ]

    # -- input --------------------------------------------------------------
    def key(self, name, event, app) -> bool:
        # Holds scroll, because a list is something a player holds a key to walk;
        # holds do not *switch tabs*, because a tab is one decision.
        if event.isAutoRepeat() and name in ("left", "right", "tab"):
            return True
        if name in ("left", "right", "tab"):
            self.tab = 1 - self.tab
            self.detail_offset = 0
            return True
        if name in ("c", "b"):
            self.tab = 0 if name == "c" else 1
            self.detail_offset = 0
            return True
        if name == "escape":
            app.pop()
            return True
        rows, _width = self._body
        if self.tab == 0:
            return self._chronicle_key(name, rows)
        return self._bestiary_key(name, rows)

    def _chronicle_key(self, name: str, rows: int) -> bool:
        total = max(0, getattr(self, "_chronicle_total", 0) - rows)
        if name == "home":
            self.offset = 0
            return True
        if name == "end":
            self.offset = total
            return True
        if name in ("down", "j"):
            step = 1
        elif name in ("up", "k"):
            step = -1
        elif name == "pagedown":
            step = self.PAGE_SCROLL
        elif name == "pageup":
            step = -self.PAGE_SCROLL
        else:
            step = 0
        if step:
            self.offset = max(0, min(self.offset + step, total))
        return True

    def _bestiary_key(self, name: str, rows: int) -> bool:
        before = self.index
        if name in ("down", "j"):
            self.index = min(self.index + 1, len(ENTRIES) - 1)
        elif name in ("up", "k"):
            self.index = max(self.index - 1, 0)
        elif name == "home":
            self.index = 0
        elif name == "end":
            self.index = len(ENTRIES) - 1
        elif name in ("pagedown", "pageup"):
            step = self.PAGE_SCROLL if name == "pagedown" else -self.PAGE_SCROLL
            self.detail_offset = max(0, self.detail_offset + step)
            return True
        if self.index != before:
            self.detail_offset = 0
        return True
