"""Tests for the music: a loop, a bed, and never required.

The effects have a whole file of tests because their one job is to be *safe* --
a machine with no audio must be silent, not broken. The music's job is the same
and one thing more: it must be **under** everything, and it must come and go with
the *run* rather than with a screen -- the title is quiet, the floor is not, and
the tally is quiet again.
"""

from __future__ import annotations

import wave
from array import array

import pytest

from neverdeads_revenge.desktop import audio, music as music_module
from neverdeads_revenge.desktop.music import GAIN, Music, RATE


class _StubStream:
    """The device, as a test would like it: it opens, and nothing is heard."""

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def start(self, callback) -> None:
        self.callback = callback

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


class _StubLibrary:
    SampleFormat = type("SampleFormat", (), {"SIGNED16": 1})
    PlaybackDevice = _StubStream

    @classmethod
    def get(cls):
        """The real library is asked for through ``get``; so is this one."""
        return cls


@pytest.fixture
def device():
    """A stubbed playback library, and the streams it was asked to open."""
    music_module._Library = audio._Library
    patcher = pytest.MonkeyPatch()
    patcher.setattr(music_module, "_Library", _StubLibrary)
    opened = []
    original = _StubLibrary.PlaybackDevice

    def recorded(**kwargs):
        stream = original(**kwargs)
        opened.append(stream)
        return stream

    patcher.setattr(_StubLibrary, "PlaybackDevice", staticmethod(recorded))
    patcher.delenv("NEVERDEADS_REVENGE_MUTE", raising=False)
    yield opened
    patcher.undo()


def test_the_music_is_not_required(device, monkeypatch):
    """No file, no library, no problem: the game is silent and nothing raises."""
    monkeypatch.setattr(music_module, "MUSIC_FILE", "a_loop_that_is_not_shipped.wav")
    player = Music(muted=True)
    player.start()
    assert not player.playing
    player.set_muted(False)
    assert not player.playing, "unmuting opened a stream with no file to play"


def test_the_music_starts_with_the_run_and_stops_at_the_tally(device):
    """The loop belongs to the *run*: not the title, not the game over."""
    from neverdeads_revenge.sdl_front.app import SdlApp

    # The sound *on* for this one: a muted game is a game whose music has
    # nothing to ask for, and this is a test about the music. The effects fail
    # to find a device on their own and stay quiet about it; that is their
    # promise, and it is not this test's subject.
    app = SdlApp(seed=3, no_sound=False)
    assert not app.music.playing, "the title screen has music"

    app.key("enter")  # new run
    app.key("enter")  # the first hero -- and there is the premise, still to skip
    app.key("escape")  # the prologue, skipped, and the floor opens
    assert app.music.playing, "the floor opened without its music"

    app.show_game_over(won=True)
    assert not app.music.playing, "the tally is still playing the floor's loop"


def test_the_loop_plays_past_its_own_end(device):
    """A loop wraps on the sample and keeps going: forty-nine seconds of music
    asked for ninety seconds' worth of buffer is the same sound, again."""
    player = Music()
    player.start()
    frames = player._frames()
    next(frames)  # the first call only primes the generator
    frame_count = 1323  # thirty milliseconds of a mono 16-bit stream
    heard = 0
    for _ in range(2000):
        block = frames.send(frame_count)
        assert len(block) == frame_count * 2, "a wrap handed back a short buffer"
        heard += len(block) // 2
    # The loop is 49.2s; this is 52.9s of asking, so the wrap has happened.
    assert heard / RATE > 52.0, f"the loop ran out after {heard / RATE:.1f}s"


def test_the_music_is_a_bed_and_not_a_voice(device):
    """Its loudest sample is a quarter of full scale, by design and by gain."""
    player = Music()
    player.start()
    frames = player._frames()
    next(frames)  # the first call only primes the generator
    frame_count = 1323
    loudest = 0
    for _ in range(40):
        block = frames.send(frame_count)
        samples = array("h")
        samples.frombytes(block)
        loudest = max(loudest, max(abs(value) for value in samples))
    assert loudest <= 32767 * GAIN + 1, f"the music peaked at {loudest}"


def test_mute_is_one_mute(device):
    """The pause menu's toggle lands on the music as well as the effects.

    Built with the sound *on* -- a muted game is a game whose music has nothing
    to ask for -- and the toggle asked the way the pause menu asks it.
    """
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3, battle_scene=True, no_sound=False)
    assert app.music.playing, "a fight opened without its music"

    app.music.set_muted(True)
    assert not app.music.playing, "a muted game still has a loop queued"
    app.music.set_muted(False)
    assert app.music.playing, "unmuting in a run did not bring the music back"
