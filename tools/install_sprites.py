"""Install the battle sprites: from the export folder into the game.

The sheets are exported as one picture per actor, and the export names them for
the eye -- ``ghoul_front``, ``noxx_back``, and once ``yedti_back`` -- while the
game looks a picture up by the actor's own name. This is the small step between
the two: copy each export to the name the arena asks for, and say what it did.

    python tools/install_sprites.py ~/Vibecoding/grafiken_kampfsystem

The monsters are exported from the front (they face the hero, who stands below
them on screen) and the heroes from behind (they face away, at the monsters).
Both are only ever *asked* for by name: `desktop/sprites.py` draws the letter
when a name has no picture, which is what makes this a copy rather than a build
step -- a missing export is a letter on the floor, not a broken fight.

The heroes have a *second* view, and it is the one the roster wants: standing in
the hero select with nobody to fight, they face the player. So they live in
``sprites/portraits/`` under their own names, and a screen that wants the hero
looking at the camera asks `portrait("Noxx")` rather than `sprite("Noxx")`.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

__all__ = ["EXPORTS", "main"]

#: The game's own sprite folder, beside the fonts and the sounds.
HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "src" / "neverdeads_revenge" / "desktop" / "sprites"
#: And the other view of the three heroes: seen from the front, which is what
#: the roster needs and what the arena has no use for.
PORTRAITS_OUT = OUT / "portraits"

#: ``export name -> the name the game asks for``. Spelled out rather than
#: derived, because a typo in an export is a typo in a file name and nothing
#: should have to guess what "yedti" wants to be.
EXPORTS: dict[str, str] = {
    "ghoul_front.png": "ghoul.png",
    "skeleton_front.png": "skeleton.png",
    "viper_front.png": "viper.png",
    "ooze_front.png": "ooze.png",
    "mound_front.png": "mound.png",
    "hunter_front.png": "hunter.png",
    "wraith_front.png": "wraith.png",
    "noxx_back.png": "Noxx.png",
    "yedti_back.png": "Yeti.png",
    "walkyrion_back.png": "Walkyrion.png",
}


#: ``export name -> the name the game asks for``, for the heroes facing the
#: player. The same names as the arena's, in a folder of their own: one actor
#: with two pictures is two *views*, and a folder says so where a file name
#: would have to be told apart by eye.
PORTRAITS: dict[str, str] = {
    "noxx_front.png": "Noxx.png",
    "yeti_front.png": "Yeti.png",
    "walkyrion_front.png": "Walkyrion.png",
}


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    source = Path(args[0] if args else "~/Vibecoding/grafiken_kampfsystem").expanduser()
    missing = []
    for table, into in ((EXPORTS, OUT), (PORTRAITS, PORTRAITS_OUT)):
        into.mkdir(parents=True, exist_ok=True)
        for export, name in table.items():
            origin = source / export
            if not origin.exists():
                missing.append(export)
                continue
            shutil.copyfile(origin, into / name)
            where = name if into is OUT else f"portraits/{name}"
            print(f"{export:26s} -> {where}")
    if missing:
        print(f"missing: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
