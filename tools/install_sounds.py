#!/usr/bin/env python3
"""Bring a folder of sound effects into the game's own palette.

The game mixes at ``desktop.audio.RATE`` (eleven thousand and twenty-five frames a
second, one channel, signed sixteen-bit) and a wav that says anything else is not a
quiet mismatch -- it is the wrong speed and the wrong pitch, and the mixer will not
tell you. So a sound from outside is *converted*, once, here, and what ships is what
the game can actually play.

What the conversion does, and why each part is not optional:

* **Resample.** A rate that is a whole multiple is decimated with a box filter over
  the group -- four taps for 44100, which is the common case -- so the result is
  band-limited rather than aliased: a naive every-fourth-sample drop turns a cymbal
  into a whistle. Rates that are not multiples get linear interpolation between the
  two nearest frames, which is honest about what it can do and does not pretend to
  be a resampler.
* **Trim.** Leading and trailing silence is length nobody hears, and a clip that
  starts with 80ms of it lands 80ms late in a fight. The trim is generous at the
  start (a little air is what makes a sound not feel clipped) and total at the end.
* **Fade.** Two milliseconds at each end. A cut sample is a click, and a click is
  the one thing a player will notice about a sound they otherwise like.
* **Peak to -1.5dB.** Loud enough to be a hit, quiet enough that two blows landing
  together do not hit the mixer's ceiling -- which is a *hard* clip, and the one
  distortion this game can produce.

The names are kept exactly as the source folder has them: the names *are* the
vocabulary the game asks sounds by, and renaming them here would put a second
dictionary between the file and the code that wants it.

Run it from the repository root:

    ./.venv/bin/python tools/install_sounds.py ~/Vibecoding/ndr_sounds

It prints what it did, per file and in total, and it is repeatable: run it again
after the source folder changes and the same sounds come back.
"""

from __future__ import annotations

import sys
import wave
from array import array
from pathlib import Path

RATE = 11025

#: How loud a converted sound is allowed to be, as a share of full scale.
PEAK = 0.85

#: Silence, in 16-bit units, that counts as silence for the trim.
FLOOR = 64

#: Air kept at the start (a sound that begins on its first sample clicks), and at
#: the end (a hard stop on the last one does too).
LEAD_KEEP = 0.006
TAIL_KEEP = 0.004

#: The fades, in seconds.
FADE = 0.002

#: Not a sound: the pack's own demo reel, which is every sound in a row.
SKIP = {"PREVIEW_ALL_SOUNDS.wav"}

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "src" / "neverdeads_revenge" / "sounds"


def read_wav(path: Path) -> tuple[array, int]:
    """A wav as (samples, rate). Stereo is mixed down, which is a loss this game
    can take: everything it plays is mono, and a stereo file played as mono
    channels is half the sound at twice the speed."""
    with wave.open(str(path)) as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width != 2:
        raise SystemExit(f"{path.name}: only 16-bit wav is supported ({width * 8}-bit)")
    samples = array("h")
    samples.frombytes(raw)
    if channels > 1:
        mixed = array("h", [0]) * (len(samples) // channels)
        for index in range(len(mixed)):
            total = 0
            for channel in range(channels):
                total += samples[index * channels + channel]
            mixed[index] = total // channels
        samples = mixed
    return samples, rate


def resample(samples: array, rate: int, want: int = RATE) -> array:
    """To the game's rate: a box filter when it divides, interpolation when not."""
    if rate == want:
        return samples
    if rate % want == 0:
        group = rate // want
        out = array("h", [0]) * (len(samples) // group)
        for index in range(len(out)):
            total = 0
            for offset in range(group):
                total += samples[index * group + offset]
            out[index] = total // group
        return out
    # Anything else: nearest two frames, weighted. Not a resampler, and it does
    # not claim to be -- it is what keeps an odd rate from being refused.
    ratio = rate / want
    out = array("h", [0]) * int(len(samples) / ratio)
    for index in range(len(out)):
        where = index * ratio
        low = int(where)
        high = min(low + 1, len(samples) - 1)
        share = where - low
        out[index] = int(samples[low] * (1.0 - share) + samples[high] * share)
    return out


def trim(samples: array, rate: int = RATE) -> array:
    """Drop the silence that would otherwise be latency."""
    first, last = 0, len(samples) - 1
    while first < len(samples) and abs(samples[first]) < FLOOR:
        first += 1
    while last > first and abs(samples[last]) < FLOOR:
        last -= 1
    if first >= last:
        return samples  # all quiet: hand it back rather than an empty array
    first = max(0, first - int(LEAD_KEEP * rate))
    last = min(len(samples) - 1, last + int(TAIL_KEEP * rate))
    return samples[first:last + 1]


def shape(samples: array, rate: int = RATE) -> array:
    """Peak to ``PEAK``, and a fade on at both ends."""
    peak = max(1, max(abs(value) for value in samples))
    gain = (PEAK * 32767) / peak
    out = array("h", [int(value * gain) for value in samples])
    fade = max(1, int(FADE * rate))
    for index in range(min(fade, len(out))):
        share = index / fade
        out[index] = int(out[index] * share)
        out[-1 - index] = int(out[-1 - index] * share)
    return out


def write_wav(path: Path, samples: array, rate: int = RATE) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())


def convert(source: Path, out_dir: Path) -> list[tuple[str, float, float, int]]:
    """Every wav under ``source``, converted into ``out_dir``. Returns a report."""
    report = []
    for path in sorted(source.rglob("*.wav")):
        if path.name in SKIP:
            continue
        samples, rate = read_wav(path)
        before = len(samples) / rate
        samples = shape(trim(resample(samples, rate)), RATE)
        write_wav(out_dir / path.name, samples)
        report.append((path.name, before, len(samples) / RATE, path.stat().st_size))
    return report


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(__doc__.strip().splitlines()[-4].strip())
        return 0 if args else 1

    source = Path(args[0]).expanduser()
    out_dir = Path(args[1]).expanduser() if len(args) > 1 else DEFAULT_OUT
    if not source.is_dir():
        print(f"no such folder: {source}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    report = convert(source, out_dir)
    if not report:
        print(f"no wav files under {source}", file=sys.stderr)
        return 1

    print(f"{'sound':22s} {'in':>6s} {'out':>6s} {'source':>9s}")
    for name, before, after, size in report:
        print(f"{name:22s} {before:5.2f}s {after:5.2f}s {size / 1024:7.0f} kB")
    total = sum(path.stat().st_size for path in out_dir.glob("*.wav"))
    print(f"\n{len(report)} sounds -> {out_dir}")
    print(f"the folder now holds {total / 1024:.0f} kB of wav at "
          f"{RATE} Hz, one channel, signed 16-bit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
