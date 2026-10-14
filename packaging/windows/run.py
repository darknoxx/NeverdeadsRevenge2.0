"""The entry point PyInstaller freezes.

The package has its own ``__main__``; this exists so the frozen app starts from a
plain script and passes its exit code back.
"""

from __future__ import annotations

import sys

from neverdeads_revenge.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
