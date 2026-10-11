"""Hero select.

The roster is data, so this is a card per hero: their letter in the block font,
their name, their prose, and the numbers that make them a choice. Locked slots
are shown rather than hidden, because the shape of what is coming is worth
seeing.
"""

from __future__ import annotations

from neverdeads_revenge.game.actors import HEROES, Hero
from neverdeads_revenge.game.combat import chance_against
from neverdeads_revenge.game.pace import MAX_ACTIONS_PER_SECOND, actions_per_second

from ..blocks import render_word
from ..chrome import ASH, BONE, BLOOD, box
from ..theme import parse_style
from .base import Screen
from .dialogs import wrap

__all__ = ["HeroSelectScreen", "FUTURE_HEROES"]

#: Slugs that exist as a design idea and not yet as code.
FUTURE_HEROES = ("revenant", "warden")


class HeroSelectScreen(Screen):
    """Choose a hero. Returns the key through the app's callback."""

    def __init__(self) -> None:
        self.index = 0

    @property
    def slots(self) -> list[Hero | None]:
        real = [HEROES[key] for key in HEROES]
        return [*real, *(None for _ in FUTURE_HEROES)]

    @property
    def current(self) -> Hero | None:
        return self.slots[self.index]

    def draw(self, buffer, app) -> None:
        buffer.clear()
        hero = self.current
        width = min(buffer.cols - 8, 76)
        height = min(buffer.rows - 4, 22)
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title="CHOOSE", border=BLOOD, fill=True)

        rows = _stat_rows(hero) if hero is not None else []
        stats_top = y + height - len(rows) - 2 if rows else y + height - 3

        if hero is None:
            self._centre(buffer, y + 3, "???", ASH)
            self._centre(buffer, y + 5, "not yet resurrected", ASH)
        else:
            art = render_word(hero.glyph)
            for i, line in enumerate(art):
                self._centre(buffer, y + 2 + i, line, f"bold {hero.color}")
            self._centre(buffer, y + 2 + len(art), f"{hero.name}  {hero.title}",
                         f"bold {hero.color}")
            body_y = y + 3 + len(art)
            for i, line in enumerate(wrap(hero.blurb, width - 8)):
                if body_y + i >= stats_top - 1:
                    break
                self._centre(buffer, body_y + i, line, BONE)
            for i, (label, value, note) in enumerate(rows):
                row = stats_top + i
                buffer.text(x + 3, row, f"{label:<9}{value:<8}", parse_style("bold " + BONE))
                buffer.text(x + 20, row, note[: width - 22], parse_style(ASH))

        roster = "   ".join(
            ("[?]" if h is None else (f"[{h.glyph}]" if i == self.index else f" {h.glyph} "))
            for i, h in enumerate(self.slots)
        )
        self._centre(buffer, y + height - 2, roster, BONE)
        self._centre(buffer, buffer.rows - 2, "← → choose   enter begin   esc back", ASH)

    @staticmethod
    def _centre(buffer, y: int, text: str, style: str) -> None:
        x = max(0, (buffer.cols - len(text)) // 2)
        buffer.text(x, y, text, parse_style(style))

    def key(self, name: str, event, app) -> bool:
        # One gesture, one motion -- and above all one confirm: a held enter
        # that opened this screen must not begin the run on its next repeat.
        if event.isAutoRepeat():
            return True
        if name in ("left", "h", "a"):
            self.index = (self.index - 1) % len(self.slots)
            return True
        if name in ("right", "l", "d"):
            self.index = (self.index + 1) % len(self.slots)
            return True
        if name in ("enter", "space"):
            hero = self.current
            if hero is not None:
                app.begin_run(hero.key)
            return True
        if name == "escape":
            app.pop()
            return True
        return False


def _stat_rows(hero: Hero) -> list[tuple[str, str, str]]:
    """The numbers, one row each -- the port of the terminal card."""
    s = hero.stats
    return [
        ("health", f"{s.max_hp}", _health_note(s.max_hp)),
        ("speed", f"{s.speed:.2f}",
         f"{actions_per_second(s.speed):.0f}/{MAX_ACTIONS_PER_SECOND:.0f} a second"),
        ("crit", f"{s.crit_chance:.0%}", f"x{s.crit_multiplier:.1f} damage"),
        ("damage", f"{s.damage[0]}-{s.damage[1]}", "per hit"),
        ("accuracy", f"{s.accuracy}", f"hits a plain thing {chance_against(s.accuracy, 0):.0%}"),
        ("evasion", f"{s.evasion}", f"their hit chance {chance_against(0, s.evasion):.0%}"),
        ("armour", f"{s.armor}", "off every hit"),
        ("revenge", hero.trait.label, f"{hero.trait.describe(1)} per kill"),
    ]


def _health_note(max_hp: int) -> str:
    if max_hp >= 44:
        return "a long argument"
    if max_hp >= 32:
        return "room to be wrong"
    return "low is a promise"
