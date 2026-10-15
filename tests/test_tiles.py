"""Tests for the arena's stone.

The tiles are *generated*, so the files themselves are checked the way the sounds
and the icon are -- regenerate and compare -- and the loader is checked for the
one thing that makes the art safe to ship at all: a machine with no tiles in it
gets the room the arena has always had, and not an error and not an empty frame.

The alphabet is underneath every picture in this game. That is the bargain the
sprites already make, and this is the second half of it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAKE_TILES = ROOT / "tools" / "make_tiles.py"

from neverdeads_revenge.desktop import tiles  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


#: Every tile the arena asks for. If the screen asks for a name that is not here,
#: that part of the room is quietly the room it used to be -- which is safe and
#: also silent, so it is checked here instead.
NAMES = ("wall", "wall_vines", "floor_a", "floor_b", "floor_a_bones", "floor_b_bones")


# -- the files -----------------------------------------------------------------
def test_every_tile_the_room_is_made_of_exists(qapp):
    for name in NAMES:
        assert (tiles.TILES_DIR / f"{name}.png").exists(), name
        assert tiles.tile(name) is not None, f"{name} would not load"


def test_the_stone_is_the_size_the_floor_is_laid_out_in(qapp):
    """Two cells to a flagstone, one cell tall, and two flagstones to a course.

    The art and the geometry agree by *construction*: the generator imports these
    numbers from nothing and the arena lays its rows out in the font's own cells,
    so the two only agree if the art was made for this font. A stone of the wrong
    size would be a floor at the wrong scale, and it would still look like stone.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import make_tiles

    floor = tiles.tile("floor_a")
    wall = tiles.tile("wall")
    assert floor is not None and wall is not None
    assert floor.width() == make_tiles.TILE_W and floor.height() == make_tiles.TILE_H
    for name, plain in (
        ("wall_vines", wall),
        ("floor_a_bones", floor),
        ("floor_b_bones", floor),
    ):
        decorated = tiles.tile(name)
        assert decorated is not None, name
        assert (decorated.width(), decorated.height()) == (plain.width(), plain.height()), (
            f"{name} is a different size from the stone it is laid among"
        )
    assert floor.width() == make_tiles.TILE_W == make_tiles.CELL_W * 2
    assert floor.height() == make_tiles.TILE_H == make_tiles.CELL_H
    assert wall.width() == make_tiles.WALL_W == make_tiles.TILE_W * 2
    assert wall.height() == make_tiles.WALL_H == make_tiles.TILE_H * 2


def test_the_stone_is_small_enough_to_ship():
    total = sum(path.stat().st_size for path in tiles.TILES_DIR.glob("*.png"))
    assert total < 40_000, f"the tiles are {total / 1024:.0f} kB"


def test_the_dungeon_is_scattered_and_not_tiled(qapp):
    """A vine here, a bone there, and the scatter is *placed*.

    A room where every stone is dressed is a room with a pattern in it, and a
    scatter that moved between frames would be a room made of flicker: the plain
    stones outnumber the decorated ones, and the bones are on the floor while the
    vines are on the wall -- bone on masonry reads as a trophy somebody hung up,
    and on the ground as somebody who did not get up.
    """
    from neverdeads_revenge.desktop.screens.battle import FLOOR_BONES, WALL_STONES

    assert "wall" in WALL_STONES, "nothing plain to lay a wall out of"
    assert WALL_STONES.count("wall") > len(WALL_STONES) / 2, "too much decoration"
    assert len(set(WALL_STONES)) > 1, "the wall is one repeated stone"
    assert not any("bones" in name for name in WALL_STONES), "bone in the wall"
    assert FLOOR_BONES > 8, "the floor is more bone than stone"


def test_the_litter_is_scattered_and_not_counted():
    """A lattice of bones is a pattern on the floor, and litter is never even.

    The first version of this placed them with ``along * 7 + row * 5 % n``, which
    is not a scatter at all -- it is a grid, and the grid was visible from across
    the room. The places have to come out of a mix of the two coordinates, so that
    what lands beside what is coincidence and not arithmetic.
    """
    from neverdeads_revenge.desktop.screens.battle import FLOOR_BONES, _scatter

    floor = [
        (along, row)
        for row in range(24)
        for along in range(60)
        if _scatter(along, row) % FLOOR_BONES == 0
    ]
    assert floor, "nothing is ever scattered at all"
    assert len(floor) < 24 * 60 / 12, "the floor is more bone than stone"

    crowded = [
        row for row in range(24) if sum(1 for _a, r in floor if r == row) > 1
    ]
    assert crowded, "no row has two of anything in it, which is not a scatter either"

    gaps = []
    for row in crowded:
        columns = [along for along, there in floor if there == row]
        gaps.extend(second - first for first, second in zip(columns, columns[1:]))
    assert len(set(gaps)) > 3, "the bones land on a lattice"
    assert min(gaps) < FLOOR_BONES // 2, "nothing ever lands near anything else"


def test_the_committed_tiles_are_what_the_generator_produces(tmp_path):
    """They are generated, so they must not be hand-edited out of sync.

    Without this, someone nudges a PNG and the next regeneration silently undoes
    it -- the same trap the sounds and the icon have a test for, and for the same
    reason.
    """
    result = subprocess.run(
        [sys.executable, str(MAKE_TILES), "--out", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    generated = {path.name: path.read_bytes() for path in tmp_path.glob("*.png")}
    committed = sorted(tiles.TILES_DIR.glob("*.png"))
    assert committed, "no tiles are committed at all"
    for path in committed:
        assert path.name in generated, f"a generated tile vanished: {path.name}"
        assert generated[path.name] == path.read_bytes(), path.name


# -- and what happens without it -----------------------------------------------
def test_a_machine_with_no_tiles_gets_the_room_it_always_had(qapp, tmp_path, monkeypatch):
    """No art is not a failure, it is the older room.

    The whole reason the arena can be painted is that nothing depends on the paint
    arriving: the grid floor is drawn first and the ``#`` walls are still in the
    file. This asks the loader half of it; the screen half is
    ``test_the_arena_has_a_room_with_no_art_in_it``.
    """
    tiles.clear()
    monkeypatch.setattr(tiles, "TILES_DIR", tmp_path)  # an empty directory
    try:
        for name in NAMES:
            assert tiles.tile(name) is None, f"{name} came from somewhere"
    finally:
        tiles.clear()
