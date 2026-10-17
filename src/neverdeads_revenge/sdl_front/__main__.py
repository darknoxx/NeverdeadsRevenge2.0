"""Entry point: ``python -m neverdeads_revenge.sdl_front``.

The same door as ``ndr2 --sdl``, for a checkout that has not been installed --
which is how a second front end is looked at while it is being built. The flags
are the ones worth having for looking: a seed, the dev door into the arena, and
how many screen pixels to a game pixel.
"""

from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ndr2-sdl",
        description="Neverdead's Revenge 2.0, drawn by SDL: no Qt in the room.",
    )
    parser.add_argument("--seed", type=int, default=None, metavar="N")
    parser.add_argument(
        "--battle-scene",
        action="store_true",
        help="open the arena straight away, against a fresh floor's first monsters",
    )
    parser.add_argument(
        "--scale", type=int, default=1, metavar="N", help="screen pixels per game pixel"
    )
    parser.add_argument(
        "--no-sound", action="store_true", help="start with the sound off"
    )
    parser.add_argument(
        "--testrun",
        action="store_true",
        help="unlock the chronicle and fill the purse, then play (a test save)",
    )
    parser.add_argument(
        "--sound-log",
        nargs="?",
        const="",
        metavar="PATH",
        help="write every sound decision to PATH (default: in the temp dir)",
    )
    parser.add_argument(
        "--no-backdrop",
        action="store_true",
        help="draw the arena's own flagstones and walls instead of the painting",
    )
    parser.add_argument(
        "--fps", action="store_true", help="show a frame counter in the corner"
    )
    args = parser.parse_args(argv)

    if args.sound_log is not None:
        import tempfile

        path = args.sound_log or os.path.join(
            tempfile.gettempdir(), "ndr2-sound.log"
        )
        os.environ["NEVERDEADS_REVENGE_SOUND_LOG"] = path
    if args.testrun:
        from ..persistence import grant_test_save

        grant_test_save()

    from .app import SdlApp

    window = SdlApp(
        seed=args.seed,
        scale=args.scale,
        no_sound=args.no_sound,
        battle_scene=args.battle_scene,
        fps=args.fps,
        backdrop=not args.no_backdrop,
    )
    window.open_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
