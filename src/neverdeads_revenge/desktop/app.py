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

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPalette
from PySide6.QtWidgets import QMainWindow

from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.lore import PAGE_COUNT
from neverdeads_revenge.game.savegame import dump, load
from neverdeads_revenge.game.shop import loadout_from
from neverdeads_revenge.game.state import RunState, start_run
from neverdeads_revenge.persistence import (
    clear_run,
    load_meta,
    load_run,
    save_meta,
    save_run,
)

from .audio import Sfx, loudest_kind, sound_for_kind
from .buffer import PatternBuffer
from .crt import CrtSettings, CrtView
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

#: The keys that are not the game: the window, the glass, and the zoom.
FULLSCREEN_KEY = Qt.Key.Key_F11
SCANLINE_KEY = Qt.Key.Key_F2
BLOOM_KEY = Qt.Key.Key_F3
GEOMETRY_KEY = Qt.Key.Key_F4
ZOOM_IN_KEYS = (Qt.Key.Key_Plus, Qt.Key.Key_Equal)
ZOOM_OUT_KEYS = (Qt.Key.Key_Minus, Qt.Key.Key_Underscore)


class DesktopApp(QMainWindow):
    """The whole desktop game: one window, one view, a stack of screens."""

    def __init__(self, *, seed: int | None = None, no_sound: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("Neverdead's Revenge")
        self.font = BitmapFont()

        saved = load_settings()
        self.crt = CrtSettings(
            scanlines=bool(saved.get("scanlines", True)),
            bloom=bool(saved.get("bloom", True)),
            geometry=bool(saved.get("geometry", False)),
        )
        zoom = saved.get("zoom")
        self.zoom: int | None = (
            int(zoom) if isinstance(zoom, (int, float)) and zoom >= 1 else None
        )

        self.view = CrtView(self.crt, self)
        self.setCentralWidget(self.view)
        self.view.installEventFilter(self)
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.progress = load_meta()
        self.seed = seed if seed is not None else int(time.time())
        self.run = None
        self.screens: list = [TitleScreen()]
        self._buffer: PatternBuffer | None = None
        self._grid = (0, 0)
        self._seen_log = 0
        self.sfx = Sfx(muted=no_sound)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#000000"))
        self.setPalette(palette)
        self.setMinimumSize(640, 400)

    # -- the frame ----------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
        super().showEvent(event)
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
        ceiling = self._max_scale(width, height)
        if self.zoom is not None:
            return max(1, min(self.zoom, ceiling))
        target = max(1, round(width / (TARGET_COLS * self.font.cell_w)))
        return max(1, min(target, ceiling))

    def _nudge_zoom(self, delta: int) -> None:
        width = max(1, self.view.width())
        height = max(1, self.view.height())
        current = self._scale_for(width, height)
        self.zoom = max(1, min(current + delta, self._max_scale(width, height)))
        self._buffer = None
        self._remember()
        self.redraw()

    def _remember(self) -> None:
        save_settings(
            {
                "zoom": self.zoom,
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
        for screen in self.screens:
            screen.draw(self._buffer, self)
        self.view.set_frame(self._buffer.render())

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
        loadout = loadout_from(self.progress)
        self.save_progress()
        missing = tuple(
            number
            for number in range(1, PAGE_COUNT + 1)
            if number not in self.progress.pages
        )
        self.run = start_run(
            HEROES[hero_key], self.seed, loadout=loadout, pages=missing
        )
        self._seen_log = 0
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
        if event.type() == QEvent.Type.KeyPress and obj is self.view:
            self._on_key(event)
            return True
        return super().eventFilter(obj, event)

    def _on_key(self, event: QKeyEvent) -> None:
        if self._window_key(event):
            return
        name = self._key_name(event)
        if name is None:
            return
        if self.screens and self.screens[-1].key(name, event, self):
            self.redraw()

    def _window_key(self, event: QKeyEvent) -> bool:
        """Fullscreen, the zoom, and the three glass keys."""
        key = event.key()
        if key == FULLSCREEN_KEY:
            self.showFullScreen() if not self.isFullScreen() else self.showNormal()
            return True
        if key in ZOOM_IN_KEYS:
            self._nudge_zoom(1)
            return True
        if key in ZOOM_OUT_KEYS:
            self._nudge_zoom(-1)
            return True
        if key == SCANLINE_KEY:
            self.crt.scanlines = not self.crt.scanlines
            self._remember()
            self.view.update()
            return True
        if key == BLOOM_KEY:
            self.crt.bloom = not self.crt.bloom
            self._remember()
            self.view.update()
            return True
        if key == GEOMETRY_KEY:
            self.crt.geometry = not self.crt.geometry
            self._remember()
            self.view.update()
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
