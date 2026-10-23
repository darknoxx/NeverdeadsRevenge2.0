"""The pattern buffer: the grid of characters the game is drawn into.

Everything above this draws characters into cells; everything below it paints
those cells into a bitmap. The split is the whole reason the CRT pass can be a
single shader -- by the time the picture exists it is a flat image at a known,
tiny resolution, and scaling it by a whole number and laying scanlines over it is
arithmetic rather than a redraw.

A cell is a character and a :class:`~neverdeads_revenge.desktop.theme.Style`.

**Qt-free on purpose.** This is where the game's alphabet actually lives, and the
alphabet is not a GUI toolkit's business: the Qt painter is a *subclass* of this
grid in :mod:`~neverdeads_revenge.desktop.buffer`, a second front end paints the
same cells with its own blitter, and neither of them owns the cells. That is why
the module carries the run-splitting the renderers want: consecutive cells that
share a style are one run, and a run is what every painter in the world draws
faster than a character at a time.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from typing import Iterator

from .theme import Style, style_on

__all__ = ["Cell", "PatternBuffer"]

#: The style of an empty cell, shared by every one of them: a `Style` is frozen,
#: so one object is safe, and a grid that made five thousand of them a frame was
#: five thousand objects to compare and collect.
BLANK = Style()


@dataclass(slots=True)
class Cell:
    char: str = " "
    style: Style = BLANK


#: The words that name a *key*, and what the same gesture is called on a pad.
#: Word boundaries only: "sentence" must not become "sBntence".
PAD_WORDS: dict[str, str] = {
    r"\benter\b": "A",
    r"\besc\b": "B",
    r"\bescape\b": "B",
    r"\bpgup\b": "LT",
    r"\bpgdn\b": "RT",
    r"\bbackspace\b": "B",
}


def pad_words(text: str) -> str:
    """Say a hint in the buttons the player is actually holding.

    The screens write "enter" and "esc" because that is the vocabulary every
    screen answers; a pad is a different set of *names on the same words*. This
    is the translation for the words that appear in hints, and only when the pad
    was the last thing touched -- a keyboard player still reads "esc".
    """
    for pattern, word in PAD_WORDS.items():
        text = re.sub(pattern, word, text)
    return text


class PatternBuffer:
    """A grid of character cells."""

    def __init__(self, cols: int, rows: int, font=None) -> None:
        self.cols = cols
        self.rows = rows
        #: Whether hints should name the pad's buttons instead of the keys. Set
        #: by the application from the last input device; off everywhere else,
        #: which is why no test has to know about it.
        self.pad = False
        #: Cells written since the last clear, for the timings report: a frame
        #: that takes twenty milliseconds to draw is a frame either writing a
        #: great many cells or writing them very slowly, and the number says
        #: which.
        self.puts = 0
        #: Kept rather than used: the grid is measured in cells and does not
        #: care how wide one is, but a painter wants the font and the caller has
        #: already got it in hand.
        self.font = font
        self.cells: list[list[Cell]] = [
            [Cell() for _ in range(cols)] for _ in range(rows)
        ]

    # -- writing ------------------------------------------------------------
    def clear(self, char: str = " ", style: Style | None = None) -> None:
        # One style for the whole grid and not one per cell: a ``Style`` is frozen,
        # so sharing it is safe, and a frame that builds two thousand six hundred
        # of them is a frame spending a millisecond and a half writing the same
        # blank. (Measured: 1.43 ms a frame, and 0.03 ms this way.)
        blank = style or Style()
        self.puts = 0
        for row in self.cells:
            for cell in row:
                cell.char = char
                cell.style = blank

    def put(self, x: int, y: int, char: str, style: Style | None = None) -> None:
        if 0 <= x < self.cols and 0 <= y < self.rows:
            self.puts += 1
            cell = self.cells[y][x]
            new = style or Style()
            if new.bg is None and cell.style.bg is not None:
                # The cell already sits on a panel. Writing a *word* onto it does
                # not lift the panel out from under the writing: the text keeps
                # the background the square had, which is why the words in a
                # menu read on the panel and not on a stripe of black.
                new = style_on(new, cell.style.bg)
            cell.char = char
            cell.style = new

    def text(self, x: int, y: int, string: str, style: Style | None = None) -> int:
        """Write ``string`` starting at ``x``. Returns the next free column.

        Characters past the right edge are dropped rather than wrapped: every
        line in this game is positioned by hand, and a wrap is a line that lands
        somewhere the screen did not ask for.
        """
        style = style or Style()
        if self.pad:
            string = pad_words(string)
        for offset, char in enumerate(string):
            self.put(x + offset, y, char, style)
        return x + len(string)

    def fill_row(self, y: int, char: str, style: Style | None = None) -> None:
        for x in range(self.cols):
            self.put(x, y, char, style)

    # -- reading ------------------------------------------------------------
    def runs(self, first: int = 0, last: int | None = None) -> Iterator[tuple[int, int, list[Cell]]]:
        """Every row as runs of same-styled cells: ``(x, y, the run)``.

        The unit both painters draw in. Qt draws a string faster than a string
        of one character many times, and a blitter draws one strip of a texture
        faster than the same strip in pieces -- so the run is the thing worth
        finding once rather than twice.

        ``first`` and ``last`` are rows, for a painter that wants one band: the
        fight's menu is painted *over* the room's art, and walking three
        thousand cells to find the twenty rows of a box was most of what that
        second pass cost.
        """
        stop = self.rows if last is None else min(self.rows, last)
        for y in range(max(0, first), stop):
            row = self.cells[y]
            x = 0
            while x < self.cols:
                style = row[x].style
                key = style.key
                end = x + 1
                # An integer per style, minted once: comparing those is the
                # cheapest way to ask whether the next cell belongs to this run,
                # and this loop is asked a few thousand times a frame.
                while end < self.cols and row[end].style.key == key:
                    end += 1
                yield x, y, row[x:end]
                x = end
