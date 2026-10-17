"""The arena's own stone, painted rather than typed.

The dungeon is an alphabet and the arena was one too, until the art arrived.
Monsters came back as paintings and the room they stood in was still made of
``#`` -- a sprite in a spreadsheet -- so the room is painted now too, by
``tools/make_tiles.py``, and shipped beside the fonts and the sounds.

The alphabet is still underneath all of it. The grid floor is drawn first and the
tiles are pasted over it, so a machine with no art in it gets the room the arena
has always had, in the same place, and a fight is never missing a *room* -- only
sometimes missing a picture of one. That is the same bargain the sprites make.
"""

from __future__ import annotations

from PySide6.QtGui import QImage

from .art import TILES_DIR

__all__ = ["TILES_DIR", "clear", "tile"]

_LOADED: dict[str, QImage | None] = {}


def tile(name: str) -> QImage | None:
    """The tile called ``name``, or ``None`` if there is none.

    Asked once per tile and remembered, including the nothing: the room is
    painted every frame, and a directory lookup per frame is a lot of asking to
    arrive at the same answer.
    """
    if name in _LOADED:
        return _LOADED[name]
    path = TILES_DIR / f"{name}.png"
    image = QImage(str(path)) if path.exists() else None
    _LOADED[name] = image if image is not None and not image.isNull() else None
    return _LOADED[name]


def clear() -> None:
    """Forget what has been loaded. For tests, and for nothing else."""
    _LOADED.clear()
