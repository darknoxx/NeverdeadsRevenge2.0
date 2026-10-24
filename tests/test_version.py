"""The version is one number, written in two places."""

from __future__ import annotations

import tomllib
from pathlib import Path

from neverdeads_revenge import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_the_project_and_the_package_agree_on_the_version():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == __version__
