"""Hold a key to dismiss a screen.

The desktop knows when a key goes *up*, so a hold is settled honestly: presses
and their repeats advance the fill, a ``KeyRelease`` ends it. But there is a
wrinkle the terminal never had, and Wayland handed to us as a bug report: the
compositor announces its repeat phase by lifting the key *first* and pressing
it again as repeats. A naive release handler reads that lift as the end of the
hold -- the user saw a bar fill, empty itself, and start over.

So a release is held open for a moment, and only a press *marked* as an
auto-repeat can redeem it. A press that is not a repeat -- somebody really
tapping -- voids the hold at once. If nothing follows the lift at all, silence
after a grace does what the old silence heuristic did. A tap is a tap; a hold
does not stutter.

Completion still comes from the press that crosses the fill, never from a
timer. The redraws that keep the bar visible while it fills are only
pictures, not decisions.
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

#: A lift this old, with no repeat press behind it, is a key that went up for
#: good. The Wayland lift-and-repeat sequence is over in a frame or two; a
#: person tapping presses at least a tenth of a second apart, and a tap press
#: is not flagged as a repeat anyway.
RELEASE_GRACE = 0.25

#: Cells in the progress bar.
BAR_CELLS = 10

#: Keys that mean "yes, go on".
HOLD_KEYS = ("enter", "return")


class HoldToContinue:
    """Watches one key and says when it has been held long enough.

    Owned by a screen. The screen feeds it presses (with the repeat flag) and
    releases, and dismisses when :meth:`press` returns True -- the redraw
    ticks only draw the fill, they decide nothing.
    """

    def __init__(
        self,
        keys: tuple[str, ...] = HOLD_KEYS,
        seconds: float = HOLD_SECONDS,
        reset_after: float = RESET_AFTER,
        release_grace: float = RELEASE_GRACE,
    ) -> None:
        self.keys = keys
        self.seconds = seconds
        self.reset_after = reset_after
        self.release_grace = release_grace
        self._started: float | None = None
        self._released_at: float | None = None
        self._last_press = 0.0

    def press(self, key: str, repeat: bool = False) -> bool:
        """Record a press of ``key``. True when the screen should go.

        ``repeat`` is kept in the call shape for honesty, but not trusted: on
        some compositors the repeat presses arrive as plain presses with no
        flag on them. The timing does the work instead -- a press close behind
        a lift is the repeat phase, whatever it is labelled.
        """
        if key not in self.keys:
            return False

        now = time.monotonic()
        if self._released_at is not None:
            if now - self._released_at <= self.release_grace:
                # A press this soon behind a lift is the compositor repeating
                # -- flagged or not. The hold lives on, fill included.
                self._released_at = None
            else:
                # The lift was real and stood for the whole grace: the key
                # went up, and nothing is banked.
                self._started = None
                self._released_at = None
        if self._started is not None and now - self._last_press > self.reset_after:
            # No event ended the hold (a window stole focus), but the silence
            # has gone on too long to be a repeat stream's.
            self._started = None
        if self._started is None:
            self._started = now
        self._last_press = now
        return self.progress >= 1.0

    def release(self, key: str) -> None:
        """The key came up -- *or* the compositor is about to repeat it.

        Not decided here: a release is only held against the future, and the
        next press settles it. Either a repeat redeems the hold, an unflagged
        press voids it, or the grace expires and silence wins.
        """
        if key in self.keys and self._released_at is None:
            self._released_at = time.monotonic()

    # -- what the player sees ------------------------------------------------
    @property
    def holding(self) -> bool:
        """True while a press of the key might still be held down."""
        now = time.monotonic()
        if self._released_at is not None:
            return now - self._released_at <= self.release_grace
        return self._started is not None and now - self._last_press <= self.reset_after

    @property
    def progress(self) -> float:
        """How far through the hold, 0.0 to 1.0."""
        if self._started is None:
            return 0.0
        now = time.monotonic()
        if self._released_at is not None and now - self._released_at > self.release_grace:
            # The lift was real: the key went up, and nothing is banked.
            self._started = None
            self._released_at = None
            return 0.0
        if now - self._last_press > self.reset_after:
            self._started = None
            return 0.0
        return min(1.0, (now - self._started) / self.seconds)

    def bar(self) -> str:
        """The bar as plain text; the screen decides how to colour it."""
        filled = round(self.progress * BAR_CELLS)
        return "█" * filled + "░" * (BAR_CELLS - filled)
