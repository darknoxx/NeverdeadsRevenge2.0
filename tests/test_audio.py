"""Tests for the sounds.

Two halves. The files themselves are generated, so they are checked the way the
icon is -- regenerate and compare -- and the playback is checked for the thing
that actually matters about it: that it is **safe**. A machine with no audio must
get silence and no delay, never an error, because a sound effect is not worth a
crash and most machines running a terminal game have no business making noise.

And three invariants that are the whole reason this was rewritten:

* **the device's position is measured, not guessed.** A sound is mixed into a
  buffer whose head is the frame the device is about to play, so the drop
  decision is a comparison between two numbers read off the same buffer the
  sound is inserted into. The version before this scheduled by its own clock
  and dropped by its own guess.
* **a fight is a mixer, not a playlist.** Ten blows a second against sounds of
  a tenth of a second is a queue that runs away, so sounds are added *on top*
  of each other and the buffer's length is bounded by the longest clip rather
  than by how many blows landed. This is the difference between a fight and a
  fight that is three seconds behind itself.
* **bytes land in the order they were queued in**, which is what makes the
  *order* no longer the thing that goes wrong.
"""

from __future__ import annotations

import math
import subprocess
import sys
import wave
from array import array
from pathlib import Path
from typing import ClassVar

import pytest

from neverdeads_revenge.game.state import LogKind
from neverdeads_revenge.desktop import audio
from neverdeads_revenge.desktop.audio import SOUNDS_DIR, RATE, Sfx, loudest_kind, sound_for_kind

ROOT = Path(__file__).resolve().parent.parent
MAKE_SOUNDS = ROOT / "tools" / "make_sounds.py"
TOOL = ROOT / "tools" / "install_sounds.py"


# -- the files ---------------------------------------------------------------
def test_every_sound_the_game_can_ask_for_exists():
    """The code is the list -- and a sound named in it and not shipped plays
    nothing, silently, forever.

    Two places name a sound: the tables in ``desktop.audio`` that the log's kinds
    and the tricks go through, and the literal names in a ``play(...)`` call at
    the moment something happens -- a door, a chest, a level. Both are swept, by
    *walking the source* rather than by keeping a list here: a list in a test is
    a list that goes stale the first time somebody adds a sound in a hurry, and
    the pack added fifty of them in one afternoon.
    """
    named = set(audio.BY_KIND.values())
    named |= set(audio.BY_SPECIAL.values())
    named |= set(audio.BY_LOOK.values())
    named |= set(audio.URGENT)
    for inflicts in ((), ("bleed",), ("maul",), ("chill",)):
        named.add(audio.weapon_sound(inflicts))
    named |= _tables_in_the_screens()
    named |= _literals_in_the_code()

    assert len(named) > 20, f"the sweep found almost nothing: {sorted(named)}"
    for name in sorted(named):
        assert (SOUNDS_DIR / f"{name}.wav").exists(), (
            f"{name} is asked for by the code and not in the pack"
        )


#: The tables in the screens that name a sound: the interface's clicks, what a
#: wound sounds like, and the three ultimates. They are listed here rather than
#: guessed at, because a table of sounds is a decision somebody made and this is
#: the inventory of those decisions. A *new* table belongs in this list -- and
#: ``test_a_fight_never_asks_for_a_sound_that_is_not_there`` is what catches the
#: one somebody forgets to add.
TABLES = (
    ("neverdeads_revenge.desktop.screens.base", "Screen", "UI_SOUNDS"),
    ("neverdeads_revenge.desktop.screens.game", "GameScreen", "UI_SOUNDS"),
    ("neverdeads_revenge.desktop.screens.game", None, "ULTIMATE_SOUND"),
    ("neverdeads_revenge.desktop.screens.battle", None, "STATUS_SOUNDS"),
)


def _tables_in_the_screens() -> set[str]:
    import importlib

    named: set[str] = set()
    for module_name, class_name, attribute in TABLES:
        holder = importlib.import_module(module_name)
        if class_name is not None:
            holder = getattr(holder, class_name)
        table = getattr(holder, attribute)
        named |= set(table.values())
    return named


def _literals_in_the_code() -> set[str]:
    """Every ``play("...")`` in the source: the sounds named where they happen."""
    import ast

    named: set[str] = set()
    for path in sorted((ROOT / "src").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = (
                func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            )
            if called != "play":
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value:
                        named.add(arg.value)
    return named
    for path in sorted(source.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", None)
            )
            if called != "play":
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value:
                        named.add(arg.value)

    assert len(named) > 20, f"the sweep found almost nothing: {sorted(named)}"
    for name in sorted(named):
        assert (SOUNDS_DIR / f"{name}.wav").exists(), (
            f"{name} is asked for by the code and not in the pack"
        )


def test_every_committed_sound_is_a_playable_wav():
    files = sorted(SOUNDS_DIR.glob("*.wav"))
    assert len(files) >= 10, "the sound set shrank"
    for path in files:
        with wave.open(str(path), "rb") as handle:
            assert handle.getnchannels() == 1, path.name
            assert handle.getsampwidth() == 2, path.name
            assert handle.getframerate() == RATE, path.name
            assert handle.getnframes() > 0, path.name


def test_no_sound_outlives_the_thing_it_announces():
    """A sound effect in a turn-based game is punctuation. Anything long enough
    to be waited for is a sound the player learns to dread.

    A second, then: the pack's two long ones are a bell tolling and a run ending
    (0.95s and 0.87s, both of them trimmed from what they arrived as), and those
    are moments rather than punctuation. Everything else is well under it.
    """
    for path in SOUNDS_DIR.glob("*.wav"):
        with wave.open(str(path), "rb") as handle:
            seconds = handle.getnframes() / handle.getframerate()
        assert seconds <= 1.0, f"{path.name} is {seconds:.2f}s"


def test_the_sounds_are_small_enough_to_ship():
    """Three quarters of a megabyte of sound, which a game this size can afford
    and a download should. It was 118 kB before the pack arrived, and the pack
    is the point: it is what the game sounds *like*, and it travels with the
    code because nothing else can read it."""
    total = sum(path.stat().st_size for path in SOUNDS_DIR.glob("*.wav"))
    assert total < 1_000_000, f"the sound set is {total / 1024:.0f} kB"


def test_the_committed_sounds_are_what_the_generator_produces(tmp_path):
    """The *generated* half of the set, and only that half.

    Two kinds of file live in the sound folder now. The ones ``make_sounds.py``
    writes are checked the way the icon is -- regenerate and compare -- so that
    a nudge to a WAV is not silently undone by the next regeneration. The other
    half arrived as a pack and is put through ``tools/install_sounds.py``
    instead; nothing in the repository can regenerate those, so nothing here
    pretends to check them (the converter has its own test, and every name the
    code asks for is checked above).
    """
    result = subprocess.run(
        [sys.executable, str(MAKE_SOUNDS), "--out", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    generated = {path.name: path.read_bytes() for path in tmp_path.glob("*.wav")}
    assert generated, "the generator produced nothing at all"
    shipped = {path.name: path.read_bytes() for path in SOUNDS_DIR.glob("*.wav")}
    for name, data in generated.items():
        assert name in shipped, f"a generated sound vanished: {name}"
        assert shipped[name] == data, (
            f"{name} has been edited away from what make_sounds.py writes"
        )


# -- what each kind of message sounds like -----------------------------------
def test_every_kind_of_message_is_classified():
    """A sound per kind, or a sound for none of them."""
    for kind in audio.BY_KIND:
        assert sound_for_kind(kind), kind


def test_taking_a_blow_is_the_loudest_thing_a_turn_said():
    assert audio.LOUDNESS[LogKind.DAMAGE] > audio.LOUDNESS[LogKind.CRIT]
    assert audio.LOUDNESS[LogKind.CRIT] > audio.LOUDNESS[LogKind.COMBAT]


def test_the_loudest_kind_of_an_empty_turn_is_silence():
    assert loudest_kind([]) is None
    assert loudest_kind([LogKind.PLAIN, LogKind.SYSTEM]) is None


# -- the playback device -----------------------------------------------------
class _SampleFormat:
    SIGNED16 = "S16_LE"


class _StubPlayback:
    """A playback device that records what was asked of it and starts nothing."""

    instances: ClassVar[list] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started: list = []
        self.stopped = 0
        self.closed = 0
        _StubPlayback.instances.append(self)

    def start(self, generator) -> None:
        self.started.append(generator)

    def stop(self) -> None:
        self.stopped += 1

    def close(self) -> None:
        self.closed += 1


class _StubLibrary:
    SampleFormat = _SampleFormat
    PlaybackDevice = _StubPlayback


@pytest.fixture
def devices():
    """Stubs out the playback library, so no test ever makes a noise.

    The library's ``get`` is patched rather than the module's, so the device is
    opened through the same path the game uses and nothing about the test is
    special-cased.
    """
    _StubPlayback.instances = []
    patcher = pytest.MonkeyPatch()
    patcher.setattr(audio._Library, "get", lambda: _StubLibrary)
    patcher.delenv(audio.MUTE_ENV, raising=False)
    yield _StubPlayback.instances
    patcher.undo()


@pytest.fixture
def _libraryless(monkeypatch):
    """A machine where the playback library cannot be found."""
    monkeypatch.setattr(audio._Library, "get", lambda: None)


def _frames_of(name: str) -> int:
    with wave.open(str(SOUNDS_DIR / f"{name}.wav"), "rb") as handle:
        return handle.getnframes()


def _drain(sfx: Sfx) -> None:
    """Let the sound worker catch up with everything queued."""
    sfx._queue.join()


# -- a machine without a library ---------------------------------------------
def test_a_machine_without_the_library_is_silent_and_harmless(_libraryless):
    """The common case, and the one that has to be perfect: most machines
    running a terminal game have nothing to play a sound with."""
    sfx = Sfx()

    assert not sfx.available
    sfx.play("hit")
    sfx.play("no-such-sound")
    _drain(sfx)
    sfx.close()
    assert sfx._ring.pending_frames() == 0


# -- the device is opened once, and reused -----------------------------------
def test_the_device_is_opened_before_the_first_blow(devices):
    """An audio session is created once and reused, which is why the first hit
    of the first fight does not pay for the startup itself."""
    sfx = Sfx()

    assert devices, "nothing was opened up front"
    sfx.close()


def test_a_muted_session_does_not_open_anything(devices):
    """Nothing is going to be played, so nothing should be started."""
    Sfx(muted=True)

    assert devices == []


def test_the_device_is_opened_at_the_rate_the_sounds_are_written_at(devices):
    """A rate mismatch is a slow high-pitched soundtrack rather than an error
    anybody would find."""
    Sfx()
    device = devices[-1]
    assert device.kwargs["sample_rate"] == RATE
    assert device.kwargs["nchannels"] == 1
    assert device.kwargs["buffersize_msec"] == 30


def test_unmuting_opens_the_device(devices):
    sfx = Sfx(muted=True)
    assert devices == []

    sfx.set_muted(False)

    assert devices, "unmuting left it silent"
    sfx.close()


def test_closing_lets_go_of_the_device(devices):
    sfx = Sfx()
    device = devices[-1]

    sfx.close()

    assert device.stopped == 1, "the device was told to stop"
    assert device.closed == 1, "the device was closed"
    assert sfx._device is None


def test_close_twice_stops_the_device_once(devices):
    sfx = Sfx()
    device = devices[-1]

    sfx.close()
    sfx.close()

    assert device.stopped == 1


# -- what lands in the mixing buffer -----------------------------------------
def test_a_played_sound_lands_in_the_buffer(devices):
    """``play`` is a mix, and what is in the buffer next is the clip the game
    asked for."""
    sfx = Sfx()
    assert sfx._ring.pending_frames() == 0

    sfx.play("hit")
    _drain(sfx)

    assert sfx._ring.pending_frames() == _frames_of("hit")
    assert sfx._ring.seconds_pending == pytest.approx(0.08, abs=0.01)


def test_two_sounds_mix_rather_than_queue(devices):
    """The invariant the whole rewrite exists for: two blows in one turn play on
    top of each other, and the buffer's length is the longer of the two."""
    sfx = Sfx()
    hit = _frames_of("hit")
    crit = _frames_of("crit")

    sfx.play("hit")
    sfx.play("crit")
    _drain(sfx)

    # A queue would be hit + crit; a mixer is the longer of the two.
    assert sfx._ring.pending_frames() == max(hit, crit), (
        f"{sfx._ring.pending_frames()} frames, expected {max(hit, crit)}"
    )


def test_mixing_is_a_sample_wise_sum(devices):
    """Two clips of the same volume become one louder one, not one pushed
    behind the other."""
    sfx = Sfx()
    queued = array("h", [100] * 16).tobytes()
    arriving = array("h", [200] * 16).tobytes()

    sfx._ring.add(queued)
    sfx._ring.add(arriving)

    with sfx._ring._lock:
        head = array("h", bytes(sfx._ring._buf))
    assert list(head) == [300] * 16, "the sum was not sample-wise"


def test_two_loud_sounds_clip_rather_than_wrap(devices):
    """Clipped the way an audio mixer clips: past the ceiling is the ceiling,
    not a wrapped-around negative number."""
    sfx = Sfx()
    loud = array("h", [32767] * 4).tobytes()

    sfx._ring.add(loud)
    sfx._ring.add(loud)

    with sfx._ring._lock:
        head = array("h", bytes(sfx._ring._buf))
    assert list(head) == [32767] * 4, "the sum wrapped around"


def test_a_silence_does_not_change_what_is_queued(devices):
    sfx = Sfx()
    before = sfx._ring.pending_frames()
    sfx._ring.add(b"\x00" * 64)

    assert sfx._ring.pending_frames() == before + 32


def test_the_buffer_is_bounded_by_the_longest_clip(devices):
    """Ten blows a second must not leave a buffer that runs away."""
    sfx = Sfx()
    longest = max(
        (_frames_of(path.stem) for path in SOUNDS_DIR.glob("*.wav")),
    )

    for _ in range(10):
        sfx.play("hit")
    _drain(sfx)

    assert sfx._ring.pending_frames() <= longest
    assert sfx._ring.seconds_pending <= 0.8


# -- the callback drains from the head --------------------------------------
def _mix_bytes(*clips: bytes) -> bytes:
    """What the mixing buffer looks like after those clips were played."""
    longest = max(len(clip) for clip in clips)
    head = array("h")
    head.frombytes(b"\x00" * longest)

    for clip in clips:
        arriving = array("h")
        arriving.frombytes(clip)
        for index, value in enumerate(arriving):
            head[index] = max(-32768, min(32767, head[index] + value))

    return head.tobytes()


def test_the_callback_drains_what_the_device_asks_for(devices):
    """The device asks for ``frame_count`` frames and this hands it what it
    asked for, from the head."""
    sfx = Sfx()
    sfx.play("hit")
    sfx.play("crit")
    _drain(sfx)

    generator = devices[-1].started[0]

    # Primed before it was handed over, so it is sitting at its first send. And
    # the head of the buffer is the *mix* of the two, because two blows in one
    # turn play on top of each other rather than in sequence.
    take = generator.send(_frames_of("hit"))
    expected = _mix_bytes(
        (SOUNDS_DIR / "hit.wav").read_bytes()[44:],
        (SOUNDS_DIR / "crit.wav").read_bytes()[44:],
    )
    assert take == expected[: _frames_of("hit") * 2], (
        "the wrong part came off the head"
    )

    and_the_rest = generator.send(_frames_of("crit") - _frames_of("hit"))
    assert and_the_rest == expected[_frames_of("hit") * 2 :], (
        "the tail did not follow on"
    )


def test_an_empty_buffer_is_silence(devices):
    """An empty buffer is a device with nothing queued, which happens every time
    the player goes quiet for longer than the longest clip."""
    sfx = Sfx()
    generator = devices[-1].started[0]

    silence = generator.send(200)

    assert silence == b"\x00" * 200 * 2


# -- muting ------------------------------------------------------------------
def test_muting_a_running_buffer_clears_what_is_left(devices):
    """The device is *not* closed by muting: opening one again costs as much as
    unmuting ever would. What muting does is stop the queue and empty it."""
    sfx = Sfx()
    sfx.play("kill")
    _drain(sfx)
    assert sfx._ring.pending_frames() > 0

    sfx.set_muted(True)

    assert sfx._device is not None
    assert sfx._ring.pending_frames() == 0


def test_the_environment_cannot_be_overridden_by_the_setting(devices, monkeypatch):
    """The one caller that matters is the test suite.

    A save file that says "sound on" must not be able to turn the sound on in a
    test run, or the suite would be audible on any machine that happens to have
    a playback library installed.
    """
    monkeypatch.setenv(audio.MUTE_ENV, "1")
    monkeypatch.setattr(audio._Library, "get", lambda: _StubLibrary)
    assert Sfx(muted=False).muted


# -- silence by accident -----------------------------------------------------
def test_one_hiccup_does_not_silence_the_session(devices):
    """The old version muted on the first exception, which is why the sound used
    to stop and never come back."""
    sfx = Sfx()
    sfx._count_failure()
    assert not sfx.muted, "a single hiccup killed the sound"


def test_three_in_a_row_do(devices):
    sfx = Sfx()
    for _ in range(audio.GIVE_UP_AFTER):
        sfx._count_failure()
    assert sfx.muted


# -- where the sounds live ---------------------------------------------------
def test_the_sounds_live_inside_the_package():
    """They are read at runtime, so they have to travel with the code rather
    than sitting in assets/ with the desktop file."""
    package = Path(audio.__file__).resolve().parent.parent
    assert SOUNDS_DIR == package / "sounds"
    assert SOUNDS_DIR.exists()


# -- a failure is a failure ---------------------------------------------------
def test_an_open_failure_counts_once_a_row(devices, monkeypatch):
    """A counter that counts double reaches its give-up in half the time, and
    one that resets on every unmute never reaches it at all."""
    class _RaisingPlayback:
        def __init__(self, **kwargs):
            raise RuntimeError("no card")

    class _RaisingLibrary:
        SampleFormat = _SampleFormat
        PlaybackDevice = _RaisingPlayback

    monkeypatch.setattr(audio._Library, "get", lambda: _RaisingLibrary)
    sfx = Sfx()

    assert sfx._failures == 1, "failed once, counted twice"


def test_no_device_means_no_ring_to_drain(devices):
    """An urgent sound bypasses the backlog on purpose -- which is exactly why it
    has to refuse when the open failed and nothing is draining what it pumps."""
    sfx = Sfx()
    sfx._close_stream()
    assert sfx._device is None

    for _ in range(60):
        sfx.play("death")  # urgent: it would bypass the backlog if it queued

    assert sfx._ring.seconds_pending == 0.0
    assert sfx._queue.empty(), "the names queued up for nobody"


# -- bringing a sound in from outside ----------------------------------------
def test_the_converter_writes_the_rate_the_game_plays(tmp_path):
    """``tools/install_sounds.py``, asked the one question that matters.

    A sound from outside arrives at whatever rate it was made at -- the pack is
    44.1kHz, which is four times what this game mixes -- and a file that arrived
    unchanged is not a small mistake: it is the wrong speed and the wrong pitch,
    and the mixer will not say so. So: write a wav that looks nothing like the
    game's, convert it, and check what comes out.
    """
    source = tmp_path / "from_elsewhere"
    source.mkdir()
    out = tmp_path / "installed"
    silence = array("h", [0] * 4000)
    tone = array("h")
    for index in range(22050):
        tone.append(int(9000 * (1 if index % 2 else -1)))
    with wave.open(str(source / "loud_and_stereo.wav"), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes((silence + tone + tone + silence).tobytes())

    result = subprocess.run(
        [sys.executable, str(TOOL), str(source), str(out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out / "loud_and_stereo.wav").exists(), "nothing came out"

    with wave.open(str(out / "loud_and_stereo.wav"), "rb") as handle:
        assert handle.getnchannels() == 1, "stereo was not mixed down"
        assert handle.getsampwidth() == 2, "the sample width changed"
        assert handle.getframerate() == RATE, "the rate is not the game's"
        seconds = handle.getnframes() / handle.getframerate()
    # The wav above is *two* channels of 48104 samples, which is 24052 frames --
    # 0.545s, and a reminder that frames are not samples. Out comes the same
    # sound a quarter as long, with the silence at each end gone (silence is a
    # sound that arrives late) and a hair of air put back.
    assert 0.5 < seconds < 0.6, f"the conversion gave {seconds:.2f}s"


def test_a_fight_never_asks_for_a_sound_that_is_not_there(devices, monkeypatch, tmp_path):
    """The runtime half of the same question, and the one that cannot go stale.

    The sweep above knows where sounds are *named*; this one knows where they are
    *asked for* -- a whole fight, watched to its end with the sound log switched
    on, and the log says ``MISSING`` in the middle of it if any name along the way
    has no file. Which is the failure worth catching: a sound that is not in the
    pack is not an error, it is silence, and silence in a fight reads as a bug in
    the game rather than as a typo in a table.
    """
    log = tmp_path / "sound.log"
    monkeypatch.setenv(audio.DEBUG_ENV, str(log))

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3, battle_scene=True)
    # A few rounds of a real fight, the way the app plays them: the choice, the
    # queue, then the frames that play it out.
    for _ in range(3):
        for key in ("a", "enter"):
            app.key(key)
        for _frame in range(400):
            if not app.screens[-1].busy:
                break
            app.tick(1 / 30.0)
        app.key("enter")
    app.sfx._queue.join()
    app.sfx.close()

    text = log.read_text(encoding="utf-8")
    assert "MISSING" not in text, text
    # And the log is not empty: a test that passed because nothing was ever
    # asked for would pass for the wrong reason.
    assert "sound log:" in text, text


def _rms_db(name: str) -> float:
    """A sound's loudness the way an ear hears it, and not its peak."""
    with wave.open(str(SOUNDS_DIR / f"{name}.wav"), "rb") as handle:
        samples = array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
    mean = sum(value * value for value in samples) / max(1, len(samples))
    return 20 * math.log10(math.sqrt(mean) / 32768) if mean else float("-inf")


def test_the_cursor_is_quieter_than_the_choice_it_makes():
    """The most repeated sound in the game is the quietest one in the interface.

    Peak normalisation is the right rule for a pack generated in one go and the
    wrong one for fifty milliseconds of a hard attack played on *every* cursor
    move: measured, the move came out at -8.2dB RMS against the confirm's -12.4,
    which made it the loudest thing in the interface by four decibels -- and the
    first thing anybody said about the pack. The converter has a level table for
    exactly this case, and this is the one sound in it, so this test is where the
    ear that asked for it is written down.
    """
    move = _rms_db("cursor_move")
    confirm = _rms_db("cursor_confirm")
    assert move < confirm - 1.0, (
        f"the cursor is only {confirm - move:.1f}dB away from the confirm it makes"
    )
    # And not *nothing*: a move nobody hears is a cursor that feels broken.
    assert move > confirm - 12.0, f"the cursor is inaudible at {move:.1f}dB"
