"""What the game looks like, drawn into a pattern buffer.

This is the port of the terminal screens' *content* -- the map, the sidebar, the
log, the two columns -- into cells. The layout is the same one ``app.tcss``
described, in cells: the map takes what is left, the sidebar is a fixed strip
down the right, and the bottom row is the log and the two columns.

Kept as plain functions taking a buffer and a state, with no widget and no
window anywhere, for one reason: this is the part worth testing, and a test can
build a buffer and read the cells back without a screen attached.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from neverdeads_revenge.game.actors import ActorKind
from neverdeads_revenge.game.draughts import draught_by_key
from neverdeads_revenge.game.npcs import NPC_COLOR, NPC_GLYPH
from neverdeads_revenge.game.state import GameState, LogKind
from neverdeads_revenge.world.generator import ESCAPE_DEPTH
from neverdeads_revenge.world.items import (
    AMULET_GLYPH,
    ARMOUR_GLYPH,
    CHEST_GLYPH,
    ITEMS,
    WEAPON_GLYPH,
)
from neverdeads_revenge.world.tiles import Tile

from .pattern import BLANK, PatternBuffer
from .chrome import ASH, rule
from ..game.difficulty import BASE_PACK_SLOTS
from ..game.shop import META_UPGRADES
from .theme import BACKGROUND, Colour, Style, parse_style

__all__ = [
    "SIDEBAR",
    "BOTTOM",
    "HUD_WIDTH",
    "Ink",
    "regions",
    "viewport",
    "screen_point",
    "draw_game",
    "log_text",
    "paste_log",
    "sidebar_text",
    "Slot",
    "MAX_PACK_SLOTS",
    "SLOT_SIZE",
    "SLOT_COLUMNS",
    "paste_sidebar",
    "draw_title",
    "hud_lines",
    "marks_names",
    "log_style",
]

#: The sidebar is a fixed strip, exactly as wide as the terminal's.
SIDEBAR = 34

#: How much larger the overworld's field is drawn when the zoom is on. A whole
#: number, because a character is a character: half a character is a smear.
FIELD_ZOOM = 2
#: The bottom row's height: the log, pasted smaller, and nothing else.
BOTTOM = 7
#: What the HUD wraps at, inside the sidebar's content box.
HUD_WIDTH = SIDEBAR - 4

#: LogKind -> style, the same mapping the terminal log used.
_KIND_STYLES: dict[LogKind, str] = {
    LogKind.PLAIN: "white",
    LogKind.COMBAT: "bright_white",
    LogKind.CRIT: "bold yellow",
    LogKind.DAMAGE: "orange1",
    LogKind.GOOD: "bold green",
    LogKind.BAD: "bold red",
    LogKind.SYSTEM: "bold cyan",
    LogKind.COIN: "bold yellow",
}

#: The frame a column is drawn in, and its headings. Matches ``marks.py``.
_STYLE_BY_GROUP = {
    "curses": "red",
    "gifts": "bright_green",
    "effects": "cyan",
    "draughts": "#c98fe0",
    "statuses": "yellow",
}

#: The glyph the sidebar lists each slot with. The map's own alphabet.
_SLOT_GLYPH = {
    "weapon": WEAPON_GLYPH,
    "armour": ARMOUR_GLYPH,
    "amulet": AMULET_GLYPH,
}
_SLOT_ORDER = ("weapon", "armour", "amulet")
_SHORT_NAME = 12
_BAR_CELLS = 12


# -- layout -------------------------------------------------------------------
def regions(cols: int, rows: int) -> dict[str, tuple[int, int, int, int]]:
    """The rectangles, in cells: map, sidebar, and the log strip under the map.

    The sidebar runs the full height on the right and owns everything on it --
    the stats, a rule, the curses, gifts and effects, another rule, and the
    legend. The bottom strip under the map is the log's alone; the columns used
    to share it and moved into the sidebar, which is why their width constants
    are gone.
    """
    map_w = max(1, cols - SIDEBAR)
    map_h = max(1, rows - BOTTOM)
    bottom_y = map_h
    return {
        "map": (0, 0, map_w, map_h),
        "sidebar": (map_w, 0, SIDEBAR, rows),
        "bottom": (0, bottom_y, map_w, BOTTOM),
        "log": (0, bottom_y, map_w, BOTTOM),
    }


# -- the map ------------------------------------------------------------------
def viewport(state: GameState, map_w: int, map_h: int) -> tuple[int, int, int, int]:
    """The dungeon window the map shows: ``(left, top, view_w, view_h)``.

    One function for it and not three, because the map draws from it and the
    effects have to land on what the map drew.
    """
    dungeon = state.dungeon_map
    view_w = min(map_w, dungeon.width)
    view_h = min(map_h, dungeon.height)
    left = max(0, min(state.player.position[0] - view_w // 2, dungeon.width - view_w))
    top = max(0, min(state.player.position[1] - view_h // 2, dungeon.height - view_h))
    return left, top, view_w, view_h


def screen_point(
    state: GameState,
    position,
    cols: int,
    rows: int,
    cell_w: int,
    cell_h: int,
    zoom: int = 1,
) -> tuple[float, float] | None:
    """The centre of a dungeon square, as buffer pixels -- or ``None``.

    The buffer is the *camera*, not the dungeon: a square at `(38, 9)` is
    somewhere else on the screen unless the camera happens to say so. Every
    moving pixel needs this translation, and everything that skipped it drew in
    the wrong place (which is exactly what the blood did).

    ``zoom`` is the field's own scale: the map is drawn into a grid ``zoom`` times
    smaller and blown up on the way to the frame, so a square is ``zoom`` cells
    wide, and its camera is the small grid's camera and not the frame's.
    """
    areas = regions(cols, rows)
    map_w, map_h = areas["map"][2], areas["map"][3]
    left, top, view_w, view_h = viewport(state, map_w // zoom, map_h // zoom)
    x, y = position
    if not (left <= x < left + view_w and top <= y < top + view_h):
        return None
    return (
        (x - left + 0.5) * cell_w * zoom,
        (y - top + 0.5) * cell_h * zoom,
    )


def draw_game(buffer: PatternBuffer, state: GameState, zoom: bool = False) -> None:
    """The whole play screen: map, sidebar, and the bottom strip.

    The log is *not* drawn here: it is a smaller face than the rest of the
    frame, so it is pasted on afterwards by :func:`paste_log`, straight onto the
    rendered image. What this leaves behind is the panel the log sits on.

    ``zoom`` leaves the field out of the cells entirely: the front end paints it
    into a grid half the size and doubles it on the way to the frame, so the
    panels keep their own size and the room grows. A zoomed field is a picture,
    not a grid, and only a painter can make one.
    """
    buffer.clear()
    areas = regions(buffer.cols, buffer.rows)
    if not zoom:
        _draw_map(buffer, state, areas["map"])
    _draw_sidebar(buffer, state, areas["sidebar"])


def draw_field(buffer: PatternBuffer, state: GameState, area) -> None:
    """The map alone, into a grid of the caller's own -- the zoom's small camera."""
    _draw_map(buffer, state, area)


def _draw_map(buffer, state, area) -> None:
    x0, y0, width, height = area
    dungeon = state.dungeon_map
    left, top, view_w, view_h = viewport(state, width, height)
    # THE FROZEN FORTRESS. While it stands the whole floor lies under its own
    # light: every cell gets the cold white behind it, so the room reads as
    # the thing it has become. The glyphs keep their colours; the background
    # is what changes.
    frosted = state.fortress is not None
    # THE RAVAGING FIRE. Its own weather and only that: the ground goes red and
    # the walls go darker under it, and every glyph keeps the colour it had --
    # because unlike the frost, nothing here is lying on the floor to be read
    # against it. What the fire is *for* is not on this screen at all: it is in
    # the fights, and in the counting of them.
    burning = state.ravaging
    # THE CARRION TONGUE paints the floor's dead rather than marking it: a
    # glyph loses to whatever else is on the square -- and a kill almost always
    # leaves coin there, so the stain was invisible exactly where it mattered
    # most. The *background* is the one channel loot does not use.
    tongue = state.has_draught("carrion_tongue")
    # Who stands where, once: asking the state per square is a scan per square.
    standing = state.standing()

    for y in range(view_h):
        for x in range(view_w):
            position = (left + x, top + y)
            glyph, style = _cell_content(position, state, standing)
            if position in state.hits:
                # A square something struck this turn flashes in reverse --
                # parsed onto the cell's own style, so the wall stays a wall.
                style = parse_style("reverse", style)
            if tongue and position in state.death_squares and style.bg is None:
                style = Style(
                    fg=style.fg,
                    bg=BLOOD_TINT,
                    bold=style.bold,
                    dim=style.dim,
                    reverse=style.reverse,
                    italic=style.italic,
                )
            if burning and style.bg is None:
                fg = style.fg
                actor = standing.get(position)
                if dungeon.display_tile(position) is Tile.WALL or (
                    actor is not None and actor.kind is ActorKind.ENEMY
                ):
                    # THE FLOOR BURNS. The walls and the things walking on them
                    # are the fire's own colour -- the map's whole alphabet for
                    # "this floor is alight" -- while the floor, the loot and the
                    # hero keep theirs: it is the *dungeon* that is on fire, and
                    # the player still has to be able to find himself in it.
                    fg = EMBER_INK
                style = Style(
                    fg=fg,
                    bg=EMBER,
                    bold=style.bold,
                    dim=style.dim,
                    reverse=style.reverse,
                    italic=style.italic,
                )
            if frosted and style.bg is None:
                fg = style.fg
                if dungeon.display_tile(position) is Tile.WALL:
                    # The walls go darker with the cold on them. The frost is
                    # light ground, and a light wall on light ground would be
                    # the one thing the fortress's own weather erases.
                    fg = parse_style("grey15").fg
                elif (
                    standing.get(position) is not None
                    or dungeon.item_at(position) is not None
                ):
                    # Everything alive and everything lying there goes black
                    # in the fortress's weather: a green ghoul on light ground
                    # is a smudge, and the room is meant to read as a room.
                    fg = parse_style("black").fg
                style = Style(
                    fg=fg,
                    bg=FROST,
                    bold=style.bold,
                    dim=style.dim,
                    reverse=style.reverse,
                    italic=style.italic,
                )
            buffer.put(x0 + x, y0 + y, glyph, style)


def _cell_content(position, state: GameState, standing=None) -> tuple[str, Style]:
    """One map cell: an actor, else loot, else the glass, else terrain.

    The port of ``map_view._cell_content``: same order, same rules, including
    WHAT THE DARK KNOWS seeing through walls and THE HUNGRY ROAD's red comma.

    ``standing`` is :meth:`GameState.standing` for this frame -- who is where, in
    one pass -- because a subscription to it per square is the whole difference
    between a floor with four monsters and a floor with ten. A caller with one
    square in its hand may leave it out and pay for that one pass.
    """
    if standing is None:
        standing = state.standing()
    dungeon = state.dungeon_map
    visible = dungeon.is_visible(position)

    actor = standing.get(position)
    if actor is not None:
        if visible:
            return actor.glyph, parse_style(f"bold {actor.color}")
        if actor.kind.name == "ENEMY" and state.has_gift("dark_knows"):
            return actor.glyph, parse_style(actor.color)

    item = dungeon.item_at(position)
    if item is not None and visible:
        return item.glyph, parse_style(f"bold {item.color}")

    if visible and position in state.trail:
        return ",", parse_style("red")
    if (
        visible
        and state.has_draught("carrion_tongue")
        and position in state.death_squares
    ):
        # THE CARRION TONGUE shows the floor's dead: a dim blood spot where
        # something stopped moving. A middle dot, because the bright red comma
        # is the hungry road's trail and a floor with two red commas meaning
        # two things is a floor that lies. Dim, because a stain lies *on* the
        # ground rather than standing on it -- and only while the tongue is
        # working, since it is the tongue's sense of the floor, not decoration.
        return "·", parse_style("dim #8b1a1a")

    tile = dungeon.display_tile(position)
    if visible:
        return tile.glyph, parse_style(tile.color)
    if (
        dungeon.is_explored(position) or state.void_sight
    ) and (
        tile.blocks_movement
        or tile in (Tile.STAIRS_DOWN, Tile.RIFT, Tile.SPRING)
    ):
        return tile.glyph, parse_style("grey30")
    return " ", BLANK


# -- the sidebar --------------------------------------------------------------
def _draw_sidebar(buffer, state, area) -> None:
    """The HUD in the big face, then a rule, and nothing else.

    Everything under that rule belongs to the small face -- the glance groups
    and the legend -- which is pasted straight onto the frame afterwards
    (:func:`paste_sidebar`). The old blank row between stats and rule is gone
    too: a rule drawn directly under the last stat stands closer than a
    paragraph gap, and the panel was half air.
    """
    x0, y0, width, height = area
    y = y0
    for text, style in hud_lines(state):
        buffer.text(x0 + 1, y, text[: width - 2], parse_style(style))
        y += 1
    rule(buffer, x0 + 1, y, width - 2, ASH)


def small_face_top(state) -> int:
    """The sidebar row the small face starts on: right under the rule."""
    return len(hud_lines(state)) + 1


#: One line of the small face: what it says, where it goes, and in which of the
#: palette's colours. A *shape* and not a drawing, because two front ends draw
#: these rows and only one of them has QPainter -- the same split the verdict
#: panel and the roster's portraits already keep.
@dataclass(frozen=True)
class Ink:
    text: str
    x: int
    y: int
    colour: str


#: How many things the pack could ever hold: the two everybody starts with and
#: every slot the shop's pack upgrade sells. The sidebar shows *all* of them, so
#: the ones not bought yet are a promise rather than a surprise.
MAX_PACK_SLOTS = BASE_PACK_SLOTS + META_UPGRADES["pack"].max_stacks

#: A square of the pack: a place, not a drawing. The painter puts the bottle in
#: it -- an item's picture is a fact about the sheet, and the sidebar is a fact
#: about the run.
@dataclass(frozen=True)
class Slot:
    """One square of the pack, as a place on the frame."""

    x: int
    y: int
    size: int
    #: The draught's item key, or ``None`` for an empty square.
    key: str | None = None
    #: A slot the shop has not sold yet: a grey square with an X in it.
    locked: bool = False


#: The pack's squares: how big, how far apart, and how many to a row. Seven to a
#: row -- one per slot the game can ever sell -- so the belt never changes shape
#: as the pack grows, and so it fits under the legend at the smallest window
#: without taking the legend with it.
SLOT_SIZE = 44
SLOT_GAP = 2
SLOT_COLUMNS = 7
#: Air between the legend and the squares. None on purpose: at the smallest
#: window the legend and the pack are neighbours, and a line of air here is a
#: line the groups above would have to give up.
SLOT_LEAD = 0


def sidebar_text(
    state,
    cols: int,
    rows: int,
    cell_w: int,
    cell_h: int,
    small_cell_w: int,
    small_cell_h: int,
    now: float | None = None,
    pad: bool = False,
) -> tuple[list[Ink], tuple[int, int, int] | None, list[Slot]]:
    """Everything under the HUD's rule, as rows to draw.

    The glance groups first -- lower case now, they were shouting in a panel meant
    for a glance, and a small face has no room for headlines anyway -- then the
    void's line, then a thin rule, then the pointer to the legend, and the pack's
    squares at the foot. Measured from the same top row the map hands over, so the
    two cannot drift apart, and measured in the *caller's* cell: both front ends
    lay this out in their own small face, and how wide a small cell is is the
    face's business. ``now`` drives the ready state's breath; it defaults so a
    caller with no clock still gets a prompt drawn.

    The pack is laid out *first* and from the bottom: it is the one part of the
    panel a player checks mid-fight, so the groups above give way to it rather
    than the other way round.
    """
    areas = regions(cols, rows)
    sx, sy, sw, _sh = areas["sidebar"]

    out: list[Ink] = []
    top = (sy + small_face_top(state)) * cell_h
    left = sx * cell_w + small_cell_w
    text_x = left + small_cell_w * 2  # one cell for a glyph, one for air under it
    text_w = (sx + sw) * cell_w - text_x - small_cell_w
    chars = max(1, text_w // small_cell_w)
    bottom = rows * cell_h

    # The pack, from the foot up, before anything above it is allowed to grow.
    slot_rows = (MAX_PACK_SLOTS + SLOT_COLUMNS - 1) // SLOT_COLUMNS
    slots_height = slot_rows * SLOT_SIZE + (slot_rows - 1) * SLOT_GAP
    slots_top = bottom - slots_height
    slots: list[Slot] = []
    for index in range(MAX_PACK_SLOTS):
        row, column = divmod(index, SLOT_COLUMNS)
        slot_x = left + column * (SLOT_SIZE + SLOT_GAP)
        slot_y = slots_top + row * (SLOT_SIZE + SLOT_GAP)
        if index < state.pack_capacity:
            item = state.inventory[index] if index < len(state.inventory) else None
            slots.append(Slot(slot_x, slot_y, SLOT_SIZE, item.item_id if item else None))
        else:
            slots.append(Slot(slot_x, slot_y, SLOT_SIZE, None, locked=True))
    # The two ways into the pack, right above the belt: the quick draught and
    # the pack itself. The words are the keyboard's and the pad's are the same
    # sentence with the buttons it actually has.
    quick, bag = ("Y", "B") if pad else ("Q", "I")
    hints = (
        (f"Press {quick} for fast healing.", "grey35"),
        (f"Press {bag} to open the pack.", "grey35"),
    )
    hints_top = slots_top - (len(hints) * small_cell_h + small_cell_h // 2)
    for number, (text, colour) in enumerate(hints):
        out.append(Ink(text[:chars], left, hints_top + number * small_cell_h, colour))
    # And the rows above stop short of them.
    bottom = hints_top - small_cell_h // 2

    y = top
    for kind in ("curses", "gifts", "effects", "draughts", "statuses"):
        if y + small_cell_h > bottom:
            break
        out.append(Ink(kind, left, y, "grey30"))
        y += small_cell_h
        names = marks_names(state, kind)
        if names:
            for name in names:
                if y + small_cell_h > bottom:
                    break
                out.append(Ink(name[:chars], text_x, y, _STYLE_BY_GROUP[kind]))
                y += small_cell_h
        else:
            out.append(Ink("-", text_x, y, "grey30"))
            y += small_cell_h

    # The void's own line, belonging to the group of rules the sidebar keeps: grey
    # until the level, dark petrol and breathing while it can be given into, grey
    # again once the floor has had it. The pulse is luminance on purpose -- the
    # shader's bloom is already a reading of brightness, so the glow needs no new
    # pass.
    prompt = _void_prompt(state, time.time() if now is None else now)
    if prompt is not None:
        text, colour = prompt
        if y + small_cell_h <= bottom:
            out.append(Ink(text[:chars], text_x, y, colour.name()))
            y += small_cell_h + small_cell_h // 4
        # And the price, in the smallest voice the sidebar owns: the ask is paid
        # in kill points, and a price nobody is told is not a choice.
        price = (
            "the price is paid: 5 kill points"
            if state.sacrificed
            else (
                "X  sacrifice your kill points for power"
                if pad
                else "f  sacrifice your kill points for power"
            )
        )
        if y + small_cell_h <= bottom:
            out.append(Ink(price[:chars], text_x, y, "grey35"))
            y += small_cell_h + small_cell_h // 4
    y += small_cell_h // 3  # air between the groups and the legend
    rule = None
    if y < bottom:
        # The thin rule between the run and the pointer: handed over as its two
        # ends, because a line is the one thing here that is not a row of text.
        rule = (sx * cell_w + small_cell_w, (sx + sw) * cell_w - small_cell_w, y)
        y += (small_cell_h * 3) // 2
    # The legend lives in its own menu now (`l`). The sidebar's job is the run in
    # progress, and a reference that never changes was spending the best rows on
    # every turn -- so what is left here is the pointer to it.
    if y + small_cell_h <= bottom:
        out.append(
            Ink(
                "RB legend   R3 reference" if pad else "l legend   ? reference",
                left,
                y,
                "grey30",
            )
        )
    return out, rule, slots


def log_text(
    state,
    cols: int,
    rows: int,
    cell_w: int,
    cell_h: int,
    small_cell_w: int,
    small_cell_h: int,
) -> tuple[tuple[int, int, int, int], list[Ink]]:
    """The combat log as a panel and the rows to draw in it.

    The log gets a smaller face than the rest of the frame, and that is the one
    place a mixed size pays for itself: a battle is words, and words a player is
    reading while deciding what to press next are worth more of the frame than the
    ground they are printed on. The panel is handed over with the rows because it
    is drawn solid -- the frame underneath it is nothing at all now that the cells
    are clear -- and because where it is is not the painter's guess.
    """
    areas = regions(cols, rows)
    x0, y0, width, height = areas["log"]
    # Aligned with the columns beside it: their headings sit one row into the
    # bottom strip, so the log starts there too and shares its floor line with
    # them.
    rect = (x0 * cell_w, (y0 + 1) * cell_h, width * cell_w, (height - 1) * cell_h)
    left = rect[0] + small_cell_w * 2  # still clear of the corner
    text_w = rect[0] + rect[2] - left - small_cell_w
    chars = max(1, text_w // small_cell_w)
    lines_fit = max(1, rect[3] // small_cell_h)
    visible = state.log[-lines_fit:]
    y = rect[1] + rect[3] - small_cell_h * len(visible) + 1
    out: list[Ink] = []
    for entry in visible:
        out.append(Ink(entry.text[:chars], left, y, log_style(entry.kind)))
        y += small_cell_h
    return rect, out


def _legend_colour(glyph: str) -> str:
    """The colour a legend row's glyph is drawn in.

    The same colour the *map* draws the same glyph in, and one walker for each
    family the map has: the people, the monsters, then the ground -- a spring
    and its water colour, not a grey -- and only then the things lying there.
    Ask an item last, because several things share a glyph's word and the map's
    answer is the one a legend row is promising.
    """
    from neverdeads_revenge.game.actors import ENEMIES
    from neverdeads_revenge.world.items import CHEST_COLOR, COIN_COLOR, COIN_GLYPH
    from neverdeads_revenge.world.tiles import Tile

    if glyph == NPC_GLYPH:
        return NPC_COLOR
    if glyph == COIN_GLYPH:
        # A coin is not in the item table: it is made, not rolled, and its
        # colour is a constant the map has been using all along.
        return COIN_COLOR
    if glyph == CHEST_GLYPH:
        return CHEST_COLOR
    for template in ENEMIES.values():
        if template.glyph == glyph:
            return template.color
    for tile in Tile:
        if tile.glyph == glyph:
            # Terrain first for the spring and the stairs, which the item table
            # never hears about.
            return tile.color
    for item in ITEMS.values():
        if item.glyph == glyph:
            return item.color
    return "grey70"


def hud_lines(state: GameState) -> list[tuple[str, str]]:
    """The HUD, as ``(text, style)`` lines. The port of ``Hud.redraw``.

    Returned as lines rather than drawn, so a test can read the sidebar without
    a screen -- the same reason ``legend_rows`` is a function in the engine.
    """
    player = state.player
    lines: list[tuple[str, str]] = []

    lines.append((f"{player.glyph} {player.name}", f"bold {player.color}"))
    lines.append((state.hero.title, "dim"))

    ratio = player.hp / player.max_hp if player.max_hp else 0.0
    filled = max(0, min(_BAR_CELLS, round(ratio * _BAR_CELLS)))
    bar_colour = "green" if ratio > 0.5 else "yellow" if ratio > 0.25 else "red"
    lines.append(
        (
            "HP  " + "█" * filled + "░" * (_BAR_CELLS - filled) + f"  {player.hp}/{player.max_hp}",
            bar_colour,
        )
    )

    low, high = player.damage_range
    lines.append((f"DMG {low}-{high}  CRT {player.crit_chance:.0%}", "bold white"))

    speed = f"SPD {player.speed:.2f}"
    if player.speed_bonus:
        speed += f"+{player.speed_bonus:.1f}"
    lines.append((f"{speed}  ARM {player.armor}  EVA {player.evasion}", "bold white"))

    if state.revenge_stacks:
        # Name the grant by its own name, not by the system's: BLACK TIDE means
        # a different thing to play around than FROZEN FORTRESS, and neither is
        # just "revenge". And the ceiling with it, because the ceiling is
        # invisible otherwise.
        lines.append(
            (
                f"{player.trait.title} x{state.revenge_stacks}/{player.trait.cap}  "
                f"{player.trait.describe(state.revenge_stacks)}",
                "bold green",
            )
        )

    gear = []
    for slot in ("weapon", "armour"):
        item = player.equipment.get(slot)
        name = item.name.split()[-1][:_SHORT_NAME] if item else "—"
        gear.append(f"{_SLOT_GLYPH[slot]} {name}")
    lines.append(("  ".join(gear), "bold white"))
    amulet = player.equipment.get("amulet")
    amulet_name = amulet.name.split()[-1][:_SHORT_NAME] if amulet else "—"
    lines.append((f"{_SLOT_GLYPH['amulet']} {amulet_name}", "bold white"))

    score = f"Floor {state.depth}/{ESCAPE_DEPTH}  Score {state.score}"
    if state.fame:
        score += f"  x{state.score_multiplier:.2f}"
    lines.append((score, "bold cyan"))

    if state.rewind_ready:
        lines.append(("r take the hour back", "bold green"))
    if state.at_the_rift:
        lines.append(("The rift hums.", "bold bright_cyan"))

    # Gold alone, now: the pack is a belt of squares at the foot of the panel,
    # and a counter beside the purse was saying the same thing twice -- once
    # correctly and once as a number nobody counted.
    lines.append((f"Gold {state.gold}", "bold yellow"))

    lines.append(
        (
            # "+3" is the three kills the *next* level still wants. It reads as a
            # footnote to the level rather than a fourth number in a row, which
            # is what the line has room for.
            f"Kills {state.kills}  Lv {state.level} (+{state.kills_to_level})"
            f"  Turns {state.total_turns}",
            "bold green",
        )
    )
    return lines


# -- the bottom row -----------------------------------------------------------
def log_style(kind: LogKind) -> str:
    """The style a log line is drawn in, by what kind of line it is."""
    return _KIND_STYLES.get(kind, "white")




#: Each hero's promise, as the sidebar says it: the name, and the colour it
#: is said in. Noxx's petrol, Yeti's ice, Walkyrion's gold -- the colour of
#: the thing the ask actually summons.
ULTIMATE_PROMPTS: dict[str, tuple[str, tuple[int, int, int]]] = {
    # Noxx's own: the friends he calls are the ones the room will remember.
    "noxx": ("friends like these", (14, 111, 111)),
    "yeti": ("build the Frozen Fortress", (159, 227, 239)),
    "walkyrion": ("shatter the golden bell", (212, 175, 55)),
    "inferno": ("set the floor alight", (192, 32, 42)),
}

#: The blood the floor keeps while the carrion tongue works. Dark, so a coin
#: or a glyph on top of it still reads, and so it reads as a soaked square
#: rather than as a second kind of floor.
BLOOD_TINT = Colour(0x3A, 0x0F, 0x12)

#: The cold the floor goes while the Frozen Fortress stands. A cold grey-blue
#: rather than paper white: bright enough to be the fortress's own weather,
#: dark enough that the grey of a remembered wall still reads against it.
FROST = Colour(0xBF, 0xCE, 0xD2)

#: And the red it goes while it burns. *Dark* red rather than a bright one, for
#: the opposite reason to the frost being pale: the frost had to keep dark
#: glyphs legible on it, and this has to keep every glyph in the dungeon legible,
#: because the things that are not burning keep the colours they had. A bright
#: red would make the map a warning sign with writing on it.
EMBER = Colour(0x4A, 0x12, 0x0C)

#: And what the fire itself is drawn in: the walls and everything walking on
#: them. Amber rather than the background's red, because the two are the fire and
#: what it has caught -- an ember ground with ember writing is a frame, and the
#: *dungeon* is what should look like it is burning.
EMBER_INK = Colour(0xFF, 0xB0, 0x2E)


def ultimate_ready(state: GameState) -> bool:
    """Whether the hero's ask is live: available, off cooldown, and the level
    is there. Read by the prompt and by the app's breathing tick, so the pulse
    and the promise cannot disagree about what state they are in."""
    return (
        state.ultimate_available
        and state.atritas is None
        and state.fortress is None
        and state.level >= state.ultimate_level
    )


def _void_prompt(state: GameState, now: float) -> tuple[str, Colour] | None:
    """The sidebar's promise of the dark, in the state it is in.

    One line per hero, in that hero's colour: grey before the level, breathing
    in the colour once it is live, grey again once the floor has had its ask.
    While the fortress stands the line turns into its health, because a wall
    with hit points is a thing the player needs a number for.
    """
    entry = ULTIMATE_PROMPTS.get(state.hero.key)
    if entry is None:
        return None
    name, base = entry

    if state.fortress is not None:
        fortress = state.fortress
        return (
            f"the fortress stands {fortress.stats.hp}/{fortress.stats.max_hp}",
            Colour(*base),
        )
    if state.ravaging:
        # The receipt: the fire does not run out and cannot be walked away from,
        # so the line says what is still true of the floor.
        return ("the floor burns", Colour(*base))
    if state.atritas is not None or not state.ultimate_available:
        # Given: grey until the next floor says otherwise. The dead line is
        # the receipt, not an invitation.
        return name, parse_style("grey35").fg
    if state.level < state.ultimate_level:
        return (
            f"{name} (lvl {state.ultimate_level})",
            parse_style("grey30").fg,
        )
    # Ready: the hero's own colour, breathing -- and not a whisper of a
    # breath: the promise is supposed to catch the eye from across the log.
    # The pulse rises past the base colour on purpose; the bloom is a reading
    # of brightness and that overshoot is what makes the line visibly alive.
    breathing = 0.35 + 0.95 * (0.5 + 0.5 * math.sin(now * 2.0 * math.pi / 1.0))
    lit = tuple(
        max(0, min(255, int(round(channel * breathing)))) for channel in base
    )
    return f"{name} (f)", Colour(*lit)


def marks_names(state: GameState, kind: str) -> list[str]:
    """The names in one column group, in the order the sheet prints them."""
    from neverdeads_revenge.game.gifts import gift_by_key
    from neverdeads_revenge.game.shop import WILD_OFFERS
    from neverdeads_revenge.game.statuses import status_by_key

    if kind == "curses":
        return [curse.name for curse in state.curses]
    if kind == "gifts":
        names = []
        for key in sorted(state.gifts):
            gift = gift_by_key(key)
            if gift is not None:
                names.append(gift.name)
        return names
    if kind == "draughts":
        # The strange bottles, while they work. They count against the pack
        # and they change the floor, so they belong beside the gifts and the
        # effects rather than only in the pack screen.
        names = []
        for key in sorted(state.floor_draughts):
            draught = draught_by_key(key)
            if draught is not None:
                names.append(draught.name)
        return names
    if kind == "statuses":
        names = []
        for key, turns in state.player.statuses.items():
            status = status_by_key(key)
            if status is not None:
                names.append(f"{status.name} {turns}")
        return names
    if kind == "effects":
        names = []
        for key in sorted(state.wilds):
            offer = WILD_OFFERS.get(key)
            if offer is not None:
                names.append(offer.name)
        if state.rewind_ready:
            names.append("the borrowed hour")
        if state.shrouded:
            names.append("the borrowed face")
        if state.momentum:
            names.append(f"momentum {state.momentum}")
        if state.blood_debt:
            names.append(f"a debt of {state.blood_debt}")
        if state.has_gift("last_breath") and state.cornered:
            names.append("the last breath")
        if state.salt_ward:
            names.append("the salt circle")
        return names
    return []


# -- the title ----------------------------------------------------------------
def draw_title(buffer: PatternBuffer, subtitle: str, hint: str) -> None:
    """The title screen: the name in the block font, and a line under it."""
    from .blocks import render_word

    buffer.clear()
    art = render_word("NEVERDEAD'S")
    art += render_word("REVENGE")
    top = max(1, (buffer.rows - (len(art) * 2 + 6)) // 2)
    y = top
    for line in art:
        x = max(0, (buffer.cols - len(line)) // 2)
        buffer.text(x, y, line, parse_style("bold #a855f7"))
        y += 1
    y += 2
    buffer.text(max(0, (buffer.cols - len(subtitle)) // 2), y, subtitle, parse_style("grey70"))
    y += 2
    buffer.text(max(0, (buffer.cols - len(hint)) // 2), y, hint, parse_style("white"))
