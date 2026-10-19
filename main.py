"""The entry point Android runs.

python-for-android's SDL2 bootstrap runs ``main.py`` from the *top* of the
directory it was handed, which is why this one file sits at the repository root
and not in ``packaging/android`` with the rest of the Android work: the source
directory is the repository, so the entry point has to be here. Everything else
-- the build spec, the vendored recipe, the notes -- lives in ``packaging/android``.

The game itself is a package under ``src/``, the layout the desktop build uses
and the reason both the wheel and the PyInstaller spec name a package rather than
a file. So this puts ``src`` on the path and hands over to the very same entry
point the desktop runs (``python -m neverdeads_revenge``), with no arguments: a
handheld launch has no command line to parse.

It is deliberately this small. Everything the game *is* -- the screens, the rules,
the sounds -- is behind that one call, which is what makes the Android build the
same game and not a port of it.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from neverdeads_revenge.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main([]))
