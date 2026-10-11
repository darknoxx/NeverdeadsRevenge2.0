"""Tests for field of view.

The properties that matter for a roguelite are: you never see through a wall,
what you see is symmetric, and the explored set only ever grows.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.world.fov import compute_fov, compute_fov_full
from neverdeads_revenge.world.generator import generate_floor
from neverdeads_revenge.world.map import DungeonMap
from neverdeads_revenge.world.tiles import Tile

WIDTH = HEIGHT = 31
CENTER = (15, 15)


@pytest.fixture
def open_map() -> DungeonMap:
    """A big empty room."""
    dungeon = DungeonMap(width=WIDTH, height=HEIGHT)
    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            dungeon.set_tile((x, y), Tile.FLOOR)
    return dungeon


def fov_on(dungeon: DungeonMap, origin, radius=8):
    return compute_fov(origin, radius, dungeon.is_opaque, dungeon.in_bounds)


# -- basics ----------------------------------------------------------------
def test_origin_is_always_visible(open_map):
    assert CENTER in fov_on(open_map, CENTER)


def test_open_ground_is_exactly_a_disc(open_map):
    """The view radius is Euclidean, so the lit area is a circle, not a square."""
    for radius in (3, 5, 8):
        visible = fov_on(open_map, CENTER, radius=radius)
        expected = {
            (CENTER[0] + dx, CENTER[1] + dy)
            for dy in range(-radius, radius + 1)
            for dx in range(-radius, radius + 1)
            if dx * dx + dy * dy <= radius * radius
        }
        assert visible == expected, f"radius {radius} does not match a disc"


def test_diagonal_beyond_the_radius_stays_hidden(open_map):
    # (4, 4) is Chebyshev 4 but Euclidean 5.66, so radius 5 must not reach it.
    assert (CENTER[0] - 4, CENTER[1] - 4) not in fov_on(open_map, CENTER, radius=5)
    assert (CENTER[0] - 4, CENTER[1] - 4) in fov_on(open_map, CENTER, radius=6)


def test_nothing_beyond_the_radius(open_map):
    visible = fov_on(open_map, CENTER, radius=4)
    assert all(max(abs(x - CENTER[0]), abs(y - CENTER[1])) <= 4 for x, y in visible)


def test_zero_radius_shows_only_self(open_map):
    assert fov_on(open_map, CENTER, radius=0) == {CENTER}


def test_out_of_bounds_is_excluded(open_map):
    assert all(open_map.in_bounds(pos) for pos in fov_on(open_map, CENTER, radius=12))


def test_origin_near_the_edge_still_works(open_map):
    visible = fov_on(open_map, (0, 0), radius=8)
    assert (0, 0) in visible
    assert all(open_map.in_bounds(pos) for pos in visible)


# -- occlusion -------------------------------------------------------------
def test_wall_does_not_block_the_cell_it_occupies(open_map):
    open_map.set_tile((0, 0), Tile.WALL)
    visible = fov_on(open_map, (1, 1), radius=6)
    assert (0, 0) in visible, "you see the wall face you are looking at"


def test_wall_blocks_what_is_behind_it():
    """A pillar hides what is directly behind it, but you can see around its ends."""
    dungeon = DungeonMap(width=21, height=21)
    for y in range(21):
        for x in range(21):
            dungeon.set_tile((x, y), Tile.FLOOR)
    for y in range(5, 10):
        dungeon.set_tile((10, y), Tile.WALL)

    visible = compute_fov((4, 7), 12, dungeon.is_opaque, dungeon.in_bounds)

    assert (11, 7) not in visible, "straight through the pillar is blocked"
    assert (10, 7) in visible, "but you see the pillar face itself"
    # Going over the top of the pillar works: the line passes above it.
    assert (11, 1) in visible
    assert (11, 13) in visible


def test_a_sealed_room_is_fully_hidden():
    width = height = 21
    dungeon = DungeonMap(width=width, height=height)
    for y in range(height):
        for x in range(width):
            dungeon.set_tile((x, y), Tile.FLOOR)
    # A closed 5x5 box in the middle, with a one-tile hole we cannot see through.
    for y in range(8, 13):
        for x in range(8, 13):
            dungeon.set_tile((x, y), Tile.WALL)
    dungeon.set_tile((10, 8), Tile.RUBBLE)  # solid, blocks sight, not movement

    visible = compute_fov((10, 2), 9, dungeon.is_opaque, dungeon.in_bounds)
    assert not any(9 <= x <= 12 and 9 <= y <= 12 for x, y in visible)


def test_opaque_rubble_blocks_sight_like_a_wall(open_map):
    open_map.set_tile((CENTER[0], CENTER[1] - 3), Tile.RUBBLE)
    visible = fov_on(open_map, CENTER, radius=6)
    assert (CENTER[0], CENTER[1] - 4) not in visible


def test_door_is_transparent(open_map):
    open_map.set_tile((CENTER[0], CENTER[1] - 3), Tile.DOOR)
    visible = fov_on(open_map, CENTER, radius=6)
    assert (CENTER[0], CENTER[1] - 4) in visible


# -- symmetry --------------------------------------------------------------
def test_vision_is_symmetric_on_a_real_floor():
    """If A sees B then B must see A.

    This is a hard invariant, not a nice-to-have. An earlier shadowcasting
    implementation disagreed on roughly 10% of visible pairs on real floors,
    which let a ghoul stand in a cell the player could not see while seeing the
    player perfectly well. ``compute_fov`` therefore checks the line in both
    directions; this test is the guard that keeps it that way.
    """
    radius = 9
    for seed in range(12):
        floor = generate_floor(Rng(seed))
        positions = rng_positions(floor.map, count=40)
        fovs = {
            pos: compute_fov(pos, radius, floor.map.is_opaque, floor.map.in_bounds)
            for pos in positions
        }
        for origin, visible in fovs.items():
            for target in visible:
                if target in fovs:
                    assert origin in fovs[target], (
                        f"seed {seed}: {target} sees {origin}, but {origin} "
                        f"cannot see {target}"
                    )


def test_vision_is_symmetric_in_open_ground():
    dungeon = DungeonMap(width=21, height=21)
    for y in range(21):
        for x in range(21):
            dungeon.set_tile((x, y), Tile.FLOOR)
    radius = 6
    positions = [(x, y) for x in range(2, 19, 4) for y in range(2, 19, 4)]
    fovs = {p: compute_fov(p, radius, dungeon.is_opaque, dungeon.in_bounds) for p in positions}
    for origin, visible in fovs.items():
        for target in visible:
            if target in fovs:
                assert origin in fovs[target], f"{origin} sees {target} but not the reverse"


# -- explored --------------------------------------------------------------
def test_explored_is_a_superset_of_visible(open_map):
    visible, explored = compute_fov_full(CENTER, 6, open_map.is_opaque, open_map.in_bounds)
    assert visible <= explored


def test_explored_accumulates_across_turns():
    dungeon = DungeonMap(width=21, height=21)
    for y in range(1, 20):
        for x in range(1, 20):
            dungeon.set_tile((x, y), Tile.FLOOR)
    explored: set = set()
    previous: set = set()
    for origin in ((5, 5), (15, 5), (15, 15), (5, 15)):
        visible, seen = compute_fov_full(origin, 6, dungeon.is_opaque, dungeon.in_bounds)
        explored |= seen
        assert previous <= explored, "explored must never shrink"
        previous = set(explored)
    assert len(explored) > 40


def rng_positions(dungeon: DungeonMap, count: int) -> list[tuple[int, int]]:
    candidates = dungeon.walkable_positions()
    return Rng(4).shuffled(candidates)[:count]


# -- real floors -----------------------------------------------------------
def test_fov_on_generated_floors_is_stable():
    for seed in range(25):
        floor = generate_floor(Rng(seed))
        visible = compute_fov(
            floor.player_start, 8, floor.map.is_opaque, floor.map.in_bounds
        )
        assert floor.player_start in visible
        assert all(floor.map.in_bounds(pos) for pos in visible)


def test_visible_never_includes_a_wall_only_position_out_of_bounds():
    floor = generate_floor(Rng(9))
    visible = compute_fov(floor.player_start, 10, floor.map.is_opaque, floor.map.in_bounds)
    assert all(0 <= x < floor.map.width and 0 <= y < floor.map.height for x, y in visible)


def test_a_one_tile_gap_gives_a_narrow_cone_not_the_whole_room():
    dungeon = DungeonMap(width=31, height=31)
    for y in range(1, 30):
        for x in range(1, 30):
            dungeon.set_tile((x, y), Tile.FLOOR)
    for y in range(1, 30):
        dungeon.set_tile((15, y), Tile.WALL)
    dungeon.set_tile((15, 15), Tile.FLOOR)  # a single doorway
    origin = (14, 15)

    visible = compute_fov(origin, 6, dungeon.is_opaque, dungeon.in_bounds)

    # You can see out through the gap...
    assert (16, 15) in visible
    assert (20, 15) in visible
    # ...but only as a thin cone along the axis. The far corners of the next
    # room stay hidden, otherwise a doorway would reveal the whole chamber.
    assert (17, 5) not in visible
    assert (17, 25) not in visible
    assert (19, 10) not in visible


def test_a_corner_between_two_solids_is_blocked():
    """The permissive corner rule only opens gaps that are actually open."""
    dungeon = DungeonMap(width=15, height=15)
    for y in range(15):
        for x in range(15):
            dungeon.set_tile((x, y), Tile.FLOOR)
    # A single solid tile at (8, 8): the two diagonals past it are pinched shut.
    dungeon.set_tile((8, 8), Tile.WALL)
    origin = (5, 5)

    visible = compute_fov(origin, 8, dungeon.is_opaque, dungeon.in_bounds)
    assert (8, 8) in visible, "the blocking tile itself is seen"
    assert (9, 9) not in visible, "you cannot see past a wall corner"
