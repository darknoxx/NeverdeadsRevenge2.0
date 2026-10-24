"""Colours, and the terminal styles translated.

The game carries its colours the way the terminal version did: hex values and
Rich colour names. This is where those become something a front end can paint,
so the palette the player sees on the map is still the palette the game chose --
the desktop build is a *renderer*, not a re-skin.

A ``Style`` is the small part of Rich's style string the game actually uses:
a foreground, bold, dim, and reverse. Everything the screens pass around --
``"bold green"``, ``"dim cyan"``, ``"red"`` -- is parsed here, once, so the
screens can keep speaking the language they were written in.

**Qt-free on purpose.** This is the seam the two front ends share: one of them
turns a :class:`Colour` into a ``QColor`` where it paints, the other hands the
triple to SDL, and neither has to know about the other. It used to hold
``QColor`` objects, which made the theme -- and therefore every screen that reads
it -- impossible to use anywhere Qt is not, which is everywhere a handheld is.
``Colour`` spells itself (``.name()``) exactly as ``QColor`` did, so nothing that
already read a colour had to be told about the change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import NamedTuple

__all__ = ["Colour", "Style", "as_colour", "parse_style", "BACKGROUND", "FOREGROUND"]

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


class Colour(NamedTuple):
    """An RGB triple that knows how to spell itself, and what dimming means.

    A tuple and not a class with fields, because both front ends want it as a
    tuple -- ``QColor(*colour)`` and ``surface.fill(colour)`` -- and because a
    ``Style`` compares and hashes by it, which is what lets the renderer draw a
    *run* of same-styled cells as one string.
    """

    r: int
    g: int
    b: int

    @classmethod
    def parse(cls, word: str) -> Colour | None:
        """A colour from a name or a hex value, or ``None`` if it is not one."""
        if word in NAMED:
            return cls(*NAMED[word])
        if word.startswith("#"):
            digits = word[1:]
            if len(digits) == 3:  # #abc is #aabbcc, the way terminals read it
                digits = "".join(digit * 2 for digit in digits)
            if len(digits) == 6:
                try:
                    return cls(*(int(digits[i : i + 2], 16) for i in (0, 2, 4)))
                except ValueError:
                    return None
            return None
        if word.startswith("grey") or word.startswith("gray"):
            tail = word[4:]
            if tail.isdigit():
                level = max(0, min(100, int(tail))) * 255 // 100
                return cls(level, level, level)
        return None

    def name(self) -> str:
        """The colour as ``#rrggbb``, the way ``QColor.name()`` spells it."""
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def lighter(self, toward_white: float = 0.5) -> Colour:
        """A brighter version of itself: a step toward white.

        The other half of ``dimmed``, and here for the same reason: a wound bites
        in a colour *brighter* than the light it already wears, and how much
        brighter is a fact about the colour rather than about a painter. Toward
        white and not up the value, because the point of the mark is to be *seen*:
        the hue survives -- a brighter red is still red -- and a colour that is
        already as bright as its value allows still has somewhere to go. Half a
        step by default, which is what a mark wants and what Qt's ``lighter(150)``
        comes out at for a saturated colour; for the ones that are not, this is a
        shade lighter still, and that is the honest difference.
        """
        step = max(0.0, min(1.0, toward_white))
        return Colour(
            round(self.r + (255 - self.r) * step),
            round(self.g + (255 - self.g) * step),
            round(self.b + (255 - self.b) * step),
        )

    def dimmed(self) -> Colour:
        """Halfway to the dungeon's own black.

        Toward the background rather than toward black: the phosphor fades, it
        does not switch off, and a remembered wall has to stay a wall. It lives
        here rather than in a renderer because it is a fact about the *style* --
        a dim line is dim whichever front end is drawing it.
        """
        return Colour(
            (self.r + BACKGROUND.r) // 2,
            (self.g + BACKGROUND.g) // 2,
            (self.b + BACKGROUND.b) // 2,
        )


#: The dungeon's own black, and the phosphor the text is drawn in. Not pure
#: black and pure white: a CRT never was, and the scanline pass has nothing to
#: work with against a flat 0 or 255.
BACKGROUND = Colour(0x0B, 0x0B, 0x0B)
FOREGROUND = Colour(0xC8, 0xC8, 0xC8)

#: Style words that are not a colour.
_BOLD = {"bold", "b"}
_DIM = {"dim", "d"}
_REVERSE = {"reverse", "reversed", "r"}
_ITALIC = {"italic", "i"}


def as_colour(value) -> Colour | None:
    """Whatever a caller meant by a colour, as the shared one.

    Duck-typed rather than imported, and that is the whole trick: a ``QColor``
    has ``red``/``green``/``blue`` and so does this, and the theme must not know
    -- or care -- which of them a front end is holding. A hex string is parsed,
    a triple is taken as it is, and anything else is nothing.

    The arena used to build ``Style``s out of ``QColor`` objects it had made
    itself, which is exactly the mixing this ends: one type, understood by
    everybody, normalised where the object is built rather than where it is
    painted.
    """
    if value is None or isinstance(value, Colour):
        return value
    if isinstance(value, str):
        return Colour.parse(value)
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return Colour(*value)
    return None


@dataclass(frozen=True, slots=True)
class Style:
    """A foreground, an optional background, and four flags."""
    fg: Colour = FOREGROUND
    bg: Colour | None = None
    bold: bool = False
    dim: bool = False
    reverse: bool = False
    italic: bool = False
    #: A small integer standing for these six fields, shared by every Style that
    #: has them. The painter asks "is this cell the same style as the one before
    #: it?" a few thousand times a frame, and comparing two integers is the
    #: cheapest way to ask it.
    key: int = field(default=0, init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        # Normalised on the way in, so a Style is *always* made of the shared
        # colours whatever the caller had in hand: a QColor, a hex string, a
        # triple. Nobody downstream has to ask which kind of colour this is.
        object.__setattr__(self, "fg", as_colour(self.fg) or FOREGROUND)
        object.__setattr__(self, "bg", as_colour(self.bg))
        object.__setattr__(self, "key", _style_key(self))

    def __reduce__(self):
        # Through the fields and not the number: a copied style must not carry
        # the key this process happened to mint, which means nothing elsewhere.
        return (
            Style,
            (self.fg, self.bg, self.bold, self.dim, self.reverse, self.italic),
        )


#: The styles seen so far, by their fields: a ``Style`` is frozen, so two of them
#: with the same six fields are the same style and can share a number.
_KEYS: dict[tuple, int] = {}


def _style_key(style: Style) -> int:
    """The number for these fields, minted once and then reused."""
    fields = (style.fg, style.bg, style.bold, style.dim, style.reverse, style.italic)
    key = _KEYS.get(fields)
    if key is None:
        key = len(_KEYS) + 1
        _KEYS[fields] = key
    return key


def parse_style(text: str, base: Style | None = None) -> Style:
    """Read a Rich-ish style string into a :class:`Style`.

    Unknown words are ignored rather than raising: a colour this build has not
    learned is a colour that falls back to the foreground, which is a legible
    screen, and a screen that refuses to draw is not.

    The common call -- a plain string and nothing to build on -- is memoised, and
    not only for the time: the *same* object for the same words is what lets the
    painter compare two cells by identity and hold a run together with a pointer
    check instead of six field comparisons. Formatting a style string is a small
    cost paid a hundred times a frame; a still picture should pay it never.
    """
    if base is None:
        return _parse_style(text)
    return _parse_style_on(text, base)


@lru_cache(maxsize=1024)
def _parse_style(text: str) -> Style:
    """One style string, read once. ``Style`` is frozen, so sharing it is safe."""
    return _parse_style_on(text, Style())


def _parse_style_on(text: str, base: Style) -> Style:
    """The same parse, on top of a style somebody already has in hand."""
    fg = base.fg
    bold, dim, reverse = base.bold, base.dim, base.reverse
    italic = base.italic
    for word in text.replace(",", " ").split():
        word = word.lower()
        if word in _BOLD:
            bold = True
        elif word in _DIM:
            dim = True
        elif word in _REVERSE:
            reverse = True
        elif word in _ITALIC:
            italic = True
        elif word == "on" or word == "not":
            continue
        else:
            colour = Colour.parse(word)
            if colour is not None:
                fg = colour
    return Style(fg=fg, bold=bold, dim=dim, reverse=reverse, italic=italic)


@lru_cache(maxsize=2048)
def style_on(style: Style, bg: Colour) -> Style:
    """The same style lifted onto a panel's colour, and shared.

    A word written onto a panel keeps the panel's background (a cell does not
    lose the box it sits in because a letter landed on it). That rule used to
    make a new `Style` for every character, which is how a screen of text came to
    be a screen of styles that were *equal* and not *the same* -- and why finding
    a run cost six field comparisons per cell instead of a pointer check.
    """
    return Style(
        fg=style.fg,
        bg=bg,
        bold=style.bold,
        dim=style.dim,
        reverse=style.reverse,
        italic=style.italic,
    )
