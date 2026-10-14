"""The window, the input, and the loop.

The systems underneath do the thinking; this owns the screen stack, the progress
on disk, and the moment a key becomes a verb. A screen is a small object with a
``draw`` and a ``key``; the app is the thing that knows what is on top and where
a run goes when it ends.

Qt reports key *repeats* directly, which a terminal could not, so the two rules
the terminal approximated are exact here: a held direction moves at the hero's
own pace, and every dialog ignores a repeat outright -- which is what "only on a
fresh press" means when you can finally tell one.
"""

from __future__ import annotations

import random
import time

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPalette
from PySide6.QtWidgets import QMainWindow

from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.lore import PAGE_COUNT
from neverdeads_revenge.game.savegame import dump, load
from neverdeads_revenge.game.shop import loadout_from
from neverdeads_revenge.game.state import RunState, start_run
from neverdeads_revenge.persistence import (
    MetaProgress,
    clear_run,
    load_meta,
    load_run,
    save_meta,
    save_run,
)

from .audio import Sfx, loudest_kind, sound_for_kind
from .buffer import PatternBuffer
from .crt import CrtSettings, CrtView
from .effects import Effects
from .font import BitmapFont
from .keys import KEY_BINDINGS
from .screens.game import GameScreen
from .screens.title import TitleScreen
from .settings import load_settings, save_settings

__all__ = ["DesktopApp", "KEY_BINDINGS"]

#: How few cells the layout may be squeezed to before the window is simply too
#: small to hold the game. Rows are the tight one: the sidebar needs the HUD
#: plus the whole legend, and the bottom row takes ten more.
MIN_COLS = 80
MIN_ROWS = 24

#: How wide the grid aims to be, so the characters are *big* on a big screen
#: rather than merely numerous.
TARGET_COLS = 110

#: The keys that are not the game: the window and the glass.
FULLSCREEN_KEY = Qt.Key.Key_F11
SCANLINE_KEY = Qt.Key.Key_F2
BLOOM_KEY = Qt.Key.Key_F3
GEOMETRY_KEY = Qt.Key.Key_F4


class DesktopApp(QMainWindow):
    """The whole desktop game: one window, one view, a stack of screens."""

    #: Raised by the sound thread when the audio session gives up. It is a
    #: signal, not a call, because the thread that notices is not the one that
    #: owns the save file: a queued signal lands the change on the GUI thread.
    sound_gave_up = Signal(bool)

    def __init__(
        self,
        *,
        seed: int | None = None,
        no_sound: bool = False,
        testrun: bool = False,
        battle_scene: bool = False,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Neverdead's Revenge")
        self.font = BitmapFont()
        #: `--testrun`: the chronicle unlocked and the purse full, and for the
        #: one feature being tested this session, the void answers early.
        self.testrun = testrun

        saved = load_settings()
        self.crt = CrtSettings(
            scanlines=bool(saved.get("scanlines", True)),
            bloom=bool(saved.get("bloom", True)),
            geometry=bool(saved.get("geometry", False)),
        )
        self.font_small = BitmapFont(pixel_size=11)

        self.view = CrtView(self.crt, self)
        self.setCentralWidget(self.view)
        self.view.installEventFilter(self)
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.progress = load_meta()
        #: The seed the next run is drawn from, and whether the player pinned it
        #: with ``--seed``. A pinned seed means the same dungeon every time;
        #: unpinned, every run is a fresh roll of the dice.
        self.seed = seed if seed is not None else None
        self.seed_locked = seed is not None
        self.run = None
        self.prologue_seen = False
        self.screens: list = [TitleScreen()]
        self._buffer: PatternBuffer | None = None
        self._grid = (0, 0)
        self._seen_log = 0
        self.sfx = Sfx(muted=no_sound or self.progress.muted)
        # If the session gives up entirely the meta record must hear of it, or
        # the next toggle writes the give-up back down as unmuted. The sound
        # thread only emits; the change and the save happen here, on the GUI
        # thread, queued by Qt.
        self.sound_gave_up.connect(self._sound_gave_up)
        self.sfx.on_mute = self.sound_gave_up.emit
        #: The moving pixels. Their own layer, drawn over the still frame.
        self.effects = Effects(self.font.cell_w, self.font.cell_h)
        #: A word about the glass, said for a moment: what a toggle key just did.
        self.glass_note: tuple[str, float] | None = None
        self._asked_fullscreen = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#000000"))
        self.setPalette(palette)
        self.setMinimumSize(640, 400)

        if battle_scene:
            # M0: the stage, before there is anything to fight. A switch rather
            # than a key in the game, because a key in the game is a key the
            # game has to stop listening to first.
            self.open_battle_scene()

    # -- the frame ----------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
        super().showEvent(event)
        # The dungeon is a CRT, and a CRT shows one thing: the whole screen. The
        # player asked for this to be how the game opens; F11 still gives it up.
        # Asked once, because going fullscreen emits its own show event and a
        # recursion would be a fight about who is in charge.
        if not self._asked_fullscreen and not self.isFullScreen():
            self._asked_fullscreen = True
            self.showFullScreen()
        self.redraw()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
        super().resizeEvent(event)
        self.redraw()

    def _grid_size(self) -> tuple[int, int]:
        """How many cells fit, at the largest whole-number pixel scale."""
        width = max(1, self.view.width())
        height = max(1, self.view.height())
        scale = self._scale_for(width, height)
        cell_w, cell_h = self.font.cell_w, self.font.cell_h
        cols = max(MIN_COLS, width // (cell_w * scale))
        rows = max(MIN_ROWS, height // (cell_h * scale))
        return cols, rows

    def _max_scale(self, width: int, height: int) -> int:
        cell_w, cell_h = self.font.cell_w, self.font.cell_h
        return max(1, min(width // (MIN_COLS * cell_w), height // (MIN_ROWS * cell_h)))

    def _scale_for(self, width: int, height: int) -> int:
        """The one scale: the big one.

        There used to be a zoom the player could step, and it was two dials
        arguing about the same screen. One size here -- the one that lands the
        grid near :data:`TARGET_COLS` wide, which is a character of two pixels
        on a 1080p screen whole -- and the log's smaller face is what makes the
        words keep up with it.
        """
        ceiling = self._max_scale(width, height)
        target = max(1, round(width / (TARGET_COLS * self.font.cell_w)))
        return max(1, min(target, ceiling))

    def _remember(self) -> None:
        save_settings(
            {
                "scanlines": self.crt.scanlines,
                "bloom": self.crt.bloom,
                "geometry": self.crt.geometry,
            }
        )

    def redraw(self) -> None:
        cols, rows = self._grid_size()
        if self._buffer is None or (cols, rows) != self._grid:
            self._buffer = PatternBuffer(cols, rows, self.font)
            self._grid = (cols, rows)
        self._buffer.clear()
        # An opaque modal: nothing under it is drawn. A menu is a panel, not a
        # window onto the dungeon, so the topmost modal starts the stack.
        start = 0
        for index, screen in enumerate(self.screens):
            if getattr(screen, "modal", False):
                start = index
        for screen in self.screens[start:]:
            screen.draw(self._buffer, self)
        self._say_glass()
        image = self._buffer.render()
        if getattr(self.screens[-1], "smaller_face", False) and self.run is not None:
            from .render import paste_log, paste_sidebar

            paste_log(
                image,
                self.run,
                self._buffer.cols,
                self._buffer.rows,
                self.font.cell_w,
                self.font.cell_h,
                self.font_small,
            )
            paste_sidebar(
                image,
                self.run,
                self._buffer.cols,
                self._buffer.rows,
                self.font.cell_w,
                self.font.cell_h,
                self.font_small,
            )
        self.effects.draw(image)
        self.view.set_frame(image)

    def _say_glass(self) -> None:
        """Say what a glass key just did, for as long as it takes to read.

        Written into the pattern buffer *before* it renders: the words are
        literally part of the frame, which is also why the screen can flash
        them with nothing timing it. The earlier version wrote into the buffer
        after the image had been rendered -- invisible, and this is the
        polite way of putting it.
        """
        if self.glass_note is None:
            return
        note, until = self.glass_note
        if time.monotonic() > until:
            self.glass_note = None
            return
        from .theme import parse_style
        from .chrome import BONE

        x = max(0, (self._buffer.cols - len(note)) // 2)
        self._buffer.text(x, 1, note, parse_style(f"bold {BONE}"))

    def _note_glass(self, note: str) -> None:
        self.glass_note = (note, time.monotonic() + 2.0)
        self.redraw()

    def screen_point(self, position) -> tuple[float, float] | None:
        """The pixel centre of a dungeon square on the current frame, if it is
        on the screen."""
        if self._buffer is None or self.run is None:
            return None
        from .render import screen_point as to_screen

        return to_screen(
            self.run,
            position,
            self._buffer.cols,
            self._buffer.rows,
            self.font.cell_w,
            self.font.cell_h,
        )

    def _tick(self) -> None:
        """Advance the pixels and expire the glass word.

        Repaints only while either of them is alive, which is most of the time
        nothing at all. A hold counts as alive too: the bar should begin
        filling from the first frame of the press, not wait for the keyboard's
        first repeat to arrive, which on Wayland can be a slow half second of
        a dead bar. The ticks draw only -- completion is still the press that
        crosses the fill, never a timer callback.
        """
        holding = any(
            getattr(screen, "hold", None) is not None and screen.hold.holding
            for screen in self.screens
        )
        breathing = self._void_is_breathing()
        if not (
            holding
            or self.effects.active
            or self.view.is_shaking()
            or self.glass_note is not None
            or breathing
        ):
            return
        if breathing and not (
            holding or self.effects.active or self.view.is_shaking()
        ):
            # The breath is a slow, calm thing: ten frames of it a second is
            # already over-generous, and a full redraw on every tick would
            # spend the whole frame budget on one line of colour.
            now = time.monotonic()
            if now - self._last_pulse_paint < 0.1:
                return
            self._last_pulse_paint = now
        self.effects.step(0.033)
        self.redraw()

    _last_pulse_paint: float = 0.0

    def _void_is_breathing(self) -> bool:
        """Whether a live ultimate's prompt needs repainting to breathe.

        The pulse is drawn in the sidebar paste, and a prompt that only
        repaints on keypress would be a breath that stops every time the hero
        stops. Cheap to ask, and wrong only during the one part of the run
        where a promise can be kept.
        """
        run = self.run
        if run is None:
            return False
        from .render import ultimate_ready

        return ultimate_ready(run)

    # -- the stack ----------------------------------------------------------
    def push(self, screen) -> None:
        self.screens.append(screen)
        self.redraw()

    def pop(self) -> None:
        if len(self.screens) > 1:
            self.screens.pop()
        self.redraw()

    def return_to_title(self) -> None:
        self.run = None
        self.effects.clear()
        self.screens = [TitleScreen()]
        self.redraw()

    # -- progress -----------------------------------------------------------
    def save_progress(self) -> None:
        try:
            save_meta(self.progress)
        except OSError:
            pass

    def has_saved_run(self) -> bool:
        return load_run() is not None

    def record_run(self, state, name: str = "") -> int:
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

    # -- navigation ---------------------------------------------------------
    def open_hero_select(self) -> None:
        from .screens.hero_select import HeroSelectScreen

        self.push(HeroSelectScreen())

    def begin_run(self, hero_key: str) -> None:
        if not self.prologue_seen:
            # The premise, told once, between the choice and the floor. A held
            # enter lets it go; escape skips it; and every run after the first
            # starts without it being repeated.
            self.prologue_seen = True
            from .screens.prologue import PrologueScreen

            self.push(PrologueScreen(on_done=lambda: self.begin_run(hero_key)))
            return
        # A fresh seed per run, unless the player pinned one with --seed. This
        # used to be one seed for the whole session, which meant every NEW RUN
        # was the same dungeon wearing yesterday's clothes.
        if not self.seed_locked:
            self.seed = random.SystemRandom().randrange(2**32)
        loadout = loadout_from(self.progress)
        self.save_progress()
        missing = tuple(
            number
            for number in range(1, PAGE_COUNT + 1)
            if number not in self.progress.pages
        )
        self.run = start_run(
            HEROES[hero_key], self.seed, loadout=loadout, pages=missing,
            ultimate_level=1 if self.testrun else None,
        )
        self._seen_log = 0
        self.effects.clear()
        self.screens = [GameScreen(self.run)]
        self.redraw()

    def continue_run(self) -> None:
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
        self._seen_log = len(state.log)
        self.screens = [GameScreen(state)]
        self.redraw()

    def open_shop(self) -> None:
        from .screens.menus import ShopScreen

        self.push(ShopScreen())

    def open_scoreboard(self) -> None:
        from .screens.menus import ScoreboardScreen

        self.push(ScoreboardScreen())

    def open_chronicle(self) -> None:
        from .screens.menus import ChronicleScreen

        self.push(ChronicleScreen())

    def open_battle_scene(self) -> None:
        """M0: the battle stage as a picture, reached with ``--battle-scene``.

        The stack is *replaced* rather than pushed onto. A battle is not a
        dialog over the dungeon -- it is somewhere else, with the run standing
        still underneath it -- and a dialog is exactly what this is not.
        """
        from .screens.battle import BattleScreen

        self.screens = [BattleScreen()]
        self.redraw()

    def open_delete_progress(self) -> None:
        """Ask for the word, then erase everything.

        The dialog is the whole safety: it returns ``True`` only when the
        player typed DELETE, and a ``False`` -- an escape, a changed mind --
        leaves the profile exactly where it was.
        """
        from .screens.dialogs import DeleteProgressScreen

        self.push(
            DeleteProgressScreen(
                on_done=lambda confirmed: self.delete_progress() if confirmed else None
            )
        )

    def delete_progress(self) -> None:
        """Wipe the profile and the saved run. Nothing is kept back."""
        self.progress = MetaProgress()
        self.save_progress()
        clear_run()
        self.run = None
        self._note_glass("EVERYTHING DELETED")

    def save_and_quit(self) -> None:
        if self.run is not None:
            save_run(dump(self.run))
        self.return_to_title()

    def quit_requested(self) -> None:
        from .screens.dialogs import ConfirmScreen

        self.push(
            ConfirmScreen(
                "QUIT NEVERDEAD'S REVENGE?",
                "The dungeon will still be here when you come back.",
                on_done=lambda yes: self.close() if yes else None,
            )
        )

    def confirm_quit_to_title(self) -> None:
        from .screens.dialogs import ConfirmScreen

        self.push(
            ConfirmScreen(
                "QUIT TO THE TITLE?",
                "The run does not come back. It is not written down.",
                on_done=lambda yes: self.return_to_title() if yes else None,
            )
        )

    def toggle_sound(self) -> None:
        self.sfx.toggle()
        self.progress.muted = self.sfx.muted
        self.save_progress()

    def _sound_gave_up(self, muted: bool) -> None:
        """The audio session quit on its own; the record has to agree."""
        self.progress.muted = muted
        self.save_progress()

    # -- sound --------------------------------------------------------------
    def play(self, name: str | None) -> None:
        if name:
            self.sfx.play(name)

    def play_after(self, before: tuple[int, int, int]) -> None:
        """Make the noise the last thing that happened deserves."""
        run = self.run
        if run is None or run.over:
            return
        before_log, before_depth, before_level = before
        if run.depth != before_depth:
            self.play("stairs")
            return
        if run.level != before_level:
            self.play("level")
            return
        kind = loudest_kind(entry.kind for entry in run.log[before_log:])
        self.play(sound_for_kind(kind) if kind is not None else None)

    # -- input --------------------------------------------------------------
    def eventFilter(self, obj, event):  # noqa: N802 - Qt's spelling
        if obj is self.view and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            self._on_key(event)
            return True
        return super().eventFilter(obj, event)

    def _on_key(self, event: QKeyEvent) -> None:
        if event.type() == QEvent.Type.KeyRelease:
            # The terminal build had to *guess* a release from silence, and
            # every heuristic built on that guess was ours instead. Qt hands
            # over the key going up; the holds want it voided: without the
            # release a tap is indistinguishable from a hold. A True return
            # means the hold changed under the key -- a fillaborting, most
            # likely -- so the paint must follow it, or the bar freezes half
            # drawn on the glass.
            name = self._key_name(event)
            if name and self.screens and self.screens[-1].key_up(name, event, self):
                self.redraw()
            return
        if self._window_key(event):
            return
        name = self._key_name(event)
        if name is None:
            return
        if self.screens and self.screens[-1].key(name, event, self):
            self.redraw()

    def _window_key(self, event: QKeyEvent) -> bool:
        """Fullscreen and the three glass keys."""
        key = event.key()
        # Glass toggles answer a press, not a held key: F2 held down would
        # flip the scanlines thirty times a second and rewrite the settings
        # with it. But ONLY the glass keys are swallowed here -- a returned
        # True for *every* repeat would starve the hold screens, which live
        # precisely on those repeats. That was the bug: a held enter on the
        # prologue fed the bar once and then hit this wall, and nothing
        # happened until the key came up and went down again.
        if event.isAutoRepeat():
            return key in (FULLSCREEN_KEY, SCANLINE_KEY, BLOOM_KEY, GEOMETRY_KEY)
        if key == FULLSCREEN_KEY:
            self.showFullScreen() if not self.isFullScreen() else self.showNormal()
            return True
        if key == SCANLINE_KEY:
            self.crt.scanlines = not self.crt.scanlines
            self._remember()
            self._note_glass(f"SCANLINES {'ON' if self.crt.scanlines else 'OFF'}")
            return True
        if key == BLOOM_KEY:
            self.crt.bloom = not self.crt.bloom
            self._remember()
            self._note_glass(f"BLOOM {'ON' if self.crt.bloom else 'OFF'}")
            return True
        if key == GEOMETRY_KEY:
            self.crt.geometry = not self.crt.geometry
            self._remember()
            self._note_glass(f"CRT CURVE {'ON' if self.crt.geometry else 'OFF'}")
            return True
        return False

    @staticmethod
    def _key_name(event: QKeyEvent) -> str | None:
        """The name the key tables use for this event, or ``None``."""
        named = {
            Qt.Key.Key_Up: "up",
            Qt.Key.Key_Down: "down",
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_Right: "right",
            Qt.Key.Key_Home: "home",
            Qt.Key.Key_PageUp: "pageup",
            Qt.Key.Key_End: "end",
            Qt.Key.Key_PageDown: "pagedown",
            Qt.Key.Key_Space: "space",
            Qt.Key.Key_Return: "enter",
            Qt.Key.Key_Enter: "enter",
            Qt.Key.Key_Escape: "escape",
            Qt.Key.Key_Backspace: "backspace",
            Qt.Key.Key_Delete: "delete",
            Qt.Key.Key_F1: "f1",
        }
        if event.key() in named:
            return named[event.key()]
        text = event.text()
        return text.lower() if text else None
