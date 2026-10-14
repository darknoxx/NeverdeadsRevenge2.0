"""The battle stage: the isometric view, drawn but not yet played.

This is **M0**, and it is a picture. There is no turn order, no command that
does anything, no damage and no enemy: three figures stand on receding ground,
the hero stands at the front of it, and two panels sit at the bottom with the
verbs a fight will have. The question this file exists to answer is the only
one that can be answered cheaply -- *does a stage look like this game?* -- and
everything expensive (a battle state, a timeline, balance) is deliberately
absent until that is settled.

The ground is built out of the one thing a cell grid is good at. A cell is
10x20 pixels, so two cells side by side are a square: a floor tile. Two rows of
those, staggered half a tile from each other, are a checkerboard -- and a
checkerboard whose rows narrow and darken as they go up *is* a floor in
perspective, seen from above and behind the hero. The tiles are filled rather
than dotted: a floor is a surface, and the first attempt at this drew it as
`░` on black, which read as static rather than as ground.

Figures are silhouettes: a head, a body, a base, in the colour the dungeon
already draws them in (a ghoul is green there, so it is green here), sized by
how far away they stand. Their names sit underneath in their own colour, and
the one the player has chosen wears the blade the menus already use for the
chosen line.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from ..buffer import PatternBuffer
from ..chrome import ASH, BLOOD, BONE, box, menu
from ..theme import Style, parse_style
from .base import Screen

__all__ = ["BattleScreen", "Staged"]

#: The floor's two tile tones at the hero's feet, and the same two at the
#: horizon. Distance is shade here, not size: the far rows fade into the dark
#: the way a remembered wall does, because the phosphor fades rather than
#: switches off.
FLOOR_NEAR = QColor("#2c2c36")
FLOOR_NEAR_ALT = QColor("#202028")
FLOOR_FAR = QColor("#16161c")
FLOOR_FAR_ALT = QColor("#101014")
#: Where something is standing: the tiles under it go nearly black.
SHADOW = QColor("#08080a")
#: The floor's own edge, and the dark above it.
EDGE = "grey30"


class Staged:
    """One figure on the stage, before there is anything to fight about.

    A stand-in for an ``EnemyTemplate`` and a hero to be read into later: M0
    needs a name, a colour, and how big somebody stands.
    """

    __slots__ = ("name", "colour", "width", "height", "legs")

    def __init__(
        self, name: str, colour: str, width: int, height: int, legs: bool = False
    ) -> None:
        self.name = name
        self.colour = colour
        self.width = width
        self.height = height
        #: A pair of legs rather than a base. Only the hero has them: a monster
        #: is a thing that stands, a person is a thing that walks.
        self.legs = legs


def _stage_figures(field: int) -> list[Staged]:
    """The three the picture is drawn with, straight out of the bestiary.

    Real monsters by key, so the names and the colours are the game's and not a
    mock-up's -- a ghoul is green here for the same reason it is green on the
    map. They differ in size because depth is the only size cue a flat grid has,
    and they grow with the field: a monster that keeps its five cells on a wide
    glass is a monster standing in a cathedral.
    """
    from neverdeads_revenge.game.actors import ENEMIES

    big = field >= 110
    wanted = (
        ("ghoul", 6 if big else 5, 4 if big else 3),
        ("bone", 6 if big else 5, 4 if big else 3),
        ("wraith", 5 if big else 4, 4 if big else 3),
    )
    figures: list[Staged] = []
    for key, cells, height in wanted:
        template = ENEMIES.get(key)
        figures.append(
            Staged(
                name=template.name if template else key,
                colour=template.color if template else "white",
                width=cells,
                height=height,
            )
        )
    return figures


#: The verbs a fight will have. Nothing answers them yet.
VERBS = (
    ("a", "ATTACK"),
    ("s", "SPECIAL"),
    ("i", "ITEM"),
    ("d", "DEFEND"),
    ("f", "FLEE"),
)


class BattleScreen(Screen):
    """The stage, the two panels, and nothing else. Yet.

    Escape leaves: M0 is reached from the title with ``--battle-scene``, so the
    way out has to exist before the way in does anything interesting.
    """

    def draw(self, buffer: PatternBuffer, app) -> None:
        buffer.clear()
        areas = self._areas(buffer.cols, buffer.rows)
        self._draw_ground(buffer, *areas["ground"])
        self._draw_figures(buffer, *areas["ground"])
        self._draw_plate(buffer, *areas["plate"])
        self._draw_commands(buffer, *areas["commands"])

    def key(self, name: str, event, app) -> bool:
        if name == "escape":
            app.return_to_title()
            return True
        return False

    # -- the shape of the screen --------------------------------------------
    def _areas(self, cols: int, rows: int) -> dict[str, tuple[int, int, int, int]]:
        """Where the three pieces sit, in cells: ground, plate, commands.

        Two panels along the bottom, the hero's on the left and the verbs' on
        the right -- the hand on the left, the choice on the right, which is
        where a fight with a menu has always put them. The panels are as tall as
        the five verbs and their numbers need; a short window gets a shorter
        field and fewer verbs, never a broken one.
        """
        margin = max(1, min(3, cols // 24))
        panel_h = 7 if rows >= 26 else 5 if rows >= 16 else 3
        panel_y = max(1, rows - panel_h - margin)
        panel_w = max(12, min((cols - margin * 3) // 2, 36))
        ground_y = margin
        ground_h = max(1, panel_y - ground_y - 1)
        return {
            "ground": (margin, ground_y, max(1, cols - margin * 2), ground_h),
            "plate": (margin, panel_y, panel_w, panel_h),
            "commands": (max(0, cols - margin - panel_w), panel_y, panel_w, panel_h),
        }

    # -- the ground ---------------------------------------------------------
    def _draw_ground(
        self, buffer: PatternBuffer, x0: int, y0: int, width: int, height: int
    ) -> None:
        """Rows of filled tiles, staggered, narrowing and fading as they recede.

        Row ``i`` counts from the horizon down to the hero's feet. Its inset
        grows with the distance to the back, and its tone falls off on the way,
        so the same two colours in the same two glyphs turn into a floor that
        goes somewhere.
        """
        if width < 8 or height < 3:
            return
        back_inset = max(1, int(width * 0.12))
        for i in range(height):
            depth = i / (height - 1)
            inset = int(round((1.0 - depth) * back_inset))
            # Half a tile of stagger per row: this is the whole of the
            # isometric illusion. Two cells are one tile, so the phase is a cell.
            phase = i % 2
            for x in range(inset, width - inset):
                alt = ((x + phase) // 2) % 2 == 0
                buffer.put(x0 + x, y0 + i, " ", Style(bg=self._tile(depth, alt)))
        self._draw_horizon(buffer, x0, y0, width, back_inset)

    @staticmethod
    def _tile(depth: float, alt: bool) -> QColor:
        """The floor's colour at ``depth``: 0 at the horizon, 1 at the hero."""
        near, far = (FLOOR_NEAR, FLOOR_FAR) if alt else (FLOOR_NEAR_ALT, FLOOR_FAR_ALT)
        return QColor(
            int(far.red() + (near.red() - far.red()) * depth),
            int(far.green() + (near.green() - far.green()) * depth),
            int(far.blue() + (near.blue() - far.blue()) * depth),
        )

    def _draw_horizon(
        self, buffer: PatternBuffer, x0: int, y0: int, width: int, back_inset: int
    ) -> None:
        """The far edge of the floor, and two shapes that end it.

        The line runs along the *back edge of the floor* rather than the whole
        glass: a horizon wider than the floor it ends is a horizon nobody
        believes.
        """
        left = x0 + back_inset
        span = width - back_inset * 2
        if span < 6:
            return
        for x in range(left, left + span):
            buffer.put(x, y0 - 1, "─", parse_style(EDGE))
        # Two blocks of stone at the ends of it: enough to say the stage stands
        # *in* the dungeon rather than floating in a void, and not enough to be
        # a room that has to be drawn.
        buffer.text(left, y0 - 1, "▓▓", parse_style(EDGE))
        buffer.text(left + span - 2, y0 - 1, "▓▓", parse_style(EDGE))

    # -- the figures --------------------------------------------------------
    def _draw_figures(
        self, buffer: PatternBuffer, x0: int, y0: int, width: int, height: int
    ) -> None:
        if width < 24 or height < 8:
            return
        centre = x0 + width // 2
        # The enemies stand in the far half, at three depths, so the row reads
        # as a row standing *on* the floor rather than pasted across it.
        places = (
            (centre - max(8, width // 4), y0 + max(2, height // 4), 0),
            (centre - max(2, width // 12), y0 + max(1, height // 5), 1),
            (centre + max(8, width // 4), y0 + max(3, height // 3), 2),
        )
        for figure, (x, y, index) in zip(_stage_figures(width), places):
            self._figure(buffer, x, y, figure, chosen=index == 0)

        big = width >= 110
        hero = Staged("Noxx", "#a855f7", 9 if big else 7, 7 if big else 5, legs=True)
        self._figure(
            buffer,
            centre - hero.width // 2,
            y0 + height - hero.height,
            hero,
            chosen=False,
        )

    def _figure(
        self, buffer: PatternBuffer, x: int, y: int, figure: Staged, chosen: bool
    ) -> None:
        """One silhouette: a head, a body, a base, its pool of shadow, its name.

        The shadow goes onto the floor *first* -- the tiles where it stands go
        nearly black -- so the figure lands on the ground instead of hovering a
        cell above it.
        """
        ink = parse_style(f"bold {figure.colour}")
        name_ink = ink if chosen else parse_style(figure.colour)
        for i in range(-1, figure.width + 1):
            buffer.put(x + i, y + figure.height - 1, " ", Style(bg=SHADOW))

        head = max(2, figure.width - 2)
        head_x = x + (figure.width - head) // 2
        buffer.text(head_x, y, "█" * head, ink)
        for j in range(1, figure.height - 1):
            buffer.text(x, y + j, "█" * figure.width, ink)
        foot = y + figure.height - 1
        if figure.legs:
            for i in (1, figure.width - 2):
                buffer.put(x + i, foot, "█", ink)
        else:
            base = max(2, figure.width - 2)
            buffer.text(x + (figure.width - base) // 2, foot, "█" * base, ink)

        marker = "►" if chosen else " "
        label = f"{marker} {figure.name}"
        name_x = max(0, x + figure.width // 2 - len(label) // 2)
        buffer.text(name_x, y + figure.height, label, name_ink)

    # -- the panels ---------------------------------------------------------
    def _draw_plate(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The hero's plate: who he is, how much of him is left, what he carries."""
        box(buffer, x, y, width, height, title="NOXX", border=BLOOD, fill=True)
        if height < 4 or width < 14:
            return
        bar = min(12, max(4, width - 22))
        buffer.text(x + 2, y + 1, "HP", parse_style(ASH))
        self._bar(buffer, x + 5, y + 1, bar, 0.72)
        buffer.text(x + 6 + bar, y + 1, " 22/30", parse_style(BONE))
        if height >= 5:
            buffer.text(x + 2, y + 2, "DRGT  ● ● ○", parse_style("dim #a855f7"))
        if height >= 6:
            buffer.text(x + 2, y + 3, "THE VOID", parse_style(ASH))
            buffer.text(x + 12, y + 3, "ready", parse_style("bold bright_yellow"))
        if height >= 7:
            buffer.text(x + 2, y + height - 2, "esc  leave the stage", parse_style(ASH))

    def _draw_commands(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The verbs, arranged the way every menu in this game is."""
        box(buffer, x, y, width, height, title="COMMAND", border=BLOOD, fill=True)
        if height < 4 or width < 12:
            return
        menu(buffer, x + 2, y + 1, list(VERBS[: height - 2]), index=0)

    @staticmethod
    def _bar(buffer: PatternBuffer, x: int, y: int, cells: int, ratio: float) -> None:
        filled = max(0, min(cells, round(cells * ratio)))
        colour = (
            "bright_green"
            if ratio > 0.5
            else "bright_yellow"
            if ratio > 0.25
            else "bright_red"
        )
        buffer.text(x, y, "█" * filled, parse_style(colour))
        buffer.text(x + filled, y, "░" * (cells - filled), parse_style("grey23"))
