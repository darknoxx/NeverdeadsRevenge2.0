"""AppWindow: one part of the SDL application."""

from __future__ import annotations

import os
import sys
import time
from .. import __version__


from .app_shared import (
    MIN_COLS,
    MIN_ROWS,
    TARGET_COLS,
)


class AppWindow:
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

    def _grid_size(self, width: int, height: int) -> tuple[int, int]:
        """How many cells fit in a window of this size, at that scale.

        The Qt build's rule, number for number, because it is the rule the game's
        panels were laid out for -- and because a second front end with its own
        idea of how much room there is would draw a different game at the same
        size. At 960x540 it comes out at the 96x27 both front ends start with;
        at 2560x1440 it comes out at 128x36, which is a full screen and no bars.
        """
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
        if self.fullscreen_start and desktop:
            cols, rows = self._grid_size(*desktop[0])
            mode = f"full screen {desktop[0][0]}x{desktop[0][1]} = {cols}x{rows} cells"
        else:
            width, height = self._buffer_size()
            mode = f"windowed {width * self.scale}x{height * self.scale}"
        try:
            surface = pygame.display.get_surface()
            drawable = surface.get_size() if surface is not None else None
        except pygame.error:
            drawable = None
        grid = self._grid_size(self.cols * self.font.cell_w, self.rows * self.font.cell_h)
        try:
            driver = pygame.display.get_driver()
        except pygame.error:
            driver = "none"
        return [
            f"platform      {sys.platform}",
            f"version       {__version__}",
            f"saves         {self._data_dir()}",
            f"video driver  {driver}",
            f"session       wayland={os.environ.get('WAYLAND_DISPLAY')!r} "
            f"display={os.environ.get('DISPLAY')!r} "
            f"session={os.environ.get('XDG_SESSION_TYPE')!r}",
            # What a launcher put in front of the game, because "slow only when
            # Steam starts it" is a question about this and not about the game.
            f"ld preload    {os.environ.get('LD_PRELOAD', '-')}",
            f"ld path       {os.environ.get('LD_LIBRARY_PATH', '-')}",
            f"wrapper       steam={os.environ.get('STEAM_RUNTIME', '-')!r} "
            f"pressure={os.environ.get('PRESSURE_VESSEL_VERSION', '-')!r}",
            f"start mode    {mode}",
            f"dpi scale     {self._dpi():.2f}",
            f"desktop       {desktop}",
            f"drawable      {drawable}",
            f"window        {self._shown}",
            f"canvas        {self.cols}x{self.rows} cells "
            f"= {self.cols * self.font.cell_w}x{self.rows * self.font.cell_h} px",
            f"scale setting {self.scale}",
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

        flags = 0
        if self.fullscreen_start:
            # The display is the size, and the grid is taken from it. On a 1280x800
            # Deck this comes out at exactly 128x40 cells with no bars; on a
            # 1920x1080 desktop at 96x27 with the picture doubled. The old start
            # was a fixed 1920x1080 window, which is a window the size of a
            # monitor the player may not have.
            desktop = pygame.display.get_desktop_sizes()[0]
            self.cols, self.rows = self._grid_size(*desktop)
            self.scale = self._scale_for(*desktop)
            size = desktop
            flags = pygame.FULLSCREEN
            self._fullscreen = True
        else:
            base = self._buffer_size()
            size = (base[0] * self.scale, base[1] * self.scale)
        base = self._buffer_size()
        # The glass is made whether or not an effect is *on* at this moment: the
        # three switches are uniforms, not a different window, and a window made
        # without a context can never grow one. Turning the scanlines back on
        # after starting with them off used to do nothing at all until the next
        # launch -- which is exactly how a player loses the CRT for good.
        if self._try_glass(pygame, size, flags, base):
            return
        # No context, no CRT: a plain window at the same size. A machine that
        # cannot make one -- an old driver, a remote session, a compositor with
        # no GL -- still gets the game.
        self._window = pygame.display.set_mode(size, flags)
        self._fit()
        if self.show_timings:
            print(f"crt      not available, plain blit: {self._glass_error}")

    def _try_glass(self, pygame, size, flags, base) -> bool:
        """One attempt at a window with a context, and the glass on top of it."""
        try:
            import moderngl

            pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 2)
            pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 1)
            self._window = pygame.display.set_mode(
                size, pygame.OPENGL | pygame.DOUBLEBUF | flags
            )
            from .glass import SdlGlass

            self.glass = SdlGlass(
                self.crt,
                base,
                self._window.get_size(),
                context=moderngl.create_context(),
            )
            self._glass_error = None
            self._fit()
            return True
        except Exception as error:
            self.glass = None
            self._glass_error = error
            return False

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
        # The grid comes from the window, the way the Qt build's does: whatever
        # is left over after the biggest whole-number scale becomes *cells* and
        # not black bars.
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
        if self.glass is not None:
            # The glass has the whole picture and the whole window: it is the
            # thing that scales, so the shake goes in as part of its offset.
            self.glass.draw(
                self._surface, (offset[0] * fit, offset[1] * fit)
            )
            pygame.display.flip()
            return
        # A whole-number fit of one -- the Deck's 1280x800, and any window that
        # is exactly its own grid -- needs no scaling at all: `scale` would copy
        # a megabyte to hand back the same pixels, and a fill would paint over
        # the picture before it went down. Between the two that was most of what
        # presenting a frame cost on a machine this game should run on.
        shown = (self._surface.get_width() * fit, self._surface.get_height() * fit)
        at = (self._shown_at[0] + offset[0] * fit, self._shown_at[1] + offset[1] * fit)
        if shown != surface.get_size() or at != (0, 0):
            # Something will be left bare -- bars, or the edge the shake pulled
            # the picture away from -- so the frame underneath is cleared.
            surface.fill((0, 0, 0))
        if shown == self._surface.get_size():
            scaled = self._surface
        else:
            scaled = pygame.transform.scale(self._surface, shown)
        surface.blit(scaled, at)
        pygame.display.flip()

    @property
    def fullscreen(self) -> bool:
        """Whether the window is the whole screen, for the settings to say."""
        return self._fullscreen

    def open_settings(self) -> None:
        from ..desktop.screens.settings import SettingsScreen

        self.push(SettingsScreen())

    def _glass_key(self, name: str) -> bool:
        """The four keys that belong to the glass and not to a screen.

        The same four the Qt build answers, under the same names, because a key
        that turns the scanlines off should do it in either front end. The
        settings are written down as they change, so the choice survives the
        window.
        """

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
        # The frame is still a still life between inputs now, so the toggle has
        # to ask for the repaint itself.
        self.redraw()
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
                "zoom": self.field_zoom,
            }
        )

    def _data_dir(self) -> str:
        """Where the game keeps its saves, its settings and this launch's log."""
        from ..persistence import data_dir

        return str(data_dir())

