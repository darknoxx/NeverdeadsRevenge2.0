"""The Almanac: the chronicle, the monsters, and the blades that cut them.

Three books in one cover, because they answer the same question from three
sides. The chronicle is what the old lords left behind; the bestiary is what is
still down there, written down the moment it is first killed; the armory is what
is lying about to kill it with, written down the moment it is first taken up.

Both collections are *earned*: a page is blank until the run has met the thing,
so the books fill as the player survives. That is the whole reason they are
collections and not manuals -- a manual would have told them what the hush does,
and finding out is the game.

Order is alphabetical by the name on the page. Not by floor (nobody looks a
monster up by the floor it stood on) and not by when it was met (that is the
shelf of a collector, not a book). The armory sorts without the article, since
half the blades are called "the something" and a catalogue filed under T is a
catalogue nobody can use.
"""

from __future__ import annotations

from ...game.actors import ENEMIES
from ...game.armory import WEAPONS, Weapon
from ...game.armory import stat_lines as weapon_stats
from ...game.bestiary import ENTRIES, Entry, stat_lines, title_of
from ...game.lore import PAGE_COUNT, TITLE, numeral, page
from ...world.items import ITEMS
from ..art import Placed, exists as art_exists, size as art_size
from ..chrome import ASH, BONE, BLOOD, PURPLE, box, rule
from ..padmap import ALMANAC as ALMANAC_PAD
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
    """Three books, one cover."""

    modal = True
    #: Back closes the book, the shoulders turn the tab page, the triggers page
    #: the text and the right stick scrolls it.
    PAD = ALMANAC_PAD
    pad_scroll = True

    #: The three, in the order they are read: the story, then what it is about,
    #: then what you do about it. The other order would open the book on a list
    #: of things that have not happened yet.
    TABS = ("CHRONICLE", "BESTIARY", "ARMORY")

    #: How wide a collection's index is, in cells -- a third of the page and no
    #: wider, so the page never gets the narrow half. The longest name is
    #: shortened on the index and whole on the page: an index is for finding a
    #: thing, the page is for reading it.
    LIST_WIDTH = 30

    #: Rows of a twenty-pixel line a monster's picture takes. Eight is half
    #: again the height the sheets were painted at, which is the size a figure
    #: wants on a page: big enough to look at, small enough that the words still
    #: have the page. The application smooth-scales it, the same way the arena
    #: scales its own figures -- no nearest-neighbour blocks, no blur.
    PICTURE_ROWS = 8

    #: The column a picture stands in, in cells, when the page is wide enough to
    #: afford one. Beside the words and not above them: a page whose lore has to
    #: give up its last lines so an illustration can breathe is a page that has
    #: its priorities backwards.
    FIGURE_COLUMN = 16

    #: How far a page-up moves the body, in lines: the chronicle's scroll and a
    #: long page's, because both are prose a player reads downward.
    PAGE_SCROLL = 9

    def __init__(self, tab: int = 0, select: str | None = None) -> None:
        self.tab = tab
        #: Where the keyboard is: the tab row, the index, or a thing's card.
        #: Three places, and the arrows walk between them the way the page is
        #: laid out -- up out of the top of a list lands on the tabs, left and
        #: right cross between the names and the page.
        #:
        #: It starts on the tabs, because the first question the book asks is
        #: *which* book: a cursor already sitting in the chronicle's text assumes
        #: an answer the player has not given yet.
        self.focus = "tabs"
        #: The chronicle's scroll, and a cursor and page scroll per collection:
        #: the bestiary's and the armory's are different lists, and one cursor
        #: for both would jump a page every time the player changed books.
        self.offset = 0
        self.index = 0
        self.weapon_index = 0
        self.list_offset = 0
        self.detail_offset = 0
        #: The size of the body as of the last draw: the key handler needs it to
        #: refuse scrolling a list that does not overflow, and to page a body
        #: that does.
        self._body = (0, 0)
        #: How long the two scrollable bodies came out last time, for the same
        #: reason: an end key has to stop where the text stops.
        self._chronicle_total = 0
        self._card_total = 0
        if select is not None:
            self.select(select)

    def select(self, key: str) -> None:
        """Open the book at one page: what R3 does mid-fight.

        The keyboard is put on the *page* rather than the index, because the
        question that sent the player here was "what does this thing do" and the
        answer is the page, not the list it is in.
        """
        pages = self._entries()
        for number, page in enumerate(pages):
            if page.key == key:
                self._set_cursor(number)
                self.focus = "page"
                self.detail_offset = 0
                return

    # -- what the books know -------------------------------------------------
    @staticmethod
    def known(app) -> set[str]:
        """The monsters whose page has been written."""
        return set(getattr(app.progress, "bestiary", ()))

    @staticmethod
    def known_weapons(app) -> set[str]:
        """The blades whose page has been written."""
        return set(getattr(app.progress, "armory", ()))

    def _entries(self) -> tuple:
        """The pages of the collection that is open."""
        return ENTRIES if self.tab == 1 else WEAPONS

    def _known_now(self, app) -> set[str]:
        return self.known(app) if self.tab == 1 else self.known_weapons(app)

    def _cursor(self) -> int:
        return self.index if self.tab == 1 else self.weapon_index

    def _set_cursor(self, value: int) -> None:
        if self.tab == 1:
            self.index = value
        else:
            self.weapon_index = value

    def _selected(self):
        pages = self._entries()
        return pages[max(0, min(self._cursor(), len(pages) - 1))]

    # -- the frame ----------------------------------------------------------
    def _frame(self, buffer) -> tuple[int, int, int, int]:
        width = min(buffer.cols - 4, 100)
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
            self._collection(buffer, app, x, y, width, body_rows)
        rule(buffer, x + 1, y + height - 2, width - 2, ASH)
        hint = self._hint()
        # The arrow is the same "there is more below" the reading panels use: a
        # page that is quietly missing its last paragraph is a page that lied.
        more = "  ▼" if self._more else ""
        buffer.text(x + 3, y + height - 1, (hint + more)[: width - 6], parse_style(ASH))

    def _tabs(self, buffer, app, x: int, y: int, width: int) -> None:
        """The three tabs, with the one you are *in* lit.

        The bracket says which book is open; the reverse says the keyboard is up
        here choosing. Two different facts, and a player needs both: a tab bar
        that looked the same whether the arrows were on it or in the text would
        leave them pressing left and wondering why nothing moved.
        """
        cursor = x + 2
        for number, name in enumerate(self.TABS):
            chosen = number == self.tab
            label = f"[ {name} ]" if chosen else f"  {name}  "
            if chosen and self.focus == "tabs":
                style = parse_style(f"bold {BONE} reverse")
            elif chosen:
                style = parse_style(f"bold {BONE}")
            else:
                style = parse_style(ASH)
            buffer.text(cursor, y + 1, label, style)
            cursor += len(label) + 1
        if self.tab == 0:
            count = f"{len(app.progress.pages)} of {PAGE_COUNT} pages"
        elif self.tab == 1:
            count = f"{len(self.known(app))} of {len(ENTRIES)} written"
        else:
            count = f"{len(self.known_weapons(app))} of {len(WEAPONS)} found"
        buffer.text(x + width - 3 - len(count), y + 1, count, parse_style(ASH))

    # -- the chronicle ------------------------------------------------------
    def chronicle_lines(self, app, width: int = 88) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for number in range(1, PAGE_COUNT + 1):
            if number in app.progress.pages:
                rows.append((f"PAGE {numeral(number)}", f"bold {BONE}"))
                for line in _wrap((page(number) or "").strip(), width - 12):
                    rows.append((f"      {line}", BONE))
                rows.append(("", ""))
            else:
                rows.append((f"PAGE {numeral(number):<8} ——— unread", ASH))
        rows.insert(0, (TITLE, PURPLE))
        rows.insert(1, ("", ""))
        return rows

    def _chronicle(self, buffer, app, x, y, width, body_rows) -> None:
        rows = self.chronicle_lines(app, width)
        #: How long the book is, for the key handler: it pages what is drawn,
        #: and a scroll that counted anything else would stop short of the end.
        self._chronicle_total = len(rows)
        self.offset = max(0, min(self.offset, max(0, len(rows) - body_rows)))
        self._more = self.offset + body_rows < len(rows)
        for i, (text, style) in enumerate(rows[self.offset : self.offset + body_rows]):
            buffer.text(x + 3, y + 3 + i, text[: width - 6], parse_style(style))

    # -- a collection: names on the left, the page on the right --------------
    def _collection(self, buffer, app, x, y, width, body_rows) -> None:
        pages = self._entries()
        known = self._known_now(app)
        cursor = self._cursor()
        self._list_window(body_rows, len(pages), cursor)
        left = x + 2
        # Never more than a third of the inside, never less than a name that
        # cannot be read: the index is a column, not the page.
        list_w = max(22, min(self.LIST_WIDTH, (width - 4) // 3))
        for row in range(body_rows):
            number = self.list_offset + row
            if number >= len(pages):
                break
            entry = pages[number]
            chosen = number == cursor
            marker = "►" if chosen else " "
            if entry.key in known:
                text = f"{marker} {entry.name}"
                style = f"bold {BONE}" if chosen else BONE
            else:
                # A page that is not written yet recedes: the names the player
                # *has* are the index, and a column of question marks at the same
                # weight as the names would be a list of holes.
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
        # column instead: sixteen cells out of forty is a page with no room to
        # read.
        figure = self.FIGURE_COLUMN if room >= self.FIGURE_COLUMN + 38 else 0
        text_left = left + (figure + 2 if figure else 0)
        text_room = room - (figure + 2 if figure else 0)
        #: What ``art`` needs to put the figure down: the column, its width, and
        #: where the page starts. Kept in cells, and multiplied out by whichever
        #: front end is painting.
        self._figure = (left, figure, y + 3)
        entry = self._selected()
        if entry.key not in self._known_now(app):
            self.detail_offset = 0
            self._card_total = 0
            buffer.text(text_left, y + 3, "NOT YET WRITTEN", parse_style(f"bold {ASH}"))
            note = _wrap(self._locked_note(), text_room)
            for i, line in enumerate(note):
                buffer.text(text_left, y + 5 + i, line, parse_style(ASH))
            page_count = len(self._entries())
            met = len(self._known_now(app))
            buffer.text(
                text_left,
                y + 7 + len(note),
                f"{met} of {page_count} {'met' if self.tab == 1 else 'found'}.",
                parse_style(ASH),
            )
            return
        rows = self._lines(entry, text_room)
        self._card_total = len(rows)
        self.detail_offset = max(0, min(self.detail_offset, max(0, len(rows) - body_rows)))
        self._more = self.detail_offset + body_rows < len(rows)
        for i, (text, style) in enumerate(
            rows[self.detail_offset : self.detail_offset + body_rows]
        ):
            buffer.text(text_left, y + 3 + i, text[:text_room], parse_style(style))

    def _locked_note(self) -> str:
        return (
            "Kill one and the page writes itself."
            if self.tab == 1
            else "Take one up and the page writes itself."
        )

    def _lines(self, entry, room: int) -> list[tuple[str, str]]:
        return (
            self.monster_lines(entry, room)
            if self.tab == 1
            else self.weapon_lines(entry, room)
        )

    def monster_lines(self, entry: Entry, room: int) -> list[tuple[str, str]]:
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

    def weapon_lines(self, entry: Weapon, room: int) -> list[tuple[str, str]]:
        """One blade's page: its numbers first, because that is what it is for."""
        colour = ITEMS[entry.key].color
        stats, where = weapon_stats(entry)
        rows: list[tuple[str, str]] = [(entry.name.upper(), f"bold {BONE}")]
        for i, line in enumerate(_wrap(f"{entry.glyph}   {stats}", room)):
            rows.append((line, colour if i == 0 else ASH))
        rows.append((where, ASH))
        rows.append(("", ""))
        rows.append(("WHAT IT IS", f"bold {PURPLE}"))
        rows += [(line, BONE) for line in _wrap(entry.what, room)]
        rows.append(("", ""))
        rows += [(line, "grey60") for line in _wrap(entry.lore, room)]
        return rows

    # -- the picture --------------------------------------------------------
    def art(self, app) -> list[Placed]:
        """The thing's own drawing, in the column its page keeps for it.

        The column is the picture's *own*, so the words can scroll beside it
        without ever printing over it -- which is the reason it is a column and
        not a band across the top of the page.
        """
        if self.tab == 0:
            return []
        entry = self._selected()
        if entry.key not in self._known_now(app):
            return []
        left, column, top = getattr(self, "_figure", (0, 0, 0))
        if column <= 0:
            return []
        picture = entry.picture
        if not art_exists(picture):
            return []
        measured = art_size(picture)
        if measured is None:
            return []
        cell_w, cell_h = app.font.cell_w, app.font.cell_h
        # Monsters are filled to the column's height -- the sheets are painted
        # between a hundred and a hundred and twenty pixels, and eight rows is
        # half again that. Blades are painted at the size a card draws them, so
        # they stop at 1:1; a stretched sword is a sword that has been resampled.
        tall = self.PICTURE_ROWS * cell_h - 8
        if self.tab == 2:
            tall = min(tall, measured[1])
        # Never wider than the column, so a wide figure does not run over the
        # divider.
        wide = tall * measured[0] / max(1, measured[1])
        if wide > self.FIGURE_COLUMN * cell_w:
            wide = self.FIGURE_COLUMN * cell_w
            tall = round(wide * measured[1] / max(1, measured[0]))
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
    def _hint(self) -> str:
        """What the arrows do *here*, which is a different sentence per place."""
        if self.focus == "tabs":
            return "←→ tab   ↓ open   esc close"
        if self.tab == 0:
            return "→ bestiary   ↑↓ scroll   ↑ at top: tabs   esc close"
        if self.focus == "page":
            return "← names   ↑↓ page   pgup/pgdn   esc close"
        previous = self.TABS[self.tab - 1].lower()
        return f"→ card   ← {previous}   ↑ at top: tabs   esc close"

    def key(self, name, event, app) -> bool:
        # Holds scroll, because a list is something a player holds a key to walk;
        # holds do not cross between panes or tabs, because those are decisions
        # and a held key that crossed them would flicker between two pages.
        if event.isAutoRepeat() and name in ("left", "right", "tab", "c", "b", "a"):
            return True
        if name in ("escape", "m"):
            # Back closes the book; `m` is the same door from the other side.
            app.pop()
            return True
        if name in ("[", "]"):
            # The shoulders: previous and next tab, from wherever the keyboard is.
            step = -1 if name == "[" else 1
            self._switch(max(0, min(len(self.TABS) - 1, self.tab + step)))
            if self.focus == "page":
                self.focus = "list"
            return True
        if name in ("c", "b", "a"):
            # Shortcuts, not part of the arrow language: each names a book and
            # lands the keyboard in it.
            self._open({"c": 0, "b": 1, "a": 2}[name])
            return True
        if name == "tab":
            self._switch((self.tab + 1) % len(self.TABS))
            if self.focus == "page":
                # The card belongs to the thing in the other book; the list is
                # where the keyboard belongs after a jump like that.
                self.focus = "list"
            return True
        if self.focus == "tabs":
            return self._tab_key(name)
        if self.tab == 0:
            return self._chronicle_key(name)
        return self._collection_key(name)

    def _open(self, tab: int) -> None:
        """Jump straight into a book: the tab, and the keyboard with it."""
        self._switch(tab)
        self.focus = "list"

    def _switch(self, tab: int) -> None:
        self.tab = tab
        self.detail_offset = 0

    # -- the tab row ---------------------------------------------------------
    def _tab_key(self, name: str) -> bool:
        if name == "left":
            # Left and right walk the row and show the book as they pass, so
            # what the player is choosing is the thing in front of them.
            self._switch(max(0, self.tab - 1))
            return True
        if name == "right":
            self._switch(min(len(self.TABS) - 1, self.tab + 1))
            return True
        if name in ("down", "enter", "space"):
            self.focus = "list"
            return True
        return True

    # -- the chronicle's body ------------------------------------------------
    def _chronicle_key(self, name: str) -> bool:
        if name == "right":
            # This book has no second pane, so the arrow points at the only
            # thing to its right: the next book.
            self._open(1)
            return True
        if name == "left":
            return True
        rows = self._body[0]
        total = max(0, self._chronicle_total - rows)
        if name in ("up", "k"):
            if self.offset == 0:
                # The top of the text is the tab row above it.
                self.focus = "tabs"
                return True
            self.offset = max(0, self.offset - 1)
            return True
        if name in ("down", "j"):
            self.offset = min(self.offset + 1, total)
        elif name == "pageup":
            self.offset = max(0, self.offset - self.PAGE_SCROLL)
        elif name == "pagedown":
            self.offset = min(self.offset + self.PAGE_SCROLL, total)
        elif name == "home":
            self.offset = 0
        elif name == "end":
            self.offset = total
        return True

    # -- a collection: two panes --------------------------------------------
    def _collection_key(self, name: str) -> bool:
        # The arrows point where the panes are: right is the card, left is the
        # names -- and left again, out of the names, is the book beside this one.
        if name == "right":
            if self.focus == "list":
                self.focus = "page"
            return True
        if name == "left":
            if self.focus == "page":
                self.focus = "list"
            else:
                self._open(self.tab - 1)
            return True
        if self.focus == "list":
            return self._names_key(name)
        return self._card_key(name)

    def _names_key(self, name: str) -> bool:
        pages = self._entries()
        before = self._cursor()
        index = before
        if name in ("up", "k"):
            if index == 0:
                # Above the first name is the tab row.
                self.focus = "tabs"
                return True
            index -= 1
        elif name in ("down", "j"):
            index = min(index + 1, len(pages) - 1)
        elif name == "home":
            index = 0
        elif name == "end":
            index = len(pages) - 1
        elif name in ("pageup", "pagedown"):
            step = self.PAGE_SCROLL if name == "pagedown" else -self.PAGE_SCROLL
            index = max(0, min(index + step, len(pages) - 1))
        self._set_cursor(index)
        if index != before:
            # A new thing is a new page, and a page that opened halfway down
            # would be a page that started in the middle of a sentence.
            self.detail_offset = 0
        return True

    def _card_key(self, name: str) -> bool:
        rows = self._body[0]
        total = max(0, self._card_total - rows)
        if name in ("up", "k"):
            self.detail_offset = max(0, self.detail_offset - 1)
        elif name in ("down", "j"):
            self.detail_offset = min(self.detail_offset + 1, total)
        elif name == "pageup":
            self.detail_offset = max(0, self.detail_offset - self.PAGE_SCROLL)
        elif name == "pagedown":
            self.detail_offset = min(self.detail_offset + self.PAGE_SCROLL, total)
        elif name == "home":
            self.detail_offset = 0
        elif name == "end":
            self.detail_offset = total
        return True
