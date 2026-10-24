"""The game's small text rules, kept in one place so two screens agree."""

from __future__ import annotations

__all__ = ["the"]


def the(name: str) -> str:
    """``the`` before a name that needs one, and not before one that has it.

    Half the equipment is called "the something" -- every amulet is, and the
    strongest blades are -- and "You start with the the patient knife" is the
    sort of thing that makes a whole screen look unfinished.
    """
    return name if name.startswith("the ") else f"the {name}"
