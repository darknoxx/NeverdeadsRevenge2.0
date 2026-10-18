"""The two screens a run ends on: the tally, and the name.

The tally takes a *held* enter, because it is the only place a run is added up
and a stray press should not throw it away. The name entry is arcade-style: five
slots, letters and digits, because that is what a scoreboard column wants.
"""

from __future__ import annotations

from ..chrome import ASH, BONE, BLOOD, PURPLE, box, rule
from ..hold import HoldToContinue
from ..theme import parse_style
from .base import Screen

__all__ = ["GameOverScreen", "NameEntryScreen", "REWIND", "SLOTS", "clean_name"]

REWIND = "rewind"
SLOTS = 5
ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


def clean_name(raw: str) -> str:
    """Whatever the player typed, as it goes on the board."""
    letters = [char for char in raw.upper() if char in ALLOWED]
    return "".join(letters[:SLOTS])


def _summary_lines(state) -> list[tuple[str, str]]:
    """The run, added up. The same lines the terminal summary printed."""
    won = state.run_state.name == "ESCAPED"
    lines: list[tuple[str, str]] = []
    if won:
        lines.append((f"Out of the dark on floor {state.depth}", "bold bright_cyan"))
    else:
        lines.append((f"Floor reached  {state.depth}", "bold cyan"))
    lines.append((f"Monsters slain  {state.kills}", BONE))
    lines.append((f"Kill score      {state.kill_score}",
                  "bold white" if state.kill_score else ASH))
    lines.append((f"Level reached   {state.level}", BONE))
    lines.append((f"Coins banked    {state.gold}", BONE))
    lines.append((f"Turns taken     {state.total_turns}", BONE))
    lines.append((f"Cells walked    {state.player.steps}", BONE))
    lines.append((f"Speed bonus     {state.speed_bonus:+d}",
                  "bold green" if state.speed_bonus else ASH))
    if state.fame:
        lines.append((f"Fame            {state.fame}  "
                      f"(worth {state.score_multiplier:.2f}x)", "bold green"))
    lines.append((f"Score           {state.score}", f"bold {PURPLE}"))
    if won:
        lines.append(("You were not granted death.", "italic"))
    return lines


class GameOverScreen(Screen):
    """The tally. A held enter goes on; ``r`` takes the ending back."""

    modal = True

    def __init__(self, state, won: bool, best: int, can_rewind: bool, on_done=None) -> None:
        self.state = state
        self.won = won
        self.best = best
        self.can_rewind = can_rewind
        self.on_done = on_done
        self.hold = HoldToContinue()

    def draw(self, buffer, app) -> None:
        lines = _summary_lines(self.state)
        width = min(buffer.cols - 6, 46)
        height = len(lines) + 8
        x, y = (buffer.cols - width) // 2, max(0, (buffer.rows - height) // 2)
        title = "VICTORY" if self.won else "YOU DIED"
        box(buffer, x, y, width, height, title=title, border=BLOOD, fill=True)
        for i, (text, style) in enumerate(lines):
            buffer.text(x + 3, y + 2 + i, text[: width - 6], parse_style(style))
        rule(buffer, x + 1, y + height - 3, width - 2, ASH)
        buffer.text(x + 3, y + height - 2, f"Best  {self.best}", parse_style(f"bold {BONE}"))
        self._hint(buffer, x, y + height - 1, width)

    def _hint(self, buffer, x: int, y: int, width: int) -> None:
        bar = self.hold.bar()
        if self.can_rewind:
            text = f"hold enter   {bar}      r take it back"
        else:
            text = f"hold enter   {bar}"
        buffer.text(x + 3, y, text[: width - 6], parse_style(ASH))

    def key(self, name, event, app) -> bool:
        if name == "escape":
            # One gesture: a held escape from the screen before this one must
            # not close the tally before a word of it is read. The hold's own
            # repeats are a different matter -- they *are* the hold.
            if not event.isAutoRepeat():
                self.finish(app, None)
            return True
        if name == "r" and self.can_rewind:
            if not event.isAutoRepeat():
                # The one moment the game gives a run back, and it should sound
                # like what it is.
                app.play("revive_resurrect")
                self.finish(app, REWIND)
            return True
        if name in ("enter", "return"):
            # Repeats are fed on purpose: the hold *is* the repeats.
            if self.hold.press(name, event.isAutoRepeat()):
                self.finish(app, None)
            return True
        return True

    def key_up(self, name, event, app) -> bool:
        # The desktop can see the key come up: a tap is a tap, and nothing a
        # tap did banks itself. Platforms that synthesise repeats as
        # press/release pairs pair the release too; those are not a key
        # coming up.
        if not event.isAutoRepeat():
            self.hold.release(name)
        return True

    def finish(self, app, value) -> None:
        app.pop()
        if self.on_done is not None:
            self.on_done(value)


class NameEntryScreen(Screen):
    """Five slots for the scoreboard."""

    modal = True

    def __init__(self, score: int, previous: str = "", on_done=None) -> None:
        self.score = score
        self.name = clean_name(previous)
        self.on_done = on_done

    def draw(self, buffer, app) -> None:
        width = 40
        height = 9
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title="ENTER YOUR NAME", border=BLOOD, fill=True)
        buffer.text(x + 3, y + 2, f"for a score of {self.score}", parse_style(ASH))
        cells = []
        for i in range(SLOTS):
            char = self.name[i] if i < len(self.name) else "_"
            cells.append(f" {char} ")
        buffer.text(x + 3, y + 4, " ".join(cells), parse_style(f"bold {PURPLE}"))
        rule(buffer, x + 1, y + height - 2, width - 2, ASH)
        buffer.text(
            x + 3,
            y + height - 1,
            "letters and digits   backspace   enter to keep",
            parse_style(ASH),
        )

    def key(self, name, event, app) -> bool:
        if event.isAutoRepeat():
            return True
        if name in ("enter", "return", "escape"):
            self.finish(app, self.name or "???")
            return True
        if name in ("backspace", "delete"):
            self.name = self.name[:-1]
            return True
        char = clean_name(event.text() or "")
        if char and len(self.name) < SLOTS:
            self.name += char
        return True

    def finish(self, app, value) -> None:
        app.pop()
        if self.on_done is not None:
            self.on_done(value)
