"""Hold a key to dismiss a screen.

The fill is wall-clock time from the first press: pauses inside the hold do
not restart it, because on this desktop a "hold" does not arrive as a steady
stream -- a Wayland compositor may lift the key and hand the repeats back
later, and the terminal-era idea of counting presses could never tell that
from somebody tapping.

Taps are settled by their own length. A press that is down briefly and never
repeats is a tap; releasing it banks nothing. A press that is down for a
repeat delay and repeats away is a hold, whatever the composites between its
events look like. Long silence (longer than the hold itself) means nothing
could still be down -- a focus-thieving window swallowed the events -- and
the fill goes cold.

Completion comes from the press that crosses the fill, never from a timer.
The redraw ticks only paint; they decide nothing.
"""

from __future__ import annotations

import time

__all__ = ["HoldToContinue", "BAR_CELLS", "HOLD_SECONDS"]

#: How long the key has to be held, in seconds.
HOLD_SECONDS = 1.0

#: A press shorter than this, that never repeated, is a tap: a tap banks
#: nothing, so tapping -- even quickly -- can never walk through. A held
#: key's down is at least a repeat delay long; nothing trustworthy lives
#: between those two lengths.
TAP_SECONDS = 0.18

#: Cells in the progress bar.
BAR_CELLS = 10

#: Keys that mean "yes, go on".
HOLD_KEYS = ("enter", "return")


class HoldToContinue:
    """Watches one key and says when it has been held long enough.

    Owned by a screen. The screen feeds it presses (repeat-flagged where the
    platform says so) and releases; the screen dismisses when :meth:`press`
    returns True.
    """

    def __init__(
        self,
        keys: tuple[str, ...] = HOLD_KEYS,
        seconds: float = HOLD_SECONDS,
        tap_seconds: float = TAP_SECONDS,
    ) -> None:
        self.keys = keys
        self.seconds = seconds
        self.tap_seconds = tap_seconds
        self._started: float | None = None  # the fill's origin: the first press
        self._last_press = 0.0
        self._down_from: float | None = None  # when the current down began
        self._down_repeated = False  # did the current down repeat yet?
        self._releases_in_fill = 0  # lifts that stood unbought inside one fill

    def press(self, key: str, repeat: bool = False) -> bool:
        """Record a press of ``key``. True when the screen should go."""
        if key not in self.keys:
            return False

        now = time.monotonic()
        if self._started is not None and now - self._last_press > self.seconds:
            # A gap longer than the hold itself: nothing could still be down,
            # regardless of what events say. Whatever fill there was is cold,
            # and the next press starts an entirely new bargain.
            self._started = None
            self._releases_in_fill = 0
        if self._started is None:
            self._started = now
            self._releases_in_fill = 0
        if not repeat:
            self._down_from = now
            self._down_repeated = False
        else:
            self._down_repeated = True
        self._last_press = now
        return self.progress >= 1.0

    def release(self, key: str) -> None:
        """The key came up. This settles what the down *was*.

        A short press that never repeated was somebody tapping: a tap is not
        a hold, and it banks nothing. A long down -- or one that repeated --
        was the hold, and it keeps its fill right through its own release:
        the compositor may be about to hand the repeats back.

        The compositor lifts the key once. A *second* release inside one fill
        is not a compositor, it is a hand -- deliberate half-second taps that
        banked the first press would otherwise be able to add up to a hold
        they never held. The second release discharges the whole bank.
        """
        if key not in self.keys:
            return
        if self._down_from is not None:
            down = time.monotonic() - self._down_from
            if down < self.tap_seconds and not self._down_repeated:
                self._started = None
            elif self._releases_in_fill:
                # The second one, wrecked out: taps cannot add up through
                # banking, and no compositor lifts twice.
                self._started = None
                self._releases_in_fill = 0
            else:
                self._releases_in_fill += 1
            self._down_from = None
            self._down_repeated = False

    # -- what the player sees ------------------------------------------------
    @property
    def holding(self) -> bool:
        """True while the fill is alive enough to paint."""
        return self._started is not None and (
            time.monotonic() - self._last_press <= self.seconds
        )

    @property
    def progress(self) -> float:
        """How far through the hold, 0.0 to 1.0."""
        if self._started is None:
            return 0.0
        now = time.monotonic()
        if now - self._last_press > self.seconds:
            self._started = None
            return 0.0
        return min(1.0, (now - self._started) / self.seconds)

    def bar(self) -> str:
        """The bar as plain text; the screen decides how to colour it."""
        filled = round(self.progress * BAR_CELLS)
        return "█" * filled + "░" * (BAR_CELLS - filled)
