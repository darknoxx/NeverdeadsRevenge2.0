"""Draw the PNG an AppImage carries at its root.

Run it once with the repository's own virtualenv, and commit the result:

    ./.venv/bin/pip install PySide6   # a one-off tool, not a runtime dependency
    ./.venv/bin/python packaging/linux/make_icon.py

An AppImage wants a PNG whose name matches the ``Icon=`` line of its desktop
entry, and the launchers read the 256 pixel one. The drawing is shared with the
Windows icon in ``packaging/mark.py``; only the container is different.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from mark import SVG, render  # noqa: E402 - the path above has to be set first

#: The size the AppImage specification asks for, and the one a launcher draws.
SIZE = 256

OUT = HERE / "neverdeads-revenge-2.png"


def main() -> int:
    OUT.write_bytes(render(SVG.read_bytes(), SIZE))
    print(f"wrote {OUT.name} ({OUT.stat().st_size} bytes, {SIZE}x{SIZE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
