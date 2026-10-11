"""Shared test setup.

Two things have to happen before anything else, and both of them are about a
test run not reaching out of its own sandbox.

The save file goes to a throwaway directory: ``persistence`` reads
``NEVERDEADS_REVENGE_HOME`` first, and without this every UI test would read and
*write* the real ``~/.local/share/neverdeads_revenge/meta.json`` -- so running
the suite would quietly rewrite the player's high score.

And the sound is muted. ``ui.audio`` looks for ``aplay`` or ``paplay`` on the
machine and plays through it, which would make a test run *audible* -- and, worse
than audible, dependent on what happens to be installed. A suite that passes on
one machine and behaves differently on another is not a suite. The audio tests
build their own ``Sfx`` and do not read this.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_save_file(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("neverdeads-home")
    monkeypatch.setenv("NEVERDEADS_REVENGE_HOME", str(home))
    monkeypatch.setenv("NEVERDEADS_REVENGE_MUTE", "1")
    yield home
