"""Hero select.

The roster is data, so this is a card per hero: their picture, their name, their
prose, and the numbers that make them a choice. Locked slots are shown rather
than hidden, because the shape of what is coming is worth seeing.

The picture is the hero *facing the player* -- the sheets' own front view, which
is the second set of art the arena has no use for -- asked for as a ``Placed``
record and put down by whichever application is drawing, standing on the line the
block letter stood on. The letter is still what happens when there is no picture:
a hero the sheets have never heard of is a letter on the card, not a broken menu,
and the screen asks the *sheets* whether there is one rather than asking a
toolkit.
"""

from __future__ import annotations

from ..art import Placed, exists
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

#: Heroes whose sheets are being redrawn: in the roster, and not a choice.
#:
#: They keep their *slot* -- the order of the cards and the row of hotkeys do not move,
#: because a slot that moved would move four others with it -- and draw as one of the
#: "not yet resurrected" ones until they have their art back. A name in here and out
#: again is the whole switch; it is empty today, and Walkyrion is the reason the
#: switch exists.
UNFINISHED: tuple[str, ...] = ()

#: How many rows the picture band is, in cells: the block font's own height, and
#: a *constant* rather than a measurement. The card's layout is the same card for
#: every hero, and deriving its height from the hero's letter meant that a hero
#: whose letter the font happened not to carry -- which is exactly what happened
#: to the fourth one -- got a band of a different height and a picture standing
#: somewhere else on the card.
ART_ROWS = 5

#: The height every hero's picture is drawn at, whatever height the sheets
#: exported it at. The four cards are otherwise the same card four times, and a
#: figure a third smaller than its neighbours -- with its feet on the same line,
#: so it hangs where its own transparent margin would have been -- reads as a
#: hero who is not finished rather than one who is small.
#:
#: Ninety is not a taste: it is what the three exported at, so they are drawn at
#: the size they were painted and only a smaller export is scaled up to meet
#: them. The filter is *smooth* here and nowhere else in this game: these are
#: paintings, and the pixel art on the plate is not.
PORTRAIT_HEIGHT = 90


class HeroSelectScreen(Screen):
    """Choose a hero. Returns the key through the app's callback."""

    def __init__(self) -> None:
        self.index = 0
        #: Where the hero's picture goes, in pixels: the centre of the card and
        #: the line the figure stands on. Decided in ``draw`` and handed out by
        #: ``art``, because the grid pass knows the card's rows and the frame is
        #: the front end's business -- and this screen is the one that has to
        #: know both, so it carries the seam between them.
        self._where: tuple[int, int] | None = None

    @property
    def slots(self) -> list[Hero | None]:
        real = [None if key in UNFINISHED else HEROES[key] for key in HEROES]
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

        self._where = None
        if hero is None:
            self._centre(buffer, y + 3, "???", ASH)
            self._centre(buffer, y + 5, "not yet resurrected", ASH)
        else:
            # The band is the block font's own five rows whether or not there
            # is a picture to put in them: the name and the prose below sit on
            # the same line for every hero, which is what keeps one card from
            # being taller than the next one's.
            face = exists(f"sprites/portraits/{hero.name}.png")
            if not face:
                for i, line in enumerate(render_word(hero.glyph)[:ART_ROWS]):
                    self._centre(buffer, y + 2 + i, line, f"bold {hero.color}")
            self._centre(buffer, y + 2 + ART_ROWS, f"{hero.name}  {hero.title}",
                         f"bold {hero.color}")
            if face:
                # The figure stands on the last row of the band, the way it
                # stands on the arena's floor: a picture floats, a *figure* is
                # standing somewhere.
                self._where = (
                    buffer.cols * app.font.cell_w // 2,
                    (y + 2 + ART_ROWS) * app.font.cell_h,
                )
            body_y = y + 3 + ART_ROWS
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

    def art(self, app) -> list[Placed]:
        """The hero, as a picture the front end can put on the frame.

        At a fixed *height* and centred on the card's own line, which is the same
        promise the arena keeps: these are painted figures, and every one of them
        stands the same height on the same line, because that is the whole of what
        a roster row is for. The width is the picture's own shape, which the front
        end has in hand and this screen deliberately does not.

        Named rather than loaded: the screen says *what* and *where*, and whichever
        application is drawing blits it. A screen that loaded its own picture would
        be a screen that needed a toolkit.
        """
        hero = self.current
        if hero is None or self._where is None:
            # Nothing to place it on, or nothing to place: the card is a letter or
            # a question mark, and the grid has already drawn it.
            return []
        cx, baseline = self._where
        return [Placed(f"sprites/portraits/{hero.name}.png", cx, baseline, PORTRAIT_HEIGHT)]

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
