"""The CRT's own numbers, with no toolkit in them.

Which effects are on, and the shader that draws them. Both used to live in
``crt.py`` beside the Qt widget that runs them, which meant a second front end
could not have the same glass: importing the settings meant importing Qt. They are
facts about a *look*, not about a library, so they live here now, and `crt.py`
imports them back.

The shader is GLSL 1.20 as it always was. `source` is the one thing added here:
the same body under whichever version line the context wants -- desktop GL is
happy with 1.20, and GLES wants 1.00 and a precision statement, which is the
difference between running on a handheld and not.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FRAGMENT", "VERTEX", "CrtSettings", "source"]


@dataclass
class CrtSettings:
    """Which effects are on. Scanlines and bloom on, geometry off, as asked."""

    scanlines: bool = True
    bloom: bool = True
    geometry: bool = False

VERTEX = """
#version 120
attribute vec2 position;
attribute vec2 uv;
varying vec2 v_uv;
void main() {
    v_uv = uv;
    gl_Position = vec4(position, 0.0, 1.0);
}
"""

FRAGMENT = """
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
            //
            // It used to be a hard cutoff at half brightness, which is why a
            // skeleton glowed and a ghoul did not -- phosphor does not work in
            // steps like that. Now it is a matter of degree: every cell adds
            // light in proportion to how much light it has above a floor, so
            // bright things breathe, mid-dark ones (the hero's purple, a
            // ghoul's green) get a soft breath of their own, and the dark ones
            // -- floor and rock -- glow only as far as their greyness reaches
            // anyway, which is the faintest.
            vec3 glow = vec3(0.0);
            for (int i = -2; i <= 2; i++) {
                for (int j = -2; j <= 2; j++) {
                    vec2 tap = (cell + vec2(float(i), float(j)) * 1.5) / buffer;
                    vec3 c = texture2D(pattern, tap).rgb;
                    float light = max(0.0, luminance(c) - 0.25);
                    glow += c * light;
                }
            }
            colour += glow * 0.045;
        }

        if (scanlines == 1) {
            // Tied to the display's own rows, so the stripe is always one pixel
            // of the real raster and never beats against the scale.
            float row = mod(floor(screen.y), 2.0);
            float dark = row < 1.0 ? 0.72 : 1.0;
            colour *= mix(1.0, dark, 0.85);
        }
        // The edge darkening -- the vignette -- is off for now, on trial, so
        // the curve above can be judged on its own. It lives where it was: a
        // radial dim over the frame, plus a smoothstep mask on the last few
        // pixels, both inside `geometry == 1`.
    }

    gl_FragColor = vec4(colour, 1.0);
}
"""


def source(fragment: bool = True, gles: bool = False) -> str:
    """The shader, under the version line the context in front of us wants.

    Only the first line changes: desktop GL takes 1.20 exactly as it was written,
    and GLES takes 1.00, where a fragment shader also has to say what precision
    its floats are. Everything under it -- the attributes, the barrel, the bloom,
    the scanlines -- is the same arithmetic either way. (Stripping the version
    line and *not* the whole header: the attribute declarations in the vertex
    shader are part of the shader, and a body that started at `main` compiled to
    three complaints about undeclared names.)
    """
    text = (FRAGMENT if fragment else VERTEX).lstrip()
    if text.startswith("#version"):
        text = text.split("\n", 1)[1]
    if gles:
        head = "#version 100\n"
        if fragment:
            head += "precision mediump float;\n"
    else:
        head = "#version 120\n"
    return head + text


