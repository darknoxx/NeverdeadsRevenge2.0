"""Colours, and the terminal styles translated.

The game carries its colours the way the terminal version did: hex values and
Rich colour names. This is where those become something Qt can paint, so the
palette the player sees on the map is still the palette the game chose -- the
desktop build is a *renderer*, not a re-skin.

A ``Style`` is the small part of Rich's style string the game actually uses:
a foreground, bold, dim, and reverse. Everything the screens pass around --
``"bold green"``, ``"dim cyan"``, ``"red"`` -- is parsed here, once, so the
screens can keep speaking the language they were written in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtGui import QColor

__all__ = ["Style", "parse_style", "BACKGROUND", "FOREGROUND"]


#: The dungeon's own black, and the phosphor the text is drawn in. Not pure
#: black and pure white: a CRT never was, and the scanline pass has nothing to
#: work with against a flat 0 or 255.
BACKGROUND = QColor("#0b0b0b")
FOREGROUND = QColor("#c8c8c8")

#: The named colours the game uses, as RGB. Standard and bright ANSI, the two
#: greys, and the one orange a damage line is drawn in -- the same values the
#: terminal approximated, written down so both builds agree.
NAMED: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "red": (170, 0, 0),
    "green": (0, 170, 0),
    "yellow": (170, 170, 0),
    "blue": (0, 0, 170),
    "magenta": (170, 0, 170),
    "cyan": (0, 170, 170),
    "white": (192, 192, 192),
    "bright_black": (128, 128, 128),
    "bright_red": (255, 85, 85),
    "bright_green": (85, 255, 85),
    "bright_yellow": (255, 255, 85),
    "bright_blue": (85, 85, 255),
    "bright_magenta": (255, 85, 255),
    "bright_cyan": (85, 255, 255),
    "bright_white": (255, 255, 255),
    "grey30": (77, 77, 77),
    "grey70": (179, 179, 179),
    "orange1": (255, 135, 0),
}

#: Style words that are not a colour.
_BOLD = {"bold", "b"}
_DIM = {"dim", "d"}
_REVERSE = {"reverse", "reversed", "r"}


@dataclass(frozen=True, slots=True)
class Style:
    """A foreground and three flags. The whole of what a cell can be."""

    fg: QColor = field(default_factory=lambda: QColor(FOREGROUND))
    bold: bool = False
    dim: bool = False
    reverse: bool = False


def _colour(word: str) -> QColor | None:
    """A colour from a name or a hex value, or ``None`` if it is not one."""
    if word in NAMED:
        return QColor(*NAMED[word])
    if word.startswith("#") and len(word) in (4, 7):
        colour = QColor(word)
        return colour if colour.isValid() else None
    if word.startswith("grey") or word.startswith("gray"):
        digits = word[4:]
        if digits.isdigit():
            level = max(0, min(100, int(digits))) * 255 // 100
            return QColor(level, level, level)
    return None


def parse_style(text: str, base: Style | None = None) -> Style:
    """Read a Rich-ish style string into a :class:`Style`.

    Unknown words are ignored rather than raising: a colour this build has not
    learned is a colour that falls back to the foreground, which is a legible
    screen, and a screen that refuses to draw is not.
    """
    style = base or Style()
    fg = style.fg
    bold, dim, reverse = style.bold, style.dim, style.reverse
    for word in text.replace(",", " ").split():
        word = word.lower()
        if word in _BOLD:
            bold = True
        elif word in _DIM:
            dim = True
        elif word in _REVERSE:
            reverse = True
        elif word == "on" or word == "not":
            continue
        else:
            colour = _colour(word)
            if colour is not None:
                fg = colour
    return Style(fg=fg, bold=bold, dim=dim, reverse=reverse)
