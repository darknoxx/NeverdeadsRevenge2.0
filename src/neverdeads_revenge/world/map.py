"""The dungeon grid and the things scattered across it."""

from __future__ import annotations

from dataclasses import dataclass, field

from neverdeads_revenge.core.direction import CARDINALS, Direction, Pos

from .modifiers import Modifiers
from .tiles import Tile

__all__ = ["GroundItem", "DungeonMap", "Modifiers"]


@dataclass(slots=True)
class GroundItem:
    """An item lying on the floor, or worn by somebody.

    ``heal`` is the health a drink restores. ``modifiers`` is what wearing it
    changes. A thing is one or the other: nothing is both a draught and a coat.
    """

    item_id: str
    name: str
    glyph: str = "*"
    color: str = "yellow"
    heal: int = 0
    #: What kind of thing it is: ``draught``, ``weapon``, ``armour`` or
    #: ``chest``. Used to group the legend, which has room for one row per kind
    #: and not per item.
    kind: str = "draught"
    #: Which equipment slot it fills, or ``None`` for something you drink.
    slot: str | None = None
    #: What wearing it changes. Frozen, so one shared empty instance is fine.
    modifiers: Modifiers = Modifiers()
    #: A chest's curse, by key. Only ``game/`` knows what the key means, which
    #: is why this is a string and not a :class:`Curse`.
    curse: str | None = None
    #: What is inside a chest. ``None`` for everything else.
    contents: GroundItem | None = None
    #: A gift a chest holds *instead* of contents, by key. Like ``curse``, a
    #: string: the world places the bargain and ``game/`` knows what it means.
    gift: str | None = None
    #: Which page of the chronicle this is, for a page lying on the floor. The
    #: number is the whole of what a page *is*: it is what decides the slot it
    #: goes into, and a page without one cannot go back into the book.
    page: int | None = None
    #: Coins in a pile. Zero for everything that is not a coin.
    gold: int = 0
    #: Which amulet ability this grants, by key. Like ``curse``, a string: the
    #: rule belongs to ``game/``, and ``world/`` only carries the name of it.
    amulet: str | None = None
    #: Statuses a blow from this weapon leaves running, by key. Like ``curse``
    #: and ``amulet``, names rather than rules: the table is in
    #: :mod:`game.statuses` and the world has no business knowing what a bleed
    #: does.
    inflicts: tuple[str, ...] = ()
    #: Damage dealt back to whatever lands a blow on the wearer. Only
    #: coats have it, and it is the one property that acts when the player
    #: is *hit* rather than when they swing.
    thorns: int = 0


@dataclass(slots=True)
class DungeonMap:
    """A rectangular grid of :class:`Tile`.

    Tiles are stored as a flat list of ints (the enum values) rather than a list
    of enums: it is smaller, compares fast, and FOV touches every cell.
    """

    width: int
    height: int
    depth: int = 1
    tiles: list[int] = field(default_factory=list)
    items: dict[Pos, GroundItem] = field(default_factory=dict)
    explored: set[Pos] = field(default_factory=set)
    visible: set[Pos] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.tiles:
            self.tiles = [Tile.VOID.value] * (self.width * self.height)
        expected = self.width * self.height
        if len(self.tiles) != expected:
            raise ValueError(f"expected {expected} tiles, got {len(self.tiles)}")

    # -- bounds -------------------------------------------------------------
    @property
    def bounds(self) -> tuple[Pos, Pos]:
        """Inclusive ``(top_left, bottom_right)``."""
        return (0, 0), (self.width - 1, self.height - 1)

    def in_bounds(self, pos: Pos) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def _index(self, pos: Pos) -> int:
        return pos[1] * self.width + pos[0]

    # -- tiles --------------------------------------------------------------
    def tile_at(self, pos: Pos) -> Tile:
        if not self.in_bounds(pos):
            return Tile.VOID
        return Tile(self.tiles[self._index(pos)])

    def set_tile(self, pos: Pos, tile: Tile) -> None:
        if self.in_bounds(pos):
            self.tiles[self._index(pos)] = tile.value

    # -- movement -----------------------------------------------------------
    def is_walkable(self, pos: Pos) -> bool:
        """True if an actor could stand here."""
        if not self.in_bounds(pos):
            return False
        return self.tile_at(pos).blocks_movement is False

    def is_opaque(self, pos: Pos) -> bool:
        """True if this tile stops line of sight."""
        if not self.in_bounds(pos):
            return True
        return self.tile_at(pos).blocks_sight

    def neighbours(self, pos: Pos) -> list[Pos]:
        """The four orthogonal neighbours that are in bounds."""
        return [n for n in (d.step(pos) for d in CARDINALS) if self.in_bounds(n)]

    def neighbours8(self, pos: Pos) -> list[Pos]:
        """All eight neighbours that are in bounds."""
        return [n for n in (d.step(pos) for d in Direction if d is not Direction.NONE) if self.in_bounds(n)]

    def display_tile(self, pos: Pos) -> Tile:
        """What to *draw* at ``pos``, which is not always what is there.

        Rock that touches a walkable cell is drawn as wall. The generator carves
        rooms out of solid stone and gives only some of a room's boundary a wall
        tile; the rest is floor against void, which is a room with no wall on
        one side. Nothing about the *rules* changes -- void is still not
        walkable and still not visible until it has been seen -- but a room the
        player can see the edge of should look like a room.

        It lives here rather than in either screen because both of them draw the
        same dungeon and neither of them should be the one that knows.
        """
        tile = self.tile_at(pos)
        if tile is Tile.VOID and self._touches_walkable(pos):
            return Tile.WALL
        return tile

    def _touches_walkable(self, pos: Pos) -> bool:
        """Whether anything walkable is within one cell, diagonals included.

        Diagonals matter: a room's corner is only diagonal to the floor inside
        it, and a boundary with four pinholes at its corners is a boundary that
        reads as broken.
        """
        return any(self.is_walkable(n) for n in self.neighbours8(pos))

    # -- perception ---------------------------------------------------------
    def is_visible(self, pos: Pos) -> bool:
        return pos in self.visible

    def is_explored(self, pos: Pos) -> bool:
        return pos in self.explored

    def clear_visibility(self) -> None:
        self.visible.clear()

    # -- items --------------------------------------------------------------
    def item_at(self, pos: Pos) -> GroundItem | None:
        return self.items.get(pos)

    def add_item(self, pos: Pos, item: GroundItem) -> None:
        self.items[pos] = item

    def remove_item(self, pos: Pos) -> GroundItem | None:
        return self.items.pop(pos, None)

    # -- queries ------------------------------------------------------------
    def walkable_positions(self) -> list[Pos]:
        """Every position an actor could stand on."""
        return [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if self.is_walkable((x, y))
        ]

    def floor_positions(self) -> list[Pos]:
        """Walkable positions that are plain floor, excluding stairs and doors."""
        return [
            pos
            for pos in self.walkable_positions()
            if self.tile_at(pos) is Tile.FLOOR
        ]

    def find_tile(self, tile: Tile) -> list[Pos]:
        """Every position holding the given tile."""
        return [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if self.tile_at((x, y)) is tile
        ]

    def __repr__(self) -> str:
        return f"DungeonMap({self.width}x{self.height}, depth={self.depth})"
