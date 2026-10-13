"""Procedural dungeon generation.

Deliberately conservative: rectangular rooms joined by L-shaped corridors, then
validated. Nothing clever, but the output is always fully connected and always
has a reachable exit, which is the property that actually matters for a
roguelite. Exotic generators can come later without touching anything else.

Layout is produced first, then validated, and only then populated. That ordering
means a room can never hold the player, an enemy, and the stairs all at once in a
way that could not possibly connect.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from neverdeads_revenge.core.direction import Pos
from neverdeads_revenge.core.rng import Rng

from .items import (
    GIFT_CHANCE,
    chest_count,
    make_page,
    page_count,
    equipment_count,
    loot_count,
    make_chest,
    make_item,
    rare_find_count,
    roll_chest_contents,
    roll_item,
    strange_count,
)
from .map import DungeonMap, GroundItem
from .tiles import Tile

__all__ = [
    "GeneratedFloor",
    "generate_floor",
    "enemy_count",
    "npc_count",
    "ESCAPE_DEPTH",
    "NPC_CHANCE",
    "HUNTER_CHANCE_BY_DEPTH",
    "hunter_chance",
]


def enemy_count(depth: int) -> int:
    """How many monsters a floor holds, before the map's own limits.

    A named function rather than a number in the middle of the generator: it is
    the difficulty dial that is easiest to overshoot, and a dial you can call is
    a dial you can measure.

    Raised from seven on the experimental branch, and again to eleven when the
    floors felt thin: more bodies is a *different* kind of hard from bigger
    numbers -- it costs turns, it crowds corridors, and it is the thing a slow
    hero has least of.
    """
    return 11 + depth


#: How likely a floor is to have somebody on it.
#:
#: Not every floor. A person every time is furniture; a person once every four
#: floors is somebody you remember walking into, which is the whole point of
#: them -- they are the only thing down here that is not trying to kill you.
NPC_CHANCE = 0.25

#: How likely a floor is to have the hunter on it, by depth.
#:
#: It climbs, because the hunter is a *decision* and the deeper the floor the
#: more of a decision it can carry: floor two is the first hint of one, and the
#: floors near the bottom are half hunter. Floor one stays at zero and for the
#: same reason it always did -- it is where a player learns what a monster looks
#: like, and the first thing they learn should not be something they cannot
#: kill.
#:
#: The last floor holds at half rather than climbing further, and stays there
#: for anything deeper: a floor where the hunter is *certain* is not a decision
#: any more, it is the floor.
HUNTER_CHANCE_BY_DEPTH: dict[int, float] = {
    1: 0.0,
    2: 0.0,
    3: 0.0,
    4: 0.0,
    # From the fifth floor on, and never before: measured, the hunter kills a
    # 26-health hero in 1.5 blows from floor five, which is a wall the early
    # floors should not have to explain.
    5: 0.20,
    6: 0.25,
    7: 0.30,
    8: 0.40,
    9: 0.50,
    10: 0.50,
}


def hunter_chance(depth: int) -> float:
    """How likely a floor at ``depth`` is to have the hunter on it.

    Anything past the last floor keeps the last floor's value rather than
    silently dropping to nothing, which is the failure mode a bare ``.get``
    would have.
    """
    if depth < 5:
        # Nothing before the fifth floor. The table above says so; this says it
        # again so a table edit cannot quietly reintroduce a floor-2 ambush.
        return 0.0
    last = max(HUNTER_CHANCE_BY_DEPTH)
    return HUNTER_CHANCE_BY_DEPTH.get(depth, HUNTER_CHANCE_BY_DEPTH[last])


def npc_count(rng: Rng, depth: int) -> int:
    """Whether this floor has somebody on it. Never the first one."""
    if depth < 2:
        return 0
    return 1 if rng.chance(NPC_CHANCE) else 0

#: The floor that holds the way out instead of stairs down.
#:
#: A fixed depth rather than an unlocked one. A run has to have a shape the
#: player can plan against -- "I need to reach ten" is a decision, "keep going
#: until you die" is not.
ESCAPE_DEPTH = 10

#: How likely a floor is to hold a cleansing spring.
#:
#: Not every floor, on purpose. A curse that can be washed off at the next
#: staircase costs a walk; one you have to carry for three floors is a decision
#: about whether the chest was worth opening at all, which is the decision the
#: chest is meant to be.
SPRING_CHANCE = 0.45

#: The floor from which a second spring may stand. Deep enough that the chests
#: have had time to charge a few curses, and late enough that it does not make
#: the early floors soft.
SECOND_SPRING_DEPTH = 5


@dataclass(frozen=True, slots=True)
class Rect:
    """An inclusive rectangle."""

    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> Pos:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def contains(self, pos: Pos) -> bool:
        px, py = pos
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height

    def intersects(self, other: Rect) -> bool:
        return not (
            self.x + self.width <= other.x
            or other.x + other.width <= self.x
            or self.y + self.height <= other.y
            or other.y + other.height <= self.y
        )

    def shrunk(self, margin: int) -> Rect:
        return Rect(
            self.x + margin,
            self.y + margin,
            max(1, self.width - 2 * margin),
            max(1, self.height - 2 * margin),
        )

    @property
    def inner(self) -> Rect:
        """The room without its wall ring."""
        return self.shrunk(1)

    @property
    def inner_positions(self) -> list[Pos]:
        inner = self.inner
        return [
            (x, y)
            for y in range(inner.y, inner.y + inner.height)
            for x in range(inner.x, inner.x + inner.width)
        ]


@dataclass(slots=True)
class GeneratedFloor:
    """A finished floor, ready to be handed to a game."""

    map: DungeonMap
    player_start: Pos
    stairs_down: Pos
    spawn_points: list[Pos]
    depth: int
    #: Where the hunter starts, or ``None`` for a floor that has none. Its own
    #: field rather than another entry in ``spawn_points`` because the game rolls
    #: a template per spawn point, and this one has exactly one template.
    hunter: Pos | None = None
    #: Which tile marks the exit. ``STAIRS_DOWN`` everywhere but the last floor,
    #: where it is ``RIFT`` and taking it wins the run instead of continuing it.
    exit_tile: Tile = Tile.STAIRS_DOWN
    #: Where the loot ended up, for tests and for the map to draw.
    items: dict[Pos, GroundItem] = field(default_factory=dict)
    #: Where the cleansing spring is, or ``None`` on a floor without one. The
    #: first of them: ``springs`` holds every one.
    spring: Pos | None = None
    #: Every spring on the floor. One, usually; two from the fifth floor down,
    #: where the chests have had time to pile curses on.
    springs: tuple[Pos, ...] = ()
    #: Who is standing about, as ``(position, key)``. Usually nobody.
    npcs: list[tuple[Pos, str]] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        return self.exit_tile is Tile.RIFT


# -- layout ----------------------------------------------------------------


MIN_ROOM_WIDTH = 5
MIN_ROOM_HEIGHT = 4
MAX_ROOM_WIDTH = 11
MAX_ROOM_HEIGHT = 8


def _make_room(rng: Rng, dungeon: Rect) -> Rect | None:
    """Pick a random room inside ``dungeon``, or ``None`` if it cannot fit."""
    if dungeon.width < MIN_ROOM_WIDTH or dungeon.height < MIN_ROOM_HEIGHT:
        return None
    # Clamp to the dungeon so the placement range can never invert.
    width = min(rng.between(MIN_ROOM_WIDTH, MAX_ROOM_WIDTH), dungeon.width)
    height = min(rng.between(MIN_ROOM_HEIGHT, MAX_ROOM_HEIGHT), dungeon.height)
    x = rng.between(dungeon.x, dungeon.x + dungeon.width - width)
    y = rng.between(dungeon.y, dungeon.y + dungeon.height - height)
    return Rect(x, y, width, height)


def _carve_room(dungeon_map: DungeonMap, room: Rect) -> None:
    for y in range(room.y, room.y + room.height):
        for x in range(room.x, room.x + room.width):
            dungeon_map.set_tile((x, y), Tile.WALL)
    for pos in room.inner_positions:
        dungeon_map.set_tile(pos, Tile.FLOOR)


def _carve_h_tunnel(dungeon_map: DungeonMap, x1: int, x2: int, y: int) -> None:
    for x in range(min(x1, x2), max(x1, x2) + 1):
        dungeon_map.set_tile((x, y), Tile.FLOOR)


def _carve_v_tunnel(dungeon_map: DungeonMap, y1: int, y2: int, x: int) -> None:
    for y in range(min(y1, y2), max(y1, y2) + 1):
        dungeon_map.set_tile((x, y), Tile.FLOOR)


def _corridor_between(dungeon_map: DungeonMap, start: Pos, end: Pos) -> None:
    """Join two points with an L-shaped corridor, going horizontal first."""
    _carve_h_tunnel(dungeon_map, start[0], end[0], start[1])
    _carve_v_tunnel(dungeon_map, start[1], end[1], end[0])


def _build_rooms(
    rng: Rng, dungeon_map: DungeonMap, dungeon: Rect, attempts: int
) -> list[Rect]:
    """Place non-overlapping rooms, then connect them.

    Corridors are carved only after every room is in place. Carving them eagerly
    as each room is accepted looks equivalent but is not: a later room's wall ring
    can land on top of an earlier corridor and sever it, leaving rooms stranded.
    Doing corridors last means they always win.
    """
    rooms: list[Rect] = []
    for _ in range(attempts):
        room = _make_room(rng, dungeon)
        if room is None or any(room.intersects(other) for other in rooms):
            continue
        _carve_room(dungeon_map, room)
        rooms.append(room)

    for previous, current in zip(rooms, rooms[1:]):
        _corridor_between(dungeon_map, previous.center, current.center)
    return rooms


# -- validation ------------------------------------------------------------


def _reachable(start: Pos, dungeon_map: DungeonMap) -> set[Pos]:
    """Flood fill over walkable tiles from ``start``."""
    seen = {start}
    frontier = [start]
    while frontier:
        current = frontier.pop()
        for neighbour in dungeon_map.neighbours(current):
            if neighbour not in seen and dungeon_map.is_walkable(neighbour):
                seen.add(neighbour)
                frontier.append(neighbour)
    return seen


def _scatter_decor(rng: Rng, dungeon_map: DungeonMap, rooms: list[Rect], count: int) -> None:
    """Sprinkle rubble and grass for texture. Purely cosmetic, never on stairs."""
    reserved = {pos for room in rooms for pos in room.inner_positions}
    candidates = [pos for pos in dungeon_map.walkable_positions() if pos not in reserved]
    if not candidates:
        return
    for pos in rng.shuffled(candidates)[:count]:
        tile = rng.choice_weighted([(Tile.RUBBLE, 3.0), (Tile.GRASS, 5.0)])
        if dungeon_map.tile_at(pos) is Tile.FLOOR:
            dungeon_map.set_tile(pos, tile)


def generate_floor(
    rng: Rng,
    depth: int = 1,
    width: int = 61,
    height: int = 39,
    room_attempts: int = 140,
    enemy_budget: int | None = None,
    curse_keys: tuple[str, ...] = (),
    filled_slots: tuple[str, ...] = (),
    npc_keys: tuple[str, ...] = (),
    gift_keys: tuple[str, ...] = (),
    page_keys: tuple[int, ...] = (),
) -> GeneratedFloor:
    """Build one complete, validated dungeon floor.

    Args:
        rng: Seeded generator; the caller owns it so runs stay reproducible.
        depth: 1-based floor number, used for difficulty scaling.
        width, height: Map dimensions.
        room_attempts: How many random rooms to try before giving up.
        enemy_budget: Overrides the enemy count. Defaults to scaling with depth.
        curse_keys: Which curses a chest may hold. Passed in rather than imported
            for the same reason ``filled_slots`` is.
        filled_slots: Equipment slots the player already has something in. What a
            chest holds is decided here, at build time, and a chest that hands
            out a third coat is a chest nobody opens twice.
        npc_keys: Who might be standing on this floor. Keys only, like the
            curses: the generator places a person and has no idea what they say.

    Raises:
        RuntimeError: If no connected layout could be produced. With the default
            dimensions this does not happen, but a caller may pass a tiny map.
    """
    dungeon_map = DungeonMap(width=width, height=height, depth=depth)
    dungeon = Rect(1, 1, width - 2, height - 2)

    rooms = _build_rooms(rng, dungeon_map, dungeon, room_attempts)
    if not rooms:
        raise RuntimeError(
            f"failed to generate a floor at {width}x{height}; try a larger map"
        )

    # The first room is the safest bet for the player, the last for the exit.
    start_room = rooms[0]
    exit_room = rooms[-1]

    reachable = _reachable(start_room.center, dungeon_map)
    if exit_room.center not in reachable:
        raise RuntimeError("exit room is not reachable from the entrance")

    player_start = start_room.center
    exit_pos = exit_room.center
    # The deepest floor holds the way out rather than a way further in.
    exit_tile = Tile.RIFT if depth >= ESCAPE_DEPTH else Tile.STAIRS_DOWN
    dungeon_map.set_tile(exit_pos, exit_tile)

    # Spawn candidates: interior floor of every room, minus the player's room so
    # nothing materialises on top of you.
    candidates = [
        pos
        for room in rooms[1:]
        for pos in room.inner_positions
        if pos != exit_pos
    ]
    # Never hand out fewer spawn points than we need; a cramped floor is fine.
    if enemy_budget is None:
        enemy_budget = min(enemy_count(depth), len(candidates))
    spawn_points = rng.shuffled(candidates)[:enemy_budget]

    # The hunter, sometimes, on ground nothing else is standing on. Placed
    # before the spring, the npcs and the loot so that the spring's tile rule
    # and the exclusions passed down can keep its cell clear.
    hunter = None
    chance = hunter_chance(depth)
    if chance and rng.chance(chance):
        taken = set(spawn_points) | {exit_pos}
        free = [pos for pos in candidates if pos not in taken]
        if free:
            hunter = rng.pick(free)

    _scatter_decor(rng, dungeon_map, rooms, count=len(dungeon_map.walkable_positions()) // 18)

    # The spring before the loot, so that the loot's "plain floor only" rule
    # keeps it clear without a second exclusion list. The hunter is handed
    # down as ground the spring may not stand on.
    spring = _place_spring(
        rng, dungeon_map, candidates, exit_pos, depth,
        avoid=(hunter,) if hunter is not None else (),
    )
    springs: list[Pos] = [spring] if spring is not None else []
    if depth >= SECOND_SPRING_DEPTH:
        # A second spring down where the curses pile up: chests are one a
        # floor and each charges a curse, and a single 45% spring could not
        # keep up with a player who opens them all.
        second = _place_spring(
            rng, dungeon_map, candidates, exit_pos, depth,
            avoid=(hunter,) if hunter is not None else (),
        )
        if second is not None:
            springs.append(second)

    # Somebody, sometimes. Placed before the loot so the loot's plain-floor rule
    # keeps their cell clear the same way it keeps the spring's -- and the
    # hunter's cell is not theirs to stand on either. Immutable people: an
    # item under an npc is one nobody can ever pick up.
    npcs = _place_npcs(
        rng, dungeon_map, candidates, exit_pos, depth, npc_keys,
        avoid=(hunter,) if hunter is not None else (),
    )

    # Loot last, and on whatever is still plain floor. Placing it after the decor
    # means an item can never be swallowed by a patch of grass, and after the
    # npcs means an item can never be swallowed by a person.
    items = _scatter_loot(
        rng,
        dungeon_map,
        candidates,
        depth,
        curse_keys,
        filled_slots,
        gift_keys,
        page_keys,
        blocked=tuple(pos for pos, _ in npcs),
    )

    return GeneratedFloor(
        map=dungeon_map,
        player_start=player_start,
        stairs_down=exit_pos,
        spawn_points=spawn_points,
        hunter=hunter,
        depth=depth,
        exit_tile=exit_tile,
        items=items,
        spring=spring,
        springs=tuple(springs),
        npcs=npcs,
    )


def _place_spring(
    rng: Rng,
    dungeon_map: DungeonMap,
    candidates: list[Pos],
    exit_pos: Pos,
    depth: int,
    avoid: tuple[Pos, ...] = (),
) -> Pos | None:
    """Put a cleansing spring somewhere reachable, or decide not to.

    Never on the first floor and never on the exit, and never under somebody
    who is placed before: ``avoid`` carries the hunter's cell down. The first
    floor is the one floor where nobody can be carrying anything worth washing
    off, and a spring standing on the way out is a spring the player has to
    choose to walk past.
    """
    if depth < 2 or not rng.chance(SPRING_CHANCE):
        return None

    spots = [
        pos
        for pos in candidates
        if pos != exit_pos and pos not in avoid and dungeon_map.tile_at(pos) is Tile.FLOOR
    ]
    if not spots:
        return None

    pos = rng.pick(spots)
    dungeon_map.set_tile(pos, Tile.SPRING)
    return pos


def _place_npcs(
    rng: Rng,
    dungeon_map: DungeonMap,
    candidates: list[Pos],
    exit_pos: Pos,
    depth: int,
    npc_keys: tuple[str, ...],
    avoid: tuple[Pos, ...] = (),
) -> list[tuple[Pos, str]]:
    """Stand somebody about, if this floor has anybody and anywhere to put them.

    Never on the exit -- a conversation standing on the way out is a
    conversation the player has to walk past twice -- and never on the hunter,
    who is handed down in ``avoid``.
    """
    if not npc_keys:
        return []

    placed: list[tuple[Pos, str]] = []
    for _ in range(npc_count(rng, depth)):
        spots = [
            pos
            for pos in candidates
            if pos != exit_pos
            and pos not in avoid
            and dungeon_map.tile_at(pos) is Tile.FLOOR
            and all(pos != taken for taken, _ in placed)
        ]
        if not spots:
            return placed
        placed.append((rng.pick(spots), rng.pick(npc_keys)))
    return placed


def _scatter_loot(
    rng: Rng,
    dungeon_map: DungeonMap,
    candidates: list[Pos],
    depth: int,
    curse_keys: tuple[str, ...] = (),
    filled_slots: tuple[str, ...] = (),
    gift_keys: tuple[str, ...] = (),
    page_keys: tuple[int, ...] = (),
    blocked: tuple[Pos, ...] = (),
) -> dict[Pos, GroundItem]:

    """Drop the floor's draughts, equipment and chests.

    Items may land under a monster. That is deliberate: a potion you have to
    fight for is more interesting than one lying in an empty room, and the
    player can always kill the occupant and come back. What they may *not* do
    is land on the player's own room -- ``candidates`` already excludes it --
    on the exit, or on an npc: a person blocking a floor item does not fight,
    cannot be spent, and would be a piece of loot hidden somewhere the game
    never gives back. ``blocked`` carries the npc cells down for that.

    ``curse_keys`` is passed in rather than imported: the generator places a
    chest holding *a* curse and does not need to know what any of them do. The
    game layer owns the meanings, ``world/`` owns the furniture.
    """
    placed: dict[Pos, GroundItem] = {}
    open_floor = [
        pos
        for pos in candidates
        if pos not in blocked and dungeon_map.tile_at(pos) is Tile.FLOOR
    ]
    if not open_floor:
        return placed

    # Separate pools, rolled separately and then placed together. One shared
    # table would let equipment crowd out the healing the whole game is balanced
    # around, which is exactly what happened the first time.
    to_place: list[GroundItem] = [
        make_item(roll_item(rng, depth, kinds=("draught",)))
        for _ in range(loot_count(depth))
    ]
    to_place += [
        make_item(roll_item(rng, depth, kinds=("weapon", "armour")))
        for _ in range(equipment_count(depth))
    ]
    # And the strange draughts, from their own pool: five bottles that lay a
    # rule on the floor, none of them medicine. Rolled from the draught pool
    # they would have cut the healing to a fifth; rolled apart, the floor holds
    # both.
    to_place += [
        make_item(roll_item(rng, depth, kinds=("strange",)))
        for _ in range(strange_count(depth))
    ]
    if curse_keys:
        # A different curse in each chest on a floor, and never more chests than
        # there are prices left to pay. Two chests offering the same curse would
        # be one bargain sold twice, and the second one would be a dialog that
        # reads out a price it has already charged -- which is exactly what the
        # caller hands us ``unpaid`` curses to avoid. Drawing from a shuffled
        # copy keeps the choice random and the *set* distinct.
        keys = rng.shuffled(list(curse_keys))
        # Gifts are drawn from a separate shuffled pool so two chests on one
        # floor cannot hand over the same rule -- two of the same rule is not
        # twice the rule.
        gifts = rng.shuffled(list(gift_keys))
        for key in keys[: chest_count(depth)]:
            holding_a_gift = bool(gifts) and rng.chance(GIFT_CHANCE)
            to_place.append(
                make_chest(
                    key,
                    None if holding_a_gift else roll_chest_contents(
                        rng, depth, filled_slots
                    ),
                    gift=gifts.pop() if holding_a_gift else None,
                )
            )
    # The chronicle, torn up and scattered. Drawn without replacement from what
    # the player has *not* found, so a page never turns up twice -- finding one
    # already in the book would be a find that gives nothing.
    if page_keys:
        to_place += [
            make_page(number)
            for number in rng.shuffled(list(page_keys))[: page_count(depth)]
        ]
    # And, rarely, the strong tier lying in the open with nothing owed for it.
    # The same two questions are asked of it: what are you missing, and how deep
    # is this.
    to_place += [
        make_item(roll_chest_contents(rng, depth, filled_slots))
        for _ in range(rare_find_count(rng, depth))
    ]

    for pos, item in zip(rng.shuffled(open_floor), to_place):
        dungeon_map.add_item(pos, item)
        placed[pos] = item
    return placed
