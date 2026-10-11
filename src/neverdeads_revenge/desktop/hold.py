"""Hold a key to dismiss a screen.

The desktop knows when a key goes *up*, so a hold is settled honestly: presses
and their repeats advance the fill, a ``KeyRelease`` voids it. What the
terminal build could only guess -- a tap standing in for a hold -- does not
need guessing here, and the fallback that counted deliberate taps is gone:
three quick presses dismiss nothing, because on the desktop a tap is
measurable and means *not holding*.

There is still no timer deciding anything. Completion comes from the press
that crosses the fill, and the redraws that keep the bar visible while it
fills are only pictures, not decisions.
"""

from __future__ import annotations

import time

__all__ = ["HoldToContinue", "BAR_CELLS", "HOLD_SECONDS"]

#: How long the key has to be held, in seconds.
HOLD_SECONDS = 1.0

#: Silence longer than this means the key was released -- the fallback rule,
#: for a release event that failed to arrive (a window stealing focus won't
#: send one). Comfortably slower than a keyboard's repeat stream.
RESET_AFTER = 0.25

#: Cells in the progress bar.
BAR_CELLS = 10

#: Keys that mean "yes, go on".
HOLD_KEYS = ("enter", "return")


class HoldToContinue:
    """Watches one key and says when it has been held long enough.

    Owned by a screen. The screen feeds it presses and dismisses when
    :meth:`press` returns True -- there is nothing to tick.
    """

    def __init__(
        self,
        keys: tuple[str, ...] = HOLD_KEYS,
        seconds: float = HOLD_SECONDS,
        reset_after: float = RESET_AFTER,
    ) -> None:
        self.keys = keys
        self.seconds = seconds
        self.reset_after = reset_after
        self._started: float | None = None
        self._presses: list[float] = []

    def press(self, key: str) -> bool:
        """Record a press of ``key``. True when the screen should go."""
        if key not in self.keys:
            return False

        now = time.monotonic()
        if self._started is not None and self._presses and now - self._presses[-1] > self.reset_after:
            # A silence this long since the last press means no event told us
            # the key went up (a window stealing focus does that). Whatever
            # progress an old hold had banked must go too -- or the next tap
            # inherits it whole, and a fresh press reads as a completed hold.
            self._started = None
        if self._started is None:
            self._started = now

        self._presses.append(now)
        return self.progress >= 1.0

    def release(self, key: str) -> None:
        """The key came up. Nothing was held past this; nothing is banked.

        Measured on the desktop from Qt's own ``KeyRelease``, which is why a
        tap is a tap -- the old terminal fallback that counted deliberate
        taps cannot happen here and does not exist anymore: three quick
        presses dismiss nothing.
        """
        if key in self.keys and self._started is not None:
            self._started = None
            self._presses = []

    # -- what the player sees ------------------------------------------------
    @property
    def holding(self) -> bool:
        """True while a press of the key might still be held down."""
        return self._started is not None and (
            time.monotonic() - self._last_press <= self.reset_after
        )

    @property
    def progress(self) -> float:
        """How far through the hold, 0.0 to 1.0."""
        if self._started is None:
            return 0.0
        # A gap this long means the key came up, and the next press starts over.
        if time.monotonic() - self._last_press > self.reset_after:
            self._started = None
            return 0.0
        return min(1.0, (time.monotonic() - self._started) / self.seconds)

    def bar(self) -> str:
        """The bar as plain text; the screen decides how to colour it."""
        filled = round(self.progress * BAR_CELLS)
        return "█" * filled + "░" * (BAR_CELLS - filled)

    # -- internals -----------------------------------------------------------
    @property
    def _last_press(self) -> float:
        return self._presses[-1] if self._presses else 0.0
