#!/usr/bin/env python3
"""The release version: the package, the project file and the tag.

CI runs it on a tag, where all three have to agree. A local run compares the
first two; the tag is only read when the environment says this is a build.
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

from neverdeads_revenge import __version__

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    if version != __version__:
        print(
            f"pyproject says {version}, the package says {__version__}",
            file=sys.stderr,
        )
        return 1
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if tag.startswith("v") and tag != f"v{version}":
        print(f"tag {tag} but the code says v{version}", file=sys.stderr)
        return 1
    print(f"version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
