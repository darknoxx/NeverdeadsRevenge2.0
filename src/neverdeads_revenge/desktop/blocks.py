"""A five-by-five block font.

Hand-made rather than a figlet one. Both obvious alternatives were tried and
rejected on the result:

* The ``_|/\\`` figlet style spells only the first word legibly, and barely: at
  five rows of underscores and pipes the eye cannot pick the letters out.
* The block figlet fonts (ANSI Shadow and friends) read beautifully but are eight
  columns per letter, so ``NEVERDEAD'S`` alone is 88 wide and will not fit an
  80-column terminal.

Five by five solid blocks are the compromise: legible at a glance, and the whole
title fits in 65 columns.

Its own module because two screens draw with it now -- the title spells the game's
name in it, and the hero select shows the hero's letter at that size rather than
as one character beside a name. A font that lives inside the screen that first
needed it is a font the second screen has to reach into that screen to borrow.
"""

from __future__ import annotations

__all__ = ["BLOCK", "ROWS", "LETTER_GAP", "render_word", "render_letter"]

#: The alphabet the font carries, as five rows of ``█`` and space.
#:
#: Deliberately not a full alphabet. It holds the title's name and the letters
#: the roster's names start with -- plus the ones the two locked slots will need
#: -- and nothing else. A font nobody asked for is a font nobody checks.
BLOCK: dict[str, tuple[str, ...]] = {
    "A": (" ███ ", "█   █", "█████", "█   █", "█   █"),
    "D": ("████ ", "█   █", "█   █", "█   █", "████ "),
    "E": ("█████", "█    ", "████ ", "█    ", "█████"),
    "G": (" ████", "█    ", "█  ██", "█   █", " ███ "),
    "N": ("█   █", "██  █", "█ █ █", "█  ██", "█   █"),
    "R": ("████ ", "█   █", "████ ", "█  █ ", "█   █"),
    "S": (" ████", "█    ", " ███ ", "    █", "████ "),
    "T": ("█████", "  █  ", "  █  ", "  █  ", "  █  "),
    "V": ("█   █", "█   █", "█   █", " █ █ ", "  █  "),
    # Three peaks at the top and two valleys at the bottom, which is the only
    # reading of a W that five columns allow. Written the other way round -- the
    # outer strokes solid to the floor -- it is an M with a bar through it.
    "W": ("█   █", "█   █", "█ █ █", "█ █ █", " █ █ "),
    "Y": ("█   █", "█   █", " █ █ ", "  █  ", "  █  "),
    # One column wide and two rows tall, sitting high. In a five-wide cell it
    # floated so far from the letter before it that it read as a stray mark
    # rather than a possessive, and the name looked misspelled. Cells are not
    # all the same width here, and this is the reason why.
    "'": ("█", "█", " ", " ", " "),
}

#: Blank columns between letters.
LETTER_GAP = " "

ROWS = 5


def render_word(word: str) -> list[str]:
    """Draw ``word`` in the block font, one string per row.

    Unknown characters are skipped rather than raising: the alternative is a
    screen that refuses to load because someone typed a letter the font does not
    have, and a title screen is the worst place to find that out.
    """
    # (glyph rows, whether a gap goes before it). The apostrophe takes no gap on
    # either side -- it is punctuation hanging off the letter, not a letter.
    cells: list[tuple[tuple[str, ...], bool]] = []
    previous = ""
    for char in word.upper():
        if char not in BLOCK:
            continue
        gap = bool(cells) and char != "'" and previous != "'"
        cells.append((BLOCK[char], gap))
        previous = char

    if not cells:
        return []
    return [
        "".join((LETTER_GAP if gap else "") + glyph[row] for glyph, gap in cells)
        for row in range(ROWS)
    ]


def render_letter(char: str, style: str = "") -> str:
    """One character as block art, optionally coloured, or an empty string.

    A single letter rather than a word, so there is no gap to place and no
    baseline to align -- which is why it is a second function and not a flag on
    the first.
    """
    rows = render_word(char)
    if not rows:
        return ""
    art = "\n".join(rows)
    return f"[{style}]{art}[/]" if style else art
