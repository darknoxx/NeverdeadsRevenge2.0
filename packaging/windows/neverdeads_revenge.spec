# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows build of Neverdead's Revenge 2.0.

Build it **on Windows** -- PyInstaller does not cross-compile -- which is why the
CI workflow does it on a ``windows-latest`` runner rather than here.

The game's only runtime data is its sound effects: the font is a system face
(Consolas or Courier New on Windows, DejaVu on Linux) and everything else is
code. So the spec carries ``sounds/`` at the path ``audio.py`` expects to find it
beside the package, and nothing else.

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
    ],
    hiddenimports=[
        # Imported lazily by the audio layer, so static analysis misses it.
        "miniaudio",
    ],
    hookspath=[],
    runtime_hooks=[],
    # Qt is huge; none of this is used and leaving it out is most of the saving.
    excludes=[
        "tkinter",
        "unittest",
        "pydoc_data",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
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
