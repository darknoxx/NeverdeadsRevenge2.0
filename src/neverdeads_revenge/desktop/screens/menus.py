"""The read-only screens and the shop.

Four of these are the same thing -- a titled box with a scrolling list -- so they
share one panel. The shop is the odd one out: it has a cursor, prices, and the
only place in the game outside a run where coin changes hands.
"""

from __future__ import annotations

from neverdeads_revenge.game.actions import drink, drop
from neverdeads_revenge.game.gifts import gift_by_key
from neverdeads_revenge.game.lore import PAGE_COUNT, numeral
from neverdeads_revenge.game.shop import ShopError, WILD_OFFERS, build_stock, buy, describe_item
from neverdeads_revenge.world.items import ITEMS

from ..chrome import ASH, BONE, BLOOD, PURPLE, box, menu, rule
from ..theme import parse_style
from .base import Screen

__all__ = [
    "HelpScreen",
    "PackScreen",
    "CharacterScreen",
    "ScoreboardScreen",
    "ChronicleScreen",
    "ShopScreen",
]


class _Panel(Screen):
    """A titled box with a scrolling list and one hint line."""

    modal = True
    title = ""
    hint = "↑↓ scroll   esc close"

    def __init__(self) -> None:
        self.offset = 0
        # The list's size and the visible window, as of the last draw: the
        # key handler needs them to refuse scrolling a list that does not
        # overflow, with no dead travel at the floor.
        self._body_size = (0, 0)

    def lines(self, app) -> list[tuple[str, str]]:
        return []

    def draw(self, buffer, app) -> None:
        width = min(buffer.cols - 4, 74)
        height = min(buffer.rows - 2, 26)
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title=self.title, border=BLOOD, fill=True)
        body = self.lines(app)
        window = height - 4
        self._body_size = (len(body), window)
        self.offset = max(0, min(self.offset, max(0, len(body) - window)))
        for i, (text, style) in enumerate(body[self.offset : self.offset + window]):
            buffer.text(x + 3, y + 2 + i, text[: width - 6], parse_style(style))
        rule(buffer, x + 1, y + height - 2, width - 2, ASH)
        more = "  ▼" if self.offset + window < len(body) else ""
        buffer.text(x + 3, y + height - 1, (self.hint + more)[: width - 6], parse_style(ASH))

    def key(self, name, event, app) -> bool:
        # Held scroll keys walk the list at the keyboard's pace, like in the
        # terminal; repeats of everything else must not answer (a held enter
        # that opened this screen must not close it from underneath).
        moving = name in ("up", "k", "w", "down", "j", "s")
        if event.isAutoRepeat() and not moving:
            return True
        total, window = self._body_size
        floor = max(0, total - window)
        if name in ("down", "j", "s"):
            if floor:
                self.offset = min(self.offset + 1, floor)
            return True
        if name in ("up", "k", "w"):
            self.offset = max(0, self.offset - 1)
            return True
        if name in ("escape", "enter", "space"):
            app.pop()
            return True
        return True


class LegendScreen(_Panel):
    """What the glyphs are, off the main screen and into a menu.

    The sidebar's job is the run in progress; a reference that never changes
    was spending the sidebar's best rows on every turn. Opened with `l`.
    """

    title = "THE LEGEND"
    hint = "↑↓ scroll   esc closes"

    def __init__(self, state) -> None:
        super().__init__()
        self.state = state

    def lines(self, app) -> list[tuple[str, str]]:
        from neverdeads_revenge.game.prologue import legend_rows

        from ..render import _legend_colour

        rows: list[tuple[str, str]] = []
        for glyph, text in legend_rows(self.state.depth, self.state.hero):
            if glyph:
                rows.append((f"{glyph}   {text}", _legend_colour(glyph)))
            elif text:
                rows.append((f"    {text}", "grey70"))
            else:
                rows.append(("", ""))
        return rows


class HelpScreen(_Panel):
    """The controls and the terrain reference."""

    title = "CONTROLS & REFERENCE"
    hint = "↑↓ scroll   esc closes"

    def lines(self, app) -> list[tuple[str, str]]:
        from neverdeads_revenge.game.prologue import terrain_help

        rows = [
            ("MOVE      arrows / wasd / hjk / yubn (diagonals)", BONE),
            ("WAIT      . or space", BONE),
            ("TAKE      enter  (loot, stairs, or speak)", BONE),
            ("DRINK     q      PACK  i      SHEET  c", BONE),
            ("LEGEND    l      REFERENCE  ?      HOUR  r", BONE),
            ("ULTIMATE  f      (once a floor, from level 7)", BONE),
            ("MENU      escape", BONE),
            ("", ""),
            ("THE GLASS", f"bold {PURPLE}"),
            ("F11 fullscreen   F2 scanlines   F3 bloom   F4 curve", ASH),
            ("", ""),
            ("THE DUNGEON", f"bold {PURPLE}"),
        ]
        rows += [(line, BONE) for line in terrain_help().splitlines()]
        return rows


class PackScreen(_Panel):
    """What is being carried -- a small box with a hand in it.

    Two things can be done with what is in here: **drink it** or **set it
    down**. `q` on the map still drinks the cheapest thing that covers a
    wound, because that is the choice nobody wants to make twice; this screen
    is for the *other* choices -- the five strange bottles, which are drunk by
    name, and the space they take up.
    """

    title = "THE PACK"
    hint = "↑↓  enter drink  x drop  esc close"

    def __init__(self, state) -> None:
        super().__init__()
        self.state = state
        self.index = 0
        self.message = ""

    #: What the draw uses for its width, so the wrap and the box agree.
    width = 46
    _text_room = width - 12

    def _kinds(self) -> list[tuple[str, int]]:
        """``(item_id, count)`` in the order the box shows them."""
        counts: dict[str, int] = {}
        for item in self.state.inventory:
            counts[item.item_id] = counts.get(item.item_id, 0) + 1
        return sorted(counts.items())

    def _rows(self, kinds: list[tuple[str, int]]) -> list[tuple[str, str, str | None]]:
        from .dialogs import wrap

        if not kinds:
            return [("You carry nothing.", ASH, None)]
        rows: list[tuple[str, str, str | None]] = []
        for position, (item_id, count) in enumerate(kinds):
            template = ITEMS.get(item_id)
            if template is None:
                continue
            label = f"{count}x {template.name}" if count > 1 else template.name
            chosen = position == self.index
            tag = "►" if chosen else " "
            style = f"bold {BONE}" if chosen else BONE
            rows.append((f"{tag} {label}", style, item_id))
            # Wrapped, not clipped: the strange bottles explain themselves in a
            # sentence, and a sentence the box cuts in half is a bottle nobody
            # dares drink.
            for piece in wrap(describe_item(template), self._text_room):
                rows.append((f"      {piece}", ASH, None))
        return rows

    def draw(self, buffer, app) -> None:
        kinds = self._kinds()
        self.index = max(0, min(self.index, len(kinds) - 1)) if kinds else 0
        rows = self._rows(kinds)
        width = min(buffer.cols - 8, 46)
        height = min(buffer.rows - 2, max(len(rows) + 6, 8))
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title=self.title, border=BLOOD, fill=True)
        window = height - 4
        self._body_size = (len(rows), window)
        self.offset = max(0, min(self.offset, max(0, len(rows) - window)))
        # The cursor walks and the box follows, two rows per line like the
        # shop's shelf: a pack line is a thing and what it does.
        chosen_id = kinds[self.index][0] if kinds else None
        selected = next(
            (n for n, row in enumerate(rows) if row[2] is not None and row[2] == chosen_id),
            0,
        )
        if selected < self.offset:
            self.offset = selected
        elif selected >= self.offset + window - 1:
            self.offset = selected - window + 2
        self.offset = max(0, min(self.offset, max(0, len(rows) - window)))
        for i, (text, style, _id) in enumerate(rows[self.offset : self.offset + window]):
            buffer.text(x + 3, y + 2 + i, text[: width - 6], parse_style(style))
        rule(buffer, x + 1, y + height - 2, width - 2, ASH)
        line = self.message or self.hint
        more = "  ▼" if self.offset + window < len(rows) else ""
        buffer.text(x + 3, y + height - 1, (line + more)[: width - 6], parse_style(ASH))

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        kinds = self._kinds()
        if name in ("up", "k"):
            if kinds:
                self.index = (self.index - 1) % len(kinds)
            return True
        if name in ("down", "j"):
            if kinds:
                self.index = (self.index + 1) % len(kinds)
            return True
        if name in ("enter", "return") and kinds:
            self.message = drink(self.state, kinds[self.index][0])
            app.play("item")
            return True
        if name in ("x", "d") and kinds:
            self.message = drop(self.state, kinds[self.index][0])
            return True
        if name in ("escape", "i"):
            app.pop()
            return True
        return True


class CharacterScreen(_Panel):
    """The full sheet: the numbers, the gear, the gifts and the curses."""

    title = "THE HERO"

    def __init__(self, state) -> None:
        super().__init__()
        self.state = state

    def _detail(self, text: str, app) -> list[str]:
        """A rule's fine print, wrapped to the sheet's own width, indented
        under the name it explains. One long line truncated at the frame was
        the difference between a rule and a rumour."""
        from .dialogs import wrap

        buffer = app._buffer
        cols = buffer.cols if buffer is not None else 96
        room = max(16, min(cols - 4, 74) - 6 - 10)
        return wrap(text, room)

    def lines(self, app) -> list[tuple[str, str]]:

        def detail(text: str) -> list[tuple[str, str]]:
            return [(f"          {piece}", ASH) for piece in self._detail(text, app)]

        p = self.state.player
        low, high = p.damage_range
        rows = [
            (f"{p.name}  {self.state.hero.title}", f"bold {p.color}"),
            (f"HP {p.hp}/{p.max_hp}   DMG {low}-{high}   CRT {p.crit_chance:.0%}", BONE),
            (f"SPD {p.speed:.2f}   ARM {p.armor}   EVA {p.evasion}   ACC {p.accuracy}", BONE),
            (
                f"{p.trait.title} {self.state.revenge_stacks}/{p.trait.cap}  "
                f"{p.trait.describe(self.state.revenge_stacks)}",
                "green",
            ),
            ("", ""),
        ]
        rows.append(("WORN", f"bold {PURPLE}"))
        for slot in ("weapon", "armour", "amulet"):
            item = p.equipment.get(slot)
            if item is None:
                rows.append((f"  {slot:<7} —", ASH))
            else:
                rows.append((f"  {slot:<7} {item.name}", BONE))
                rows.extend(detail(describe_item(ITEMS[item.item_id])))
        if self.state.gifts:
            rows.append(("", ""))
            rows.append(("GIFTS", "bold green"))
            for key in sorted(self.state.gifts):
                gift = gift_by_key(key)
                if gift is None:
                    continue
                rows.append((f"  {gift.name}", "green"))
                rows.extend(detail(gift.blurb))
        if self.state.wilds:
            # The run's own bargains: the same pitch-and-catch the shop read
            # out when they were sold, because a deal whose terms disappear
            # after one visit is not a deal the player can honour.
            rows.append(("", ""))
            rows.append(("EFFECTS", "bold yellow"))
            for key in sorted(self.state.wilds):
                offer = WILD_OFFERS.get(key)
                if offer is None:
                    continue
                rows.append((f"  {offer.name}", "yellow"))
                rows.extend(detail(f"{offer.pitch}; {offer.catch}"))
        if self.state.curses:
            rows.append(("", ""))
            rows.append(("CURSES", "bold red"))
            for curse in self.state.curses:
                rows.append((f"  {curse.name}", "red"))
                rows.extend(detail(curse.price))
        return rows


class ScoreboardScreen(_Panel):
    """Every run that finished, best first."""

    title = "THE BOARD"

    def lines(self, app) -> list[tuple[str, str]]:
        scores = list(app.progress.scores)
        if not scores:
            return [("Nobody has been down there yet.", ASH)]
        rows = [(f"{'name':<7}{'hero':<10}{'floor':>6}{'score':>9}", ASH)]
        for entry in sorted(scores, key=lambda e: e.score, reverse=True):
            mark = " ✝" if not entry.won else ""
            rows.append(
                (
                    f"{entry.name:<7}{entry.hero:<10}{entry.depth:>6}{entry.score:>9}{mark}",
                    BONE,
                )
            )
        return rows


class ChronicleScreen(_Panel):
    """The book: every page found, written out in full.

    It used to show one line per page, which made it a shelf of unread spines.
    A chronicle is for *reading* -- so each found page carries its whole text,
    wrapped, under its heading, and the still-missing ones say so.
    """

    title = "THE CHRONICLE"

    def lines(self, app) -> list[tuple[str, str]]:
        from neverdeads_revenge.game.lore import page

        from .dialogs import wrap

        rows: list[tuple[str, str]] = []
        found = 0
        for number in range(1, PAGE_COUNT + 1):
            if number in app.progress.pages:
                found += 1
                text = (page(number) or "").strip()
                rows.append((f"PAGE {numeral(number)}", f"bold {BONE}"))
                for line in wrap(text, 60):
                    rows.append((f"      {line}", BONE))
                rows.append(("", ""))
            else:
                rows.append((f"PAGE {numeral(number):<8} ——— unread", ASH))
        rows.insert(0, (f"{found} of {PAGE_COUNT} found", f"bold {PURPLE}"))
        rows.insert(1, ("", ""))
        return rows


class ShopScreen(Screen):
    """Spend coin. The one menu with a price on every line."""

    modal = True

    def __init__(self) -> None:
        self.index = 0
        self.message = ""
        self.offers = []
        self.offset = 0

    def _restock(self, app) -> None:
        # A fresh book has never rolled its wild shelf, because the shelf only
        # rerolls after a run ends -- so the very first visit would offer no
        # wilds at all, exactly when a new player is looking at the shop.
        # One roll, here, fills it; afterwards the rotation owns itself. The
        # dice are session dice, the same shape record_run uses: this choice
        # must not ride on the run's seed.
        if not app.progress.wild_stock:
            import random

            from neverdeads_revenge.core.rng import Rng

            app.progress.reroll_wilds(Rng(random.SystemRandom().randrange(2**32)))
            app.save_progress()
        self.offers = build_stock(app.progress)
        self.index = max(0, min(self.index, len(self.offers) - 1))

    def _rows(self, width: int) -> list[tuple[str, str, int | None]]:
        """The shelf as lines: a heading per section, then a line per offer.

        Sectioned the way the terminal shop was, because a flat list of
        twenty-three things with prices is a spreadsheet. The third element is
        the offer a line belongs to, or ``None`` for a heading and a detail
        line -- which is what lets the cursor step over the headings.
        """
        rows: list[tuple[str, str, int | None]] = []
        section = None
        for i, offer in enumerate(self.offers):
            if offer.section != section:
                section = offer.section
                rows.append((section, f"bold {PURPLE}", None))
            chosen = i == self.index
            # What the player cannot afford, or what is already taken in full,
            # is closed: ash, with the reason next to the price. A row a player
            # cannot act on should not read as a thing on offer.
            price = "maxed" if offer.maxed else f"{offer.price}g"
            if not offer.affordable:
                price = f"{offer.price}g (out of reach)"
                style = ASH
            elif offer.maxed:
                price = "maxed"
                style = ASH
            else:
                style = f"bold {BONE}" if chosen else BONE
            tag = "►" if chosen else " "
            rows.append((f"{tag} {offer.label:<26}{price:>7}", style, i))
            rows.append((f"      {offer.detail}", ASH, None))
        return rows

    def draw(self, buffer, app) -> None:
        if not self.offers:
            self._restock(app)
        width = min(buffer.cols - 4, 74)
        height = min(buffer.rows - 2, 24)
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title="THE SHOP", border=BLOOD, fill=True)
        buffer.text(x + 3, y + 1, f"Gold {app.progress.gold}", parse_style(f"bold {PURPLE}"))

        rows = self._rows(width)
        window = height - 6
        self._body_size = (len(rows), window)
        selected = next((n for n, row in enumerate(rows) if row[2] == self.index), 0)
        # The house style for a menu cursor: it walks *inside* the window, and
        # the window only shifts when the cursor reaches one of its edges. The
        # old stateless formula (offset = selected - window + 1) parked the
        # cursor on the bottom edge and dragged the list under it, so going
        # back up scrolled the shelf while the cursor stood still.
        self.offset = max(0, min(self.offset, max(0, len(rows) - window)))
        if selected <= next((n for n, row in enumerate(rows) if row[2] is not None), 0):
            # The cursor is back on the first offer of the list: the window
            # sits open at the top, heading and all. Anything else leaves the
            # shelf clung to wherever the walk stopped.
            self.offset = 0
        elif selected < self.offset:
            # The cursor has crossed the window's top edge: pin it there and
            # let the window come with it, the exact mirror of the bottom
            # edge. A press moves the cursor its own stride, so the window
            # moves the same stride -- never a jump.
            self.offset = selected
        elif selected >= self.offset + window - 1:
            # A shelf line is two rows: the offer, and the line that says what
            # it does. Pinning the cursor on the very last visible row hid the
            # description of whatever sat there -- most visibly the last wild
            # offer, whose detail was the one thing the window always cut. So
            # the cursor pins one row higher, and its detail keeps the edge.
            self.offset = selected - window + 2
        for n, (text, style, _offer) in enumerate(rows[self.offset : self.offset + window]):
            buffer.text(x + 3, y + 3 + n, text[: width - 6], parse_style(style))

        rule(buffer, x + 1, y + height - 3, width - 2, ASH)
        if self.message:
            buffer.text(x + 3, y + height - 2, self.message[: width - 6], parse_style("bold red"))
        buffer.text(
            x + 3,
            y + height - 1,
            "↑↓ choose   enter buy   esc leave",
            parse_style(ASH),
        )

    def key(self, name, event, app) -> bool:
        # The scroll keys are allowed to be held (a held key scrolls the shelf
        # at the keyboard's repeat pace, as in the terminal) -- repeats of
        # everything else, a held enter among it, are refused.
        moving = name in ("up", "k", "down", "j")
        if event.isAutoRepeat() and not moving:
            return True
        if not self.offers:
            self._restock(app)
        if name in ("up", "k"):
            self.index = max(0, self.index - 1)  # stop at the top, no loop
            return True
        if name in ("down", "j"):
            # ...and at the bottom of the shelf.
            self.index = min(max(0, len(self.offers) - 1), self.index + 1)
            return True
        if name == "enter" and self.offers:
            try:
                self.message = buy(app.progress, self.offers[self.index])
            except ShopError as refusal:
                self.message = str(refusal)
            else:
                # The till has a bell. A purchase that makes no noise feels
                # like it never happened, and the second-guesser walks back
                # through the shelves counting.
                app.play("coin")
                app.save_progress()
                self._restock(app)
            return True
        if name in ("escape", "s"):
            app.pop()
            return True
        return True
