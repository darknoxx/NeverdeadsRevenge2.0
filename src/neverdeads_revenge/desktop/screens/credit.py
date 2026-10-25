"""The house's credit: three pieces from the deep, shown before the door starts.

The pieces are rolled when the run is made, not when this card opens; the card
is the place the player is allowed to look at the loan before it becomes the
run. One reroll is offered for coin, and only one -- a shelf that rerolls until
the player likes it is a shelf that has already made the choice.

The card is a dialog over the floor, not a separate game state. Closing it is
the first step of the run.
"""

from __future__ import annotations

from ...game.state import CREDIT_REROLL, GameState
from ...world.items import ITEMS
from ..art import Placed, exists as art_exists, item_icon, size as art_size
from ..chrome import ASH, BONE, BLOOD, PURPLE, box
from ..theme import parse_style
from .base import Screen
from .dialogs import wrap

__all__ = ["CreditScreen"]

#: How many pieces the card promises. Kept beside the screen because the screen
#: is where the promise is read.
PIECES = 3


class CreditScreen(Screen):
    """Show the loan; allow one paid reroll; then begin."""

    modal = True
    OPTIONS = ("BEGIN", "REROLL")

    def __init__(self, state: GameState) -> None:
        self.state = state
        self.index = 0
        self.message = ""
        #: Where the three sprites stand, in cells: set by ``draw`` and read by
        #: ``art`` on the same frame, because a picture is pixels and the layout
        #: is cells.
        self._slots: list[tuple[float, int]] = []

    def _item_lines(self, width: int) -> list[str]:
        lines: list[str] = []
        for number, item in enumerate(self.state.credit_gear, start=1):
            kind = item.kind if item.kind else "thing"
            lines.append(f"{number}. {item.name}   ({kind})")
            detail = ", ".join(item.modifiers.describe())
            if detail:
                lines.extend(f"   {line}" for line in wrap(detail, width - 8))
        return lines

    def draw(self, buffer, app) -> None:
        state = self.state
        width = min(buffer.cols - 8, 84)
        height = min(buffer.rows - 4, 19)
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(
            buffer,
            x,
            y,
            width,
            height,
            title="THE HOUSE CREDIT",
            border=BLOOD,
            fill=True,
        )

        for i, text in enumerate(
            [
                f"Level 18. {PIECES} pieces from the deep. Purse {state.gold} coin.",
                f"One reroll costs {CREDIT_REROLL} coin, once.",
            ]
        ):
            buffer.text(x + 3, y + 2 + i, text[: width - 6], parse_style(BONE))

        # Three columns, each with its own sprite above its name. The sprite
        # band is five rows; the name and its numbers sit under the feet.
        inside = width - 6
        column = max(18, inside // 3)
        left = x + 3
        self._slots = []
        for number, item in enumerate(state.credit_gear):
            centre = left + column * number + column / 2
            self._slots.append((centre, y + 10))
            name = item.name[: column - 1]
            buffer.text(
                left + column * number,
                y + 11,
                name,
                parse_style(f"bold {BONE}"),
            )
            buffer.text(
                left + column * number,
                y + 12,
                item.kind[: column - 1],
                parse_style(PURPLE),
            )
            detail = ", ".join(item.modifiers.describe())
            for line_number, text in enumerate(
                wrap(detail, column - 1)[:2]
            ):
                buffer.text(
                    left + column * number,
                    y + 13 + line_number,
                    text,
                    parse_style(ASH),
                )

        rerolled = state.credit_rerolled
        options = [
            f"[{self.OPTIONS[0]}]" if self.index == 0 else " BEGIN ",
            (
                " REROLL USED "
                if rerolled
                else (
                    f"[REROLL  {CREDIT_REROLL}]"
                    if self.index == 1
                    else f" REROLL  {CREDIT_REROLL} "
                )
            ),
        ]
        line = "     ".join(options)
        buffer.text(
            x + max(2, (width - len(line)) // 2),
            y + height - 4,
            line,
            parse_style(f"bold {PURPLE}"),
        )
        hint = "← → choose   enter take   r reroll   esc begin"
        buffer.text(
            x + max(2, (width - len(hint)) // 2),
            y + height - 2,
            hint,
            parse_style(ASH),
        )
        if self.message:
            buffer.text(
                x + 3,
                y + height - 3,
                self.message[: width - 6],
                parse_style(ASH),
            )

    def art(self, app) -> list[Placed]:
        """The three pieces, by their own drawings.

        The card is the first time the player sees what the house is lending;
        three names are a list, three pictures are a set of equipment. A weapon
        has its own sheet, a coat and an amulet share the kind's drawing until
        they are painted one apiece.
        """
        if not self._slots:
            return []
        cell_w, cell_h = app.font.cell_w, app.font.cell_h
        placed: list[Placed] = []
        for (centre, bottom_row), item in zip(
            self._slots, self.state.credit_gear, strict=False
        ):
            template = ITEMS.get(item.item_id)
            if template is None:
                continue
            picture = item_icon(template)
            if picture is None or not art_exists(picture):
                continue
            measured = art_size(picture)
            if measured is None:
                continue
            # One size for all three, so a coat does not read as a smaller
            # promise than a sword.
            placed.append(
                Placed(
                    picture,
                    centre * cell_w,
                    bottom_row * cell_h - 2,
                    96,
                )
            )
        return placed

    # -- input --------------------------------------------------------------
    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name in ("left", "a", "up", "w"):
            self.index = 0
            return True
        if name in ("right", "d", "down", "s"):
            self.index = 1
            return True
        if name == "r":
            self._reroll(app)
            return True
        if name in ("enter", "space", "escape"):
            self._begin(app)
            return True
        return False

    def _reroll(self, app) -> None:
        if self.state.credit_rerolled:
            self.message = "The house has already rolled again."
            app.play("error_locked")
            return
        if self.state.gold < CREDIT_REROLL:
            self.message = f"The house wants {CREDIT_REROLL} coin."
            app.play("error_locked")
            return
        self.state.reroll_credit()
        self.message = ""
        app.play("coin")
        app.redraw()

    def _begin(self, app) -> None:
        app.pop()
        app.redraw()
