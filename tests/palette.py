"""Just enough colour parsing for the tests that compare the map palette.

The engine carries colours as the strings the terminal version used: hex values
and a handful of ANSI names. Rich used to do this parsing, and 2.0 has no rich,
so this is the small part of it the two palette tests actually need -- the
standard and bright ANSI triples, and ``grey70``.

Only the names the game actually uses are here. A name that turns up without an
entry raises rather than guessing, so a new colour in the game is a failure in a
test rather than a silent zero.
"""

from __future__ import annotations

#: Standard (0-7) and bright (8-15) ANSI, plus the one grey the game names.
NAMED: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "blue": (0, 0, 128),
    "green": (0, 128, 0),
    "cyan": (0, 128, 128),
    "red": (128, 0, 0),
    "magenta": (128, 0, 128),
    "brown": (128, 128, 0),
    "grey": (192, 192, 192),
    "bright_black": (128, 128, 128),
    "bright_red": (255, 0, 0),
    "bright_green": (0, 255, 0),
    "bright_yellow": (255, 255, 0),
    "bright_blue": (0, 0, 255),
    "bright_magenta": (255, 0, 255),
    "bright_cyan": (0, 255, 255),
    "bright_white": (255, 255, 255),
    "grey70": (179, 179, 179),
}


def truecolor(name: str) -> tuple[int, int, int]:
    """The RGB of a colour string: ``#rrggbb`` or one of :data:`NAMED`."""
    if name.startswith("#"):
        value = name[1:]
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    try:
        return NAMED[name]
    except KeyError:
        raise AssertionError(f"no truecolour for {name!r}; add it to tests/palette.py")


def distance(left: str, right: str) -> int:
    """Squared RGB distance, the same measure the palette tests use."""
    a, b = truecolor(left), truecolor(right)
    return sum((x - y) ** 2 for x, y in zip(a, b))
