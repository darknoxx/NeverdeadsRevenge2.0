"""The game's own presentation: cells, chrome, letters and art paths.

The systems under it -- ``core``, ``world``, ``game`` -- are the fork of the
terminal game and know nothing about a screen. Everything that does know is in
here, and *only* the parts that do not care who is drawing: the pattern buffer
the game is written into, the CRT's own settings, the layout specs a screen is
placed by, and the paths its art is read from. A cell is a cell whoever blits it.

What is deliberately not here is a painter. The one this game has lives in
:mod:`~neverdeads_revenge.sdl_front` -- it was built twice for a while, once on
Qt and once on SDL, and the SDL one is what ships: a window that also builds for
Windows and, in time, for Android. So a screen in this package is a *shape*: it
writes cells, it stages figures, it answers a key -- and the front end puts the
pixels down.

The name is a leftover and it is honest about it: this was the desktop layer when
the desktop was Qt's, and renaming a package that every screen imports would have
been a diff with no truth in it.
"""

from __future__ import annotations

__all__: list[str] = []
