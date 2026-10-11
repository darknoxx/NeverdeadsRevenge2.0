"""The read-only screens and the shop.

Four of these are the same thing -- a titled box with a scrolling list -- so they
share one panel. The shop is the odd one out: it has a cursor, prices, and the
only place in the game outside a run where coin changes hands.
"""

from __future__ import annotations

from neverdeads_revenge.game.gifts import gift_by_key
from neverdeads_revenge.game.lore import PAGE_COUNT, numeral
from neverdeads_revenge.game.shop import ShopError, build_stock, buy, describe_item
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

    def lines(self, app) -> list[tuple[str, str]]:
        return []

    def draw(self, buffer, app) -> None:
        width = min(buffer.cols - 4, 74)
        height = min(buffer.rows - 2, 26)
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title=self.title, border=BLOOD, fill=True)
        body = self.lines(app)
        window = body[self.offset : self.offset + height - 4]
        for i, (text, style) in enumerate(window):
            buffer.text(x + 3, y + 2 + i, text[: width - 6], parse_style(style))
        rule(buffer, x + 1, y + height - 2, width - 2, ASH)
        more = "  ▼" if self.offset + height - 4 < len(body) else ""
        buffer.text(x + 3, y + height - 1, (self.hint + more)[: width - 6], parse_style(ASH))

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name in ("down", "j", "s"):
            self.offset += 1
            return True
        if name in ("up", "k", "w"):
            self.offset = max(0, self.offset - 1)
            return True
        if name in ("escape", "enter", "space"):
            app.pop()
            return True
        return True


class HelpScreen(_Panel):
    """The controls and the terrain reference."""

    title = "CONTROLS & REFERENCE"
    hint = "↑↓ scroll   any key closes"

    def lines(self, app) -> list[tuple[str, str]]:
        from neverdeads_revenge.game.prologue import terrain_help

        rows = [
            ("MOVE      arrows / hjkl / yubn (diagonals)", BONE),
            ("WAIT      . or space", BONE),
            ("TAKE      enter  (loot, stairs, or speak)", BONE),
            ("DRINK     q      PACK  i      SHEET  c", BONE),
            ("HOUR      r      (with the gift)   HELP  ?", BONE),
            ("MENU      escape", BONE),
            ("", ""),
            ("THE GLASS", f"bold {PURPLE}"),
            ("F11 fullscreen   +/- zoom   F2 scanlines   F3 bloom   F4 curve", ASH),
            ("", ""),
            ("THE DUNGEON", f"bold {PURPLE}"),
        ]
        rows += [(line, BONE) for line in terrain_help().splitlines()]
        return rows


class PackScreen(_Panel):
    """What is being carried."""

    title = "THE PACK"

    def __init__(self, state) -> None:
        super().__init__()
        self.state = state

    def lines(self, app) -> list[tuple[str, str]]:
        counts: dict[str, int] = {}
        for item in self.state.inventory:
            counts[item.item_id] = counts.get(item.item_id, 0) + 1
        if not counts:
            return [("You carry nothing.", ASH)]
        rows: list[tuple[str, str]] = []
        for item_id, count in sorted(counts.items()):
            template = ITEMS.get(item_id)
            if template is None:
                continue
            label = f"{count}x {template.name}" if count > 1 else template.name
            rows.append((f"{label}", f"bold {BONE}"))
            rows.append((f"    {describe_item(template)}", ASH))
        return rows


class CharacterScreen(_Panel):
    """The full sheet: the numbers, the gear, the gifts and the curses."""

    title = "THE HERO"

    def __init__(self, state) -> None:
        super().__init__()
        self.state = state

    def lines(self, app) -> list[tuple[str, str]]:
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
                rows.append((f"          {describe_item(ITEMS[item.item_id])}", ASH))
        if self.state.gifts:
            rows.append(("", ""))
            rows.append(("GIFTS", f"bold green"))
            for key in sorted(self.state.gifts):
                gift = gift_by_key(key)
                if gift is not None:
                    rows.append((f"  {gift.name}", "green"))
                    rows.append((f"          {gift.blurb}", ASH))
        if self.state.curses:
            rows.append(("", ""))
            rows.append(("CURSES", "bold red"))
            for curse in self.state.curses:
                rows.append((f"  {curse.name}", "red"))
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

    def _restock(self, app) -> None:
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
        selected = next((n for n, row in enumerate(rows) if row[2] == self.index), 0)
        offset = max(0, selected - window + 1)
        offset = min(offset, max(0, len(rows) - window))
        for n, (text, style, _offer) in enumerate(rows[offset : offset + window]):
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
        if event.isAutoRepeat():
            return True
        if not self.offers:
            self._restock(app)
        if name in ("up", "k"):
            self.index = (self.index - 1) % max(1, len(self.offers))
            return True
        if name in ("down", "j"):
            self.index = (self.index + 1) % max(1, len(self.offers))
            return True
        if name == "enter" and self.offers:
            try:
                self.message = buy(app.progress, self.offers[self.index])
            except ShopError as refusal:
                self.message = str(refusal)
            else:
                app.save_progress()
                self._restock(app)
            return True
        if name in ("escape", "s"):
            app.pop()
            return True
        return True
