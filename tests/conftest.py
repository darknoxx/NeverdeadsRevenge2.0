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

import gc

import pytest

#: How many tests between one walk of the heap.
#:
#: The UI tests build a Qt window with a screenful of images and then drop the
#: lot, and every one of those objects is garbage that only leaves when something
#: *asks*. Without a schedule the collector keeps up on its own, and the walk
#: gets longer with every test: measured here, the tracked objects went from 28k
#: to 70k across the desktop block and a full collection from 2.4ms to 19ms, and
#: the domain tests *after* that block ran six times slower than the same tests
#: on their own. Twenty is often enough to keep the heap flat and rare enough
#: that the walking is noise.
GC_EVERY = 20


def pytest_sessionstart(session) -> None:
    """Put everything imported so far out of the collector's way.

    The imported graph -- this game, Qt, pytest -- is most of what is alive and
    none of it is ever garbage. Freezing it means the collector never walks it
    again, which is the cheap half of the fix; the schedule below is the other.
    """
    gc.collect()
    if hasattr(gc, "freeze"):
        gc.freeze()


@pytest.fixture(autouse=True)
def _tidy_the_heap():
    """Collect on a schedule, so no test pays for the tests before it."""
    yield
    _tidy_the_heap.count += 1
    if _tidy_the_heap.count % GC_EVERY == 0:
        gc.collect()


_tidy_the_heap.count = 0


@pytest.fixture(autouse=True)
def _isolated_save_file(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("neverdeads-home")
    monkeypatch.setenv("NEVERDEADS_REVENGE_HOME", str(home))
    monkeypatch.setenv("NEVERDEADS_REVENGE_MUTE", "1")
    yield home
