"""The SDL window, the screens, and the keys between them.

The same job as ``desktop/app.py``: hold the stack of screens, route a key to the
top of it, keep the run and the meta-progress, and paint whatever comes out. What
it does *not* do is own the game -- every rule, every screen and every panel it
shows is the same code the Qt build shows, because none of them ever knew what a
window was.

Two things are honestly missing, and named rather than hidden:

* **The effects layer.** The Qt build has sparks, flashes and a shaking glass;
  those are painted in pixels and they are the next session's work. The screens
  ask for them the same way they always did, and this answers politely and does
  nothing -- so a fight is playable and quieter than it will be.
* **The screens that are not ported yet.** The shop, the scoreboard and the
  chronicle are Qt screens; opening one here says so. A front end that pretended
  to open them would be a front end that lost a purchase.
"""

from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

from ..persistence import load_meta
from ..desktop.theme import BACKGROUND, Colour
from .font import SdlFont
from .effects import SdlEffects
from .keys import name_of, typed
from .pad import DIRECTION_KEYS, button_name, dpad_direction
from .paint import paint

__all__ = ["SdlApp", "FONT", "MIN_COLS", "MIN_ROWS", "SMALL_PIXELS"]

#: The size of the smaller face the sidebar and the log are drawn in, one step
#: down from the grid: the Qt build uses the same number, which is what makes the
#: two layouts come out the same.
SMALL_PIXELS = 11

FONT = Path(__file__).resolve().parent.parent / "desktop" / "fonts" / "DejaVuSansMono.ttf"

#: The smallest playable grid, matching the Qt build: every panel in the game is
#: laid out for at least this, and a window that fit fewer cells would not be a
#: smaller game but a broken one. (These said 76 for a while, which is a *different*
#: number from the one the Qt build derives its grid with -- so the same window had
#: two answers about how many cells fit.)
MIN_COLS = 80
MIN_ROWS = 24

#: How wide the grid wants to be on a big screen. The scale is chosen to land near
#: this, and then the leftover room becomes *cells* rather than black bars -- which
#: is the whole difference between a 1440p monitor full of dungeon and one with a
#: couple of hundred pixels of nothing on every side.
TARGET_COLS = 110

#: How long a pushed direction waits before it walks, in seconds, and how often
#: it is fed once it does.
#:
#: A keyboard repeats by itself -- SDL's own delay and interval, asked for below
#: -- but a pad sends *nothing* between a button going down and coming up, so on
#: a handheld the stream has to be made here, or a held direction moves exactly
#: one square. The *pace* is deliberately not decided here: the floor throttles
#: its repeats by the hero's own ``action_gap``, exactly as it does for a held
#: key, so a fast hero walks fast on both instruments.
PAD_WALK_DELAY = 0.22

#: How long the pad's A waits before it starts repeating, in seconds.
#:
#: Longer than the walk delay, and longer on purpose: the hold screens settle a
#: tap by its own length (``hold.TAP_SECONDS``, 0.18) and a tap banks nothing, so
#: a first repeat that arrived sooner than that would turn every tap into a hold
#: nobody held.
PAD_HOLD_DELAY = 0.30

#: How often the made-up repeat stream ticks, in seconds. The hold's fill is
#: wall-clock time, so this only sets how smoothly its bar moves.
PAD_REPEAT_RATE = 0.05

#: The handheld draws its canvas at *half* the screen, and the GPU puts it back.
#:
#: That is the ordinary pipeline of a pixel game -- a fixed low-resolution canvas,
#: scaled up by a whole number with nearest-neighbour filtering -- and it is what a
#: phone actually wants: every pixel the game blends is a *quarter* of the work of
#: blending at the panel's own resolution, and the scaling is the one thing the GPU
#: is good at. Measured before this: the art pass alone was 47 ms a frame on a
#: device whose GPU would have done the same picture for nothing.
#:
#: Two, and not a ladder of zooms: 1240x1080 divided by two is exactly 620x540,
#: which is 62 cells by 27 at the game's own ten-by-twenty cell -- the desktop's
#: twenty-seven rows, the same face, the same figures. A third or a fourth would
#: not divide the grid, and a fractional upscale is a pixel game with uneven
#: pixels, which is the one thing a pixel game cannot be.
HANDHELD_SCALE = 2

#: The handheld's screen, for the one thing that has to be known before a window
#: exists: the canvas. The platform is asked first -- it knows -- and this is what a
#: platform that answers nonsense gets.
SCREEN = (1240, 1080)


def on_android() -> bool:
    """Whether this process is running inside a python-for-android package.

    p4a sets ``ANDROID_ARGUMENT`` (and ``ANDROID_PRIVATE``) before the app starts,
    and a desktop sets neither, so this is the honest test for "there is no
    command line here" -- which is the whole reason the handheld's canvas and its
    save directory are decided rather than asked for.
    """
    return bool(os.environ.get("ANDROID_ARGUMENT"))


class KeyPress:
    """A key press, in the shape the screens already ask for.

    They want two things a name cannot carry: whether the key is *held* -- which
    the hold bars count -- and the character it types. Making the same two
    questions answerable here is the whole of what a front end owes a screen.
    """

    def __init__(self, repeat: bool = False, text: str = "") -> None:
        self._repeat = repeat
        self._text = text

    def isAutoRepeat(self) -> bool:  # noqa: N802 - Qt's spelling, and the screens'
        return self._repeat

    def text(self) -> str:
        return self._text


def _changed_rows(before: tuple[int, ...], after: tuple[int, ...]) -> list[tuple[int, int]]:
    """The rows that differ, as ``(first, last)`` bands of consecutive rows.

    One band per uninterrupted stretch of changed lines, because a screen that
    scrolls its log changes three rows *next to each other* and a blit of a band is
    one blit rather than three.
    """
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for index, (old, new) in enumerate(zip(before, after)):
        if old != new:
            if start is None:
                start = index
        elif start is not None:
            bands.append((start, index))
            start = None
    if start is not None:
        bands.append((start, len(after)))
    return bands


class SdlApp:
    """A window, a stack of screens, and the run they are about."""

    def __init__(
        self,
        *,
        seed: int = 3,
        cols: int = 96,
        rows: int = 27,
        scale: int = 2,
        screen=None,
        headline: bool = True,
        no_sound: bool = True,
        battle_scene: bool = False,
        fps: bool = False,
        timings: bool = False,
        sniff: bool = False,
        handheld: bool | None = None,
        backdrop: bool = True,
    ) -> None:
        import pygame

        # A DPI-aware process, said out loud rather than left to a toolkit's default.
        #
        # On a display scaled to 125% the *window* is the same size on the desk and a
        # quarter more pixels across it. Left unaware, a full screen is handed the
        # scaled-down view of the desktop -- 2048x1152 on a 2560x1440 monitor -- and
        # the room is derived from *that*: a quarter more cells across, a backdrop
        # fitted to a bigger canvas, and the same sprites in it. Which reads as
        # figures that shrank, and it is the one thing a player notices at once.
        #
        # Aware, full screen is the panel's own mode, the canvas comes out the same as
        # it would on an unscaled display, and the painting covers it exactly -- so
        # there is nothing to fix up afterwards.
        os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")
        # The canvas is a pixel game's and the renderer scales it; linear filtering
        # would turn every pixel into a smear, which is the whole thing a pixel
        # game exists against.
        os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "0")
        pygame.init()
        # The screens decide what a *held* key means -- the floor walks on one, a
        # shelf scrolls on one, and everything else refuses the repeats -- but SDL
        # does not make any unless it is asked, so holding a direction did nothing
        # at all. Delay and interval are the terminal's own feel: a pause long
        # enough that a tap is a tap, then the key's own pace.
        pygame.key.set_repeat(400, 60)
        #: The pads, if there are any. A handheld has nothing else and a desktop
        #: usually has none, which is why every screen still answers a keyboard:
        #: the keyboard is the *stand-in* here and not the other way round.
        #:
        #: Kept as a plain list so a test can hand in a pad that is not plugged
        #: in -- which is the only way the mapping can be held still.
        pygame.joystick.init()
        # The sticks and triggers do not need an *event*: the app polls the d-pad
        # every frame and reads the axes for the bench. SDL, left alone, puts an
        # event in the queue for every twitch of a noisy axis -- thousands a
        # second on a handheld -- and feeding each one cost about a third of the
        # frame. Blocked, the state is still there to be read; only the stream of
        # "it moved a hundredth" is gone.
        pygame.event.set_blocked([pygame.JOYAXISMOTION, pygame.JOYHATMOTION])
        self.joysticks: list = [
            pygame.joystick.Joystick(index)
            for index in range(pygame.joystick.get_count())
        ]
        #: Pad buttons that are *down* right now, by SDL's number. SDL reports a
        #: press and a release and nothing in between, so this is what tells a
        #: held button from a tap -- and what the made-up repeats are fed from.
        self._buttons_down: set[int] = set()
        self._pad_walk: str | None = None
        self._pad_walk_from = 0.0
        self._pad_walk_last = 0.0
        self._pad_hold_from: float | None = None
        self._pad_hold_last = 0.0
        #: Android's own lifecycle, by number. pygame names these three and a
        #: desktop never sends one; -1 is a type SDL never uses, so on a desktop
        #: the comparisons stay false and nothing has to be guarded twice.
        self._app_background = getattr(pygame, "APP_WILLENTERBACKGROUND", -1)
        self._app_foreground = getattr(pygame, "APP_DIDENTERFOREGROUND", -1)
        self._app_terminating = getattr(pygame, "APP_TERMINATING", -1)
        #: Whether SDL's own renderer presents the frame. On Android it must: a
        #: plain window surface is copied to the screen *in software* on every
        #: flip, and that is the difference between a game and a slide show. A
        #: renderer keeps the frame as a texture and the GPU scales it -- which
        #: is what the handheld fork did for exactly this reason.
        self._renderer = on_android()
        #: Whether a frame has been drawn yet. The one thing that has to know is
        #: ``_fit``: the canvas is chosen before the window exists, and on Android
        #: the window is the screen and gets the last word -- but only before the
        #: first frame, so a resize never moves the game.
        self._drawn = False
        #: The painted cells, and what they were painted from. A fight's panels and
        #: log are the same frame after frame -- the animation is the *art* pass --
        #: and repainting a megapixel of glyphs to get the same picture back is the
        #: one cost this application cannot afford on a phone.
        self._base = None
        self._base_rows: tuple[int, ...] | None = None
        self._base_frame: tuple | None = None
        #: Scaled pieces of art, keyed by what they were scaled from: a roster's
        #: portrait does not change size between frames either.
        self._art_scaled: dict[tuple, object] = {}
        #: The frame's numbers, on the frame. A handheld has no terminal to print
        #: `--timings` into and no ESC menu in a fight, so the one place the battle
        #: can be measured is over the battle: Select and Start together, or F1.
        self.show_overlay = False
        #: Whether this is a handheld's canvas rather than a window's grid. On
        #: Android it is, without being asked -- there is no command line on a
        #: handheld -- and on a desktop it is how the handheld is previewed.
        self.handheld = handheld if handheld is not None else on_android()
        pixel = 16
        self.font = SdlFont(str(FONT), pixel)
        #: The same smaller face the Qt build uses for the sidebar and the log:
        #: one size down, which is the one place a mixed size pays for itself.
        self.font_small = SdlFont(str(FONT), SMALL_PIXELS)
        self._pinned: tuple[int, int] | None = (
            self._handheld_grid() if self.handheld else None
        )
        self.progress = load_meta()
        #: The glass: the same settings the Qt build reads out of the same file,
        #: so a player who turned the scanlines off keeps them off. The shader and
        #: the settings are shared; only the context is this front end's.
        from ..desktop.crt_gl import CrtSettings
        from ..desktop.settings import load_settings

        saved = load_settings()
        self.crt = CrtSettings(
            scanlines=bool(saved.get("scanlines", True)),
            bloom=bool(saved.get("bloom", True)),
            geometry=bool(saved.get("geometry", False)),
        )
        self.glass = None
        #: A frame counter, for the flag that asks for one. Smoothed, because a
        #: number that jitters by ten a frame tells you nothing.
        self.show_fps = fps
        #: And where the frame's milliseconds go, for the other flag. Printed once
        #: a second and never drawn: a breakdown is a thing to read in a terminal,
        #: not a thing to put in the picture.
        self.show_timings = timings
        self._timing: dict[str, tuple[float, int]] = {}
        #: The worst a stage has been, for the bench: an average hides the frame
        #: that took a second, and the frame that took a second is the question.
        self._worst: dict[str, float] = {}
        self._timing_since = time.monotonic()
        #: The grid, made once and cleared from then on. It is *this* app's, so it
        #: is made here rather than on the first frame -- a screen is handed a
        #: blank grid and never has to ask whose turn it is.
        from ..desktop.pattern import PatternBuffer

        # A pinned canvas is the device's, and the device's alone: the window may
        # be a preview of it at half size on a laptop, but the grid is the one the
        # screen will be drawn at. The floor below is what the *derived* path
        # needs -- a window that fit fewer cells than this would not be a smaller
        # game but a broken one -- and a chosen grid is not derived from anything.
        if self._pinned is not None:
            self.cols, self.rows = self._pinned
        else:
            self.cols = max(MIN_COLS, cols)
            self.rows = max(MIN_ROWS, rows)
        self.grid = PatternBuffer(self.cols, self.rows, self.font)
        #: Whether the arena is one painted room or the game's own tiles. The
        #: reference build has no painting, so this is a dial for looking at art.
        self.backdrop = backdrop
        self.frames = 0.0
        self.seed = seed
        self.run = None
        #: The premise, told once between the choice and the floor -- the same
        #: once-per-session the Qt build means, and the same screen. It needs a
        #: key *release* to tell a tap from a hold, which is why this waited for
        #: one: see ``feed``.
        self.prologue_seen = False
        #: What a glass key just did, for as long as it takes to read.
        self.glass_note: tuple[str, float] | None = None
        self.scale = max(1, scale)
        if screen is not None:
            self.screens = [screen]
        else:
            from ..desktop.screens.title import TitleScreen

            self.screens = [TitleScreen()]
        self.effects = SdlEffects()
        #: The glass, which is the same object: a landed blow shakes the *frame*,
        #: and the frame is this application's own. The arena asks ``view.shake``
        #: exactly as it does under Qt, and what it gets is a surface drawn a few
        #: pixels off centre -- which is what a shaken glass is.
        self.view = self.effects
        #: The same sound system the Qt build plays through, and always an
        #: object: a screen asks it whether it is muted, and a *missing* mixer is
        #: not the same answer as a quiet one. Where a machine has no audio the
        #: mixer gives up on its own and says so.
        from ..desktop.audio import Sfx

        self.sfx = Sfx(muted=no_sound or self.progress.muted)
        #: And when it gives up mid-session, the record has to agree -- or the
        #: next toggle writes the give-up back down as "unmuted".
        self.sfx.on_mute = self._sound_gave_up
        #: What the game asked to be heard. A front end with no sound is still a
        #: front end that was asked, and a test can read this.
        self.played: list[str] = []
        self.headline = headline
        self._window = None
        self._surface = None
        self._last_frame: float | None = None
        #: Whether the window is the whole screen, and where the picture sits in
        #: whatever size the window has now. Both move on F11 and on a resize.
        self._fullscreen = False
        #: Keys that are *down* right now, and the ones that were already down
        #: when the screen on top changed. A held key repeats thirty times a
        #: second, and a new screen must not be answered by a press that happened
        #: before it existed -- holding enter to start used to run straight
        #: through the name entry behind the death screen.
        self._down: set[str] = set()
        self._stale: set[str] = set()
        self._shown = self._buffer_size()
        self._shown_at = (0, 0)
        self._title = "Neverdead's Revenge"
        #: Whether the window loop should keep going. Only ``quit`` clears it --
        #: there is no window object to ask on this front end.
        self._running = True
        if battle_scene:
            self.open_battle_scene()
        if sniff:
            self.open_bench()

    # -- the stack ---------------------------------------------------------
    def _forget_presses(self) -> None:
        """A new screen has to be told the key is already down, and not by a press.

        The houses rule in this game is that a screen answers a *press*: a key
        held from the screen before this one must not choose anything here. Holds
        keep their repeats -- they live on them -- but the first press on a new
        screen has to be a fresh one.
        """
        self._stale |= self._down

    def push(self, screen) -> None:
        self.screens.append(screen)
        self._forget_presses()

    def pop(self) -> None:
        if len(self.screens) > 1:
            self.screens.pop()
        self._forget_presses()

    def swap(self, screen) -> None:
        self.screens[-1:] = [screen]
        self._forget_presses()

    def return_to_title(self) -> None:
        from ..desktop.screens.title import TitleScreen

        self.screens = [TitleScreen()]

    # -- what the screens ask of an application ------------------------------
    def has_saved_run(self) -> bool:
        from ..persistence import load_run

        return load_run() is not None

    def play(self, name: str = "hit") -> None:
        """Make the noise. The same sound system the Qt build uses, and the same
        files -- it never knew about a window either."""
        self.played.append(name)
        self.sfx.play(name)

    def play_after(self, before: tuple[int, int, int]) -> None:
        """Make the noise the last thing that happened deserves.

        The port of the Qt build's own rules, and the rules are the game's: a new
        floor beats a level, a level beats a kill, and the loudest line in the log
        says what the rest sounded like.
        """
        run = self.run
        if run is None or run.over:
            return
        from ..desktop.audio import loudest_kind, sound_for_kind

        before_log, before_depth, before_level = before
        if run.depth != before_depth:
            self.play("door_creak")
            return
        if run.level != before_level:
            self.play("level_up")
            return
        kind = loudest_kind(entry.kind for entry in run.log[before_log:])
        sound = sound_for_kind(kind)
        if sound:
            self.play(sound)

    def save_progress(self) -> None:
        from ..persistence import save_meta

        try:
            save_meta(self.progress)
        except OSError:
            pass

    def show_game_over(self, won: bool = False) -> None:
        from ..desktop.screens.game_over import GameOverScreen

        self.play("quest_complete" if won else "death_game_over")
        self.push(
            GameOverScreen(
                state=self.run,
                won=won,
                best=max(self.progress.best_score, self.run.score),
                can_rewind=self.run.rewind_ready and not won,
                on_done=lambda answer: self.after_summary(answer),
            )
        )

    def open_encounter(self) -> bool:
        """The floor handed a fight over: the arena goes on top of the room.

        Two things differ from the Qt build, and both are because of what is not
        ported yet. The *turning* -- the step, the letter coming at the camera,
        the white -- is painted in pixels, so the fight opens without it; and
        because there is no turning screen in between, the arena is *pushed* on
        top of the floor rather than swapped over it. Under Qt the arena replaces
        the turning screen and the floor is already underneath; pushing is the
        same stack with the missing screen left out.

        What is not skipped is the fight: the same ``open_fight`` builds the same
        room, with the same rules, and the player fights it.
        """
        if self.run is None or self.run.encounter is None:
            return False
        from ..game.battle import Battle, encounter_around
        from .turning import SdlTurning

        trigger = self.run.encounter
        # Cleared before the arena opens: the domain is done with it the moment
        # it is set, and a fight that is asked for twice would be two fights.
        self.run.encounter = None
        battle = Battle(self.run, encounter_around(self.run, trigger))
        self.push(SdlTurning(trigger, battle))
        return True

    def enter_battle(self, battle) -> None:
        """The arena, in the place of whoever was turning the room over."""
        from .arena import SdlArena

        self.swap(SdlArena(battle, backdrop=self.backdrop))

    def leave_battle(self) -> None:
        """The fight is over: back to the floor, or home if there is no floor."""
        if len(self.screens) > 1:
            self.pop()
        else:
            self.return_to_title()
        screen = self.screens[-1] if self.screens else None
        if screen is not None:
            catch_up = getattr(screen, "catch_up", None)
            if catch_up is not None:
                catch_up(self)

    def screen_point(self, position):
        """Where a cell is, in the frame's own pixels -- or ``None``.

        The grid is the *camera* and not the dungeon, so this is the game's own
        translation and not a multiplication: a square at ``(38, 9)`` is somewhere
        else on the screen unless the camera happens to say so. Everything that
        skipped it drew in the wrong place, which is exactly what happened to the
        coins here -- sprayed over a wall while the hero picked them up on the
        other side of it.
        """
        from ..desktop.render import screen_point

        if self.run is None:
            return None
        return screen_point(
            self.run,
            position,
            self.cols,
            self.rows,
            self.font.cell_w,
            self.font.cell_h,
        )

    def open_battle_scene(self) -> None:
        """The dev door: a fight against the first monsters of a fresh floor.

        The same door the Qt build has, and for the same reason: a run starts on
        the floor and a fight is reached by walking into one, which is the game
        and not a shortcut -- but looking at the arena should not cost a walk.
        """
        from ..game.actors import HEROES
        from ..game.battle import Battle
        from ..game.state import start_run
        from .arena import SdlArena

        if self.run is None:
            self.run = start_run(HEROES["noxx"], self._a_seed())
        self.screens = [
            SdlArena(Battle(self.run, self.run.enemies[:3]), backdrop=self.backdrop)
        ]
        self.redraw()

    def open_shop(self) -> None:
        """The shop: the same screen the Qt build pushes, on this stack."""
        from ..desktop.screens.menus import ShopScreen

        self.push(ShopScreen())

    def open_scoreboard(self) -> None:
        from ..desktop.screens.menus import ScoreboardScreen

        self.push(ScoreboardScreen())

    def open_chronicle(self) -> None:
        from ..desktop.screens.menus import ChronicleScreen

        self.push(ChronicleScreen())

    def open_bench(self) -> None:
        """The pad bench: what *this* pad actually sends, raw.

        Reachable from the command line (``--sniff``) and from the pause menu
        whenever a pad is plugged in, which is the door that matters on a
        handheld: there is no command line to pass a flag to once the app is
        installed, and the question it answers -- is the button arriving at all,
        and as what? -- can only be asked on the device.
        """
        from .bench import PadBench

        self.push(PadBench())

    def open_delete_progress(self) -> None:
        """Ask for the word, then erase everything.

        The dialog is the whole safety: it answers ``True`` only when DELETE was
        typed, and anything else leaves the profile exactly where it was.
        """
        from ..desktop.screens.dialogs import DeleteProgressScreen

        self.push(
            DeleteProgressScreen(
                on_done=lambda confirmed: self.delete_progress() if confirmed else None
            )
        )

    def delete_progress(self) -> None:
        """Wipe the profile and the saved run. Nothing is kept back."""
        from ..persistence import clear_run
        from ..persistence import MetaProgress

        self.progress = MetaProgress()
        self.save_progress()
        clear_run()
        self.run = None

    def record_run(self, state, name: str = "") -> int:
        """Put the run on the board -- the board outlives the window, so it is
        the *progress*'s business and not this application's."""
        from ..core.rng import Rng
        from ..game.state import RunState

        self.progress.record_run(
            depth=state.depth,
            score=state.score,
            kills=state.kills,
            gold=state.gold,
            won=state.run_state is RunState.ESCAPED,
            name=name,
            hero=state.hero.key,
        )
        self.progress.reroll_wilds(Rng(random.SystemRandom().randrange(2**32)))
        self.save_progress()
        return self.progress.best_score

    def after_summary(self, answer) -> None:
        """The summary is answered: a name for the board, or the hour back.

        The same two doors the Qt build has, and the same screens behind them: a
        run that escaped may be written down, and one that ended in the dark may
        spend the hour it borrowed to be here.
        """
        from ..desktop.screens.game_over import REWIND, NameEntryScreen
        from ..game.actions import Action, perform_action

        state = self.run
        if state is None:
            return
        if answer != REWIND:

            def done(name: str) -> None:
                if state is not None:
                    self.record_run(state, name or "???")
                self.return_to_title()

            self.push(
                NameEntryScreen(state.score, self.progress.last_name, on_done=done)
            )
            return
        perform_action(state, Action.REWIND)
        self.redraw()

    def save_and_quit(self) -> None:
        """Put the run down and go back to the title, keeping it for later."""
        from ..game.savegame import dump
        from ..persistence import save_run

        if self.run is not None:
            save_run(dump(self.run))
        self.return_to_title()

    # -- the phone's own interruptions ---------------------------------------
    def _suspend(self) -> None:
        """The app is leaving the foreground: write the run down and stand down.

        Android can take the process away without another word, and a run is forty
        kilobytes of map. It goes into the same file "save and quit" writes, so
        ``continue_run`` picks it up exactly as it would after a deliberate exit --
        which is the whole difference between a handheld and a desktop here: a
        desktop that closes has been asked, and a phone has not.
        """
        from ..game.savegame import dump
        from ..persistence import save_run

        if self.run is not None:
            try:
                save_run(dump(self.run))
            except OSError:
                # A save that cannot be written is not a reason to die on the way
                # out: the process is going to be taken away anyway.
                pass

    def _resume(self) -> None:
        """Back in front: repaint what was underneath."""
        self.redraw()

    def quit(self) -> None:
        """Close the window: the loop stops at the end of this frame."""
        self._running = False

    def quit_requested(self) -> None:
        from ..desktop.screens.dialogs import ConfirmScreen

        self.push(
            ConfirmScreen(
                "QUIT NEVERDEAD'S REVENGE?",
                "The dungeon will still be here when you come back.",
                on_done=lambda yes: self.quit() if yes else None,
            )
        )

    def confirm_quit_to_title(self) -> None:
        from ..desktop.screens.dialogs import ConfirmScreen

        self.push(
            ConfirmScreen(
                "QUIT TO THE TITLE?",
                "The run does not come back. It is not written down.",
                on_done=lambda yes: self.return_to_title() if yes else None,
            )
        )

    def _sound_gave_up(self, muted: bool) -> None:
        """The audio session quit on its own; the record has to agree."""
        self.progress.muted = muted
        self.save_progress()

    def toggle_sound(self) -> None:
        """Turn the sound over, and write the answer down: a player who mutes a
        game expects it to *stay* muted the next time they open it."""
        self.sfx.toggle()
        self.progress.muted = self.sfx.muted
        self.save_progress()

    def open_hero_select(self) -> None:
        from ..desktop.screens.hero_select import HeroSelectScreen

        self.push(HeroSelectScreen())

    def _a_seed(self) -> int:
        """The seed for the run about to begin.

        Fresh per run -- *not* stored: keeping the roll would make every NEW RUN
        in one session the same dungeon wearing yesterday's clothes, which is the
        bug the Qt build has a comment about. A seed the player pinned with
        ``--seed`` is the exception, and ``is None`` and not a truth test,
        because seed 0 is a seed.
        """
        if self.seed is not None:
            return self.seed
        return random.SystemRandom().randrange(2**32)

    def begin_run(self, hero_key: str) -> None:
        from ..desktop.screens.game import GameScreen

        if not self.prologue_seen:
            # The premise, told once, between the choice and the floor. A held
            # enter lets it go; escape skips it; and every run after the first
            # starts without it being repeated.
            self.prologue_seen = True
            from ..desktop.screens.prologue import PrologueScreen

            self.push(PrologueScreen(on_done=lambda: self.begin_run(hero_key)))
            return
        from ..game.actors import HEROES
        from ..game.lore import PAGE_COUNT
        from ..game.shop import loadout_from
        from ..game.state import start_run

        loadout = loadout_from(self.progress)
        self.save_progress()
        self.run = start_run(
            HEROES[hero_key],
            self._a_seed(),
            loadout=loadout,
            # The pages this book is still missing, so a run knows what is out
            # there -- the same tuple the Qt build hands over.
            pages=tuple(
                number
                for number in range(1, PAGE_COUNT + 1)
                if number not in self.progress.pages
            ),
        )
        self.effects.clear()
        self.screens = [GameScreen(self.run)]
        self.redraw()

    def continue_run(self) -> None:
        """Pick a saved run back up -- and let go of the file once it is open.

        The same shape as the Qt build's, and for the same reason: a run that is
        being played lives in memory, and a copy left lying on disk would be the
        run the player *had* the next time they sat down. A save this build cannot
        read -- written by another version, or half written when the machine went
        down -- is thrown away rather than thrown, because a dungeon that will not
        open is not a crash, it is an empty slot.
        """
        from ..desktop.screens.game import GameScreen
        from ..game.savegame import load
        from ..persistence import clear_run, load_run

        payload = load_run()
        if not payload:
            return
        try:
            state = load(payload)
        except Exception:
            clear_run()
            return
        clear_run()
        self.run = state
        self.screens = [GameScreen(state)]
        self.redraw()

    # -- the picture --------------------------------------------------------
    def feed(self, event) -> None:
        """Hand one event from the window to the game: all the loop does.

        Its own method, and not three lines inside the loop, because this is the
        only place where a *real* key press is turned into what a screen answers
        -- and that is exactly the seam a test could not reach while it lived in
        a `while` that never returns. It was wrong there for a while: the event
        object itself was passed where a bool belonged, so every key looked like
        an auto-repeat, and the menus -- which answer one press and not thirty a
        second -- swallowed the lot.
        """
        import pygame

        # The bench (``--sniff``) is shown every event *raw*, before any mapping
        # has read it -- which is the whole point of it: the question there is
        # what arrives, not what survived. No other screen defines this.
        note = getattr(self.screens[-1], "note", None)
        if note is not None:
            note(event, self)
        if event.type == pygame.QUIT:
            self.quit()
        elif event.type == self._app_background:
            # Android is about to put us in the background, and it may take the
            # process away without another word. A run is forty kilobytes of map,
            # and it is written down now rather than hoped for later.
            self._suspend()
        elif event.type == self._app_foreground:
            self._resume()
        elif event.type == self._app_terminating:
            self._suspend()
            self.quit()
        elif event.type == pygame.KEYDOWN:
            text = typed(event)
            name = name_of(event)
            if name is not None and name in self._stale:
                # Down before this screen existed: it has to come up and be
                # pressed again before anything here hears it.
                return
            if name is not None:
                self._down.add(name)
            self.key(
                name_of(event),
                # ``repeat`` and not the event: the screens ask whether the key
                # is being *held*, and anything truthy answers yes.
                KeyPress(bool(getattr(event, "repeat", False)), text),
                text,
            )
        elif event.type == pygame.KEYUP:
            # Which half of a hold: a screen that runs a hold bar has to be told
            # when the key comes *up*, or a tap banks itself and a screen walked
            # through on a press nobody held. Not every platform pairs its
            # repeats with a release; this one does, so it is passed on.
            name = name_of(event)
            if name is not None:
                self._down.discard(name)
                self._stale.discard(name)
            screen = self.screens[-1]
            if name and screen.key_up(name, KeyPress(False, typed(event)), self):
                self.redraw()
        elif event.type == pygame.VIDEORESIZE:
            # The window manager's answer, not ours: the picture is fitted to
            # whatever it says, and the glass hears about it.
            self._fit()
            self.redraw()
        elif event.type == pygame.JOYBUTTONDOWN:
            self._pad_button(event.button, down=True)
        elif event.type == pygame.JOYBUTTONUP:
            self._pad_button(event.button, down=False)

    # -- the pad ------------------------------------------------------------
    def _pad_button(self, button: int, *, down: bool) -> None:
        """One pad button, in the game's own words.

        A button is an *event*, exactly like a key: one press, one action. Only
        the directions are polled (a d-pad is a position and not a stream of
        presses), and only the holds are repeated (SDL sends nothing between a
        button going down and coming up) -- both of which live in ``tick``.

        The two books are kept the same way a key's are, for the same reason: a
        held button that opened a screen must not choose anything on it.
        """
        name = button_name(button)
        if name is None:
            return
        if down:
            self._buttons_down.add(button)
            if {4, 6} <= self._buttons_down:
                # Select and Start together: the numbers, over whatever is on the
                # frame -- which in a fight is the only way to see them at all.
                self.show_overlay = not self.show_overlay
                self.redraw()
            if name in self._stale:
                # Down before this screen existed: it has to come up and be
                # pressed again before anything here hears it.
                return
            self._down.add(name)
            self.key(name, KeyPress(False, ""), "")
            return
        self._buttons_down.discard(button)
        self._down.discard(name)
        self._stale.discard(name)
        screen = self.screens[-1]
        if screen.key_up(name, KeyPress(False, ""), self):
            self.redraw()

    def pad_direction(self) -> str | None:
        """Where the pad is being pushed, as the key the game answers to.

        The d-pad only. The analog stick is deliberately **not** read for
        movement: it drifts, and a resting stick on the bench reported itself as
        "down" forever -- which walked the premise and ran the menus off the
        bottom of the screen. The bench still shows the stick raw, which is
        where a mapping is checked.

        No keyboard fallback either, and that is the one place this differs from
        the handheld build it comes from: on a desktop the arrow keys already
        repeat themselves (SDL's own delay and interval, asked for above), so
        reading them here as well would walk a held key twice per repeat.
        """
        for stick in self.joysticks:
            pushed = dpad_direction(stick)
            if pushed is not None:
                return DIRECTION_KEYS.get(pushed)
        return None

    def _poll_pad(self, now: float) -> None:
        """A pushed direction walks, and the pad's A holds.

        Read on the clock and not on events, because neither is a stream: a
        d-pad is a *position*, and a held button is a *state*. A keyboard does
        both by itself; a pad sends one press and one release and nothing in
        between, so both streams are made here.
        """
        self._poll_pad_walk(now)
        self._poll_pad_hold(now)

    def _poll_pad_walk(self, now: float) -> None:
        """A held direction: one step at once, then repeats at the game's pace."""
        direction = self.pad_direction()
        if direction is None:
            self._pad_walk = None
            return
        if direction != self._pad_walk:
            # A new direction, or the first frame of one: that is a press, not a
            # repeat, so a tap of any ordinary length is exactly one square.
            self._pad_walk = direction
            self._pad_walk_from = now + PAD_WALK_DELAY
            self._pad_walk_last = now
            self.key(direction, KeyPress(False, ""), "")
            return
        if now < self._pad_walk_from or now - self._pad_walk_last < PAD_REPEAT_RATE:
            return
        self._pad_walk_last = now
        self.key(direction, KeyPress(True, ""), "")

    def _poll_pad_hold(self, now: float) -> None:
        """The pad's A, fed as the repeat stream a hold screen waits for.

        The prologue, the death tally and erasing the profile all advance on a
        *stream* of presses -- the fill is the time since the first one -- and a
        pad does not send one. Fed here rather than by the keyboard's own
        repeats, so a desktop hold is exactly what it was: only the pad's A is
        watched, and the first repeat waits longer than a tap so that a tap
        still banks nothing.
        """
        hold = getattr(self.screens[-1], "hold", None)
        key = hold.keys[0] if hold is not None and hold.keys else None
        if key is None or key != button_name(0) or 0 not in self._buttons_down:
            self._pad_hold_from = None
            return
        if self._pad_hold_from is None:
            self._pad_hold_from = now + PAD_HOLD_DELAY
            self._pad_hold_last = now
            return
        if now < self._pad_hold_from or now - self._pad_hold_last < PAD_REPEAT_RATE:
            return
        self._pad_hold_last = now
        self.key(key, KeyPress(True, ""), "")

    def tick(self, dt: float) -> None:
        """A frame went by: let the screen play, let the pixels move, repaint.

        Called by the window loop and by anything driving this headless. A screen
        that is *moving* is asked every frame -- a fight breathes whether or not it
        is talking, and this is the only clock the second front end has -- and one
        that is busy is asked until it is done.
        """
        now = time.monotonic()
        if self._last_frame is not None:
            # Measured here and not from ``dt``: the loop clamps its step to a
            # thirtieth of a second so the *game* keeps its pace, and a counter
            # reading that would report thirty forever.
            gap = max(1e-4, now - self._last_frame)
            self.frames = (self.frames * 9.0 + (1.0 / gap)) / 10.0
        self._last_frame = now
        mark = time.perf_counter()
        screen = self.screens[-1]
        if getattr(screen, "busy", False) or getattr(screen, "animating", False):
            screen.step(dt, self)
        self.effects.step(dt)
        # A pad sends no repeats of its own: a held direction and a held button
        # are turned into the stream the screens already answer, before the frame
        # that shows what they did.
        self._poll_pad(now)
        # Between the clock and the frame: the fight's own playback, the effects
        # and the pad. Booked because it is the one part of a frame the bench could
        # not see, and on a device it was about a third of it.
        self._note("logic", mark)
        self.redraw()
        self._report_timings(time.monotonic())

    def redraw(self) -> None:
        """Draw the stack into the grid, and the grid onto the window."""
        from ..desktop.pattern import PatternBuffer

        # The grid is reused and cleared rather than rebuilt. A frame of this game
        # is two thousand six hundred cells, and a fresh buffer every frame was two
        # thousand six hundred cells and their styles made again to hold the same
        # blanks. The *shape* can change -- the window moves, and the grid is
        # derived from it -- so the shape is what is checked.
        if (self.grid.cols, self.grid.rows) != (self.cols, self.rows):
            self.grid = PatternBuffer(self.cols, self.rows, self.font)
        else:
            self.grid.font = self.font
            self.grid.clear()
        mark = time.perf_counter()
        # An opaque modal: nothing under it is drawn. A menu is a panel, not a
        # window onto the dungeon, so the topmost modal roots the stack -- the
        # same rule the Qt build keeps, and the reason a dialog is not a
        # see-through ghost of the fight behind it.
        start = 0
        for index, screen in enumerate(self.screens):
            if getattr(screen, "modal", False):
                start = index
        for screen in self.screens[start:]:
            screen.draw(self.grid, self)
        mark = self._note("cells", mark)
        # A screen may bring its own paper: the arena's painted room goes *under*
        # the cells, so the panels, the log and the sidebar sit on it instead of
        # on a black field beside it.
        base = BACKGROUND
        paper = getattr(self.screens[-1], "paper", None)
        if paper is not None:
            # A screen with no painting to show answers None, and flat paper is
            # what the frame wanted all along.
            base = paper(self.cols, self.rows, self.font) or BACKGROUND
        # The cells are repainted only when something was *written*, and then only
        # the *rows* that were written: a cursor in a menu and a line arriving in
        # the log are one row each, and a row is a hundredth of the frame. The art
        # over the cells is not part of this cache -- it moves every frame, which
        # is the point.
        rows = tuple(self.grid.row_signature)
        frame = (self.cols, self.rows, base)
        if self._base is None or frame != self._base_frame:
            self._base = paint(self.grid, self.font, base)
            self._base_rows = rows
            self._base_frame = frame
        elif rows != self._base_rows:
            for first, last in _changed_rows(self._base_rows, rows):
                band = paint(self.grid, self.font, base, rows=(first, last))
                self._base.blit(band, (0, first * self.font.cell_h))
            self._base_rows = rows
        self._surface = self._frame()
        self._surface.blit(self._base, (0, 0))
        mark = self._note("paint", mark)
        self._small_face()
        # And a screen may paint straight onto the frame once the grid is drawn:
        # that is where the art lives -- sprites do not fit in a character cell.
        # It is called `paint_over` and not `paste`, which is Qt's name for the
        # same pass, because the Qt screens in this same stack have a `paste` too
        # and it wants a QImage: one name for two media is one crash waiting.
        paint_over = getattr(self.screens[-1], "paint_over", None)
        if paint_over is not None:
            paint_over(self._surface, self)
        mark = self._note("art", mark)
        self._blit_art()
        # And the pixels that are not the room: sparks thrown by whatever just
        # happened, drawn last so they land on top of everything.
        self.effects.draw(self._surface)
        self._draw_note()
        if self.show_fps:
            self._draw_fps()
        if self.show_overlay:
            self._draw_costs()
        self._present()
        self._drawn = True
        self._note("present", mark)

    def _frame(self):
        """The frame's surface, reused.

        It used to be whatever the painter returned, which was a megapixel made
        afresh every frame: an allocation and a first touch that a phone feels. It
        is made once per size now, in the display's own format so that blitting
        the cells into it is a copy and not a conversion.
        """
        import pygame

        width, height = self._buffer_size()
        if self._surface is None or self._surface.get_size() != (width, height):
            self._surface = pygame.Surface((width, height))
            try:
                self._surface = self._surface.convert()
            except pygame.error:  # pragma: no cover - no display to convert to
                pass
        return self._surface

    def _note(self, name: str, mark: float) -> float:
        """Book the milliseconds since ``mark`` under ``name``, and pass it on.

        Always measured, and not only when ``--timings`` asked: four clock reads a
        frame cost nothing, and the bench on a handheld has no terminal to print
        into -- the numbers it needs are exactly these. What the flag still decides
        is whether they are also *printed* once a second.
        """
        now = time.perf_counter()
        spent = now - mark
        total, frames = self._timing.get(name, (0.0, 0))
        self._timing[name] = (total + spent, frames + 1)
        self._worst[name] = max(self._worst.get(name, 0.0), spent)
        return now

    def frame_cost(self) -> list[tuple[str, float, float]]:
        """The frame's stages: ``(name, average ms, worst ms)``.

        For the bench, which is where a handheld's numbers can be read: a screen
        that says "4 ms in the cells and 900 in the presentation" is a diagnosis,
        and one that says "less than a frame a second" is a symptom.
        """
        return [
            (name, total / frames * 1000.0, self._worst.get(name, 0.0) * 1000.0)
            for name, (total, frames) in self._timing.items()
            if frames
        ]

    def _report_timings(self, now: float) -> None:
        """Once a second: what each stage of the frame cost, in milliseconds."""
        if not self.show_timings or now - self._timing_since < 1.0:
            return
        self._timing_since = now
        if not self._timing:
            return
        # Milliseconds per stage, from seconds spent -- and per *frame*, so a
        # second of running and a second of standing still read the same.
        parts = "  ".join(
            f"{name} {spent / frames * 1000.0:.2f}"
            for name, (spent, frames) in self._timing.items()
            if frames
        )
        done = sum(
            spent / frames * 1000.0 for spent, frames in self._timing.values() if frames
        )
        print(f"{self.frames:5.1f} fps   {parts}   ({done:.2f} ms drawn)")
        self._timing.clear()

    def _small_face(self) -> None:
        """The sidebar's lower rows and the combat log, one size down.

        The Qt build draws these straight onto the frame after the grid, and this
        is the same pass with a pygame painter: the *rows* come from the shared
        specs in ``desktop/render.py`` -- what to say, where, in which colour --
        and only the blitting is this application's. That is why the two front
        ends can show the same sidebar without one of them owning the layout.
        """
        import pygame

        from ..desktop.render import log_text, sidebar_text
        from ..desktop.theme import BACKGROUND, parse_style

        screen = self.screens[-1]
        if not getattr(screen, "smaller_face", False) or self.run is None:
            return
        face = self.font_small
        surface = self._surface
        rect, rows = log_text(
            self.run,
            self.grid.cols,
            self.grid.rows,
            self.font.cell_w,
            self.font.cell_h,
            face.cell_w,
            face.cell_h,
        )
        # The log's own panel, drawn solid: nothing is underneath it now that the
        # cells above it are clear.
        surface.fill(tuple(BACKGROUND), pygame.Rect(*rect))
        for ink in rows:
            self._put_small(surface, face, ink)
        out, rule = sidebar_text(
            self.run,
            self.grid.cols,
            self.grid.rows,
            self.font.cell_w,
            self.font.cell_h,
            face.cell_w,
            face.cell_h,
        )
        for ink in out:
            self._put_small(surface, face, ink)
        if rule is not None:
            surface.fill(
                tuple(parse_style("grey30").fg),
                pygame.Rect(rule[0], rule[2], rule[1] - rule[0], 1),
            )

    def _put_small(self, surface, face, ink) -> None:
        """One row of the small face: a string, blitted a glyph at a time."""
        from ..desktop.theme import parse_style

        colour = parse_style(ink.colour).fg
        for index, char in enumerate(ink.text):
            if char == " ":
                continue
            glyph = face.glyph(char, colour)
            if glyph is not None:
                surface.blit(glyph, (ink.x + index * face.cell_w, ink.y))

    def _draw_fps(self) -> None:
        """How fast this is going, in the corner, when ``--fps`` asked for it.

        Bottom right, on its own dark patch so it can be read over a sidebar: it
        is a developer's number and not part of the fiction, so it is allowed to
        sit on top of one.
        """
        import pygame

        from ..desktop.theme import BACKGROUND

        text = f"{self.frames:4.1f} fps"
        face = self.font_small
        width = len(text) * face.cell_w + 6
        height = face.cell_h + 4
        left = max(0, self._surface.get_width() - width)
        top = max(0, self._surface.get_height() - height)
        self._surface.fill(tuple(BACKGROUND), pygame.Rect(left, top, width, height))
        for index, char in enumerate(text):
            glyph = face.glyph(char, Colour(0xC8, 0xC8, 0xC8))
            if glyph is not None:
                self._surface.blit(
                    glyph, (left + 3 + index * face.cell_w, top + 2)
                )

    def _draw_costs(self) -> None:
        """The frame's numbers, in the corner, over the picture.

        For a device: the stages as average and worst, in whole milliseconds, and
        the frame rate. Whole numbers on purpose -- a figure that changes in its
        first decimal would make this overlay a reason to repaint every frame,
        which is the cost it exists to find.
        """
        import pygame

        from ..desktop.theme import BACKGROUND, parse_style

        face = self.font_small
        lines = [f"{self.frames:4.0f} fps"]
        stages = self.frame_cost()
        for start in range(0, len(stages), 2):
            parts = [f"{name} {avg:.0f}/{worst:.0f}" for name, avg, worst in stages[start : start + 2]]
            lines.append("  ".join(parts))
        width = (max(len(line) for line in lines) + 1) * face.cell_w + 6
        height = (len(lines) + 1) * face.cell_h + 4
        left = max(0, self._surface.get_width() - width)
        patch = pygame.Rect(left, 0, width, height)
        self._surface.fill(tuple(BACKGROUND), patch)
        colour = parse_style("bone").fg
        for row, line in enumerate(lines):
            for index, char in enumerate(line):
                glyph = face.glyph(char, colour)
                if glyph is not None:
                    self._surface.blit(
                        glyph, (left + 3 + index * face.cell_w, 2 + row * face.cell_h)
                    )

    def _blit_art(self) -> None:
        """The pictures a screen asked for, put where it asked for them.

        The same ``Placed`` records the Qt build blits, read by a painter that has
        never heard of Qt: the screen says what and where, and this puts it down.
        Which is the whole reason the records exist -- one roster, two frames.
        """
        import pygame

        from .paint import load

        for piece in self.screens[-1].art(self):
            art = load(piece.art)
            if art is None:
                continue
            width = max(
                1, round(art.get_width() * piece.height / max(1, art.get_height()))
            )
            # A portrait is the same size every frame: scaling it again is a
            # filtered resize of a megapixel, once per frame, for nothing.
            key = (piece.art, width, piece.height)
            scaled = self._art_scaled.get(key)
            if scaled is None:
                scaled = pygame.transform.smoothscale(art, (width, piece.height))
                self._art_scaled[key] = scaled
            self._surface.blit(
                scaled,
                (
                    round(piece.centre - width / 2),
                    round(piece.bottom - piece.height),
                ),
            )

    def _max_scale(self, width: int, height: int) -> int:
        """The largest whole-number scale that still leaves a playable grid."""
        return max(
            1,
            min(
                width // (MIN_COLS * self.font.cell_w),
                height // (MIN_ROWS * self.font.cell_h),
            ),
        )

    def _scale_for(self, width: int, height: int) -> int:
        """The one scale: the biggest that lands the grid near the target width."""
        ceiling = self._max_scale(width, height)
        target = max(1, round(width / (TARGET_COLS * self.font.cell_w)))
        return max(1, min(target, ceiling))

    def _screen_size(self) -> tuple[int, int]:
        """The screen this will be drawn on, asked before there is a window.

        The canvas has to be known *before* the window exists -- the window is
        made from it -- so the platform is asked directly. A platform that answers
        nothing usable (no display yet, or a size no grid fits in) gets the
        handheld's own screen, which is what this is for.
        """
        import pygame

        if pygame.display.get_init():
            try:
                sizes = pygame.display.get_desktop_sizes()
            except pygame.error:  # pragma: no cover - a driver without one
                sizes = []
            if sizes:
                width, height = sizes[0]
                if width >= 640 and height >= 480:
                    return int(width), int(height)
        return SCREEN

    def _grid_for(self, width: int, height: int) -> tuple[int, int]:
        """The cells a face makes of a screen of this size."""
        return (
            max(1, width // self.font.cell_w),
            max(1, height // self.font.cell_h),
        )

    def _handheld_grid(self) -> tuple[int, int]:
        """The canvas for a handheld: the screen at half size, in the game's cells.

        Chosen from the *screen*, and left alone from then on -- with one
        correction, in ``_fit``: the screen has to be asked for before there is a
        window to ask, and on a phone the window *is* the screen, so the first one
        that exists gets the last word. A desktop's window is a preview of the
        device and is deliberately not allowed to say anything.
        """
        width, height = self._screen_size()
        return self._grid_for(width // HANDHELD_SCALE, height // HANDHELD_SCALE)

    def _grid_size(self, width: int, height: int) -> tuple[int, int]:
        """How many cells fit in a window of this size, at that scale.

        The Qt build's rule, number for number, because it is the rule the game's
        panels were laid out for -- and because a second front end with its own
        idea of how much room there is would draw a different game at the same
        size. At 960x540 it comes out at the 96x27 both front ends start with;
        at 2560x1440 it comes out at 128x36, which is a full screen and no bars.

        A *chosen* canvas is not derived from anything, so this answers the choice
        and the window has no say in it.
        """
        if self._pinned is not None:
            return self._pinned
        scale = self._scale_for(width, height)
        cols = max(MIN_COLS, width // (self.font.cell_w * scale))
        rows = max(MIN_ROWS, height // (self.font.cell_h * scale))
        return cols, rows

    @property
    def cells(self) -> tuple[int, int]:
        """How big the frame is, in cells -- the same question the Qt app answers.

        A fixed grid here (the window scales, the grid does not), which is why
        this is two numbers and not a computation.
        """
        return (self.cols, self.rows)

    def _buffer_size(self) -> tuple[int, int]:
        """The picture's own size, in pixels: a cell is ten by twenty, always."""
        return (self.cols * self.font.cell_w, self.rows * self.font.cell_h)

    def _dpi(self) -> float:
        """How many physical pixels this desktop gives one logical pixel.

        Asked of the operating system, because nothing else knows: SDL hands an
        unaware process a scaled-down view of the desktop and hands an aware one the
        real thing, and from inside the game the two look identical. Windows answers
        directly; on Linux the toolkit's own scale is read from the environment, which
        covers GNOME and KDE; anything else is 1.0, which is the behaviour before this
        question was asked at all.
        """
        if sys.platform.startswith("win"):
            try:
                import ctypes

                return max(1.0, ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100.0)
            except Exception:  # noqa: BLE001 - a scale we cannot read is 1.0
                return 1.0
        for name in ("GDK_SCALE", "QT_SCALE_FACTOR"):
            value = os.environ.get(name)
            if value:
                try:
                    return max(1.0, float(value))
                except ValueError:
                    continue
        return 1.0

    def display_report(self) -> list[str]:
        """What this machine says about its display, for the case where it lies.

        A lines-of-text report and not a picture: when the room comes out the wrong
        size on somebody's monitor, the numbers that matter are the ones the platform
        is reporting -- the window, the drawable, the desktop, the scale -- and they
        cannot be read off a screenshot.
        """
        import pygame

        if not pygame.display.get_init():
            pygame.init()
        desktop = pygame.display.get_desktop_sizes()
        try:
            surface = pygame.display.get_surface()
            drawable = surface.get_size() if surface is not None else None
        except pygame.error:
            drawable = None
        grid = self._grid_size(self.cols * self.font.cell_w, self.rows * self.font.cell_h)
        return [
            f"platform      {sys.platform}",
            f"dpi scale     {self._dpi():.2f}",
            f"desktop       {desktop}",
            f"drawable      {drawable}",
            f"window        {self._shown}",
            f"canvas        {self.cols}x{self.rows} cells "
            f"= {self.cols * self.font.cell_w}x{self.rows * self.font.cell_h} px",
            f"scale setting {self.scale}",
            # A handheld's canvas is chosen rather than derived, so the things that
            # chose it are worth saying out loud: the face, the scale the GPU puts
            # it back up by, and which renderer drew it.
            f"canvas mode   {'handheld' if self.handheld else 'window'}  "
            f"face {self.font.pixel_size}px  x{HANDHELD_SCALE if self.handheld else 1} "
            f"drawn by {self.font.renderer}",
            f"screen        {self._screen_size()}",
            f"grid if full screen at that window  {grid[0]}x{grid[1]}",
        ]

    def _open_window(self) -> None:
        """Make the window, once, before the loop starts.

        The GL attributes have to be set *before* the display exists -- pygame
        refuses them afterwards -- so the whole of the window's creation is here
        and a full screen toggle never comes back through it. Any of this
        failing -- no driver, no context, a profile that will not take the shader
        -- is a plain window and no CRT: the game goes on either way.
        """
        import pygame

        base = self._buffer_size()
        size = (base[0] * self.scale, base[1] * self.scale)
        if self._renderer:
            # SCALED asks SDL for a renderer and makes the display surface the
            # *logical* one: the canvas is what is drawn into, and the renderer
            # scales and letterboxes it to the panel on every flip. Measured on a
            # desktop, the frame costs 4.5 ms at this canvas; a phone's plain
            # window surface turned that into less than one frame a second.
            self._window = pygame.display.set_mode(
                size, pygame.SCALED | pygame.FULLSCREEN
            )
            self._fit()
            return
        if self.crt.scanlines or self.crt.bloom or self.crt.geometry:
            try:
                import moderngl

                pygame.display.gl_set_attribute(
                    pygame.GL_CONTEXT_MAJOR_VERSION, 2
                )
                pygame.display.gl_set_attribute(
                    pygame.GL_CONTEXT_MINOR_VERSION, 1
                )
                self._window = pygame.display.set_mode(
                    size, pygame.OPENGL | pygame.DOUBLEBUF
                )
                from .glass import SdlGlass

                self.glass = SdlGlass(
                    self.crt,
                    base,
                    self._window.get_size(),
                    context=moderngl.create_context(),
                )
                self._fit()
                return
            except Exception:
                self.glass = None
        self._window = pygame.display.set_mode(size)
        self._fit()

    def _toggle_fullscreen(self) -> None:
        """F11: the window's own full screen, then the fit and the viewport.

        Not ``set_mode`` again, which is what this did first: that makes a *new*
        GL context, and the shader program -- with every texture in it -- belongs
        to the old one, so the object that was dropped took the process with it.
        SDL's own toggle keeps the window and its context alive. What it does
        *not* do is move the GL viewport or re-fit the picture, and that is the
        whole of what went wrong: the game stayed in the bottom left corner --
        the viewport's origin -- with the rest of the screen black.
        """
        import pygame

        self._fullscreen = not self._fullscreen
        if self.glass is not None:
            # SDL's own toggle keeps the window *and its context*: a `set_mode`
            # here would make a new context and leave the shader program behind
            # in the old one. What SDL does not do is move the GL viewport or
            # tell the shader that the window changed -- which is the whole of
            # what went wrong.
            pygame.display.toggle_fullscreen()
        else:
            # No glass: the surface itself is what gets blitted, so full screen
            # means a full-screen surface, and there is no context to lose.
            base = self._buffer_size()
            if self._fullscreen:
                size = pygame.display.get_desktop_sizes()[0]
                self._window = pygame.display.set_mode(size, pygame.FULLSCREEN)
            else:
                self._window = pygame.display.set_mode(
                    (base[0] * self.scale, base[1] * self.scale)
                )
        self._fit()

    def _fit(self) -> None:
        """How big the picture is on this window, and where it sits.

        Reckoned from the window's *current* size and not from the one that was
        asked for: full screen is a different window, and the whole-number scale
        that fits it is a different number. Without this the picture stays in the
        corner it was first drawn in -- the GL viewport's own origin, which is the
        bottom left.
        """
        import pygame

        # The *window's* size and not the surface's, which are two different
        # numbers: pygame keeps the display surface at the size it was made at,
        # so a full-screen window still reports 960x540 and the picture stays
        # that size in the corner of a black screen. The window knows.
        if pygame.display.get_init() and pygame.display.get_surface() is not None:
            width, height = pygame.display.get_window_size()
        elif self._window is not None:
            width, height = self._window.get_size()
        else:
            return
        if self._pinned is not None and on_android() and not self._drawn:
            # A phone's window *is* its screen, and the screen had to be guessed
            # at before there was a window to ask -- so the first window that
            # exists gets the last word on the canvas. Once, and only on Android:
            # a desktop's window is a preview of the device, and letting *that*
            # have a say would make a preview a different game at a different size.
            self._pinned = self._grid_for(
                width // HANDHELD_SCALE, height // HANDHELD_SCALE
            )
        # The grid comes from the window, the way the Qt build's does: whatever
        # is left over after the biggest whole-number scale becomes *cells* and
        # not black bars. A chosen canvas is the exception and answers itself --
        # which is what makes the window on a laptop a *preview* of the device
        # rather than a different game at a different size.
        cols, rows = self._grid_size(width, height)
        if (cols, rows) != (self.cols, self.rows):
            self.cols, self.rows = cols, rows
            if self.glass is not None:
                self.glass.resize(self._buffer_size())
        buffer_w, buffer_h = self._buffer_size()
        fit = max(1, min(width // buffer_w, height // buffer_h))
        self._shown = (fit * buffer_w, fit * buffer_h)
        self._shown_at = ((width - self._shown[0]) // 2, (height - self._shown[1]) // 2)
        if self.glass is not None:
            self.glass.fit((width, height), fit, self._shown_at)

    def _present(self) -> None:
        """Put the picture on the screen, whole-number scaled, or nowhere.

        Nowhere is a real answer: a headless run of this -- which is how the
        tests drive it -- has no window to put it on, and drawing is still done
        so that everything above it is exercised.
        """
        import pygame

        if not pygame.display.get_init() or self._window is None:
            return
        surface = self._window
        offset = self.effects.offset()
        fit = max(1, self._shown[0] // max(1, self._buffer_size()[0]))
        if self._renderer:
            # The display surface *is* the canvas and `flip` hands it to the GPU,
            # so nothing here is scaled: one copy of the frame, unless a blow is
            # shaking it, which is a blit a few pixels off centre.
            if offset != (0, 0):
                surface.fill((0, 0, 0))
            surface.blit(self._surface, offset)
            pygame.display.flip()
            return
        if self.glass is not None:
            # The glass has the whole picture and the whole window: it is the
            # thing that scales, so the shake goes in as part of its offset.
            self.glass.draw(
                self._surface, (offset[0] * fit, offset[1] * fit)
            )
            pygame.display.flip()
            return
        surface.fill((0, 0, 0))
        # At one-to-one the "scale" is a full-frame copy of a megapixel, once per
        # frame, for nothing.
        scaled = (
            self._surface
            if fit == 1
            else pygame.transform.scale(
                self._surface,
                (self._surface.get_width() * fit, self._surface.get_height() * fit),
            )
        )
        surface.blit(
            scaled,
            (self._shown_at[0] + offset[0] * fit, self._shown_at[1] + offset[1] * fit),
        )
        pygame.display.flip()

    # -- the keys -----------------------------------------------------------
    def key(self, name: str, event=None, text: str = "") -> bool:
        """Hand a key to the top screen. Returns whether it was used.

        A key with no *name* but with text is not nothing: a phone's keyboard does
        not send keycodes, it sends characters, and a name entry reads them the way
        it always read a typed letter. On a desktop the two arrive together -- a
        key that types a character has that character for a name -- so this is the
        same rule it always was there.
        """
        if not name:
            return False
        if self._glass_key(name):
            return True
        if name == "select" and self.run is not None:
            # Select and Start pause, from anywhere there is a run. The pause used
            # to be reachable only through the dungeon's escape -- and a pad has no
            # escape, so the one button a handheld keeps for "stop" did nothing.
            from ..desktop.screens.pause import PauseScreen

            if not isinstance(self.screens[-1], PauseScreen):
                self.push(PauseScreen())
                return True
        screen = self.screens[-1]
        press = event or KeyPress(text=text)
        used = screen.key(name, press, self)
        self._interface_sound(name, bool(used), press)
        self.redraw()
        return bool(used)

    def _interface_sound(self, name: str, used: bool, event) -> None:
        """The click of the interface, from the one place a key is delivered.

        Which sound is the *screen's* to say -- the floor's arrows walk a body
        and a menu's arrows walk a cursor, and only the screen knows which it
        just did. This end knows two things instead, and both of them are about
        *one* press: whether anything wanted it, and whether it was a repeat.

        A repeat is not a second click. Holding a key down is one gesture -- the
        hold-to-continue screens are built on exactly that -- and a click on
        every auto-repeat is a stutter of thirty confirmations for one decision.
        The screens that *are* a hold play their own confirm when the hold
        completes, which is the moment the player made it.
        """
        if not used:
            return
        if getattr(event, "isAutoRepeat", None) is not None and event.isAutoRepeat():
            return
        sound = getattr(self.screens[-1], "key_sound", None)
        if sound is None:
            return
        played = sound(name)
        if played:
            self.play(played)

    def _glass_key(self, name: str) -> bool:
        """The four keys that belong to the glass and not to a screen.

        The same four the Qt build answers, under the same names, because a key
        that turns the scanlines off should do it in either front end. The
        settings are written down as they change, so the choice survives the
        window.
        """
        import pygame

        if name == "f1":
            # The numbers on the frame, on a desktop as on a handheld: a
            # developer's switch, next to the ones that change the glass.
            self.show_overlay = not self.show_overlay
            self.redraw()
            return True
        if name == "f11":
            self._toggle_fullscreen()
            self.redraw()
            return True
        turned = {
            "f2": "scanlines",
            "f3": "bloom",
            "f4": "geometry",
        }.get(name)
        if turned is None:
            return False
        setattr(self.crt, turned, not getattr(self.crt, turned))
        self._remember_glass()
        self._note_glass(
            {
                "scanlines": "SCANLINES",
                "bloom": "BLOOM",
                "geometry": "CRT CURVE",
            }[turned]
            + (" ON" if getattr(self.crt, turned) else " OFF")
        )
        return True

    def _note_glass(self, note: str) -> None:
        """Say what a glass key just did, for as long as it takes to read.

        The Qt build writes its note *into* the pattern buffer before the frame
        is rendered; this one has a picture already, so it goes on the picture --
        same words, same two seconds, same place at the top. A CRT setting that
        changed with no acknowledgement is a key that might not have worked.
        """
        self.glass_note = (note, time.monotonic() + 2.0)

    def _draw_note(self) -> None:
        import pygame

        if self.glass_note is None:
            return
        note, until = self.glass_note
        if time.monotonic() > until:
            self.glass_note = None
            return
        from ..desktop.chrome import BONE
        from ..desktop.theme import parse_style

        face = self.font
        left = max(0, (self._surface.get_width() - len(note) * face.cell_w) // 2)
        band = pygame.Rect(0, 0, self._surface.get_width(), face.cell_h)
        self._surface.fill((0, 0, 0), band)
        colour = parse_style(f"bold {BONE}").fg
        for index, char in enumerate(note):
            glyph = face.glyph(char, colour, bold=True)
            if glyph is not None:
                self._surface.blit(glyph, (left + index * face.cell_w, 0))

    def _remember_glass(self) -> None:
        from ..desktop.settings import save_settings

        save_settings(
            {
                "scanlines": self.crt.scanlines,
                "bloom": self.crt.bloom,
                "geometry": self.crt.geometry,
            }
        )

    def open_window(self, *, title: str = "Neverdead's Revenge") -> None:
        """A real window, and the loop that feeds it.

        Not used by the tests, which drive ``key`` and ``redraw`` directly: the
        loop is the part that cannot be tested headless, and it is deliberately
        the smallest part of this file.
        """
        import pygame

        self._title = title
        pygame.display.set_caption(title)
        self._open_window()
        self.redraw()
        clock = pygame.time.Clock()
        self._running = True
        while self._running:
            # Every beat in this game is written against a thirtieth of a second,
            # so that is the frame this loop asks for: a fight that played faster
            # on a quicker machine would be a different fight.
            self.tick(min(clock.tick(60) / 1000.0, 1 / 30.0))
            for event in pygame.event.get():
                self.feed(event)
        pygame.quit()
