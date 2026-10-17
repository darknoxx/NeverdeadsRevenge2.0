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
    target = Path((argv or sys.argv[1:] or ["/tmp/sdl_title.png"])[0])

    font = SdlFont(str(FONT))
    grid = PatternBuffer(96, 27)
    TitleScreen().draw(grid, Stub())
    surface = paint(grid, font)
    pygame.image.save(surface, str(target))

    print(f"{target}  {surface.get_width()}x{surface.get_height()}  cell {font.cell_w}x{font.cell_h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
