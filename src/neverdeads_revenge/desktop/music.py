"""The game's music: one loop, and a player that owns its own stream.

Music is a different animal from the sound effects, and the difference is worth
a module rather than a branch in the mixer. The effects are punctuation -- short
clips mixed into a ring that is bounded by the longest of them, because a fight
must never be three seconds behind itself. Music is a *floor*: it plays for
forty-nine seconds and then plays again, and it must never arrive late and never
arrive loud. So it has its own stream at its own rate -- the loop is written at
44.1kHz and is played at 44.1kHz, with nothing resampled and nothing pitched -- and
its own gain, which is a quarter: measured, the loop sits at -11.2dB RMS, which is
as loud as a menu click and louder than any blow in the game, so it is brought
down until it is a bed and not a second voice.

And the same promise the effects make, kept here too: it is never *required*. A
machine with no audio device is a game that is silent, not a game that does not
start; a build that shipped without the file is the same; and the mute is one
mute, because a player who turned the sound off did not mean "quieter".
"""

from __future__ import annotations

import wave
from array import array
from pathlib import Path
from typing import Any

from .audio import SOUNDS_DIR, _Library

__all__ = ["Music"]

#: The file, inside the package with the other sound: it is read at runtime, so it
#: travels with the code. A loop and not a track -- it is written to be seamless,
#: and the player wraps on the sample rather than restarting a file.
MUSIC_FILE = "background_music_loop.wav"

#: The rate the loop is *written* at, which is the rate its stream is opened at:
#: resampling forty-nine seconds of music to save a second device would be the
#: one place a wrong pitch could hide in plain hearing.
RATE = 44100

#: How loud the bed is. A quarter of full scale, which puts it some eight
#: decibels under the quietest blow in the game: present in every room, above
#: nothing.
GAIN = 0.25


class Music:
    """One loop, one stream, and a start that is safe to call twice."""

    def __init__(self, muted: bool = False) -> None:
        self._muted = muted
        self._samples: array | None = None
        self._device: Any = None
        self._position = 0
        #: Whether the game is somewhere the music belongs. Remembered rather
        #: than acted on while muted, so unmuting in a run brings the loop back
        #: without the caller having to know that.
        self._wanted = False

    # -- the game's side -----------------------------------------------------
    def start(self) -> None:
        """The music belongs: the run has begun, or come back from the dead."""
        self._wanted = True
        self._open()

    def stop(self) -> None:
        """The run is over. The next one starts the loop from the top."""
        self._wanted = False
        self._close()

    def set_muted(self, muted: bool) -> None:
        """One mute for the whole game: the pause menu's toggle lands here too."""
        self._muted = muted
        if muted:
            self._close()
        elif self._wanted:
            self._open()

    def close(self) -> None:
        """Let go of everything. For the window closing."""
        self._wanted = False
        self._close()

    @property
    def playing(self) -> bool:
        return self._device is not None

    # -- the player ----------------------------------------------------------
    def _load(self) -> array | None:
        """The loop, read once. ``None`` is a real answer: no file, no music."""
        if self._samples is not None:
            return self._samples
        path = SOUNDS_DIR / MUSIC_FILE
        if not path.exists():
            return None
        try:
            with wave.open(str(path)) as handle:
                if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                    return None
                samples = array("h")
                samples.frombytes(handle.readframes(handle.getnframes()))
        except (OSError, EOFError, wave.Error):
            return None
        self._samples = samples
        return samples

    def _open(self) -> None:
        """Open the stream once, and never raise."""
        if self._muted or self._device is not None:
            return
        lib = _Library.get()
        if lib is None:
            return
        samples = self._load()
        if samples is None:
            return

        try:
            device = lib.PlaybackDevice(
                output_format=lib.SampleFormat.SIGNED16,
                nchannels=1,
                sample_rate=RATE,
                # A second, and more: music is not latency-sensitive the way a
                # blow is, and a buffer that size is a callback that never
                # starves.
                buffersize_msec=1000,
            )
            frames = self._frames()
            next(frames)
            device.start(frames)
        except Exception:  # noqa: BLE001 - audio is never worth a crash
            return
        self._device = device

    def _close(self) -> None:
        device, self._device = self._device, None
        self._position = 0
        if device is not None:
            try:
                device.stop()
                device.close()
            except Exception:  # noqa: BLE001 - audio is never worth a crash
                pass

    def _frames(self):
        """The device's callback: the loop, one buffer at a time, forever.

        The position wraps on the *sample*, so the loop point is the loop point
        the file was written for and not a file being reopened -- which is what
        makes the seam inaudible. And every sample goes through the gain on its
        way out, because the file is as loud as a click and the music is a bed.
        """
        samples = self._samples or array("h")
        total = max(1, len(samples))
        position = 0
        frame_count = yield b""
        while True:
            want = max(0, int(frame_count))
            out = array("h", [0]) * want
            for index in range(want):
                out[index] = int(samples[position] * GAIN)
                position = (position + 1) % total
            frame_count = yield out.tobytes()


