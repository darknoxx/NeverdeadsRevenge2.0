"""Can this display server make a GL window? Asked out of process.

A GL driver that does not work is not polite about it: it can take the whole
process with it, and no ``try`` catches a segmentation fault. So the question is
put to a child process, which either exits cleanly or does not, and the game only
takes a road the child survived.

This module has no game in it, on purpose: it is imported by the child, and the
child must be able to answer and die.
"""

from __future__ import annotations

__all__ = ["probe_gl"]


def probe_gl(driver: str, egl: bool = False) -> bool:
    """Make a window with a context on ``driver``, and let it go again.

    ``driver`` is an SDL video driver name (``wayland``, ``x11``, an empty string
    for whatever the machine prefers); ``egl`` asks X11 to go through EGL rather
    than GLX. The size is small and the window is never shown: this is a question
    about a context, not a frame.
    """
    import os

    if driver:
        os.environ["SDL_VIDEODRIVER"] = driver
    if egl:
        os.environ["SDL_VIDEO_X11_FORCE_EGL"] = "1"
    try:
        import pygame

        pygame.init()
        # The same kind of window the game will ask for: full screen at the
        # desktop's own size. Windowed would be a smaller question, and the crash
        # worth catching is the one on the road the game actually takes.
        desktop = pygame.display.get_desktop_sizes()[0]
        window = pygame.display.set_mode(
            desktop, pygame.OPENGL | pygame.DOUBLEBUF | pygame.FULLSCREEN
        )
        import moderngl

        from ..desktop.crt_gl import CrtSettings
        from .glass import SdlGlass

        # The whole glass, not only a context: a shader that will not compile, a
        # texture upload the driver dislikes, a flip that ends the process -- all
        # of it is part of the question being asked, and all of it stays in the
        # child.
        glass = SdlGlass(
            CrtSettings(scanlines=True, bloom=True, geometry=False),
            desktop,
            window.get_size(),
            context=moderngl.create_context(),
        )
        frame = pygame.Surface(desktop)
        glass.draw(frame)
        pygame.display.flip()
    except BaseException:  # noqa: BLE001 - any failure is "this road is closed"
        return False
    return True
