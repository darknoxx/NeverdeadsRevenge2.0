"""Directions and position helpers.

Eight-way movement. ``NONE`` is used for "stay put" (waiting, failed moves).
"""

from __future__ import annotations

from enum import Enum

__all__ = ["Direction", "Pos", "chebyshev", "manhattan", "sign"]


Pos = tuple[int, int]
"""A position as ``(x, y)``."""


class Direction(Enum):
    """A movement step or relative facing."""

    NONE = (0, 0)
    NORTH = (0, -1)
    SOUTH = (0, 1)
    EAST = (1, 0)
    WEST = (-1, 0)
    NORTH_EAST = (1, -1)
    NORTH_WEST = (-1, -1)
    SOUTH_EAST = (1, 1)
    SOUTH_WEST = (-1, 1)

    @property
    def dx(self) -> int:
        return self.value[0]

    @property
    def dy(self) -> int:
        return self.value[1]

    @property
    def is_diagonal(self) -> bool:
        return self.dx != 0 and self.dy != 0

    @property
    def opposite(self) -> Direction:
        return _OPPOSITES[self]

    def rotate(self, turns: int) -> Direction:
        """Rotate 90 degrees clockwise ``turns`` times.

        Negative values turn anticlockwise. Used by simple AI that wants to take
        a direction to its left or right. ``NONE`` has no facing, so it rotates
        to itself.
        """
        if self is Direction.NONE:
            return self
        position = _CLOCKWISE.index(self)
        # _CLOCKWISE steps around the compass in 45 degree increments, so two
        # steps make one 90 degree turn.
        return _CLOCKWISE[(position + 2 * turns) % len(_CLOCKWISE)]

    def step(self, origin: Pos) -> Pos:
        """Return ``origin`` moved one step in this direction."""
        return (origin[0] + self.dx, origin[1] + self.dy)


_OPPOSITES: dict[Direction, Direction] = {
    Direction.NONE: Direction.NONE,
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
    Direction.NORTH_EAST: Direction.SOUTH_WEST,
    Direction.NORTH_WEST: Direction.SOUTH_EAST,
    Direction.SOUTH_EAST: Direction.NORTH_WEST,
    Direction.SOUTH_WEST: Direction.NORTH_EAST,
}

# Clockwise ring starting at north. Indexed explicitly by :meth:`Direction.rotate`
# rather than relying on Enum internals.
_CLOCKWISE: tuple[Direction, ...] = (
    Direction.NORTH,
    Direction.NORTH_EAST,
    Direction.EAST,
    Direction.SOUTH_EAST,
    Direction.SOUTH,
    Direction.SOUTH_WEST,
    Direction.WEST,
    Direction.NORTH_WEST,
)

# The eight real directions, i.e. everything except NONE.
DIRECTIONS: tuple[Direction, ...] = tuple(d for d in Direction if d is not Direction.NONE)
CARDINALS: tuple[Direction, ...] = (
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)
DIAGONALS: tuple[Direction, ...] = (
    Direction.NORTH_EAST,
    Direction.SOUTH_EAST,
    Direction.SOUTH_WEST,
    Direction.NORTH_WEST,
)


def chebyshev(a: Pos, b: Pos) -> int:
    """Distance with 8-way movement allowed (diagonal steps cost the same)."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def manhattan(a: Pos, b: Pos) -> int:
    """Distance with 4-way movement only."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def sign(value: int) -> int:
    """Return -1, 0 or 1 for the sign of ``value``."""
    return (value > 0) - (value < 0)


def direction_towards(origin: Pos, target: Pos) -> Direction:
    """Return the single direction that gets ``origin`` closer to ``target``.

    Both axes are considered when both differ, so this can return a diagonal.
    """
    return Direction((sign(target[0] - origin[0]), sign(target[1] - origin[1])))
