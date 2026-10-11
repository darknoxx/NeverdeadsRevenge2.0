"""The window, the input, and the loop.

The systems underneath do the thinking; this owns the three things a screen
owns: what is showing, what a key means, and when to redraw. It is deliberately
small -- a screen stack of one string, a key table, and a call to the renderer --
because everything interesting is either in ``game/`` or in ``render.py``.

Qt reports key *repeats* directly (``isAutoRepeat``), which the terminal could
never do: a terminal only ever sent the stream. So the two rules the terminal
approximated are exact here. A held direction is allowed through, no faster than
the hero's own pace. Every other key ignores repeats outright, which is what
"only on a new press" means when you can finally tell.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPalette
from PySide6.QtWidgets import QMainWindow

from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.pace import action_gap
from neverdeads_revenge.game.state import GameState, start_run
from neverdeads_revenge.persistence import load_meta

from .audio import Sfx, loudest_kind, sound_for_kind
from .buffer import PatternBuffer
from .crt import CrtSettings, CrtView
from .font import BitmapFont
from .render import draw_game, draw_title
from .settings import load_settings, save_settings

__all__ = ["DesktopApp", "KEY_BINDINGS"]

#: What a key means in the dungeon. The terminal build's table, kept as the
#: same dictionary of human key names to domain verbs so the two cannot drift
#: about what ``k`` does.
KEY_BINDINGS: dict[str, Action] = {
    "up": Action.MOVE_NORTH,
    "k": Action.MOVE_NORTH,
    "w": Action.MOVE_NORTH,
    "down": Action.MOVE_SOUTH,
    "j": Action.MOVE_SOUTH,
    "s": Action.MOVE_SOUTH,
    "left": Action.MOVE_WEST,
    "h": Action.MOVE_WEST,
    "a": Action.MOVE_WEST,
    "right": Action.MOVE_EAST,
    "l": Action.MOVE_EAST,
    "d": Action.MOVE_EAST,
    "y": Action.MOVE_NW,
    "u": Action.MOVE_NE,
    "b": Action.MOVE_SW,
    "n": Action.MOVE_SE,
    "home": Action.MOVE_NW,
    "pageup": Action.MOVE_NE,
    "end": Action.MOVE_SW,
    "pagedown": Action.MOVE_SE,
    ".": Action.WAIT,
    "space": Action.WAIT,
    "i": Action.INVENTORY,
    "q": Action.QUAFF,
    "r": Action.REWIND,
    ">": Action.DESCEND,
    "enter": Action.INTERACT,
}

#: How few cells the layout may be squeezed to before the window is simply too
#: small to hold the game. Rows are the tight one: the sidebar needs the HUD
#: plus the whole legend, and the bottom row takes ten more.
MIN_COLS = 80
MIN_ROWS = 24

#: How wide the grid aims to be. The zoom is chosen so the dungeon is about this
#: many cells across, which is what makes the characters *big* on a big screen
#: instead of merely numerous -- a 1080p monitor gets two-pixel cells and a
#: ~100-column grid rather than one-pixel cells and a 190-column one.
TARGET_COLS = 110

#: The keys that are not the game: the window, the glass, and the zoom.
FULLSCREEN_KEY = Qt.Key.Key_F11
SCANLINE_KEY = Qt.Key.Key_F2
BLOOM_KEY = Qt.Key.Key_F3
GEOMETRY_KEY = Qt.Key.Key_F4
ZOOM_IN_KEYS = (Qt.Key.Key_Plus, Qt.Key.Key_Equal)
ZOOM_OUT_KEYS = (Qt.Key.Key_Minus, Qt.Key.Key_Underscore)


class DesktopApp(QMainWindow):
    """The whole desktop game: one window, one view, one state."""

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
        #: The chosen pixel scale, or ``None`` to pick one from the window size.
        self.zoom: int | None = int(zoom) if isinstance(zoom, (int, float)) and zoom >= 1 else None

        self.view = CrtView(self.crt, self)
        self.setCentralWidget(self.view)
        self.view.installEventFilter(self)
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.meta = load_meta()
        self.seed = seed if seed is not None else int(time.time())
        self.screen = "title"
        self.run: GameState | None = None
        self._buffer: PatternBuffer | None = None
        self._grid = (0, 0)
        self._last_action: dict[str, float] = {}
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
        """How many cells fit, at the largest whole-number pixel scale.

        The scale is what makes a character big or small, and it is chosen so
        the grid lands near :data:`TARGET_COLS` wide -- a *zoom into* the field
        rather than a fill of it. On a 1080p screen that is two-pixel cells and
        about a hundred columns; on 4K, four-pixel cells and the same grid, so
        the game looks the same size relative to the eye on both. ``+`` and
        ``-`` move the scale by hand and the choice is remembered.
        """
        width = max(1, self.view.width())
        height = max(1, self.view.height())
        scale = self._scale_for(width, height)
        cell_w, cell_h = self.font.cell_w, self.font.cell_h
        cols = max(MIN_COLS, width // (cell_w * scale))
        rows = max(MIN_ROWS, height // (cell_h * scale))
        return cols, rows

    def _max_scale(self, width: int, height: int) -> int:
        """The largest scale at which the minimum layout still fits."""
        cell_w, cell_h = self.font.cell_w, self.font.cell_h
        return max(
            1,
            min(width // (MIN_COLS * cell_w), height // (MIN_ROWS * cell_h)),
        )

    def _scale_for(self, width: int, height: int) -> int:
        """The pixel scale: the chosen one, or one that hits the target width."""
        ceiling = self._max_scale(width, height)
        if self.zoom is not None:
            return max(1, min(self.zoom, ceiling))
        cell_w = self.font.cell_w
        target = max(1, round(width / (TARGET_COLS * cell_w)))
        return max(1, min(target, ceiling))

    def _nudge_zoom(self, delta: int) -> None:
        """Zoom in or out by one, and remember it."""
        width = max(1, self.view.width())
        height = max(1, self.view.height())
        current = self._scale_for(width, height)
        self.zoom = max(1, min(current + delta, self._max_scale(width, height)))
        self._buffer = None  # the grid changes, so the buffer does too
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
        if self.screen == "title":
            draw_title(
                self._buffer,
                "a desktop roguelite",
                "press any key   ·   + / - zoom   ·   F2 scanlines   F3 bloom"
                "   F4 curve   F11 fullscreen",
            )
        elif self.screen == "game" and self.run is not None:
            draw_game(self._buffer, self.run)
        self.view.set_frame(self._buffer.render())

    # -- the game -----------------------------------------------------------
    def begin(self) -> None:
        """Start a run and show it."""
        self.run = start_run(HEROES["noxx"], self.seed)
        self._seen_log = 0
        self.screen = "game"
        self.redraw()

    def _play_new_sounds(self) -> None:
        run = self.run
        if run is None:
            return
        fresh = run.log[self._seen_log :]
        self._seen_log = len(run.log)
        kind = loudest_kind(entry.kind for entry in fresh)
        if kind is not None:
            name = sound_for_kind(kind)
            if name is not None:
                self.sfx.play(name)

    def _act(self, action: Action) -> None:
        if self.run is None:
            return
        perform_action(self.run, action)
        self._play_new_sounds()
        self.redraw()

    # -- input --------------------------------------------------------------
    def eventFilter(self, obj, event):  # noqa: N802 - Qt's spelling
        if event.type() == QEvent.Type.KeyPress and obj is self.view:
            self._on_key(event)
            return True
        return super().eventFilter(obj, event)

    def _on_key(self, event: QKeyEvent) -> None:
        if self._window_key(event):
            return
        if self.screen == "title":
            if event.key() == Qt.Key.Key_Escape:
                self.close()
            elif not event.isAutoRepeat():
                self.begin()
            return
        if self.screen == "game":
            self._game_key(event)

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

    def _game_key(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.screen = "title"
            self.redraw()
            return

        name = self._key_name(event)
        action = KEY_BINDINGS.get(name)
        if action is None:
            return

        if action.direction.name != "NONE":
            # A held direction is one gesture, so its repeats are allowed -- but
            # no faster than the hero's own pace, which is what stops a held key
            # from turning a fight into an unreadable blur.
            if event.isAutoRepeat():
                speed = self.run.player.speed if self.run else 1.0
                now = time.monotonic()
                if now - self._last_action.get(name, 0.0) < action_gap(speed):
                    return
            self._last_action[name] = time.monotonic()
        elif event.isAutoRepeat():
            return  # every other key acts only on a fresh press

        self._act(action)

    @staticmethod
    def _key_name(event: QKeyEvent) -> str:
        """The name the key table uses for this event."""
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
        }
        if event.key() in named:
            return named[event.key()]
        text = event.text()
        return text.lower() if text else ""
