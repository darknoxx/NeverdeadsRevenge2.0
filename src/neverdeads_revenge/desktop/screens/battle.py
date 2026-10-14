"""The battle stage: the isometric view, drawn but not yet played.

This is **M0**, and it is a picture. There is no turn order, no command that
does anything, no damage and no enemy: three figures stand on receding ground,
the hero stands at the front of it, and two panels sit at the bottom with the
verbs a fight will have. The question this file exists to answer is the only
one that can be answered cheaply -- *does a stage look like this game?* -- and
everything expensive (a battle state, a timeline, balance) is deliberately
absent until that is settled.

**The models are the letters, and so are the walls.** The dungeon is an
alphabet: a ghoul is a green ``g`` on the map, a ``#`` is a wall, and the stage
does not replace that, it *enlarges* it. A monster is the letter it always was,
drawn in the game's own font at the size the fight needs and in the colour the
dungeon draws it in; the room is the dungeon's ``#``, big enough to be masonry.
A letter that size does not fit in a character cell -- a cell is the look of the
whole rest of the game -- so letters and walls are the things pasted straight
onto the frame (see :meth:`BattleScreen.paste`).

The walls are not *placed*, they are *projected*. Each wall is a plane, and a
plane in this view has two axes: one is vertical, and the other is the floor's
own edge -- which is why the three walls are three affine transforms of the same
``#``, each sheared along the edge it stands on. A wall that converged its own
way would be a second opinion about where the room goes, and the whole illusion
is one opinion: the floor's.

The ground is the same bargain. A cell is 10x20 pixels, so two cells side by
side are a square: a floor tile. Two rows of those, staggered half a tile, are
a checkerboard, and a checkerboard whose rows narrow and darken as they go up is
a floor in perspective.
"""

from __future__ import annotations

import math

from PySide6.QtGui import QColor, QFontMetrics, QPainter, QTransform

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
#: Where something is standing: the tiles in front of it go nearly black, and
#: the ends of the pool fade rather than stop, so a shadow reads as a shape
#: under a figure instead of as a stripe across the floor.
SHADOW = QColor("#07070a")
SHADOW_EDGE = QColor("#131318")
#: The wall. The dungeon draws a remembered wall in grey19 and a seen one in
#: grey37; the arena is lit by whatever the fight is, so it sits between the two
#: -- the far wall darkest, the near end of the side walls lightest.
WALL_NEAR = "grey30"
WALL_MID = "grey23"
WALL_FAR = "grey19"
#: How thick a letter is: the dark copy sits this many pixels below the bright
#: one, and the bright one is drawn over it.
THICKNESS = 5
#: How far apart the floor's tiles turn, as a share of the width. This is the
#: *only* perspective number: the walls are derived from it, so a room that is
#: deeper or shallower is one edit and not four.
TAPER = 0.18

#: How big each letter stands, in font pixels, by how far away it is. The hero
#: is nearest and largest; the monsters scale with their depth.
SIZES = (62, 52, 46)
HERO_SIZE = 88
#: The arrow over the one the choice is on.
ARROW = "▼"

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
    """The font a letter or a hash is drawn in, measured once per size.

    A frame is drawn thirty times a second and a font is four faces plus their
    metrics, so the sizes are kept: there are a handful of them, and they are
    the same handful for the whole game.
    """
    font = _LETTERS.get(size)
    if font is None:
        font = BitmapFont(pixel_size=size)
        _LETTERS[size] = font
    return font


class Staged:
    """One figure on the stage: who it is, and where it stands.

    The letters are drawn in pixels, so a figure is placed in pixels too -- a
    centre and a baseline -- and its *shadow* is drawn in cells underneath it,
    because that is where the floor is. :meth:`BattleScreen._stage` computes
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
        #: The cell row it stands on. The letter's baseline is the bottom of the
        #: row *above* the shadow, so the pool of shadow lies in front of it.
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

    out = []
    for key in ("ghoul", "bone", "wraith"):
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
        self._draw_ground(buffer, areas["ground"])
        self._draw_shadows(buffer, areas["ground"])
        self._draw_log(buffer, areas["log"])
        self._draw_plate(buffer, *areas["plate"])
        self._draw_commands(buffer, *areas["commands"])

    def paste(self, image, app) -> None:
        """The room and the models: walls first, then the letters, then the arrow.

        Drawn here rather than in the grid because neither a monster nor a block
        of masonry fits in a cell -- the whole look of the game is one fixed
        cell, and this is the one place that has to leave it.
        """
        buffer = app._buffer
        if buffer is None:
            return
        field = self._field(buffer.cols, buffer.rows, app.font.cell_w, app.font.cell_h)
        staged = self._stage(field)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        self._paste_walls(painter, field)
        for figure in staged:
            self._paste_letter(painter, figure, app.font.cell_h)
        for figure in staged:
            if figure.chosen:
                self._paste_arrow(painter, figure, app.font.cell_h)
        painter.end()

    def key(self, name: str, event, app) -> bool:
        if name == "escape":
            app.return_to_title()
            return True
        return False

    # -- the shape of the screen --------------------------------------------
    def _areas(self, cols: int, rows: int) -> dict[str, tuple[int, int, int, int]]:
        """Where the pieces sit, in cells: wall, ground, log, plate, commands.

        Four bands, bottom to top: the panels, a line for the fight to speak in,
        the floor, and the strip the walls stand up into. The wall strip is
        reserved rather than overlaid -- a wall drawn over the floor would be a
        wall in front of the hero.
        """
        margin = max(1, min(3, cols // 24))
        panel_h = 7 if rows >= 26 else 5 if rows >= 16 else 3
        panel_y = max(1, rows - panel_h - margin)
        log_y = max(1, panel_y - 1)
        wall_h = max(2, min(3, rows // 8))
        wall_y = margin
        ground_y = min(log_y - 1, wall_y + wall_h)
        ground_h = max(1, log_y - ground_y)
        panel_w = max(12, min((cols - margin * 3) // 2, 36))
        return {
            "wall": (margin, wall_y, max(1, cols - margin * 2), wall_h),
            "ground": (margin, ground_y, max(1, cols - margin * 2), ground_h),
            "log": (margin, log_y, max(1, cols - margin * 2), 1),
            "plate": (margin, panel_y, panel_w, panel_h),
            "commands": (max(0, cols - margin - panel_w), panel_y, panel_w, panel_h),
        }

    def _field(
        self, cols: int, rows: int, cell_w: int, cell_h: int
    ) -> dict[str, float]:
        """The floor in pixels, plus the one number the walls are built from.

        Everything that has to agree about the room reads this: the tiles, the
        shadows, the two side walls and their shear. ``inset`` is how far the
        floor's far edge is pulled in on each side, and ``edge`` is the direction
        of a side edge -- one point of floor going away from the viewer.
        """
        x0, y0, width, height = self._areas(cols, rows)["ground"]
        inset = max(1, round(width * TAPER))
        left, right = x0 * cell_w, (x0 + width) * cell_w
        top, bottom = y0 * cell_h, (y0 + height) * cell_h
        dx = inset * cell_w
        dy = bottom - top
        length = math.hypot(dx, dy) or 1.0
        return {
            "left": left,
            "right": right,
            "top": top,
            "bottom": bottom,
            "width_px": right - left,
            "height_px": dy,
            "inset_px": dx,
            "cell_w": cell_w,
            "cell_h": cell_h,
            #: The floor's own rectangle, in cells, for everything drawn in the
            #: grid rather than in pixels.
            "cells_x0": x0,
            "cells_y0": y0,
            "cells_w": width,
            "cells_h": height,
            #: One point of the left edge, going away from the viewer.
            "edge_x": dx / length,
            "edge_y": -dy / length,
            "edge_len": length,
        }

    def _stage(self, field: dict[str, float]) -> list[Staged]:
        """Who stands where: the monsters at three depths, the hero in front.

        One layout for the letters and the shadows under them, so a figure
        cannot be drawn in one place and stand in another. A figure stands on a
        *cell row* and at a *pixel* centre, because that is the two halves of
        the stage: the floor is the grid, and the letter is bigger than it.
        """
        cell_w = int(field["cell_w"])
        x0, y0 = int(field["cells_x0"]), int(field["cells_y0"])
        width, height = int(field["cells_w"]), int(field["cells_h"])
        centre = x0 + width // 2
        # A monster that keeps its size on a wide glass is a monster standing in
        # a cathedral: the room is sized in cells and the letters are sized in
        # pixels, so the two only stay in proportion if one of them follows.
        scale = 1.35 if width >= 120 else 1.0
        sizes = tuple(round(size * scale) for size in SIZES)
        hero_size = round(HERO_SIZE * scale)
        staged: list[Staged] = []
        # Rows, far to near: the left one hangs back, the right one is the
        # closest, which is what makes a row of three read as a row.
        places = (
            (centre - max(4, width // 4), y0 + max(1, height // 3)),
            (centre - max(1, width // 12), y0 + max(0, height // 6)),
            (centre + max(4, width // 4), y0 + max(1, height // 2)),
        )
        for index, ((name, glyph, colour), (cell_x, foot)) in enumerate(
            zip(_monsters(), places)
        ):
            size = sizes[index]
            staged.append(
                Staged(
                    name=name,
                    glyph=glyph,
                    colour=colour,
                    size=size,
                    cx=(cell_x + 1) * cell_w,
                    foot=foot,
                    cells=self._letter_cells(glyph, size, cell_w),
                    chosen=index == 0,
                )
            )

        from neverdeads_revenge.game.actors import NOXX

        staged.append(
            Staged(
                name=NOXX.name,
                glyph=NOXX.glyph,
                colour=NOXX.color,
                size=hero_size,
                cx=(centre + 1) * cell_w,
                foot=y0 + height - 1,
                cells=self._letter_cells(NOXX.glyph, hero_size, cell_w),
            )
        )
        return staged

    @staticmethod
    def _letter_cells(glyph: str, size: int, cell_w: int) -> int:
        """How many cells wide the pool of shadow under a letter has to be."""
        font = letter_font(size)
        advance = QFontMetrics(font.bold).horizontalAdvance(glyph)
        return max(2, round(advance / cell_w))

    # -- what is pasted -----------------------------------------------------
    def _paste_walls(self, painter: QPainter, field: dict[str, float]) -> None:
        """The room: the dungeon's ``#``, big, on three planes.

        One plane is the far wall, which faces the viewer and needs no shear at
        all. The other two are the side walls, and each is the *same* transform
        of the same glyph: the plane's horizontal axis is the floor's own edge
        and its vertical axis is the vertical, which is what a wall is. The
        hashes are all one size -- a parallel projection has no nearer and
        further, which is the whole of the isometric look.
        """
        size = self._hash_size(field)
        font = letter_font(size)
        painter.setFont(font.bold)
        advance = QFontMetrics(font.bold).horizontalAdvance("#")

        # -- the far wall, standing on the floor's far edge
        painter.setPen(parse_style(WALL_FAR).fg)
        span = field["width_px"] - field["inset_px"] * 2
        count = max(1, round(span / advance))
        start = field["left"] + field["inset_px"]
        for i in range(count):
            painter.drawText(int(start + i * advance), int(field["top"]), "#")

        # -- the two side walls, each sheared along the edge it stands on. The
        # masonry is smaller here on purpose: the same texture foreshortened
        # along the wall it runs down, which is what turning a corner does.
        side_size = max(12, int(size * 0.62))
        side_font = letter_font(side_size)
        painter.setFont(side_font.bold)
        advance = QFontMetrics(side_font.bold).horizontalAdvance("#")
        far_ink = parse_style(WALL_FAR).fg
        near_ink = parse_style(WALL_NEAR).fg
        for side in (0, 1):
            # Each wall recedes its own way: the left one goes away up and to
            # the right, the right one up and to the left, and both are the same
            # glyph under the same kind of transform.
            ux = field["edge_x"] if side == 0 else -field["edge_x"]
            uy = field["edge_y"]
            if side:
                ax0 = field["right"] - field["inset_px"]
                ax1 = field["right"]
            else:
                ax0 = field["left"] + field["inset_px"]
                ax1 = field["left"]
            ay0, ay1 = field["top"], field["bottom"]
            steps = max(1, round(field["edge_len"] / advance))
            for i in range(steps):
                t = (i + 0.5) / steps
                ax = ax0 + (ax1 - ax0) * t
                ay = ay0 + (ay1 - ay0) * t
                # The wall fades the way everything else does with distance:
                # grey30 at the near corner, grey19 up at the far one.
                painter.setPen(
                    QColor(
                        int(far_ink.red() + (near_ink.red() - far_ink.red()) * t),
                        int(far_ink.green() + (near_ink.green() - far_ink.green()) * t),
                        int(far_ink.blue() + (near_ink.blue() - far_ink.blue()) * t),
                    )
                )
                painter.save()
                painter.setTransform(
                    QTransform(ux, uy, 0.0, 1.0, ax, ay), combine=True
                )
                painter.drawText(0, 0, "#")
                painter.restore()

    @staticmethod
    def _hash_size(field: dict[str, float]) -> int:
        """How big one ``#`` is: as tall as the strip the wall stands in.

        The glyph is measured by its cap height rather than its point size, so
        the masonry fills the wall band on a 27-row window and on a 60-row one
        without a second number to keep in step.
        """
        band = field["cell_h"] * 3
        probe = 100
        cap = QFontMetrics(letter_font(probe).bold).capHeight() or probe
        return max(12, int(probe * band / cap))

    def _paste_letter(
        self, painter: QPainter, figure: Staged, cell_h: int
    ) -> None:
        """One letter, standing behind its own shadow, with a slab of thickness.

        The baseline is the *top* of the shadow row rather than its bottom: the
        pool of shadow is cast in front of whatever cast it, so the figure has
        to stand behind it.
        """
        font = letter_font(figure.size)
        painter.setFont(font.bold)
        metrics = QFontMetrics(font.bold)
        left = figure.cx - metrics.horizontalAdvance(figure.glyph) // 2
        baseline = figure.foot * cell_h - THICKNESS
        ink = parse_style(figure.colour).fg
        painter.setPen(ink.darker(320))
        painter.drawText(left, baseline + THICKNESS, figure.glyph)
        painter.setPen(ink)
        painter.drawText(left, baseline, figure.glyph)

    def _paste_arrow(self, painter: QPainter, figure: Staged, cell_h: int) -> None:
        """The blade over the chosen one -- the menus' marker, standing up.

        It hangs above the letter rather than beside it, because beside a letter
        is where the next monster is: an arrow that means "this one" has to point
        at the one it means.
        """
        font = letter_font(max(16, figure.size // 2))
        painter.setFont(font.bold)
        metrics = QFontMetrics(font.bold)
        ink = parse_style(figure.colour).fg
        cap = QFontMetrics(letter_font(figure.size).bold).capHeight()
        baseline = figure.foot * cell_h - THICKNESS - cap - metrics.height() // 3
        left = figure.cx - metrics.horizontalAdvance(ARROW) // 2
        painter.setPen(ink.darker(320))
        painter.drawText(left, baseline + THICKNESS, ARROW)
        painter.setPen(ink)
        painter.drawText(left, baseline, ARROW)

    # -- the ground ---------------------------------------------------------
    def _draw_ground(
        self, buffer: PatternBuffer, area: tuple[int, int, int, int]
    ) -> None:
        """Rows of filled tiles, staggered, narrowing and fading as they recede.

        Row ``i`` counts from the far edge down to the hero's feet. Its inset
        grows with the distance to the back, and its tone falls off on the way,
        so the same two colours in the same two glyphs turn into a floor that
        goes somewhere.
        """
        x0, y0, width, height = area
        if width < 8 or height < 3:
            return
        back_inset = max(1, round(width * TAPER))
        for i in range(height):
            depth = i / (height - 1)
            inset = round((1.0 - depth) * back_inset)
            # Half a tile of stagger per row: this is the whole of the
            # isometric illusion. Two cells are one tile, so the phase is a cell.
            phase = i % 2
            for x in range(inset, width - inset):
                alt = ((x + phase) // 2) % 2 == 0
                buffer.put(x0 + x, y0 + i, " ", Style(bg=self._tile(depth, alt)))

    @staticmethod
    def _tile(depth: float, alt: bool) -> QColor:
        """The floor's colour at ``depth``: 0 at the far edge, 1 at the hero."""
        near, far = (FLOOR_NEAR, FLOOR_FAR) if alt else (FLOOR_NEAR_ALT, FLOOR_FAR_ALT)
        return QColor(
            int(far.red() + (near.red() - far.red()) * depth),
            int(far.green() + (near.green() - far.green()) * depth),
            int(far.blue() + (near.blue() - far.blue()) * depth),
        )

    def _draw_shadows(
        self, buffer: PatternBuffer, area: tuple[int, int, int, int]
    ) -> None:
        """In front of each letter: the tiles it stands on, gone nearly black.

        A row *below* the feet rather than under them, because a figure stands
        behind its own shadow, and the ends fade instead of stopping so the pool
        reads as a shape rather than as a stripe.
        """
        font = buffer.font
        field = self._field(buffer.cols, buffer.rows, font.cell_w, font.cell_h)
        for figure in self._stage(field):
            span = figure.cells + 2
            left = round(figure.cx / font.cell_w) - span // 2
            for i in range(span):
                edge = i in (0, span - 1)
                tile = SHADOW_EDGE if edge else SHADOW
                buffer.put(left + i, figure.foot, " ", Style(bg=tile))

    # -- the log ------------------------------------------------------------
    def _draw_log(self, buffer: PatternBuffer, area: tuple[int, int, int, int]) -> None:
        """The line the fight speaks in.

        Placeholder prose for M0 -- nothing has happened yet -- but it is the
        real thing in the two ways that matter: the words are the dungeon log's
        words, and the number is the orange a damage line is drawn in there.
        """
        x, y, width, _ = area
        if width < 30:
            return
        buffer.text(x + 2, y, "►", parse_style("bright_white"))
        buffer.text(x + 4, y, "Noxx attacks the ghoul!", parse_style("bright_white"))
        buffer.text(x + 28, y, "20 damage", parse_style("orange1"))

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
