"""The CRT, on the second front end: the same shader, run by moderngl.

The glass is a *look* and not a library. `desktop/crt_gl.py` holds the settings and
the shader; the Qt build runs it on a `QOpenGLWidget` and this runs it through
moderngl -- the same GLSL, the same uniforms, the same arithmetic. What differs is
who owns the context, and that is all this file is about.

Two ways in, and both are needed. With a window open, moderngl borrows the context
pygame made (a compatibility profile, which is exactly what GLSL 1.20 wants) and
draws the quad straight at the screen. Without one -- a test, or the probe -- a
standalone context renders into an offscreen buffer and the pixels are read back,
which is slow and is not a thing anyone does every frame.

And a machine that cannot make a GL context does not get a CRT: the application
falls back to the plain scaled blit. A game that refused to start over a scanline
would be a worse game.
"""

from __future__ import annotations

import struct

from ..desktop.crt_gl import source

__all__ = ["SdlGlass"]


class SdlGlass:
    """The CRT shader, a texture, and a quad to draw it on."""

    def __init__(self, settings, buffer_size, display_size, gles=False, context=None):
        import moderngl

        self.settings = settings
        self.buffer_size = (int(buffer_size[0]), int(buffer_size[1]))
        self.display_size = (int(display_size[0]), int(display_size[1]))
        self.ctx = context if context is not None else moderngl.create_standalone_context(
            require=120
        )
        #: Whether this context is ours to draw into offscreen: a standalone one
        #: has no screen, so the frame comes back as pixels.
        self.offscreen = context is None
        self.program = self.ctx.program(
            vertex_shader=source(fragment=False, gles=gles),
            fragment_shader=source(gles=gles),
        )
        self.texture = self.ctx.texture(self.buffer_size, 4)
        #: Integer scaling is the whole promise of the shader: a character is
        #: always a character and never a smear, which one blurred texel would
        #: break.
        self.texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        quad = struct.pack(
            "16f",
            -1.0, -1.0, 0.0, 0.0,
            1.0, -1.0, 1.0, 0.0,
            -1.0, 1.0, 0.0, 1.0,
            1.0, 1.0, 1.0, 1.0,
        )
        self.buffer = self.ctx.buffer(quad)
        self.array = self.ctx.vertex_array(
            self.program, [(self.buffer, "2f 2f", "position", "uv")]
        )
        self._screen = None
        if self.offscreen:
            self._screen = self.ctx.framebuffer(
                color_attachments=[self.ctx.texture(self.display_size, 3)]
            )
        # The whole-number scale that fits the buffer in the display, and where
        # it is centred: black bars are the honest answer to a remainder.
        scale = min(
            self.display_size[0] // max(1, self.buffer_size[0]),
            self.display_size[1] // max(1, self.buffer_size[1]),
        )
        self._fit_scale = max(1, scale)
        self._fit_offset = (
            (self.display_size[0] - self.buffer_size[0] * self._fit_scale) // 2,
            (self.display_size[1] - self.buffer_size[1] * self._fit_scale) // 2,
        )
        self.program["pattern"] = 0
        self.program["buffer"] = self.buffer_size
        self.fit(self.display_size, self._fit_scale, self._fit_offset)

    def resize(self, buffer_size) -> None:
        """The grid changed size: a new texture for the frame to live in.

        The *program* stays -- same shader either way -- and only the picture's
        own surface is made again, because the moment a window goes full screen
        is exactly the moment this happens and a shader rebuilt per resize would
        be a stutter for a shape that never changed.
        """
        import moderngl

        buffer_size = (int(buffer_size[0]), int(buffer_size[1]))
        if buffer_size == self.buffer_size:
            return
        self.buffer_size = buffer_size
        self.texture.release()
        self.texture = self.ctx.texture(buffer_size, 4)
        self.texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.program["buffer"] = buffer_size

    def fit(self, display_size, scale: int, offset) -> None:
        """The window changed: where the picture goes, and how big it is.

        Which has to be *recomputed* and not kept: full screen is a different
        window, and the whole-number scale that fits it is a different number.
        The viewport goes with it, because that is the thing whose origin is the
        bottom left corner -- a glass that never moved it draws the game into the
        corner of the screen and leaves the rest black, which is exactly what
        full screen looked like.
        """
        self.display_size = (int(display_size[0]), int(display_size[1]))
        self.scale = max(1, int(scale))
        self.offset = (int(offset[0]), int(offset[1]))
        self.ctx.viewport = (0, 0, *self.display_size)
        self.program["resolution"] = self.display_size
        if self.offscreen:
            # An offscreen glass is a test or a probe, and those never resize --
            # but a wrong-sized framebuffer would be an empty picture, so it is
            # rebuilt rather than trusted.
            self._screen = self.ctx.framebuffer(
                color_attachments=[self.ctx.texture(self.display_size, 3)]
            )

    @property
    def effects(self) -> bool:
        """Whether anything is actually turned on."""
        return bool(self.settings.scanlines or self.settings.bloom or self.settings.geometry)

    def draw(self, surface, shake=(0, 0)):
        """Put the frame through the glass, and hand back pixels if offscreen.

        ``shake`` moves the whole picture by a pixel or two, which is what the
        glass does when something lands on the player -- the same movement the Qt
        build's view makes.
        """
        import pygame

        import moderngl

        # Cheap, and it keeps the one thing that must not go stale correct: the
        # viewport is the framebuffer's, and this is called from whichever
        # context is current.
        self.ctx.viewport = (0, 0, *self.display_size)
        self.texture.write(pygame.image.tostring(surface, "RGBA", True))
        self.texture.use(0)
        self.program["scale"] = float(self.scale)
        self.program["offset"] = (
            float(self.offset[0] + shake[0]),
            float(self.offset[1] + shake[1]),
        )
        self.program["scanlines"] = int(self.settings.scanlines)
        self.program["bloom"] = int(self.settings.bloom)
        self.program["geometry"] = int(self.settings.geometry)
        if self.offscreen:
            self._screen.use()
            self.ctx.clear()
            self.array.render(mode=moderngl.TRIANGLE_STRIP, vertices=4)
            # Read back bottom-up, because that is the way GL has it, and hand
            # back a surface the right way up.
            data = self._screen.read(components=3)
            return pygame.transform.flip(
                pygame.image.fromstring(data, self.display_size, "RGB"), False, True
            )
        self.ctx.screen.use()
        self.array.render(mode=moderngl.TRIANGLE_STRIP, vertices=4)
        return None

    def release(self) -> None:
        """Give the context back. For a probe, and for nothing else."""
        self.texture.release()
        self.buffer.release()
        self.array.release()
        self.program.release()
        if self._screen is not None:
            self._screen.release()
        self.ctx.release()
