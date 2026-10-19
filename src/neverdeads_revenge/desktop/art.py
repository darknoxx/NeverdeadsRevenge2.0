"""Where the art is, and what a screen asks for when it wants some on the frame.

The art is PNG files that travel with the game. Their *paths* used to live inside
the two Qt loaders, which meant anything that wanted to know where a sprite was
had to import Qt to ask -- and a second front end that must not have Qt cannot ask
a question like that. So the paths live here, in a module with no toolkit in it,
and that is all a front end needs from the art: the file, and a place to put it.

And a screen that wants a picture on the frame does not paint it. It says *what*
and *where* -- a ``Placed`` -- and whichever application is drawing blits it. That
is the same shape the verdict panel and the arena's floor already had, said out
loud here: the game says what a thing is, the painter says how it lands.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ART_ROOT",
    "PORTRAITS_DIR",
    "SPRITES_DIR",
    "STATUS_DIR",
    "TILES_DIR",
    "Placed",
    "exists",
    "path",
    "size",
]

#: The art that travels with the game, beside the fonts and the sounds.
ART_ROOT = Path(__file__).resolve().parent

#: The figures, and the two families that hang off them: the heroes seen from the
#: front with nothing to fight, and the wounds, one a status key.
SPRITES_DIR = ART_ROOT / "sprites"
PORTRAITS_DIR = SPRITES_DIR / "portraits"
STATUS_DIR = SPRITES_DIR / "status"

#: And the stone the rooms are made of.
TILES_DIR = ART_ROOT / "tiles"


@dataclass(frozen=True)
class Placed:
    """A picture, and where on the frame it goes.

    Held as ``centre`` and ``bottom`` rather than as a rectangle, because that is
    how the game thinks about a painted figure: fitted to a *height*, centred on a
    line, standing on it. Every portrait stands the same height on the same line,
    which is the whole of what a roster row is for -- and the width follows from
    the picture's own shape, which the front end has in hand and the screen does
    not.
    """

    art: str
    centre: float
    bottom: float
    height: int


def path(name: str) -> Path:
    """A piece of art by its path inside the art, e.g. ``sprites/ghoul.png``."""
    return ART_ROOT / name


def exists(name: str) -> bool:
    """Whether that piece of art is really there.

    Asked by the screens that draw a letter when the sheets have nothing for a
    hero: a card that promises a figure and then shows a blank band is a card
    that lied, and the alphabet is what is underneath every picture in this game.
    """
    return path(name).exists()


def size(name: str) -> tuple[int, int] | None:
    """How big that piece of art is in pixels, or ``None`` if it cannot be read.

    Read out of the file's own header instead of through a toolkit, because it is
    the *game* that asks: a figure's shadow is as wide as the figure is, and how
    wide a picture is is a fact about the picture. Eight bytes of PNG -- the
    signature, the chunk header, then width and height, big-endian -- and both
    front ends get the same answer without either of them being involved.
    """
    return _size_in(name)


@functools.lru_cache(maxsize=None)
def _size_in(name: str) -> tuple[int, int] | None:
    """The header read, once per picture.

    Every call is a file open, and the arena asks per figure per frame -- ten
    opens a frame for numbers that cannot change, since the art ships with the
    game. Cached here rather than at the caller because every caller has the same
    right to the same answer.
    """
    address = path(name)
    try:
        header = address.read_bytes()[:24]
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return (
        int.from_bytes(header[16:20], "big"),
        int.from_bytes(header[20:24], "big"),
    )
