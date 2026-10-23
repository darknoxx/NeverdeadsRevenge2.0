# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Linux build of Neverdead's Revenge 2.0.

Build it **on Linux** -- PyInstaller does not cross-compile -- which is what the
CI workflow does on an ``ubuntu-22.04`` runner. That release matters: glibc is
forward compatible and not backwards compatible, so a build made against a newer
glibc will not start on the older one. 22.04 is also what an AppImage is
expected to be built on, and it runs on SteamOS.

The output is a **one-folder** build, not a one-file one: it becomes the payload
of an AppImage, which unpacks once when the player runs it and then starts the
game directly. A one-file executable would unpack itself again on every start.

Run from the repository root:

    pyinstaller packaging/linux/neverdeads_revenge.spec
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

#: Libraries the *system* owns, and has to keep owning. The C++ runtime is the
#: one that matters: mesa and its drivers are built against the distribution's
#: libstdc++, and PyInstaller puts the build machine's older copy in front of it
#: on ``LD_LIBRARY_PATH``. A driver that cannot resolve its own runtime does not
#: load, and SDL reports the only thing it can see from there -- "Couldn't find
#: matching GLX visual", "Could not get EGL display" -- which is a game with no
#: CRT that works perfectly from source, on the same machine. The rest are base
#: system libraries of the same kind, and none of them are ours to ship.
SYSTEM_LIBS = {
    "libstdc++.so.6",
    "libgcc_s.so.1",
    "libz.so.1",
    "libexpat.so.1",
    "libuuid.so.1",
    "libffi.so.8",
    "libbz2.so.1.0",
    "liblzma.so.5",
    "libreadline.so.8",
    "libtinfo.so.6",
    "libmvec.so.1",
}

a.binaries = [
    entry for entry in a.binaries if os.path.basename(entry[0]) not in SYSTEM_LIBS
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="NeverdeadsRevenge2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # A game, not a console: no terminal window behind it.
    console=False,
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NeverdeadsRevenge2",
)
