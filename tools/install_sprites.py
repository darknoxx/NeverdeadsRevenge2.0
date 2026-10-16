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

And the wounds have pictures of their own -- ``sprites/status/``, one a status
key, which is what the plate wears beside the health bar. Not a view of anything:
a status is a rule, and the icon is what the rule looks like.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

__all__ = ["EXPORTS", "PORTRAITS", "STATUS_SYMBOLS", "main"]

#: The game's own sprite folder, beside the fonts and the sounds.
HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "src" / "neverdeads_revenge" / "desktop" / "sprites"
#: And the other view of the three heroes: seen from the front, which is what
#: the roster needs and what the arena has no use for.
PORTRAITS_OUT = OUT / "portraits"

#: The four wounds, as pictures. Their own folder again, because they are not a
#: *view* of anything: a status is a rule, and this is what the rule looks like
#: on the plate -- the same way the models are what the actors look like in the
#: room. Named for the status's own key and not for the export, since the export
#: says "burning" and the table says "burn".
STATUS_OUT = OUT / "status"

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
    "inferno_back.png": "Inferno.png",
}


#: ``export name -> the name the game asks for``, for the heroes facing the
#: player. The same names as the arena's, in a folder of their own: one actor
#: with two pictures is two *views*, and a folder says so where a file name
#: would have to be told apart by eye.
PORTRAITS: dict[str, str] = {
    "noxx_front.png": "Noxx.png",
    "yeti_front.png": "Yeti.png",
    "walkyrion_front.png": "Walkyrion.png",
    "inferno_front.png": "Inferno.png",
}


#: ``export name -> the status key the game asks for``. `maul` has no export of
#: its own and shares the bleeding one, exactly as it shares the shape its tick
#: makes -- a deep wound and a wound are the same wound, one of them deeper.
STATUS_SYMBOLS: dict[str, str] = {
    "status_bleed.png": "bleed.png",
    "status_poison.png": "poison.png",
    "status_burning.png": "burn.png",
    "status_frozen.png": "chill.png",
}


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    source = Path(args[0] if args else "~/Vibecoding/grafiken_kampfsystem").expanduser()
    missing = []
    # Three tables, and where each one's exports live in the sheets folder: the
    # models and the portraits sit at the top of it, and the wound symbols have
    # a folder of their own, which is how they were handed over.
    for table, under, into in (
        (EXPORTS, "", OUT),
        (PORTRAITS, "", PORTRAITS_OUT),
        (STATUS_SYMBOLS, "status", STATUS_OUT),
    ):
        into.mkdir(parents=True, exist_ok=True)
        for export, name in table.items():
            origin = (source / under if under else source) / export
            if not origin.exists():
                missing.append(export)
                continue
            shutil.copyfile(origin, into / name)
            where = name if into is OUT else f"{into.name}/{name}"
            print(f"{export:26s} -> {where}")
    if missing:
        print(f"missing: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
