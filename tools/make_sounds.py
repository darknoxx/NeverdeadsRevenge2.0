#!/usr/bin/env python3
"""Generate the game's sound effects.

Chiptune, and not only because a terminal roguelite should sound like one: it is
the one kind of music that can be *synthesised exactly*. A Gameboy's two pulse
channels are square waves with a duty cycle and its noise channel is noise, which
between them is `math` and `struct` from the standard library. No samples, no
dependencies, nothing to license, and the files are a few kilobytes each.

    python3 tools/make_sounds.py                 # all of them, into the package
    python3 tools/make_sounds.py --out /tmp/x    # somewhere else
    python3 tools/make_sounds.py --list          # what there is

The test suite regenerates every file and fails if the committed ones disagree,
the same way it does for the icon. Edit the recipes, not the WAVs.
"""

from __future__ import annotations

import argparse
import random
import struct
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Where the sounds ship from. Inside the package rather than in ``assets/``:
#: the icon is a desktop-file asset that only the installer reads, and these are
#: read at runtime, so they have to travel with the code.
DEFAULT_OUT = ROOT / "src" / "neverdeads_revenge" / "sounds"

#: Samples a second. The Gameboy's own output was around eleven kilohertz, and
#: at this rate a square wave still sounds like a square wave.
RATE = 11025

#: Full scale. A hair under 32767 so a rounding error cannot wrap a sample.
PEAK = 32000


@dataclass(frozen=True, slots=True)
class Note:
    """One tone on a pulse channel, with an envelope."""

    freq: float
    seconds: float
    #: Pulse width. 0.5 is the hollow square, 0.25 and 0.125 are the thin nasal
    #: ones the Gameboy used for leads, 0.75 is the fat one for impacts.
    duty: float = 0.5
    volume: float = 0.55
    #: Where the pitch lands. ``None`` for a steady tone.
    to: float | None = None
    #: How much noise to mix in. Impacts want some; melodies want none.
    noise: float = 0.0


#: Every sound the game can make, as a recipe.
#:
#: Short. A sound effect in a turn-based game is punctuation, and anything longer
#: than a fifth of a second is a thing the player starts waiting for.
SOUNDS: dict[str, tuple[Note, ...]] = {
    # -- combat, which is what a player hears most of ----------------------
    # The three that carry the game. A hit is a short downward chirp with a
    # little grit in it; a crit is the same shape an octave up and in two parts,
    # so it is unmistakably *more* than a hit; taking one is low, fat and harsh,
    # because the player has to hear it without looking.
    # Eighty milliseconds and a higher sweep than it used to have. It was fifty
    # milliseconds sweeping 340 to 190, which on a laptop is a click and a thump:
    # the ear needs about a tenth of a second to hear a note as a note, and the
    # small speakers in a laptop roll off hard below three hundred hertz. The
    # most common sound in the game has to survive both.
    "hit": (
        Note(520, 0.08, duty=0.5, to=320, noise=0.25, volume=0.65),
    ),
    "crit": (
        Note(560, 0.035, duty=0.25, to=720),
        Note(820, 0.07, duty=0.25, to=500, noise=0.15),
    ),
    # It was 190 to 85, which is a rumble a laptop cannot make at all: two
    # fifths of its energy was under three hundred hertz. Still the lowest sound
    # in the game, because taking a blow should sound like one.
    "hurt": (
        Note(400, 0.12, duty=0.75, to=210, noise=0.45, volume=0.7),
    ),
    "kill": (
        Note(523, 0.05, duty=0.5),
        Note(392, 0.05, duty=0.5),
        Note(262, 0.09, duty=0.5, to=200, noise=0.2),
    ),
    # -- the run -----------------------------------------------------------
    "coin": (
        Note(988, 0.03, duty=0.25),
        Note(1319, 0.055, duty=0.25, to=1175),
    ),
    "item": (
        Note(659, 0.05, duty=0.5),
        Note(880, 0.08, duty=0.5),
    ),
    "stairs": (
        Note(600, 0.20, duty=0.5, to=170, noise=0.1),
    ),
    "level": (
        Note(392, 0.055, duty=0.5),
        Note(523, 0.055, duty=0.5),
        Note(659, 0.055, duty=0.5),
        Note(784, 0.15, duty=0.25),
    ),
    "curse": (
        Note(300, 0.20, duty=0.75, to=170, noise=0.5, volume=0.7),
    ),
    "chest": (
        Note(330, 0.11, duty=0.75, noise=0.3, volume=0.6),
        Note(495, 0.20, duty=0.5, to=390, noise=0.2, volume=0.6),
    ),
    # -- the two endings ---------------------------------------------------
    "death": (
        Note(400, 0.16, duty=0.5, to=300),
        Note(300, 0.16, duty=0.5, to=200),
        Note(200, 0.32, duty=0.75, to=55, noise=0.3),
    ),
    "victory": (
        Note(523, 0.09, duty=0.5),
        Note(659, 0.09, duty=0.5),
        Note(784, 0.09, duty=0.5),
        Note(1047, 0.30, duty=0.25),
    ),
}


def render(notes: tuple[Note, ...], rate: int = RATE) -> bytes:
    """Turn a recipe into 16-bit mono PCM.

    The noise is seeded rather than drawn from the system, so the same recipe
    always produces the same bytes -- which is the whole reason the committed
    files can be checked against the generator.
    """
    noise_source = random.Random(1)
    out = bytearray()
    phase = 0.0

    for note in notes:
        count = max(1, int(note.seconds * rate))
        landing = note.freq if note.to is None else note.to
        attack = max(1, int(rate * 0.003))

        for index in range(count):
            progress = index / count
            freq = note.freq + (landing - note.freq) * progress
            phase += freq / rate
            wave_value = 1.0 if (phase % 1.0) < note.duty else -1.0
            if note.noise:
                wave_value = (
                    wave_value * (1.0 - note.noise)
                    + noise_source.uniform(-1.0, 1.0) * note.noise
                )
            # Instant attack, decay to nothing. A held note in a menu is a note
            # that outlives the thing it was announcing.
            envelope = min(1.0, index / attack) * (1.0 - progress) ** 0.7
            sample = max(-1.0, min(1.0, wave_value * note.volume * envelope))
            out += struct.pack("<h", int(sample * PEAK))

    return bytes(out)


def write_wav(path: Path, pcm: bytes, rate: int = RATE) -> None:
    """Write 16-bit mono PCM as a WAV, with no header of our own."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)


def write_all(out: Path) -> list[Path]:
    """Generate every sound into ``out``. Returns what it wrote."""
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, notes in SOUNDS.items():
        path = out / f"{name}.wav"
        write_wav(path, render(notes))
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the game's sounds.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--list", action="store_true", help="print the sounds and stop"
    )
    args = parser.parse_args(argv)

    if args.list:
        for name, notes in SOUNDS.items():
            total = sum(note.seconds for note in notes)
            print(f"{name:10} {total:5.2f}s  {len(notes)} note(s)")
        return 0

    written = write_all(args.out)
    total = sum(path.stat().st_size for path in written)
    print(f"wrote {len(written)} sounds to {args.out} ({total / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
