"""The Tenth Door: the one choice the endless mode is built around.

The floor stops at the stairs. Behind the player is the run so far; behind the
door is another ten floors and a larger number, and the only thing that makes
the larger number worth anything is that the player could have stopped. So the
screen has two answers and no third one, and the safe answer is the first one.

Not a menu of boons yet. The door is the *decision*; the room behind it will
have its own rules later.
"""

from __future__ import annotations

from ...game.state import GameState, LogKind
from ..chrome import ASH, BONE, BLOOD, PURPLE, box
from ..theme import parse_style
from .base import Screen

__all__ = ["DoorScreen"]


class DoorScreen(Screen):
    """Bank the run, or push on. One keypress, and either answer is final."""

    OPTIONS = (("b", "BANK THE RUN"), ("c", "PUSH ON"))

    def __init__(self, state: GameState) -> None:
        self.state = state
        #: The safe answer starts lit, because a player who walked into this
        #: screen by holding a direction key should not lose a run by letting go
        #: of it on the wrong frame.
        self.index = 0

    def _lines(self) -> list[str]:
        state = self.state
        return [
            f"FLOOR {state.depth}   RING {state.door_ring}",
            f"RUN SCORE {state.score}   RISK x{state.risk_multiplier:.2f}",
            f"PURSE {state.gold}   COIN x{state.coin_multiplier:.2f}",
            "",
            "The door is open, and the next ten floors are worth more.",
            "Bank what the run has made, or carry it through.",
            "",
        ]

    def draw(self, buffer, app) -> None:
        width = min(buffer.cols - 8, 66)
        height = min(buffer.rows - 4, 18)
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(
            buffer,
            x,
            y,
            width,
            height,
            title="THE TENTH DOOR",
            border=BLOOD,
            fill=True,
        )

        row = y + 3
        for line in self._lines():
            if line:
                buffer.text(
                    x + max(2, (width - len(line)) // 2), row, line, parse_style(BONE)
                )
            row += 1

        options = []
        for i, (_key, label) in enumerate(self.OPTIONS):
            options.append(f"[{label}]" if i == self.index else f" {label} ")
        line = "    ".join(options)
        buffer.text(
            x + max(2, (width - len(line)) // 2), row + 1, line, parse_style(f"bold {PURPLE}")
        )

        for i, text in enumerate(
            [
                "Banking ends the run and keeps both the number and the purse.",
                "Pushing on raises both by 1.25; death takes the purse and the run.",
            ]
        ):
            buffer.text(
                x + max(2, (width - len(text)) // 2),
                row + 4 + i,
                text,
                parse_style(ASH),
            )

        hint = "← → choose   enter answer   esc step back"
        buffer.text(
            x + max(2, (width - len(hint)) // 2),
            y + height - 2,
            hint,
            parse_style(ASH),
        )

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name in ("left", "a", "h"):
            self.index = (self.index - 1) % len(self.OPTIONS)
            return True
        if name in ("right", "d", "l"):
            self.index = (self.index + 1) % len(self.OPTIONS)
            return True
        if name in ("enter", "space"):
            self._choose(self.index, app)
            return True
        for i, (key, _label) in enumerate(self.OPTIONS):
            if name == key:
                self._choose(i, app)
                return True
        if name == "escape":
            # Stepping back is allowed. It leaves the player on the landing,
            # where the next step onto the stairs asks again.
            self.state.door_pending = False
            self.state.say("You step back from the door.", LogKind.PLAIN)
            app.pop()
            return True
        return False

    def _choose(self, index: int, app) -> None:
        if index == 0:
            app.play("door_unlock")
            self.state.bank()
            app.show_game_over(won=True)
            return
        app.play("door_creak")
        self.state.continue_through_the_door()
        app.pop()
        app.redraw()
