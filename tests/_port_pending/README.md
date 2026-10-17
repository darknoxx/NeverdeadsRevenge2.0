# Waiting to be ported

The Qt build's tests, parked here while the Qt build is being removed. They are
`.pending` and not `.py` so that nothing collects them: they import modules that
are gone (`desktop.buffer`, `desktop.app`, `desktop.font`) and they will not run
until each one has been looked at.

This is what is left of the port, in the order the failures come:

* ``test_desktop.py`` (27 tests) -- the window, the whole-number scaling and the
  key bindings. Most of it is about the Qt *window*, which no longer exists; the
  parts that are about cells (the pattern buffer, the layout rules) belong in the
  SDL suite and should be moved there one at a time.
* ``test_screens.py.pending`` (144 tests) -- the menus, the dialogs and the arena,
  driven a key at a time. Already re-harnessed onto the SDL app (see the header of
  the file): the app, the font, the blitter, the old key spellings and a
  ``pixelColor`` shim. What is left is three mechanical things and a judgement:

  1. Several tests import Qt *inside* the test (``from PySide6.QtCore import
     Qt``), which shadows the shim. Delete those lines and the module-level shim
     takes over.
  2. ``from neverdeads_revenge.desktop.buffer import PatternBuffer`` is now
     ``...desktop.pattern...``.
  3. ``screen = SdlArena(battle)`` is right for anything that looks at *pixels* --
     the SDL arena is the painter -- and wrong for anything that calls the
     screen's own machinery (``_choose``, ``_figures``), which wants
     ``BattleScreen(battle)``. A glance per test, not a rule.
  4. And the two ``..._on_qt`` tests at the end are mine and are duplicates of
     what already lives in ``tests/test_sdl_front.py``: drop them.

Everything here is coverage that the SDL suite does not have yet -- the menus,
the dialogs, the level-up, the shop, the chronicle -- so it is worth the walk.
