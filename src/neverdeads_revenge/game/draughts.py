"""Draughts that lay a rule on the floor.

Not medicine. Five bottles whose contents are a rule rather than a mending,
and every one of them lasts until the stairs and not one turn longer: a rule
carried down would be a rule the next floor never agreed to, and the floors
are meant to be separate rooms with separate weather.

The rules live here as names and sentences. What they *do* is in
:mod:`game.actions`, the same division as the gifts and the curses: the table
is for reading, the code is for behaving.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FloorDraught", "FLOOR_DRAUGHTS", "draught_by_key"]


@dataclass(frozen=True, slots=True)
class FloorDraught:
    """One strange bottle: a name, and the rule it lays down."""

    key: str
    name: str
    blurb: str


FLOOR_DRAUGHTS: dict[str, FloorDraught] = {
    "thin_veil": FloorDraught(
        key="thin_veil",
        name="THE THIN VEIL",
        blurb="nothing looks at you until you strike",
    ),
    "kindled_breath": FloorDraught(
        key="kindled_breath",
        name="THE KINDLED BREATH",
        blurb="every blow you land sets it burning",
    ),
    "short_crown": FloorDraught(
        key="short_crown",
        name="THE SHORT CROWN",
        blurb="every kill on this floor pays REVENGE twice",
    ),
    "carrion_tongue": FloorDraught(
        key="carrion_tongue",
        name="THE CARRION TONGUE",
        blurb="walk where something died and it feeds you",
    ),
    "gallows_road": FloorDraught(
        key="gallows_road",
        name="THE GALLOWS ROAD",
        blurb="the dead hold them back -- nothing walks where something died",
    ),
}


def draught_by_key(key: str | None) -> FloorDraught | None:
    """The strange draught with this key, or ``None``."""
    if key is None:
        return None
    return FLOOR_DRAUGHTS.get(key)
