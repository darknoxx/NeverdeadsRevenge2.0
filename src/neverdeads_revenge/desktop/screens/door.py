"""The Tenth Door: the choice the endless mode is built around.

The floor stops at the stairs. Behind the player is the run so far; behind the
door is another ten floors, a larger number and a purse that can be lost. So the
screen has two answers and no third one, and the safe answer is the first one.

Pushing on is two questions in one place: which of the three boons the door is
offering, and then the descent. Banking skips both -- it is the answer for a
player who has decided the run is already enough.
"""

from __future__ import annotations

from ...game import boons as boon_rules
from ...game import rings as ring_rules
from ...game.state import GameState, LogKind
from ..chrome import ASH, BONE, BLOOD, PURPLE, box
from ..theme import parse_style
from .base import Screen
from .dialogs import wrap

__all__ = ["DoorScreen"]


class DoorScreen(Screen):
    """Bank the run, or push on through one of three boons."""

    OPTIONS = (("b", "BANK THE RUN"), ("c", "PUSH ON"))

    def __init__(self, state: GameState) -> None:
        self.state = state
        self.mode = "door"
        #: The safe answer starts lit, because a player who walked into this
        #: screen by holding a direction key should not lose a run by letting go
        #: of it on the wrong frame.
        self.index = 0

    @property
    def offers(self) -> tuple[str, ...]:
        if not self.state.boon_offers:
            # A save taken with the door open can lose the shelf; the shelf is
            # derived from the seed, so putting it back costs nothing.
            self.state.boon_offers = boon_rules.offers(
                self.state.seed, self.state.door_ring
            )
        return self.state.boon_offers

    def _next_rule(self):
        return ring_rules.rule_for(self.state.seed, self.state.door_ring + 1)

    # -- drawing ------------------------------------------------------------
    def draw(self, buffer, app) -> None:
        width = min(buffer.cols - 8, 70)
        height = min(buffer.rows - 4, 20)
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(
            buffer,
            x,
            y,
            width,
            height,
            title="CHOOSE A BOON" if self.mode == "boons" else "THE TENTH DOOR",
            border=BLOOD,
            fill=True,
        )

        if self.mode == "boons":
            self._draw_boons(buffer, x, y, width, height)
        else:
            self._draw_door(buffer, x, y, width, height)

    def _centre(self, buffer, x: int, y: int, width: int, text: str, style: str) -> None:
        buffer.text(x + max(2, (width - len(text)) // 2), y, text, parse_style(style))

    def _draw_door(self, buffer, x, y, width, height) -> None:
        state = self.state
        rule = self._next_rule()
        lines = [
            f"FLOOR {state.depth}   RING {state.door_ring}",
            f"RUN SCORE {state.score}   RISK x{state.risk_multiplier:.2f}",
            f"PURSE {state.gold}   COIN x{state.coin_multiplier:.2f}",
            "",
            "The door is open, and the next ten floors are worth more.",
            "Bank what the run has made, or carry it through.",
        ]
        row = y + 2
        for line in lines:
            if line:
                self._centre(buffer, x, row, width, line, BONE)
            row += 1

        if rule is not None:
            self._centre(
                buffer, x, row + 1, width, f"NEXT RING: {rule.name}", f"bold {PURPLE}"
            )
            for i, text in enumerate(wrap(rule.blurb, width - 8)):
                self._centre(buffer, x, row + 2 + i, width, text, ASH)

        options = [
            f"[{label}]" if i == self.index else f" {label} "
            for i, (_key, label) in enumerate(self.OPTIONS)
        ]
        line = "    ".join(options)
        self._centre(buffer, x, y + 13, width, line, f"bold {PURPLE}")
        for i, text in enumerate(
            [
                "Banking ends the run and keeps both the number and the purse.",
                "Pushing on raises both by 1.25; death takes the purse and the run.",
            ]
        ):
            self._centre(buffer, x, y + 15 + i, width, text, ASH)
        self._centre(
            buffer,
            x,
            y + height - 2,
            width,
            "← → choose   enter answer   esc step back",
            ASH,
        )

    def _draw_boons(self, buffer, x, y, width, height) -> None:
        rule = self._next_rule()
        heading = (
            f"NEXT RING: {rule.name}" if rule is not None else "THE NEXT RING"
        )
        self._centre(buffer, x, y + 2, width, heading, f"bold {PURPLE}")
        self._centre(
            buffer,
            x,
            y + 3,
            width,
            "Choose one boon. It stays with the run.",
            ASH,
        )
        row = y + 6
        for i, key in enumerate(self.offers):
            boon = boon_rules.BOONS[key]
            chosen = i == self.index
            marker = ">" if chosen else " "
            style = f"bold {BONE}" if chosen else BONE
            buffer.text(x + 3, row, f"{marker} {boon.name}", parse_style(style))
            for line in wrap(boon.blurb, width - 10):
                buffer.text(x + 5, row + 1, line, parse_style(ASH))
                row += 1
            row += 1
        self._centre(
            buffer,
            x,
            y + height - 2,
            width,
            "← → choose   enter take   esc back",
            ASH,
        )

    # -- input --------------------------------------------------------------
    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name in ("left", "a", "h", "up", "w", "k"):
            self.index = (self.index - 1) % (
                len(self.offers) if self.mode == "boons" else len(self.OPTIONS)
            )
            return True
        if name in ("right", "d", "l", "down", "s", "j"):
            self.index = (self.index + 1) % (
                len(self.offers) if self.mode == "boons" else len(self.OPTIONS)
            )
            return True
        if name in ("enter", "space"):
            self._choose(self.index, app)
            return True
        if self.mode == "door":
            for i, (key, _label) in enumerate(self.OPTIONS):
                if name == key:
                    self._choose(i, app)
                    return True
        elif name in ("1", "2", "3"):
            self._choose(int(name) - 1, app)
            return True
        if name == "escape":
            if self.mode == "boons":
                self.mode = "door"
                self.index = 0
                return True
            # Stepping back is allowed. It leaves the player on the landing,
            # where the next step onto the stairs asks again.
            self.state.door_pending = False
            self.state.say("You step back from the door.", LogKind.PLAIN)
            app.pop()
            return True
        return False

    def _choose(self, index: int, app) -> None:
        if self.mode == "door":
            if index == 0:
                app.play("door_unlock")
                self.state.bank()
                app.show_game_over(won=True)
                return
            self.mode = "boons"
            self.index = 0
            return
        key = self.offers[index]
        if not self.state.take_boon(key):
            return
        app.play("door_creak")
        self.state.continue_through_the_door()
        app.pop()
        app.redraw()
