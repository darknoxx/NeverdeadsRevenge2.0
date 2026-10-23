"""The settings: the glass, and the sound.

A screen instead of four function keys. F2, F3, F4 and F11 were the whole of the
game's settings, listed under the title like a cheat sheet -- and a controller
has no F-keys at all. So the same switches live here: the picture's glass, its
size, and the sound. The keys still work for a keyboard (nothing was taken
away), and the file they write is the same ``settings.json`` the old build wrote.

Every row is a switch and A toggles it. There is no "apply": a setting that
needs a confirmation is a setting nobody changes.
"""

from __future__ import annotations

from ..chrome import ASH, BONE, BLOOD, PURPLE, box, rule
from ..padmap import SETTINGS
from ..theme import parse_style
from .base import Screen

__all__ = ["SettingsScreen"]


class SettingsScreen(Screen):
    """The switches, in one list."""

    modal = True
    PAD = SETTINGS

    #: The key that toggles each row -- the glass keys the game already had, so
    #: the settings screen and the shortcuts go through exactly one code path.
    #: ``None`` means the row calls the application instead.
    GLASS = ("f11", "f2", "f3", "f4")

    def __init__(self) -> None:
        self.index = 0

    def rows(self, app) -> list[tuple[str, bool | None]]:
        """The rows, and what each one is set to. ``None`` for "not a switch"."""
        return [
            ("full screen", app.fullscreen),
            ("scanlines", app.crt.scanlines),
            ("bloom", app.crt.bloom),
            ("crt curve", app.crt.geometry),
            ("sound", not app.sfx.muted),
            ("back", None),
        ]

    def draw(self, buffer, app) -> None:
        rows = self.rows(app)
        width = 40
        height = len(rows) + 6
        x, y = (buffer.cols - width) // 2, (buffer.rows - height) // 2
        box(buffer, x, y, width, height, title="SETTINGS", border=BLOOD, fill=True)
        for index, (label, value) in enumerate(rows):
            chosen = index == self.index
            marker = "►" if chosen else " "
            if value is None:
                text = f"{marker} {label}"
            else:
                text = f"{marker} {label:<24}{'on' if value else 'off':>4}"
            style = f"bold {BONE}" if chosen else ASH
            buffer.text(x + 3, y + 2 + index, text[: width - 6], parse_style(style))
        rule(buffer, x + 1, y + height - 3, width - 2, ASH)
        buffer.text(
            x + 3,
            y + height - 2,
            # Keyboard words: the buffer translates them to A/B when the pad
            # was the last thing touched.
            "↑↓ pick   enter toggle   esc back"[: width - 6],
            parse_style(ASH),
        )

    def key(self, name, event, app) -> bool:
        # One toggle per press: a held A must not flip a switch thirty times a
        # second, which is the same rule every menu in this game keeps.
        if event.isAutoRepeat():
            return True
        rows = self.rows(app)
        if name in ("up", "k"):
            self.index = (self.index - 1) % len(rows)
            return True
        if name in ("down", "j"):
            self.index = (self.index + 1) % len(rows)
            return True
        if name in ("enter", "return", "space", "left", "right", "a", "d"):
            self._toggle(app)
            return True
        if name in ("escape", "backspace"):
            app.pop()
            return True
        return True

    def _toggle(self, app) -> None:
        label, _value = self.rows(app)[self.index]
        if label == "back":
            app.pop()
            return
        if label == "sound":
            app.toggle_sound()
            return
        # The glass keys themselves: the same path, the same note, the same
        # saved file. A settings screen with its own copy of the toggles would
        # be a second opinion about what the scanlines are.
        for key in self.GLASS:
            turned = {"f11": "full screen", "f2": "scanlines", "f3": "bloom", "f4": "crt curve"}[key]
            if turned == label:
                app.key(key)
                return
