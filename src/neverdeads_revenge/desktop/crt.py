"""The CRT.

The picture the game produces is tiny -- a few hundred cells, each a few pixels
-- and this is the glass it is shown on. One fragment shader does all of it:

* **integer scaling.** The buffer is scaled by a whole number and centred, with
  black bars where the number does not divide. Nothing is ever sampled between
  texels, so a character is always a character and never a smear. The scanlines
  are then aligned to the *display's* own rows, which is the only raster that
  exists, so they never crawl or moire as the window changes size.
* **bloom.** Bright cells bleed into their neighbours the way a phosphor does.
  Only the bright ones: a bloom that took the walls with it would be a blur.
* **geometry.** The barrel, the rounded corners and the vignette, behind a
  toggle. Off by default: it is atmosphere, and atmosphere that cannot be turned
  off is a filter.

The shader is GLSL 1.20 on purpose -- the oldest thing that still runs
everywhere a Qt app runs, including the software rasteriser on a machine with no
GPU driver at all.
"""

from __future__ import annotations

import random
import time

from dataclasses import dataclass

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QColor, QImage, QOpenGLFunctions, QPainter, QVector2D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

__all__ = ["CrtSettings", "CrtView", "fit_scale"]

#: The handful of GL constants this file needs. Written as their standard values
#: rather than imported, because PySide6 exposes the functions but not the enum
#: names, and these three have not moved since OpenGL 1.0.
GL_COLOR_BUFFER_BIT = 0x00004000
GL_TRIANGLE_STRIP = 0x0005
GL_FLOAT = 0x1406


@dataclass
class CrtSettings:
    """Which effects are on. Scanlines and bloom on, geometry off, as asked."""

    scanlines: bool = True
    bloom: bool = True
    geometry: bool = False

    def cycle(self) -> None:
        """Step through the presets: full, plain, scanlines-only, geometry."""
        if self.geometry:
            self.geometry = False
        elif self.bloom:
            self.bloom = False
        elif self.scanlines:
            self.scanlines = False
        else:
            self.scanlines = True
            self.bloom = True
            self.geometry = True


def fit_scale(widget: QSize, buffer: QSize, minimum: float = 0.5) -> int:
    """The largest whole number that fits ``buffer`` inside ``widget``.

    A whole number, always, unless the window is too small to hold the buffer
    even once -- then the buffer is scaled down fractionally, because a game
    that cannot be seen is worse than a game that is slightly soft.
    """
    if buffer.width() <= 0 or buffer.height() <= 0:
        return 1
    scale = min(widget.width() // buffer.width(), widget.height() // buffer.height())
    return max(int(minimum) if scale < 1 else scale, 1)


_VERTEX = """
#version 120
attribute vec2 position;
attribute vec2 uv;
varying vec2 v_uv;
void main() {
    v_uv = uv;
    gl_Position = vec4(position, 0.0, 1.0);
}
"""

_FRAGMENT = """
#version 120
uniform sampler2D pattern;
uniform vec2 resolution;   // widget size, in pixels
uniform vec2 buffer;       // pattern size, in pixels
uniform vec2 offset;       // where the scaled pattern starts, in pixels
uniform float scale;       // whole-number scale
uniform int scanlines;
uniform int bloom;
uniform int geometry;

varying vec2 v_uv;

// The barrel: pull the picture toward the centre as it leaves it, so the edges
// bow the way a tube's do. Subtle -- a little goes a long way, and a lot is a
// fisheye.
vec2 warp(vec2 p) {
    vec2 centred = (p / resolution) * 2.0 - 1.0;
    float r2 = dot(centred, centred);
    centred *= 1.0 + 0.035 * r2;
    return (centred * 0.5 + 0.5) * resolution;
}

float luminance(vec3 c) {
    return dot(c, vec3(0.299, 0.587, 0.114));
}

void main() {
    vec2 screen = v_uv * resolution;

    if (geometry == 1) {
        screen = warp(screen);
    }

    // Where this pixel lands in the pattern, in buffer pixels.
    vec2 cell = (screen - offset) / scale;
    vec2 uv = cell / buffer;

    vec3 colour = vec3(0.0);

    bool inside = all(greaterThanEqual(cell, vec2(0.0)))
               && all(lessThan(cell, buffer));

    if (inside) {
        colour = texture2D(pattern, uv).rgb;

        if (bloom == 1) {
            // A cheap glow: the bright neighbours, at two radii, added back.
            // The threshold is what keeps it a phosphor bloom and not a blur --
            // the walls are dark and stay dark.
            vec3 glow = vec3(0.0);
            for (int i = -2; i <= 2; i++) {
                for (int j = -2; j <= 2; j++) {
                    vec2 tap = (cell + vec2(float(i), float(j)) * 1.5) / buffer;
                    vec3 c = texture2D(pattern, tap).rgb;
                    glow += c * step(0.45, luminance(c));
                }
            }
            colour += glow * 0.09;
        }

        if (scanlines == 1) {
            // Tied to the display's own rows, so the stripe is always one pixel
            // of the real raster and never beats against the scale.
            float row = mod(floor(screen.y), 2.0);
            float dark = row < 1.0 ? 0.72 : 1.0;
            colour *= mix(1.0, dark, 0.85);
        }

        if (geometry == 1) {
            // A tube is dimmer at the corners and does not quite reach them.
            vec2 centred = (screen / resolution) * 2.0 - 1.0;
            float r2 = dot(centred, centred);
            colour *= 1.0 - 0.25 * r2;
            float edge = max(abs(centred.x), abs(centred.y));
            colour *= 1.0 - smoothstep(0.92, 1.0, edge);
        }
    }

    gl_FragColor = vec4(colour, 1.0);
}
"""


class CrtView(QOpenGLWidget):
    """Shows a pattern image through a CRT. ``set_frame`` is the whole API."""

    def __init__(self, settings: CrtSettings | None = None, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings or CrtSettings()
        self._frame: QImage | None = None
        self._texture: QOpenGLTexture | None = None
        self._program: QOpenGLShaderProgram | None = None
        self._buffer: QOpenGLBuffer | None = None
        self._gl = None
        self._linked = False
        self._scale = 1
        self._offset = (0.0, 0.0)
        #: The glass rattling: a decaying jitter, in pixels, driven by things
        #: like a wound. Not an effect of the shader -- it warps the *sampling*,
        #: which is why it lives beside the offset.
        self._shake_until = 0.0
        self._shake_span = 0.2
        self._shake_strength = 0
        self._rng = random.Random()
        self.setMinimumSize(320, 200)

    def shake(self, strength: int = 6, seconds: float = 0.25) -> None:
        """Rattle the glass. Repeated calls keep it going, not bigger."""
        now = time.monotonic()
        if not self.is_shaking():
            self._shake_strength = strength
            self._shake_span = max(seconds, 0.05)
        self._shake_until = max(self._shake_until, now + seconds)

    def is_shaking(self) -> bool:
        return time.monotonic() < self._shake_until

    # -- the frame ----------------------------------------------------------
    def set_frame(self, image: QImage) -> None:
        """Hand over a fresh pattern image and repaint."""
        self._frame = image
        self.update()

    # -- geometry -----------------------------------------------------------
    def _recompute(self) -> None:
        if self._frame is None:
            return
        buffer = QSize(self._frame.width(), self._frame.height())
        self._scale = fit_scale(self.size(), buffer)
        drawn_w = buffer.width() * self._scale
        drawn_h = buffer.height() * self._scale
        self._offset = (
            (self.size().width() - drawn_w) / 2.0,
            (self.size().height() - drawn_h) / 2.0,
        )
        now = time.monotonic()
        if now < self._shake_until:
            fraction = (self._shake_until - now) / max(self._shake_span, 1e-6)
            wobble = self._shake_strength * min(1.0, fraction)
            self._offset = (
                self._offset[0] + self._rng.uniform(-wobble, wobble),
                self._offset[1] + self._rng.uniform(-wobble, wobble),
            )
        else:
            self._shake_strength = 0

    # -- OpenGL -------------------------------------------------------------
    def initializeGL(self) -> None:
        self._gl = QOpenGLFunctions(self.context())
        self._gl.initializeOpenGLFunctions()

        program = QOpenGLShaderProgram(self)
        program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX
        )
        program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment, _FRAGMENT
        )
        program.bindAttributeLocation("position", 0)
        program.bindAttributeLocation("uv", 1)
        self._linked = program.link()
        if not self._linked:
            # No shader, no CRT -- but not a black window. ``paintGL`` falls back
            # to QPainter and draws the frame crisp, which is the whole game with
            # the glass switched off.
            self._program = None
            return
        self._program = program

        # A fullscreen quad as a triangle strip: clip-space corners, and the
        # matching texture coordinates with v growing downward to match the
        # image's own row order.
        quad = [
            -1.0, -1.0, 0.0, 1.0,
             1.0, -1.0, 1.0, 1.0,
            -1.0,  1.0, 0.0, 0.0,
             1.0,  1.0, 1.0, 0.0,
        ]
        import struct

        buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        buffer.create()
        buffer.bind()
        data = struct.pack(f"{len(quad)}f", *quad)
        buffer.allocate(data, len(data))
        buffer.release()
        self._buffer = buffer

    def _refresh_texture(self) -> None:
        frame = self._frame
        if frame is None:
            return
        if (
            self._texture is None
            or self._texture.width() != frame.width()
            or self._texture.height() != frame.height()
        ):
            if self._texture is not None:
                self._texture.destroy()
            self._texture = QOpenGLTexture(frame)
            self._texture.setMinificationFilter(
                QOpenGLTexture.Filter.Nearest
            )
            self._texture.setMagnificationFilter(
                QOpenGLTexture.Filter.Nearest
            )
        else:
            self._texture.setData(frame)

    def paintGL(self) -> None:
        gl = self._gl
        gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT)
        if self._frame is None:
            return
        if self._program is None or self._buffer is None:
            self._paint_software()
            return

        self._recompute()
        self._refresh_texture()
        program = self._program
        program.bind()
        self._buffer.bind()
        program.enableAttributeArray(0)
        program.enableAttributeArray(1)
        program.setAttributeBuffer(0, GL_FLOAT, 0, 2, 4 * 4)
        program.setAttributeBuffer(1, GL_FLOAT, 2 * 4, 2, 4 * 4)

        program.setUniformValue1i("pattern", 0)
        if self._texture is not None:
            self._texture.bind(0)
        program.setUniformValue(
            "resolution",
            QVector2D(float(self.width()), float(self.height())),
        )
        program.setUniformValue(
            "buffer",
            QVector2D(float(self._frame.width()), float(self._frame.height())),
        )
        program.setUniformValue(
            "offset", QVector2D(float(self._offset[0]), float(self._offset[1]))
        )
        program.setUniformValue1f("scale", float(self._scale))
        program.setUniformValue1i("scanlines", 1 if self.settings.scanlines else 0)
        program.setUniformValue1i("bloom", 1 if self.settings.bloom else 0)
        program.setUniformValue1i("geometry", 1 if self.settings.geometry else 0)

        gl.glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

        program.disableAttributeArray(0)
        program.disableAttributeArray(1)
        self._buffer.release()
        if self._texture is not None:
            self._texture.release()
        program.release()

    def resizeGL(self, width: int, height: int) -> None:
        self._recompute()

    def _paint_software(self) -> None:
        """The fallback: the frame, crisp, with scanlines if they are on.

        Reached only when the shader would not link -- an old driver, a machine
        with no GPU -- and deliberately plain. The integer scale and the
        letterbox still hold, because those are arithmetic and not a shader;
        what is lost is the bloom and the curve, which need one.
        """
        self._recompute()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        target = QRect(
            int(self._offset[0]),
            int(self._offset[1]),
            self._frame.width() * self._scale,
            self._frame.height() * self._scale,
        )
        painter.drawImage(target, self._frame)
        if self.settings.scanlines:
            painter.setPen(QColor(0, 0, 0, 120))
            for y in range(target.top(), target.bottom() + 1, 2):
                painter.drawLine(target.left(), y, target.right(), y)
        painter.end()
