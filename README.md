# Neverdead's Revenge 2.0

The same dungeon, on a CRT.

This is the desktop build of **Neverdead's Revenge**: the terminal roguelite about
Noxx and the hour he borrowed, rendered as a fixed grid of characters on a
simulated MS-DOS monitor. The dungeon, the monsters, the curses, the gifts, the
shop, the save format and the balance are the *same systems* as the terminal
game — they were forked wholesale and never learned that a terminal stopped
existing. What is new is everything above them: a PySide6 window, a pattern
buffer, and a fragment shader that puts scanlines, bloom and a toggleable barrel
over the top.

It is a **fork, not a wrapper**. The terminal project was frozen the day this one
started; from here, this is where the game lives.

## Running it

```sh
python3 -m venv .venv
./.venv/bin/pip install -e '.[dev]'
./ndr2
```

`ndr2` runs the windowed game. The same launcher takes the flags the terminal
build had:

```sh
./ndr2 --seed 42          # a repeatable dungeon
./ndr2 --no-sound         # start silent
./ndr2 --sound-log        # log every sound decision to /tmp/ndr2-sound.log
./ndr2 --testrun          # unlock the chronicle and fill the purse, then play
```

## The keys

The dungeon is played with the keys it always was: the arrows or `hjkl` (and
`yubn` for the diagonals) to move, `.` to wait, `enter` to interact, `q` to
drink, `i` for the pack, `>` for the stairs, `r` to take the borrowed hour back.

The window and the glass have keys of their own:

| key | what it does |
| --- | --- |
| `F11` | fullscreen, and back |
| `+` / `-` | zoom the field in and out |
| `F2` | scanlines on/off |
| `F3` | bloom on/off |
| `F4` | the CRT's curve, corners and vignette on/off |

Scanlines and bloom are on at the start; the curve is off, because it is the one
effect that changes what the picture *is* rather than how it is lit. The zoom and
the three effects are remembered between runs.

## Size

The zoom is not a font size -- it is how many whole pixels a cell is drawn with.
The grid aims for about a hundred columns, so on a 1080p screen a cell is two
pixels and the field fills the display exactly, on a 4K screen four, and on a
small laptop one. `+` and `-` move it by hand; the game stays legible at every
step, because the scale is always a whole number and the buffer is centred with
black bars where the number does not divide.

## How it is put together

```
src/neverdeads_revenge/
  core/ world/ game/ persistence.py   the forked systems -- no screen anywhere
  desktop/                            the PySide6 presentation layer
    theme.py    the palette, and Rich styles translated
    font.py     a monospaced cell, drawn without antialiasing
    buffer.py   the grid of characters -> an image
    crt.py      the shader: integer scaling, scanlines, bloom, geometry
    render.py   the map, sidebar, log and columns, as cells
    app.py      the window, the keys, and the loop
```

The pattern buffer is the seam that makes the CRT possible. By the time the
picture exists it is a small, flat image, and scaling it by a whole number and
laying scanlines over it is arithmetic rather than a redraw. The scale is chosen
so a character is never a fraction of a pixel: on a 1080p screen a cell is two
pixels, on a 4K screen four, on a small laptop one, and the buffer is centred
with black bars where the number does not divide.

## Save data

Separate from the terminal build, on purpose: 2.0 keeps its own profile in
`~/.local/share/neverdeads_revenge2/`, so experimenting here never touches a
terminal run's scores or chronicle.

## Licence

MIT. See `LICENSE`.
