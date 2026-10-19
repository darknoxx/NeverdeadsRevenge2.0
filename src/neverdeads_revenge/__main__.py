"""Entry point: ``python -m neverdeads_revenge``, or the ``ndr2`` script.

There is one door now. The game was built twice for a while -- once on Qt and
once on SDL -- and the SDL one is the game: it plays the same run, draws the same
room, and does it with a window that also builds for Windows and, in time, for
Android. So this file no longer asks *which* front end to start; it starts the
one that is left.
"""

from __future__ import annotations

import argparse
import os
import tempfile


def main(argv: list[str] | None = None) -> int:
    """Run the game."""
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
        help="ignored: kept so that an old shortcut still starts the game",
    )
    parser.add_argument(
        "--no-backdrop",
        action="store_true",
        help="draw the arena's own flagstones and walls instead of the painting",
    )
    parser.add_argument(
        "--fps",
        action="store_true",
        help="show a frame counter in the corner",
    )
    parser.add_argument(
        "--sniff",
        action="store_true",
        help="start on the pad bench: every axis, button and hat, raw",
    )
    parser.add_argument(
        "--display",
        action="store_true",
        help="print what this machine says about its display, and stop",
    )
    parser.add_argument(
        "--timings",
        action="store_true",
        help="print what each stage of the frame costs, once a second",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=1,
        metavar="N",
        help="how many screen pixels per game pixel (default 1)",
    )
    args = parser.parse_args(argv)

    if args.sound_log is not None:
        # No value means the temp directory, which exists and is writable on
        # every platform -- a hard "/tmp" is a path Windows does not have.
        path = args.sound_log or os.path.join(
            tempfile.gettempdir(), "ndr2-sound.log"
        )
        os.environ["NEVERDEADS_REVENGE_SOUND_LOG"] = path

    if args.display:
        from .sdl_front.app import SdlApp

        for line in SdlApp(
            seed=args.seed,
            scale=args.scale,
            no_sound=True,
            backdrop=not args.no_backdrop,
        ).display_report():
            print(line)
        return 0

    if args.testrun:
        from .persistence import grant_test_save

        grant_test_save()

    from .sdl_front.app import SdlApp

    window = SdlApp(
        seed=args.seed,
        scale=args.scale,
        no_sound=args.no_sound,
        battle_scene=args.battle_scene,
        fps=args.fps,
        timings=args.timings,
        sniff=args.sniff,
        backdrop=not args.no_backdrop,
    )
    window.open_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
