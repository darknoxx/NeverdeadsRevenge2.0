"""Entry point: ``python -m neverdeads_revenge``, or the ``ndr2`` script."""

from __future__ import annotations

import argparse
import os
import sys


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
        const="/tmp/ndr2-sound.log",
        metavar="PATH",
        help="write every sound decision to PATH (default /tmp/ndr2-sound.log)",
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
    args = parser.parse_args(argv)

    if args.sound_log:
        os.environ["NEVERDEADS_REVENGE_SOUND_LOG"] = args.sound_log

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
    window = DesktopApp(seed=args.seed, no_sound=args.no_sound, testrun=args.testrun)
    window.resize(1280, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
