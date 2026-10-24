from __future__ import annotations

import os
import time
from ..persistence import load_meta
from .font import SdlFont
from .effects import SdlEffects
from .pad import Pad


from .app_shared import (
    dress_the_echo,
    SMALL_PIXELS,
    FONT,
    MIN_COLS,
    MIN_ROWS,
)

from .app_window import AppWindow
from .app_stack import AppStack
from .app_paint import AppPaint
from .app_loop import AppLoop

__all__ = ["SdlApp", "FONT", "MIN_COLS", "MIN_ROWS", "SMALL_PIXELS", "dress_the_echo"]


class SdlApp(AppWindow, AppStack, AppPaint, AppLoop):
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
        backdrop: bool = True,
        fullscreen: bool = True,
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
        pygame.init()
        # The screens decide what a *held* key means -- the floor walks on one, a
        # shelf scrolls on one, and everything else refuses the repeats -- but SDL
        # does not make any unless it is asked, so holding a direction did nothing
        # at all. Delay and interval are the terminal's own feel: a pause long
        # enough that a tap is a tap, then the key's own pace.
        pygame.key.set_repeat(400, 60)
        self.font = SdlFont(str(FONT))
        #: The same smaller face the Qt build uses for the sidebar and the log:
        #: one size down, which is the one place a mixed size pays for itself.
        self.font_small = SdlFont(str(FONT), SMALL_PIXELS)
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
        #: Whether the overworld's field is drawn twice as large. Not the glass
        #: and not the panels: a room is walked in, and a panel is read.
        self.field_zoom = bool(saved.get("zoom", False))
        #: The small grid the zoomed field is painted into, kept between frames.
        self._zoom_grid = None
        self.glass = None
        #: Why the last attempt at a GL window failed, for the diagnostics: a CRT
        #: that is not there should say so with the driver's own words.
        self._glass_error: object = None
        #: A frame counter, for the flag that asks for one. Smoothed, because a
        #: number that jitters by ten a frame tells you nothing.
        self.show_fps = fps
        #: And where the frame's milliseconds go, for the other flag. Printed once
        #: a second and never drawn: a breakdown is a thing to read in a terminal,
        #: not a thing to put in the picture.
        self.show_timings = timings
        #: Whether a launcher started us -- Steam, or a runtime around it. Such a
        #: launch has no terminal and no easy way to pass a flag, so the first
        #: fifteen seconds of frame reports are written on their own.
        launcher = any(
            os.environ.get(name)
            for name in (
                "SteamGameId",
                "SteamAppId",
                "STEAM_RUNTIME",
                "PRESSURE_VESSEL_VERSION",
            )
        )
        #: Whether a frame is being measured right now: the flag, or the start of
        #: a launcher's run. ``_timing_until`` ends the automatic window.
        self._timing_now = bool(timings or launcher)
        self._timing_until = time.monotonic() + 15.0 if launcher else 0.0
        #: Where every launch leaves a short record: what build, how it was
        #: started, and for a launcher, the first seconds of frame reports.
        self._run_log = None
        self._timing: dict[str, tuple[float, int]] = {}
        #: Events the window handed over since the last report, and their kinds.
        self._events = 0
        self._event_kinds: dict[str, int] = {}
        self._timing_since = time.monotonic()
        #: The grid, made once and cleared from then on. It is *this* app's, so it
        #: is made here rather than on the first frame -- a screen is handed a
        #: blank grid and never has to ask whose turn it is.
        from ..desktop.pattern import PatternBuffer

        self.grid = PatternBuffer(cols, rows, self.font)
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
        self.cols = max(MIN_COLS, cols)
        self.rows = max(MIN_ROWS, rows)
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
        #: The controller, if there is one. Empty and silent when there is not:
        #: a front end that refuses to start without a pad is a front end that
        #: lost a player.
        self.pad = Pad.open()
        #: Which device spoke last. Hints follow it: a pad player should read A
        #: and B, a keyboard player should read enter and esc.
        self.pad_active = False
        #: The pack's bottle sprites, scaled once per size: the sidebar is painted
        #: every frame, and a sprite resized thirty times a second is a frame
        #: spending itself on the same arithmetic.
        self._slot_faces: dict[tuple[str, int], object] = {}
        self.headline = headline
        self._window = None
        self._surface = None
        self._last_frame: float | None = None
        #: Whether the picture on the screen is out of date. The game is
        #: turn-based, so between a key and its answer *nothing moves*: a frame
        #: that redraws the same room sixty times a second is sixty times the
        #: work for a picture nobody asked to change. Screens that animate (a
        #: fight, the prologue's hold bar, a shake) say so themselves, and this
        #: flag is what carries an input across to the next repaint.
        self._dirty = True
        self._painted_at = 0.0
        #: Frames actually painted, for the timings report: with a still picture
        #: skipped, "fps" alone would not say how much drawing was done.
        self._painted = 0
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
        #: Whether the window opens on the whole screen, with the grid taken from
        #: the display. On by default, because a game that opens in a window the
        #: size of *another* screen -- 960x540 on a Deck, 1920x1080 on a laptop --
        #: is a game that has to be resized before it can be played. ``--windowed``
        #: asks for the old behaviour, which is what a developer window wants.
        self.fullscreen_start = fullscreen
        if battle_scene:
            self.open_battle_scene()

