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

Two views, and the difference is which way the actor is facing. The arena's
`heroes` are exported from behind -- they stand with their backs to the camera,
facing the monsters -- and the roster's `portraits` are the same three seen from
the front, because a hero standing in a menu has nobody to face but the player.
Both fall back to the letter, and both fall back independently.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage

__all__ = ["SPRITES_DIR", "PORTRAITS_DIR", "clear", "portrait", "sprite"]

#: The art that travels with the game, beside the fonts and the sounds.
SPRITES_DIR = Path(__file__).resolve().parent / "sprites"

#: And the heroes seen from the front, for the screens that stand them in front
#: of the player with nothing to fight.
PORTRAITS_DIR = SPRITES_DIR / "portraits"

_LOADED: dict[Path, QImage | None] = {}


def _load(path: Path) -> QImage | None:
    """One picture off the disk, asked once and remembered -- including the
    nothing, because a fight asks this every frame and a directory lookup per
    frame per monster is a lot of asking to arrive at the same answer.
    """
    if path in _LOADED:
        return _LOADED[path]
    image = QImage(str(path)) if path.exists() else None
    _LOADED[path] = image if image is not None and not image.isNull() else None
    return _LOADED[path]


def sprite(name: str) -> QImage | None:
    """The arena's view of ``name``: monsters facing the hero, and the three
    heroes from behind. ``None`` when the sheets have never heard of it.
    """
    return _load(SPRITES_DIR / f"{name}.png")


def portrait(name: str) -> QImage | None:
    """The roster's view of ``name``: the hero facing whoever is choosing.

    Its own lookup rather than a flag on `sprite`, because the two are two
    pictures rather than one picture drawn two ways -- and because a hero with a
    back and no front should fall back to the letter on the roster without
    falling back to it in the arena.
    """
    return _load(PORTRAITS_DIR / f"{name}.png")


def clear() -> None:
    """Forget what has been loaded. For tests, and for nothing else."""
    _LOADED.clear()
