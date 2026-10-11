"""Hold a key to dismiss a screen.

Terminals never report a key going *up*, so "held" cannot be measured directly.
What they do report is the stream of repeat events a held key produces, and that
is enough: the fill is a function of the time since the first press, and every
repeat re-reads it.

There is deliberately no timer. A repeating timer driving the bar was the first
attempt and it was fragile in a way that took a long time to see: dismissing a
screen from inside a timer callback left the app never reporting itself idle, so
``await pilot.pause()`` hung and took the whole test suite with it. The bar
updates on key events instead, which a held key supplies plenty of -- the
terminal sends them thirty times a second.

Because the screen closes on the press that finishes the fill, the terminal is
still repeating the key when the next screen appears. That is handled where it
lands: ``App.note_key`` spots a repeat and the screens that act on enter ignore
one. Which is what a player means by "it should only happen on a new press".
"""

from __future__ import annotations

import time

__all__ = ["HoldToContinue", "BAR_CELLS", "HOLD_SECONDS", "REPEAT_GAP", "FILTER_GAP"]

#: How long the key has to be held, in seconds.
HOLD_SECONDS = 1.0

#: Silence longer than this means the key was released.
RESET_AFTER = 0.25

#: Presses that also count, for terminals with no key repeat.
FALLBACK_PRESSES = 3

#: The window those presses are counted in.
FALLBACK_WINDOW = 2.0

#: Cells in the progress bar.
BAR_CELLS = 10

#: Keys that mean "yes, go on".
HOLD_KEYS = ("enter", "return")

#: A key arriving this soon after the same key is a repeat, not a new press.
#:
#: Comfortably above a terminal's repeat rate and comfortably below how fast
#: anybody presses a key twice on purpose.
REPEAT_GAP = 0.15

#: Silence longer than this, while the repeat filter is armed, means the key that
#: opened the screen has come up.
#:
#: Its own constant rather than ``REPEAT_GAP`` for a reason worth spelling out.
#: The filter is the thing standing between a screen that closes on a *held* key
#: and the screens after it, and two of them act on the same key: hold enter to
#: leave the death summary and the name entry that follows is also closed by
#: enter. So the filter clears only on a gap that is too long to be a repeat --
#: and a terminal repeats every ~33ms, while a repeat *rate* set slow, a loaded
#: machine, or events the terminal bundled can put a quarter of a second between
#: two repeats of the same held key. At ``REPEAT_GAP`` that reads as a new press,
#: and one held enter then walks the summary, the name entry, the title, the
#: hero select and into a new run. Measured on this machine, exactly that.
#:
#: The same rule the hold itself uses (``RESET_AFTER``): silence longer than a
#: quarter of a second is a key that came up. So a player on a terminal without
#: key repeat -- who taps deliberately, about a third of a second apart -- still
#: gets through, and a repeat stream at 180ms does not.
FILTER_GAP = 0.25


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
        fallback_presses: int = FALLBACK_PRESSES,
        fallback_window: float = FALLBACK_WINDOW,
    ) -> None:
        self.keys = keys
        self.seconds = seconds
        self.reset_after = reset_after
        self.fallback_presses = fallback_presses
        self.fallback_window = fallback_window
        self._started: float | None = None
        self._presses: list[float] = []

    def press(self, key: str) -> bool:
        """Record a press of ``key``. True when the screen should go."""
        if key not in self.keys:
            return False

        now = time.monotonic()
        if self._started is None:
            self._started = now

        self._presses = [t for t in self._presses if now - t <= self.fallback_window]
        self._presses.append(now)

        return self.progress >= 1.0 or self._deliberate()

    # -- what the player sees ------------------------------------------------
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

    def _deliberate(self) -> bool:
        """Enough presses, each after a real pause, to mean somebody is trying.

        Counting *slow gaps* rather than the total span, and that distinction is
        the whole rule. A span grows as a held key repeats, so a long hold would
        eventually look deliberate and the bar would never be seen to fill. Slow
        gaps do not: a held key produces none, and three taps produce two.

        Not "every gap must be slow" either -- one quick press followed by a
        pause and then two more is plainly somebody trying, and requiring every
        gap would throw that away for nothing.
        """
        if len(self._presses) < self.fallback_presses:
            return False
        gaps = [b - a for a, b in zip(self._presses, self._presses[1:])]
        slow = sum(1 for gap in gaps if gap > self.reset_after)
        return slow >= self.fallback_presses - 1
