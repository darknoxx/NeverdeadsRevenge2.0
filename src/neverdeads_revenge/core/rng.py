"""Seedable randomness.

Every run draws from a single seeded generator so a run can be replayed from its
seed alone. Nothing in ``core``/``world``/``game`` may call :mod:`random` directly.
"""

from __future__ import annotations

import random
from typing import Any, Sequence, TypeVar

T = TypeVar("T")

__all__ = ["Rng", "seed_from_string"]


def seed_from_string(text: str) -> int:
    """Derive a stable 32-bit seed from a string.

    Uses blake2b instead of :func:`hash` because ``hash()`` is salted per process
    and would give a different run every launch.
    """
    digest = __import__("hashlib").blake2b(text.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big")


class Rng:
    """Thin wrapper around :class:`random.Random` with the helpers we need."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._random = random.Random(seed)

    # -- primitives ---------------------------------------------------------
    def below(self, n: int) -> int:
        """Return an int in ``[0, n)``."""
        return self._random.randrange(n)

    def between(self, low: int, high: int) -> int:
        """Return an int in the inclusive range ``[low, high]``."""
        return self._random.randint(low, high)

    def chance(self, probability: float) -> bool:
        """Return ``True`` with the given probability."""
        return self._random.random() < probability

    def pick(self, seq: Sequence[T]) -> T:
        """Return a random element of ``seq``."""
        return self._random.choice(seq)

    def shuffled(self, seq: Sequence[T]) -> list[T]:
        """Return a shuffled copy of ``seq``."""
        return self._random.sample(list(seq), len(seq))

    def choice_weighted(self, options: Sequence[tuple[T, float]]) -> T:
        """Return an element of ``options`` honouring the given weights.

        ``options`` is a sequence of ``(value, weight)`` pairs. Weights are
        relative and do not need to sum to 1. Raises ``ValueError`` if all
        weights are zero.
        """
        total = sum(weight for _, weight in options)
        if total <= 0:
            raise ValueError("at least one weight must be positive")
        roll = self._random.random() * total
        upto = 0.0
        for value, weight in options:
            upto += weight
            if roll < upto:
                return value
        return options[-1][0]

    def spawn(self) -> Rng:
        """Derive an independent child generator.

        Useful for sub-generators (map layout, monster placement, loot) that
        should be reproducible but independent of draw order elsewhere.
        """
        return Rng(self._random.getrandbits(32))

    def state(self) -> Any:
        """Return the picklable internal state, for save/resume."""
        return self._random.getstate()

    def restore(self, state: Any) -> None:
        """Restore a state previously produced by :meth:`state`."""
        self._random.setstate(state)
