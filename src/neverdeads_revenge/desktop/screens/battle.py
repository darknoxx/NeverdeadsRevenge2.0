"""The battle stage: the isometric view, drawn but not yet played.

This is **M0**, and it is a picture. There is no turn order, no command that
does anything, no damage and no enemy: three figures stand on receding ground,
the hero stands at the front of it, and two panels sit at the bottom with the
verbs a fight will have. The question this file exists to answer is the only
one that can be answered cheaply -- *does a stage look like this game?* -- and
everything expensive (a battle state, a timeline, balance) is deliberately
absent until that is settled.

**The models are the letters.** The dungeon is an alphabet: a ghoul is a green
``g`` on the map and a ``#`` is a wall, and the stage does not replace that, it
*enlarges* it -- so a monster is the letter it always was, drawn in the game's
own font at the biggest size the fight needs, in the colour the dungeon draws it
in. A letter cannot be drawn large inside the character grid, which is one fixed
cell, so the letters are the one thing pasted straight onto the frame in pixels
(see :meth:`BattleScreen.paste`); every cell that matters -- the floor, the
walls, the shadows, the panels -- is still drawn in the grid, where the rest of
the game draws.

Each letter also carries a dark copy of itself a few pixels lower. That is the
whole of the depth trick and it is enough of one: the letter reads as a slab
standing on the floor with thickness, rather than as a sticker on the glass.

The ground is the same bargain. A cell is 10x20 pixels, so two cells side by
side are a square: a floor tile. Two rows of those, staggered half a tile, are
a checkerboard, and a checkerboard whose rows narrow and darken as they go up is
a floor in perspective. Its edges are walls -- the dungeon's own ``#``, in the
dungeon's own dim greys -- so the floor is a room rather than a shape, and the
side walls follow the same taper, which is what makes the room go somewhere.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFontMetrics, QPainter

from ..buffer import PatternBuffer
from ..chrome import ASH, BLOOD, BONE, box, menu
from ..font import BitmapFont
from ..theme import Style, parse_style
from .base import Screen

__all__ = ["BattleScreen", "Staged", "VERBS"]

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
#: The wall behind and beside the floor. The dungeon draws a remembered wall in
#: grey19 and a seen one in grey37; the arena is lit by whatever the fight is,
#: so it sits between the two and goes darker with the distance.
WALL_NEAR = "grey30"
WALL_FAR = "grey19"
#: How thick a letter is: the dark copy sits this many pixels below the bright
#: one, and the bright one is drawn over it.
THICKNESS = 5

#: How big each letter stands, in font pixels, by how far away it is. The hero
#: is nearest and largest; the monsters scale with their depth.
SIZES = (62, 52, 46)
HERO_SIZE = 88

#: The verbs a fight will have. Nothing answers them yet.
VERBS = (
    ("a", "ATTACK"),
    ("s", "SPECIAL"),
    ("i", "ITEM"),
    ("d", "DEFEND"),
    ("f", "FLEE"),
)

_LETTERS: dict[int, BitmapFont] = {}


def letter_font(size: int) -> BitmapFont:
    """The font a letter is drawn in, measured once per size.

    A frame is drawn thirty times a second and a font is four faces plus their
    metrics, so the sizes are kept: there are four of them, and they are the
    same four for the whole game.
    """
    font = _LETTERS.get(size)
    if font is None:
        font = BitmapFont(pixel_size=size)
        _LETTERS[size] = font
    return font


class Staged:
    """One figure on the stage: who it is, and where it stands.

    The letters are drawn in pixels, so a figure is placed in pixels too -- a
    centre and a baseline -- and the *shadow* is drawn in cells underneath it,
    because that is where the floor is. :func:`BattleScreen._stage` computes
    both from the one layout, so they cannot disagree.
    """

    __slots__ = ("name", "glyph", "colour", "size", "cx", "foot", "cells", "chosen")

    def __init__(
        self,
        name: str,
        glyph: str,
        colour: str,
        size: int,
        cx: int,
        foot: int,
        cells: int,
        chosen: bool = False,
    ) -> None:
        self.name = name
        self.glyph = glyph
        self.colour = colour
        self.size = size
        #: Where the letter stands: the centre of it, in pixels.
        self.cx = cx
        #: The cell row it stands on. Its baseline is the bottom of that row, so
        #: the shadow in the grid and the letter in the pixels line up.
        self.foot = foot
        self.cells = cells
        self.chosen = chosen


def _monsters() -> list[tuple[str, str, str]]:
    """Three out of the bestiary, by key: ``(name, glyph, colour)``.

    Real monsters, so the letters and their colours are the game's and not a
    mock-up's: a ghoul is a green ``g`` here for the same reason it is a green
    ``g`` on the map.
    """
    from neverdeads_revenge.game.actors import ENEMIES

    keys = ("ghoul", "bone", "wraith")
    out = []
    for key in keys:
        template = ENEMIES.get(key)
        if template is None:
            out.append((key, key[0], "white"))
        else:
            out.append((template.name, template.glyph, template.color))
    return out


class BattleScreen(Screen):
    """The stage, the two panels, and nothing else. Yet.

    Escape leaves: M0 is reached from the title with ``--battle-scene``, so the
    way out has to exist before the way in does anything interesting.
    """

    def draw(self, buffer: PatternBuffer, app) -> None:
        buffer.clear()
        areas = self._areas(buffer.cols, buffer.rows)
        self._draw_ground(buffer, *areas["ground"])
        self._draw_shadows(buffer, *areas["ground"])
        self._draw_names(buffer, *areas["ground"])
        self._draw_plate(buffer, *areas["plate"])
        self._draw_commands(buffer, *areas["commands"])

    def paste(self, image, app) -> None:
        """The models: the letters, big, over the floor the grid drew.

        Drawn here rather than in the grid because a letter the size of a
        monster does not fit in a cell -- the whole look of the game is one
        fixed cell, and this is the one place that has to leave it.
        """
        buffer = app._buffer
        if buffer is None:
            return
        staged = self._stage(buffer.cols, buffer.rows, app.font.cell_w, app.font.cell_h)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        for figure in staged:
            font = letter_font(figure.size)
            painter.setFont(font.bold)
            metrics = QFontMetrics(font.bold)
            left = figure.cx - metrics.horizontalAdvance(figure.glyph) // 2
            baseline = (figure.foot + 1) * app.font.cell_h - THICKNESS
            ink = parse_style(figure.colour).fg
            # The slab: the same letter, dark, sitting a few pixels lower. The
            # bright one is drawn over it, so what shows is the thickness.
            painter.setPen(ink.darker(320))
            painter.drawText(left, baseline + THICKNESS, figure.glyph)
            painter.setPen(ink)
            painter.drawText(left, baseline, figure.glyph)
        painter.end()

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

    def _stage(
        self, cols: int, rows: int, cell_w: int, cell_h: int
    ) -> list[Staged]:
        """Who stands where: the monsters at three depths, the hero in front.

        One layout for the letters and the shadows under them, so a figure
        cannot be drawn in one place and stand in another.
        """
        x0, y0, width, height = self._areas(cols, rows)["ground"]
        centre = x0 + width // 2
        monsters = _monsters()
        # Cell positions, far to near: the left one hangs back, the right one is
        # the closest, which is what makes a row of three read as a row.
        places = (
            (centre - max(8, width // 4), y0 + max(2, height // 3)),
            (centre - max(2, width // 12), y0 + max(1, height // 5)),
            (centre + max(8, width // 4), y0 + max(2, height // 2)),
        )
        staged: list[Staged] = []
        for index, ((name, glyph, colour), (cx_cell, foot)) in enumerate(
            zip(monsters, places)
        ):
            size = SIZES[index]
            staged.append(
                Staged(
                    name=name,
                    glyph=glyph,
                    colour=colour,
                    size=size,
                    cx=(cx_cell + 1) * cell_w,
                    foot=foot,
                    cells=self._letter_cells(glyph, size, cell_w),
                    chosen=index == 0,
                )
            )

        from neverdeads_revenge.game.actors import NOXX

        size = HERO_SIZE
        glyph = NOXX.glyph
        staged.append(
            Staged(
                name=NOXX.name,
                glyph=glyph,
                colour=NOXX.color,
                size=size,
                cx=((centre + 0) * cell_w),
                foot=y0 + height - 1,
                cells=self._letter_cells(glyph, size, cell_w),
            )
        )
        return staged

    @staticmethod
    def _letter_cells(glyph: str, size: int, cell_w: int) -> int:
        """How many cells wide the shadow under a letter has to be."""
        font = letter_font(size)
        advance = QFontMetrics(font.bold).horizontalAdvance(glyph)
        return max(2, round(advance / cell_w))

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
        self._draw_walls(buffer, x0, y0, width, height, back_inset)

    @staticmethod
    def _tile(depth: float, alt: bool) -> QColor:
        """The floor's colour at ``depth``: 0 at the horizon, 1 at the hero."""
        near, far = (FLOOR_NEAR, FLOOR_FAR) if alt else (FLOOR_NEAR_ALT, FLOOR_FAR_ALT)
        return QColor(
            int(far.red() + (near.red() - far.red()) * depth),
            int(far.green() + (near.green() - far.green()) * depth),
            int(far.blue() + (near.blue() - far.blue()) * depth),
        )

    def _draw_walls(
        self,
        buffer: PatternBuffer,
        x0: int,
        y0: int,
        width: int,
        height: int,
        back_inset: int,
    ) -> None:
        """The arena: the dungeon's ``#``, as a back wall and two side walls.

        The sides follow the floor's own taper cell for cell, which is the whole
        of the perspective -- a wall that converged its own way would be a
        second opinion about where the room goes. Both fade with the distance
        the way a remembered wall does: the near end of the room is ``grey30``,
        the far end ``grey19``, and the far wall is what the floor recedes into.
        """
        near = parse_style(WALL_NEAR)
        far = parse_style(WALL_FAR)
        # -- the back wall: two courses of bricks above the floor's far edge.
        # Solid rather than spaced: the side walls are solid, and a back wall of
        # dashes reads as a fence across the top of the room.
        for course in range(2 if width >= 30 else 1):
            y = y0 - 1 - course
            if y < 0:
                break
            shade = Style(fg=far.fg if course else near.fg)
            for x in range(back_inset, width - back_inset):
                buffer.put(x0 + x, y, "#", shade)
        # -- the side walls: one cell out from the floor, converging with it
        for i in range(height):
            depth = i / max(1, height - 1)
            inset = int(round((1.0 - depth) * back_inset))
            left, right = inset - 1, width - inset
            for x in (left, right):
                if 0 <= x < width:
                    buffer.put(x0 + x, y0 + i, "#", near if depth > 0.5 else far)

    def _draw_shadows(
        self, buffer: PatternBuffer, x0: int, y0: int, width: int, height: int
    ) -> None:
        """Under each letter: the tiles it stands on, gone nearly black."""
        font = buffer.font
        for figure in self._stage(buffer.cols, buffer.rows, font.cell_w, font.cell_h):
            left = round(figure.cx / font.cell_w) - 1 - figure.cells // 2
            for i in range(figure.cells):
                buffer.put(left + i, figure.foot, " ", Style(bg=SHADOW))

    def _draw_names(
        self, buffer: PatternBuffer, x0: int, y0: int, width: int, height: int
    ) -> None:
        """Who is who, under the letter that already says it.

        The letter is the model, so a name is not how the player *finds* a
        monster -- but ``s`` is a skeleton and not an ``s``, and the one the
        choice is on wears the blade the menus use for the chosen line.
        """
        font = buffer.font
        for figure in self._stage(buffer.cols, buffer.rows, font.cell_w, font.cell_h):
            marker = "►" if figure.chosen else " "
            label = f"{marker} {figure.name}"
            centre = round(figure.cx / font.cell_w) - 1
            chosen = parse_style(f"bold {figure.colour}")
            style = chosen if figure.chosen else parse_style(figure.colour)
            buffer.text(centre - len(label) // 2, figure.foot + 1, label, style)

    # -- the panels ---------------------------------------------------------
    def _draw_plate(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The hero's plate: who he is, how much of him is left, what he carries."""
        from neverdeads_revenge.game.actors import NOXX

        title = NOXX.name.upper()
        box(buffer, x, y, width, height, title=title, border=BLOOD, fill=True)
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
