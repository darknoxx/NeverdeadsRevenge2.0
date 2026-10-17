"""Entry point: ``python -m neverdeads_revenge``, or the ``ndr2`` script."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile


def main(argv: list[str] | None = None) -> int:
    """Run the desktop game."""
    parser = argparse.ArgumentParser(
        prog="ndr2",
        description="Neverdead's Revenge 2.0 -- the same dungeon, on a CRT.",
    )
    parser.add_argument(
        "--no-sound",
        action="store_true",
        help="start with the sound off, whatever the save file says",
    )
    parser.add_argument(
        "--sound-log",
        nargs="?",
        const="",
        metavar="PATH",
        help="write every sound decision to PATH (default: sound.log in the temp dir)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="N",
        help="run the dungeon this seed generated, for a repeatable run",
    )
    parser.add_argument(
        "--testrun",
        action="store_true",
        help="unlock the chronicle and fill the purse, then play (a test save)",
    )
    parser.add_argument(
        "--battle-scene",
        action="store_true",
        help="open the arena straight away, against a fresh floor's first monsters",
    )
    parser.add_argument(
        "--sdl",
        action="store_true",
        help=(
            "run the second front end instead: the same game, drawn by SDL and "
            "pygame, with no Qt anywhere in it"
        ),
    )
    parser.add_argument(
        "--fps",
        action="store_true",
        help="show a frame counter in the corner (second front end)",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=1,
        metavar="N",
        help="how many screen pixels per game pixel on the second front end (default 1)",
    )
    args = parser.parse_args(argv)

    if args.sound_log is not None:
        # No value means the temp directory, which exists and is writable on
        # every platform -- a hard "/tmp" is a path Windows does not have.
        path = args.sound_log or os.path.join(
            tempfile.gettempdir(), "ndr2-sound.log"
        )
        os.environ["NEVERDEADS_REVENGE_SOUND_LOG"] = path

    if args.sdl:
        # Before anything touches Qt, and that is the point of this door: the
        # second front end runs on a machine where PySide6 is not installed at
        # all, so the flag has to be answered before the import below.
        from .sdl_front.app import SdlApp

        window = SdlApp(
            seed=args.seed,
            scale=args.scale,
            no_sound=args.no_sound,
            battle_scene=args.battle_scene,
            fps=args.fps,
        )
        window.open_window()
        return 0

    # Wayland's input-method plumbing logs a protest at every surface change
    # ("trying to disable a surface nothing is focused on") -- a known Qt
    # quirk, and pure noise for a game that does all of its own input
    # handling. Silenced before Qt starts; nothing else in qt.qpa is muted.
    from PySide6.QtCore import QLoggingCategory

    QLoggingCategory.setFilterRules("qt.qpa.wayland.textinput=false\n")

    if args.testrun:
        from .persistence import grant_test_save

        grant_test_save()

    from PySide6.QtWidgets import QApplication

    from .desktop.app import DesktopApp

    app = QApplication(sys.argv[:1])
    window = DesktopApp(
        seed=args.seed,
        no_sound=args.no_sound,
        testrun=args.testrun,
        battle_scene=args.battle_scene,
    )
    window.resize(1280, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
