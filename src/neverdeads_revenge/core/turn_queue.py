"""Energy-based turn scheduling.

This is the mechanical heart of the game. Everyone moves on the same clock, but
how often you get to act depends entirely on your ``speed`` stat:

    interval = ENERGY_PER_TURN / speed

Noxx at speed 1.5 acts every ~66.7 time units, a shambling ghoul at 0.7 only
every ~142.9. That ratio is exactly what makes "fast" heroes feel fast, and it
falls out of the formula rather than being special-cased.

The queue keeps a heap of ``(due_time, actor)``. Asking for the next actor
fast-forwards the clock to that actor's due time, so no precision is lost to
repeated small additions and the ordering never drifts.

This module deliberately knows nothing about actors beyond ``speed``; see the
``SpeedLike`` protocol.
"""

from __future__ import annotations

import heapq
from typing import Protocol, TypeVar

__all__ = ["ENERGY_PER_TURN", "TurnQueue", "SpeedLike"]

ENERGY_PER_TURN = 100.0
"""Energy an actor must accumulate to act once. Also the base interval."""


class SpeedLike(Protocol):
    """The only thing :class:`TurnQueue` needs from an actor."""

    @property
    def speed(self) -> float: ...


A = TypeVar("A", bound=SpeedLike)


class TurnQueue:
    """Orders actors by who is due to act next."""

    def __init__(self, actors: tuple[A, ...] | list[A] = ()) -> None:
        self._heap: list[tuple[float, int, A]] = []
        self._counter = 0
        self._clock = 0.0
        for actor in actors:
            self.add(actor)

    # -- introspection ------------------------------------------------------
    @property
    def clock(self) -> float:
        """The current time in energy units."""
        return self._clock

    def __len__(self) -> int:
        return len(self._heap)

    def __contains__(self, actor: object) -> bool:
        return any(entry[2] is actor for entry in self._heap)

    # -- membership ---------------------------------------------------------
    def add(self, actor: A) -> None:
        """Schedule ``actor`` for its next action, relative to the current clock."""
        self._counter += 1
        heapq.heappush(self._heap, (self._clock + self.interval(actor), self._counter, actor))

    def remove(self, actor: A) -> bool:
        """Drop ``actor`` from the queue. Returns ``True`` if it was present.

        Rebuilds the heap rather than patching it in place: actors are removed
        rarely (on death) and this keeps us off heapq's private API.
        """
        remaining = [entry for entry in self._heap if entry[2] is not actor]
        if len(remaining) == len(self._heap):
            return False
        self._heap = remaining
        heapq.heapify(self._heap)
        return True

    # -- the actual mechanic ------------------------------------------------
    @staticmethod
    def interval(actor: SpeedLike) -> float:
        """Time between two actions of ``actor``.

        Raises ``ValueError`` for a non-positive speed, which would otherwise
        mean an actor who never gets to act at all.
        """
        speed = actor.speed
        if speed <= 0:
            raise ValueError(f"actor speed must be > 0, got {speed!r}")
        return ENERGY_PER_TURN / speed

    def pop(self) -> A | None:
        """Return the actor whose turn is next, or ``None`` if the queue is empty.

        Advances the clock to that actor's due time. Calling this repeatedly
        yields the full turn order for the run.
        """
        if not self._heap:
            return None
        due, _, actor = self._heap[0]
        if due > self._clock:
            self._clock = due
        self._counter += 1
        heapq.heapreplace(
            self._heap, (self._clock + self.interval(actor), self._counter, actor)
        )
        return actor

    def take(self, count: int) -> list[A]:
        """Pop ``count`` actors and return them in turn order."""
        return [actor for _ in range(count) if (actor := self.pop()) is not None]

    # -- determinism --------------------------------------------------------
    def snapshot(self) -> tuple:
        """Return a copy of the full queue state, for save/resume and tests."""
        return (
            sorted(self._heap, key=lambda entry: entry[:2]),
            self._counter,
            self._clock,
        )

    def restore(self, snapshot: tuple) -> None:
        """Restore a snapshot previously produced by :meth:`snapshot`."""
        entries, counter, clock = snapshot
        self._heap = list(entries)
        heapq.heapify(self._heap)
        self._counter = counter
        self._clock = clock
