# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows build of Neverdead's Revenge 2.0.

Build it **on Windows** -- PyInstaller does not cross-compile -- which is why the
CI workflow does it on a ``windows-latest`` runner rather than here.

The game's runtime data is everything it *reads*: the sound effects, the face the
screens are written in, and the art -- the sprites, the flagstones and the painting
the arena stands in. All of it travels at the paths the code looks for it, which is
inside the package.

Run from the repository root:

    pyinstaller packaging/windows/neverdeads_revenge.spec
"""

import os

#: PyInstaller sets ``SPECPATH`` to this file's own directory.
HERE = os.path.abspath(SPECPATH)
ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
SRC = os.path.join(ROOT, "src")

sounds = os.path.join(SRC, "neverdeads_revenge", "sounds")
fonts = os.path.join(SRC, "neverdeads_revenge", "desktop", "fonts")
sprites = os.path.join(SRC, "neverdeads_revenge", "desktop", "sprites")
tiles = os.path.join(SRC, "neverdeads_revenge", "desktop", "tiles")
backdrops = os.path.join(SRC, "neverdeads_revenge", "desktop", "backdrops")

a = Analysis(
    [os.path.join(HERE, "run.py")],
    pathex=[SRC],
    binaries=[],
    # What the game reads at runtime and mirrors where it looks for it: the
    # sounds (``<package>/sounds``) and the font that travels with it
    # (``<package>/desktop/fonts``).
    datas=[
        (sounds, os.path.join("neverdeads_revenge", "sounds")),
        (fonts, os.path.join("neverdeads_revenge", "desktop", "fonts")),
        (sprites, os.path.join("neverdeads_revenge", "desktop", "sprites")),
        (tiles, os.path.join("neverdeads_revenge", "desktop", "tiles")),
        (backdrops, os.path.join("neverdeads_revenge", "desktop", "backdrops")),
    ],
    hiddenimports=[
        # Imported lazily by the audio layer, so static analysis misses it --
        # and ``_cffi_backend`` with it, which is what the cffi extension
        # ``_miniaudio`` needs *at import time*. It is loaded by the extension
        # rather than imported by name, so nothing sees it: without it the
        # import fails, the audio layer catches the failure by design and stays
        # silent, and the game looks perfectly fine and makes no sound.
        "miniaudio",
        "cffi",
        "_cffi_backend",
        # The CRT is a shader and is imported where it is used, so static
        # analysis misses it. The game falls back to a plain window without it,
        # which is the right behaviour and the wrong default for a *build*: a
        # player who was promised a CRT should get one.
        "moderngl",
    ],
    hookspath=[],
    runtime_hooks=[],
    # Nothing here is used and some of it is enormous. PySide6 is named too, and
    # not only because it is not a dependency any more: a stray import of it
    # should fail the build loudly rather than double the size of it.
    excludes=[
        "tkinter",
        "unittest",
        "pydoc_data",
        "PySide6",
        "PyQt5",
        "PyQt6",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NeverdeadsRevenge2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # A game, not a console: no terminal window behind it.
    console=False,
    icon=os.path.join(HERE, "neverdeads_revenge.ico"),
)
