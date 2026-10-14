"""The painted sprites, for the arena.

The dungeon is an alphabet and the arena was one too, until the art arrived:
these are the monsters and the heroes as pictures, cut from the two contact
sheets by ``tools/cut_sprites.py`` and shipped beside the fonts (a sprite
travels with the game for the same reason the font does -- the look should not
depend on what the machine happens to have).

They are loaded once, by name, and a name with no art is not an error: the
arena draws the *letter* instead, which is what the whole game looked like
before and what a monster a sheet has never heard of should still be. That is
the fallback that makes this safe to ship -- a fight is never missing a fighter,
only sometimes missing a picture of one.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage

__all__ = ["SPRITES_DIR", "clear", "sprite"]

#: The art that travels with the game, beside the fonts and the sounds.
SPRITES_DIR = Path(__file__).resolve().parent / "sprites"

_LOADED: dict[str, QImage | None] = {}


def sprite(name: str) -> QImage | None:
    """The picture of ``name``, or ``None`` if there is none.

    Asked once per actor and remembered, including the nothing: a fight asks
    this every frame, and a directory lookup per frame per monster is a lot of
    asking to arrive at the same answer.
    """
    if name in _LOADED:
        return _LOADED[name]
    path = SPRITES_DIR / f"{name}.png"
    image = QImage(str(path)) if path.exists() else None
    _LOADED[name] = image if image is not None and not image.isNull() else None
    return _LOADED[name]


def clear() -> None:
    """Forget what has been loaded. For tests, and for nothing else."""
    _LOADED.clear()
