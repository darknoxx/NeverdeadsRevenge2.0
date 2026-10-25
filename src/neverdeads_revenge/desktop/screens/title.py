"""The title.

A grim little menu: the painted name, the version under it, and six things to
do. The stack is a list of ``(key, label)`` so the menu, the keys and the drawing
cannot disagree about what is on it.

The name is a *picture* and not the block font. The block letters are the
dungeon's own alphabet -- the one the walls are made of -- and a title is the one
place the game is allowed to look like something somebody painted. A checkout
without the art still draws the old letters, because a menu that will not open
because a PNG is missing is a menu that is not a menu.
"""

from __future__ import annotations

import math

from ...game import daily as daily_rules
from ..art import TITLE_ART, Placed, exists as art_exists, size as art_size
from ..padmap import TITLE as TITLE_PAD
from ..blocks import render_word
from ..chrome import ASH, BONE, BLOOD, PURPLE, rule
from ..theme import parse_style
from .base import Screen

__all__ = ["TitleScreen"]


class TitleScreen(Screen):
    """Where a run starts, and where one ends up."""

    #: The word that opens the whole book, typed letter by letter on the title.
    #: Never announced in the game: a cheat is something somebody tells you, not
    #: something a menu advertises.
    CHEAT = "battle4ever"

    #: Start is the settings on this screen; B quits nothing.
    PAD = TITLE_PAD

    def __init__(self) -> None:
        self.index = 0
        #: How much of the word has been typed. Fed before the menu letters, and
        #: only ever swallowing keys that are still a prefix -- "battle4ever"
        #: contains an "a", and a cheat that opened the Almanac halfway through
        #: would be a cheat that typed itself into a menu.
        self._typed = ""

    def items(self, app) -> list[tuple[str, str]]:
        items = [("n", "NEW RUN")]
        if app.has_saved_run():
            items.append(("c", "CONTINUE"))
        if getattr(app.progress, "runs_won", 0) >= 1:
            # The door is not a mode you are shown before you have earned it:
            # it opens for a player who has already stepped into the rift once.
            items.append(("t", "TENTH DOOR"))
        items += [
            ("s", "SHOP"),
            ("h", "SCORES"),
            ("a", "ALMANAC"),
            ("e", "SETTINGS"),
            ("d", "DELETE PROGRESS"),
            ("q", "QUIT"),
        ]
        return items

    def draw(self, buffer, app) -> None:
        buffer.clear()
        items = self.items(app)

        # Laid out from the *bottom*: the rules and the hint lines are what a
        # player reads most, so they get their rows first and the big picture
        # makes do with what is left. The version is one line now that the name
        # is painted, and the best score sits under it, both just above the rule.
        nav_y = buffer.rows - 3
        menu_y = buffer.rows - 5
        rule_y = buffer.rows - 6
        cell_w, cell_h = self._cell(buffer)
        piece = self._logo(buffer.cols, buffer.rows, cell_w, cell_h)
        if piece is not None:
            # The version and the best score are the last two lines of the same
            # block as the painting, so they sit under it wherever it landed --
            # and the whole block is centred in the room above the rule.
            version_y = min(rule_y - 2, math.ceil(piece.bottom / cell_h))
            best_y = min(rule_y - 1, version_y + 1)
        else:
            version_y = max(0, rule_y - 2)
            best_y = max(0, rule_y - 1)
            # No painting in this checkout: the alphabet underneath every
            # picture in this game is still the alphabet.
            alt = render_word("NEVERDEAD'S") + render_word("REVENGE")
            y = max(0, version_y - len(alt) - 1)
            for line in alt:
                self._centre(buffer, y, line, f"bold {PURPLE}")
                y += 1

        self._centre(buffer, version_y, "2.0", "bold #c81e1e")
        best = app.progress.best_score
        if best:
            self._centre(buffer, best_y, f"best {best}", ASH)

        rule(buffer, 2, rule_y, buffer.cols - 4, BLOOD)
        self._menu_line(buffer, menu_y, items, self.index)
        if getattr(app.progress, "runs_won", 0) >= 1:
            self._centre(
                buffer,
                buffer.rows - 4,
                daily_rules.label(app.progress),
                ASH,
            )
        # A pad has no escape, and B must not quit a game from its title: the
        # pad's line names the button that *does* exist for the menu, Start.
        nav = (
            "←→ choose   A take   Start settings"
            if getattr(app, "pad_active", False)
            else "←→ choose   enter take   esc quit"
        )
        self._centre(buffer, nav_y, nav, ASH)

    # -- the painting --------------------------------------------------------
    def art(self, app) -> list[Placed]:
        """The name, painted, as large as the menu leaves room for.

        Fitted to the *height* the screen can spare and then clipped by the
        width, and never scaled above the size it was painted at: a title is the
        one picture in this game that has to look like itself. Centred *with*
        the version and the best score under it, as one block, in the room above
        the rule -- so a tall window gives the lot air instead of floating the
        name somewhere and pinning the version to the menu.
        """
        piece = self._logo(app.cols, app.rows, app.font.cell_w, app.font.cell_h)
        return [piece] if piece is not None else []

    @staticmethod
    def _cell(buffer) -> tuple[int, int]:
        """How wide a cell is, for a screen that may be drawn without a face.

        Ten by twenty is the reference cell every panel in this game is laid out
        for; a test frame has no font and the art still has to know where it
        would go.
        """
        font = getattr(buffer, "font", None)
        return (getattr(font, "cell_w", 10), getattr(font, "cell_h", 20))

    @staticmethod
    def _logo(cols: int, rows: int, cell_w: int, cell_h: int) -> Placed | None:
        if not art_exists(TITLE_ART):
            return None
        measured = art_size(TITLE_ART)
        if measured is None:
            return None
        width, height = measured
        # Everything above the rule is the block's room: the painting, then the
        # version and the best score, centred as one thing. The two lines keep
        # their rows first, so a short window loses size and never the menu.
        room = max(3 * cell_h, (rows - 6) * cell_h)
        tall = min(height, room - 2 * cell_h)
        widest = max(1, (cols - 4) * cell_w)
        if tall * width / max(1, height) > widest:
            tall = round(widest * height / max(1, width))
        if tall < cell_h:
            return None
        top = max(0, (room - (tall + 2 * cell_h)) // 2)
        return Placed(TITLE_ART, cols * cell_w / 2, top + tall, tall)

    def _menu_line(self, buffer, y, items, index) -> None:
        """The menu as one line, the chosen entry lit and bracketed.

        A line rather than a box, because the title's own art is ten rows and
        the version number is ten more: on a 27-row grid a boxed menu is a menu
        that falls off the screen. The choices are all still one keypress away.
        """
        texts = [
            f"[{label}]" if i == index else label for i, (_key, label) in enumerate(items)
        ]
        # Two cells and not three, unless the line has grown a door and can no
        # longer afford it: one cell still reads as a gap, and a menu that runs
        # off the edge of the smallest grid is not a menu.
        gap = 2
        if sum(len(text) for text in texts) + gap * (len(texts) - 1) > buffer.cols:
            gap = 1
        x = max(0, (buffer.cols - sum(len(text) for text in texts)
                    - gap * (len(texts) - 1)) // 2)
        for i, (_key, _label) in enumerate(items):
            chosen = i == index
            style = parse_style(f"bold {BONE}") if chosen else parse_style(ASH)
            buffer.text(x, y, texts[i], style)
            x += len(texts[i]) + gap

    @staticmethod
    def _centre(buffer, y: int, text: str, style: str) -> None:
        x = max(0, (buffer.cols - len(text)) // 2)
        buffer.text(x, y, text, parse_style(style))

    # -- input --------------------------------------------------------------
    def key(self, name: str, event, app) -> bool:
        # Menüs answer one press, not every thirtieth of a second: a key held
        # from the screen before this one must not open its shop on the way
        # past, and a key held *here* does not cycle the shelf.
        if event.isAutoRepeat():
            return True
        if self._cheat(name, app):
            return True
        if name == "y" and daily_rules.available(app.progress):
            app.open_hero_select(tenth_door=True, daily_mode=True)
            return True
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
            # An index is only as good as the list it pointed into: the items
            # can shrink under a screen that stays put, and enter -- unlike the
            # arrows -- did not revalidate.
            if self.index >= len(items):
                return True
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

    def _cheat(self, name: str, app) -> bool:
        """Feed one key to the word. Returns whether the word ate it.

        A matching key is swallowed so the letters cannot act as menu shortcuts
        on the way past. A key that stops the match clears the buffer and is
        answered by the menu as usual -- and a key that *starts* the word again
        begins a fresh attempt, so a typo costs nothing but the typo.
        """
        candidate = self._typed + name
        if self.CHEAT.startswith(candidate):
            self._typed = candidate
            if candidate == self.CHEAT:
                self._typed = ""
                app.run_cheat()
            return True
        self._typed = name if self.CHEAT.startswith(name) else ""
        return False

    def _choose(self, key: str, app) -> None:
        if key == "n":
            app.open_hero_select()
        elif key == "c":
            app.continue_run()
        elif key == "t":
            app.open_hero_select(tenth_door=True)
        elif key == "s":
            app.open_shop()
        elif key == "h":
            app.open_scoreboard()
        elif key == "a":
            app.open_almanac()
        elif key == "e":
            app.open_settings()
        elif key == "d":
            app.open_delete_progress()
        elif key == "q":
            app.quit_requested()
