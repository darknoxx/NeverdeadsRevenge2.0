"""The daily door: one seed, one day, one attempt.

A daily is a fixed seed everyone gets on the same calendar day. It is not a
second mode: it is the Tenth Door with the dice taken out of the player's hands
-- same credit, same rings, same door. What makes it a daily is that the *same*
door is behind it for everyone who opens it today.

The day is local rather than UTC because a daily is a thing a player sits down
to, and the date on their wall is the one they remember. The seed is a hash of
the date, so two builds that agree on the date agree on the dungeon.
"""

from __future__ import annotations

import hashlib
from datetime import date

__all__ = ["today", "seed_for", "available", "label"]


def today() -> str:
    """The day the door is open, as ``YYYY-MM-DD``."""
    return date.today().isoformat()


def seed_for(day: str) -> int:
    """The seed for one day's door. Stable across builds and platforms."""
    digest = hashlib.sha256(f"tenth-door:{day}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def available(progress, day: str | None = None) -> bool:
    """Whether today's door is open and has not been answered yet.

    The door is part of the Tenth Door's unlock: a player who has never escaped
    has not seen the room the daily is a variation of.
    """
    day = day or today()
    return (
        getattr(progress, "runs_won", 0) >= 1
        and getattr(progress, "daily_date", "") != day
    )


def label(progress, day: str | None = None) -> str:
    """The title line: the offer, or the fact that it has been answered."""
    day = day or today()
    if not available(progress, day):
        return "TODAY'S DOOR   answered"
    return "TODAY'S DOOR   y to enter"
