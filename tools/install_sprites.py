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

#: And the blades, one picture each, in a folder of their own: an item is not a
#: figure, and the shop and the card ask for a *picture of a thing* rather than a
#: view of an actor. Named for the item's key, because that is what the card has
#: in hand when it wants to show what was just picked up.
WEAPONS_OUT = OUT / "weapons"

#: How much smaller a model is installed than it was exported.
#:
#: The monsters come at twice the size the room uses. A *whole* multiple, so
#: halving them is a box of four pixels into one: every edge keeps the shape it was
#: drawn with, and nothing is resampled by a fraction -- which is what makes a
#: painted sprite look resampled. The heroes come at the size they are meant to
#: stand, so they are only trimmed.
MONSTER_SCALE = 0.5

#: ``export -> (the name the game asks for, the scale it is installed at)``.
#:
#: Spelled out rather than derived, because a typo in an export is a typo in a file
#: name and nothing should have to guess what "yedti" wants to be. A name that is
#: not in the folder is reported and left alone: a missing export is a letter on
#: the floor, not a broken fight.
EXPORTS: dict[str, tuple[str, float]] = {
    "ghoul.png": ("ghoul.png", MONSTER_SCALE),
    "skeleton.png": ("skeleton.png", MONSTER_SCALE),
    "viper.png": ("viper.png", MONSTER_SCALE),
    "ooze.png": ("ooze.png", MONSTER_SCALE),
    "mound.png": ("mound.png", MONSTER_SCALE),
    "hunter.png": ("hunter.png", MONSTER_SCALE),
    "wraith.png": ("wraith.png", MONSTER_SCALE),
    # Noxx keeps his shadow in both views -- it is his look, not a summon that
    # happened to be painted in. The export named "transparent" is the arena's and
    # the newest of the two; Atritas also has a sheet of his own, for the trick
    # that calls him into the room.
    "noxx_back_transparent.png": ("Noxx.png", 1.0),
    "yeti_back.png": ("Yeti.png", 1.0),
    "walkyrion_back.png": ("Walkyrion.png", 1.0),
    "inferno_back.png": ("Inferno.png", 1.0),
    "atritas_back.png": ("atritas.png", 1.0),
    # The seven whose worth is a question. Their exports keep the article the
    # *log* puts in front of them ("The kindly one strikes you"); the game's name
    # does not, so the file the arena asks for has no "the" in it.
    "the_kindly_one.png": ("kindly_one.png", MONSTER_SCALE),
    "the_hush.png": ("hush.png", MONSTER_SCALE),
    "the_already-dying.png": ("already-dying.png", MONSTER_SCALE),
    "the_briar.png": ("briar.png", MONSTER_SCALE),
    "the_picker.png": ("picker.png", MONSTER_SCALE),
    "the_lid.png": ("lid.png", MONSTER_SCALE),
}


#: The heroes facing the player, at the size they are drawn: what the roster wants
#: and what the arena has no use for.
PORTRAITS: dict[str, tuple[str, float]] = {
    "noxx_front.png": ("Noxx.png", 1.0),
    "yeti_front.png": ("Yeti.png", 1.0),
    "walkyrion_front.png": ("Walkyrion.png", 1.0),
    "inferno_front.png": ("Inferno.png", 1.0),
}


#: ``export name -> the status key the game asks for``. `maul` has no export of
#: its own and shares the bleeding one, exactly as it shares the shape its tick
#: makes -- a deep wound and a wound are the same wound, one of them deeper.
#: ``export -> (the item key the game asks for, the scale)``. The blades are
#: painted at the size the card draws them, so they are only trimmed. Still being
#: painted: a key that is not here gets the placeholder, which is why this table
#: can grow one file at a time.
WEAPONS: dict[str, tuple[str, float]] = {
    "the_hummingbird.png": ("hummingbird.png", 1.0),
    "the_frostbite.png": ("frostbite.png", 1.0),
    "the_pyre.png": ("pyre.png", 1.0),
    "the_marksman.png": ("marksman.png", 1.0),
    "the_gambler.png": ("gambler.png", 1.0),
    "the_patient.png": ("patient.png", 1.0),
    "the_numb.png": ("numbing.png", 1.0),
    "the_runed_edge.png": ("edge.png", 1.0),
    "the_last_argument.png": ("argument.png", 1.0),
    "grave_iron.png": ("grave.png", 1.0),
    "the_blood_price.png": ("blood_price.png", 1.0),
    "the_ash_kiss.png": ("kiss.png", 1.0),
    "the_thunderclap.png": ("thunder.png", 1.0),
    "the_depthless.png": ("depthless.png", 1.0),
}


#: And one picture for the blades that have none yet. Drawn here rather than
#: handed over, because it is not art: it is the shape of a promise -- a frame and
#: a question mark, in the same ash the rest of the game is written in.
def write_placeholder(target: Path) -> None:
    import pygame

    face = pygame.font.Font(str(HERE / "src" / "neverdeads_revenge" / "desktop"
                                 / "fonts" / "DejaVuSansMono-Bold.ttf"), 64)
    size = 120
    image = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(image, (70, 70, 78), image.get_rect().inflate(-10, -10),
                     width=2, border_radius=8)
    mark = face.render("?", True, (128, 128, 138))
    image.blit(mark, mark.get_rect(center=(size // 2, size // 2)))
    target.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(image, str(target))


STATUS_SYMBOLS: dict[str, str] = {
    "status_bleed.png": "bleed.png",
    "status_poison.png": "poison.png",
    "status_burning.png": "burn.png",
    "status_frozen.png": "chill.png",
}


def install_picture(origin: Path, target: Path, scale: float) -> tuple[int, int]:
    """One export, trimmed of its canvas and installed at the game's own size.

    The exports arrive on a square canvas with a margin around the figure. The
    arena stands a figure on the room's floor by its *bottom edge*, so a margin
    under the feet is a hero floating above the ground -- which is why the trim
    comes first, and why it is here rather than in a second script.

    And then the scale, with ``smoothscale``: at a half that is a box of four
    pixels into one, which is the right way down and keeps the drawing; a
    nearest-neighbour pick would keep one of four and throw away the edge it did
    not pick.
    """
    import pygame

    image = pygame.image.load(str(origin)).convert_alpha()
    image = image.subsurface(image.get_bounding_rect(8)).copy()
    if scale != 1.0:
        image = pygame.transform.smoothscale(
            image,
            (
                max(1, round(image.get_width() * scale)),
                max(1, round(image.get_height() * scale)),
            ),
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(image, str(target))
    return image.get_size()


def main(argv: list[str] | None = None) -> int:
    import pygame

    pygame.init()
    pygame.display.set_mode((64, 64))

    args = argv if argv is not None else sys.argv[1:]
    source = Path(args[0] if args else "~/Vibecoding/grafiken_kampfsystem").expanduser()
    missing = []
    # Three tables, and where each one's exports live in the sheets folder: the
    # models and the portraits sit at the top of it, and the wound symbols have
    # a folder of their own, which is how they were handed over.
    for table, under, into in (
        (EXPORTS, "", OUT),
        (PORTRAITS, "", PORTRAITS_OUT),
        (WEAPONS, "weapons", WEAPONS_OUT),
    ):
        into.mkdir(parents=True, exist_ok=True)
        for export, (name, scale) in table.items():
            origin = (source / under if under else source) / export
            if not origin.exists():
                missing.append(export)
                continue
            size = install_picture(origin, into / name, scale)
            where = name if into is OUT else f"{into.name}/{name}"
            print(f"{export:26s} -> {where:22s} {size[0]}x{size[1]}")
    # The wound symbols are pictures already at the size they are drawn: copied,
    # not trimmed, because their canvas is the slot they are fitted into.
    if STATUS_SYMBOLS:
        STATUS_OUT.mkdir(parents=True, exist_ok=True)
        for export, name in STATUS_SYMBOLS.items():
            origin = source / "status" / export
            if not origin.exists():
                missing.append(export)
                continue
            shutil.copyfile(origin, STATUS_OUT / name)
            print(f"{export:26s} -> status/{name}")
    # The one picture that is made here rather than handed over: the card's
    # placeholder for a blade that has not been painted yet.
    write_placeholder(WEAPONS_OUT / "_placeholder.png")
    if missing:
        print(f"missing: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
