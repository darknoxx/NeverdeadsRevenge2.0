#!/usr/bin/env python3
"""The probe: a real screen, drawn by SDL instead of Qt.

Not a test and not a build -- a *question*, asked once and answered in a picture:
can the game's own panels be painted by something that is not Qt, with the same
cells and the same typeface, without touching a line of the game?

The answer is in what this writes. It draws the *real* title screen, through the
*real* ``TitleScreen.draw`` and the *real* ``PatternBuffer``, and hands the cells
to ``sdl_front.paint`` -- which knows about SDL and nothing else. The only thing
standing in for the app is the two attributes that screen actually reads, which
is the measurement worth having: a screen whose whole interface is a buffer, a
key name and two questions about the run is a screen that can be shown anywhere.

Run it beside ``tools/qt_probe.py`` and look at the two images:

    python tools/sdl_probe.py /tmp/sdl_title.png
    python tools/qt_probe.py /tmp/qt_title.png

It also writes the *arena*, which is the harder question and the one the port
turned on for a whole session. A fight is the one screen that is not just a grid:
under Qt it is painted, and the painting is pixels. This draws it through the
*same* ``BattleScreen.draw`` the Qt build uses -- the plate, the log, the verbs,
the order strip and the monsters' health bars are cell work and always were --
and stages the figures as the letters they have always been. One round is then
fought, so the log in the picture is a real round and not an empty panel:

    python tools/sdl_probe.py /tmp/sdl.png /tmp/sdl_arena.png /tmp/sdl_roster.png

The third picture is the roster, and it is the first *art* on this side of the
seam: a screen hands over ``Placed`` records -- what, and where -- and this
application puts them down. The same records the Qt build reads.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from neverdeads_revenge.desktop.pattern import PatternBuffer  # noqa: E402
from neverdeads_revenge.desktop.screens.title import TitleScreen  # noqa: E402
from neverdeads_revenge.sdl_front.font import SdlFont  # noqa: E402
from neverdeads_revenge.sdl_front.paint import paint  # noqa: E402

FONT = ROOT / "src" / "neverdeads_revenge" / "desktop" / "fonts" / "DejaVuSansMono.ttf"


class Stub:
    """The whole app, as far as the title screen is concerned.

    Two attributes and one question -- that is the interface between a screen and
    the thing drawing it, which is the reason any of this is possible at all. A
    screen that needed the application would be a screen that could only be shown
    by the application.
    """

    class Progress:
        best_score = 4120

    def __init__(self) -> None:
        self.progress = self.Progress()

    def has_saved_run(self) -> bool:
        return True


def main(argv: list[str] | None = None) -> int:
    import pygame

    pygame.init()
    given = list(argv if argv is not None else sys.argv[1:])
    target = Path(given[0]) if given else Path("/tmp/sdl_title.png")
    arena_target = Path(given[1]) if len(given) > 1 else None
    roster_target = Path(given[2]) if len(given) > 2 else None

    font = SdlFont(str(FONT))
    grid = PatternBuffer(96, 27)
    TitleScreen().draw(grid, Stub())
    surface = paint(grid, font)
    pygame.image.save(surface, str(target))

    print(
        f"{target}  {surface.get_width()}x{surface.get_height()}"
        f"  cell {font.cell_w}x{font.cell_h}"
    )

    if arena_target is not None:
        fight = _drawn_into_a_fight()
        pygame.image.save(fight, str(arena_target))
        print(
            f"{arena_target}  {fight.get_width()}x{fight.get_height()}"
            "  the arena, one round in"
        )

    if roster_target is not None:
        roster = _standing_on_the_roster()
        pygame.image.save(roster, str(roster_target))
        print(
            f"{roster_target}  {roster.get_width()}x{roster.get_height()}"
            "  the roster, with the hero painted on it"
        )
    return 0


def _standing_on_the_roster(seed: int = 3):
    """The roster, on a front end with no QPainter: two keys and a real run.

    The hero on the card is there because the screen *asked* for it and this
    application blitted it -- which is the whole of what the ``Placed`` records
    are for, and the thing a picture can show and a sentence cannot.
    """
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=seed)
    app.key("enter")  # NEW RUN
    return app._surface


def _drawn_into_a_fight(seed: int = 3):
    """A real fight, reached the way a player reaches one: by walking into it.

    Nothing is faked and nothing is skipped: the same ``open_fight`` the game
    calls builds the room, the same screen draws the panels, and the round in the
    picture was decided by the rules. Three monsters are put on the floor so the
    staging has something to stage -- that is a fixture, and it is the only line
    here that is.
    """
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy
    from neverdeads_revenge.sdl_front.app import SdlApp
    from neverdeads_revenge.world.tiles import Tile

    app = SdlApp(seed=seed)
    app.key("enter")  # NEW RUN
    app.key("enter")  # the first hero

    state = app.run
    here = state.player.position
    beside = (here[0] + 1, here[1])
    for name, spot in (("viper", beside), ("ghoul", (here[0], here[1] - 1)), ("ooze", here)):
        if spot != here:
            state.dungeon_map.set_tile(spot, Tile.FLOOR)
        monster = make_enemy(ENEMIES[name], spot)
        state.enemies.append(monster)
        state.turn_queue.add(monster)
    state.refresh_vision()
    app.key("right")  # into them
    app.key("a")  # ATTACK
    app.key("enter")  # and swing
    return app._surface


if __name__ == "__main__":
    raise SystemExit(main())
