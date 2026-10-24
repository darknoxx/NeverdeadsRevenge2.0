"""AppLoop: one part of the SDL application."""

from __future__ import annotations

import os
import time
from .. import __version__
from ..desktop.padmap import DEFAULT as DEFAULT_PAD
from .keys import name_of, typed


from .app_shared import (
    KeyPress,
)


class AppLoop:
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

        if event.type == pygame.QUIT:
            self.quit()
        elif event.type == pygame.KEYDOWN:
            self.pad_active = False
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
                self._dirty = True
        elif event.type == pygame.VIDEORESIZE:
            # The window manager's answer, not ours: the picture is fitted to
            # whatever it says, and the glass hears about it.
            self._fit()
            self.redraw()

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
        mark = time.perf_counter() if self._timing_now else 0.0
        self._poll_pad(dt)
        mark = self._note("pad", mark)
        screen = self.screens[-1]
        #: A screen with something playing -- a fight breathing, a hold bar
        #: filling -- has a picture that changes without a key, so it is stepped
        #: and repainted every frame. Everything else is a still life between
        #: presses, and repainting it is the work this game does not need to do.
        playing = bool(
            getattr(screen, "busy", False) or getattr(screen, "animating", False)
        )
        if playing:
            screen.step(dt, self)
        if self.effects.step(dt):
            self._dirty = True
        if self.glass_note is not None and now > self.glass_note[1]:
            # The note has had its two seconds: the frame it is standing on has
            # to be drawn again for it to come off.
            self.glass_note = None
            self._dirty = True
        if self.show_fps and now - self._painted_at >= 0.5:
            # A counter that only moves when the player does is a counter that
            # lies about the machine. Twice a second is enough to read it.
            self._dirty = True
        if playing or self._dirty:
            self.redraw()
        self._report_timings(time.monotonic())

    def _poll_pad(self, dt: float) -> None:
        """Ask the controller what it did, and hand it on as key names.

        The top screen says what its buttons mean (``PAD``) and whether it wants
        eight directions and the right stick's pages; everything else is the same
        road a keystroke takes, which is the whole reason the screens never had
        to learn about a pad.
        """
        screen = self.screens[-1]
        mapping = getattr(screen, "PAD", DEFAULT_PAD)
        events = self.pad.poll(
            dt,
            mapping,
            diagonals=bool(getattr(screen, "pad_diagonals", False)),
            scroll=bool(getattr(screen, "pad_scroll", False)),
        )
        for name, kind, repeat in events:
            self.pad_active = True
            screen = self.screens[-1]
            if kind == "up":
                if screen.key_up(name, KeyPress(False), self):
                    self._dirty = True
            else:
                self.key(name, KeyPress(repeat))

    def rumble(self, low: float, high: float, ms: int = 90) -> None:
        """Shake the pad: a blow, a kill, a level, a death."""
        self.pad.rumble(low, high, ms)

    def key(self, name: str, event=None, text: str = "") -> bool:
        """Hand a key to the top screen. Returns whether it was used."""
        if not name:
            return False
        if self._glass_key(name):
            return True
        screen = self.screens[-1]
        press = event or KeyPress(text=text)
        used = screen.key(name, press, self)
        self._interface_sound(name, bool(used), press)
        # A key makes the picture out of date; it does not paint it. The loop
        # paints once a frame, which is the same picture at a fraction of the
        # work -- and it means a burst of events (a pad repeating, a launcher's
        # idea of a key) costs one frame, not one frame each.
        self._dirty = True
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

    def _note(self, name: str, mark: float) -> float:
        """Book the milliseconds since ``mark`` under ``name``, and pass it on.

        Nothing but two clock reads when ``--timings`` was not asked for, which is
        why it can stand in the middle of the frame at all.
        """
        if not self._timing_now:
            return mark
        now = time.perf_counter()
        spent, frames = self._timing.get(name, (0.0, 0))
        self._timing[name] = (spent + (now - mark), frames + 1)
        return now

    def _report_timings(self, now: float) -> None:
        """Once a second: what each stage of the frame cost, in milliseconds."""
        if self._timing_until and now > self._timing_until:
            # The free look is over: a launcher's start has been measured, the
            # log has it, and the game stops paying for stages nobody asked for.
            self._timing_until = 0.0
            self._timing_now = self.show_timings
        if not self._timing_now or now - self._timing_since < 1.0:
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
            spent / frames * 1000.0
            for name, (spent, frames) in self._timing.items()
            if frames and not name.startswith("draw[")
        )
        painted, self._painted = self._painted, 0
        events, self._events = self._events, 0
        kinds = sorted(self._event_kinds.items(), key=lambda one: -one[1])[:2]
        self._event_kinds.clear()
        said = " ".join(f"{name} {count}" for name, count in kinds)
        self._say(
            f"{self.frames:5.1f} fps  {painted:3d} painted/s   "
            f"cells {self.grid.cols}x{self.grid.rows}/{self.grid.puts} written   "
            f"{parts}   ({done:.2f} ms a painted frame)   "
            f"events {events}{f' ({said})' if said else ''}"
        )
        self._timing.clear()

    def _say(self, line: str) -> None:
        """Say a timings line in the terminal, and in the data directory too.

        A game started by a launcher has no terminal: Steam runs the shortcut and
        keeps the output to itself. The same line goes to ``timings.log`` beside
        the save, so a slow launch can be read afterwards instead of guessed at.
        The file is truncated when the window opens, so it is this run and not a
        pile of runs.
        """
        if self._timing_now:
            print(line)
        if self._run_log is not None:
            try:
                self._run_log.write(line + "\n")
                self._run_log.flush()
            except OSError:
                self._run_log = None

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
        self._run_log = self._open_run_log()
        width, height = (
            self._window.get_size() if self._window is not None else (0, 0)
        )
        self._say(
            f"mode     ndr2 {__version__} {pygame.display.get_driver()} "
            f"{width}x{height} {'full screen' if self._fullscreen else 'window'}, "
            f"{self.cols}x{self.rows} cells, "
            f"{'crt' if self.glass is not None else 'plain blit'}"
        )
        self._say(
            f"launch   preload={os.environ.get('LD_PRELOAD', '-')!r} "
            f"path={os.environ.get('LD_LIBRARY_PATH', '-')!r} "
            f"steam={os.environ.get('SteamGameId', '-')!r} "
            f"runtime={os.environ.get('STEAM_RUNTIME', '-')!r} "
            f"pressure={os.environ.get('PRESSURE_VESSEL_VERSION', '-')!r}"
        )
        self.redraw()
        clock = pygame.time.Clock()
        self._running = True
        while self._running:
            # Every beat in this game is written against a thirtieth of a second,
            # so that is the frame this loop asks for: a fight that played faster
            # on a quicker machine would be a different fight.
            elapsed = clock.tick(60) / 1000.0
            # The keys first, then the frame: the pad is polled inside ``tick``,
            # and a key handled after the paint would be a frame late beside it.
            for event in pygame.event.get():
                if self._timing_now:
                    # How much the window is handing over, and of what: a pad in
                    # a launcher's hands can arrive as a stream of axis events,
                    # and a stream of events is a stream of Python objects.
                    self._events += 1
                    kind = pygame.event.event_name(event.type)
                    self._event_kinds[kind] = self._event_kinds.get(kind, 0) + 1
                self.feed(event)
            self.tick(min(elapsed, 1 / 30.0))
        if self._run_log is not None:
            self._run_log.close()
            self._run_log = None
        pygame.quit()

