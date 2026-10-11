"""The things the player set, kept between runs.

Not the save: a run and its progress live in ``meta.json``, and this is only the
glass -- the zoom, and which CRT effects are on. It is deliberately a separate
little file that a corrupt version of can be thrown away without touching a
score.
"""

from __future__ import annotations

import json
import os

from neverdeads_revenge.persistence import data_dir

__all__ = ["load_settings", "save_settings", "settings_path"]


def settings_path():
    """Where the desktop settings live."""
    return data_dir() / "settings.json"


def load_settings() -> dict:
    """The settings as written, or an empty dict if there are none to read."""
    try:
        payload = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_settings(settings: dict) -> None:
    """Write the settings, atomically -- staged to a sibling file and renamed
    in, the same rule the meta save keeps. A settings file that cannot be
    written is not worth failing a game over."""
    try:
        settings_path().parent.mkdir(parents=True, exist_ok=True)
        staging = settings_path().with_name("settings.json.tmp")
        staging.write_text(json.dumps(settings), encoding="utf-8")
        os.replace(staging, settings_path())
    except OSError:
        pass
