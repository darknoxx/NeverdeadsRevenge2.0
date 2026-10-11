"""Additive changes to a hero's stats.

A hero's numbers come from three places: the base ``Stats`` they were born with,
the temporary bonuses REVENGE grants for a kill, and everything they are
wearing. This is the third one.

Frozen and additive so that any number of sources can be summed without any of
them knowing about the others -- a weapon, a coat, a curse, all the same shape.
That is the whole reason it exists rather than one more ``_bonus`` field on
``Actor``: the second field was fine, the fifth would not have been.

Lives in ``world/`` rather than ``game/`` because a ``GroundItem`` carries one
and the generator has to place items without importing the game layer.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

__all__ = ["Modifiers"]


@dataclass(frozen=True, slots=True)
class Modifiers:
    """Additive changes to a hero's stats."""

    speed: float = 0.0
    damage: int = 0
    crit_chance: float = 0.0
    crit_multiplier: float = 0.0
    accuracy: int = 0
    evasion: int = 0
    armor: int = 0

    def __add__(self, other: Modifiers) -> Modifiers:
        return Modifiers(
            **{
                field.name: getattr(self, field.name) + getattr(other, field.name)
                for field in fields(self)
            }
        )

    @property
    def is_empty(self) -> bool:
        return all(getattr(self, field.name) == 0 for field in fields(self))

    def describe(self) -> list[str]:
        """One short line per change, for the character sheet.

        Ordered by what a player looks for first -- how hard it hits, then what
        it does to the odds -- rather than by field order, because the field
        order is the order the stats happened to be written down in.
        """
        out: list[str] = []
        for name, label, fmt in _DESCRIPTIONS:
            value = getattr(self, name)
            if value:
                out.append(f"{value:+{fmt}} {label}")
        return out


#: ``(field, label, number format)`` for describing a modifier to a player.
_DESCRIPTIONS: tuple[tuple[str, str, str], ...] = (
    ("damage", "damage", "d"),
    ("crit_chance", "crit", ".0%"),
    ("crit_multiplier", "crit damage", ".1f"),
    ("accuracy", "accuracy", "d"),
    ("evasion", "evasion", "d"),
    ("armor", "armour", "d"),
    ("speed", "speed", ".2f"),
)
