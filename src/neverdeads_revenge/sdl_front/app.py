"""The SDL window, the screens, and the keys between them.

The same job as ``desktop/app.py``: hold the stack of screens, route a key to the
top of it, keep the run and the meta-progress, and paint whatever comes out. What
it does *not* do is own the game -- every rule, every screen and every panel it
shows is the same code the Qt build shows, because none of them ever knew what a
window was.

Two things are honestly missing, and named rather than hidden:

* **The effects layer.** The Qt build has sparks, flashes and a shaking glass;
  those are painted in pixels and they are the next session's work. The screens
  ask for them the same way they always did, and this answers politely and does
  nothing -- so a fight is playable and quieter than it will be.
* **The screens that are not ported yet.** The shop, the scoreboard and the
  chronicle are Qt screens; opening one here says so. A front end that pretended
  to open them would be a front end that lost a purchase.
"""

from __future__ import annotations

import random
from pathlib import Path

from ..persistence import load_meta
from .font import SdlFont
from .keys import name_of, typed
from .paint import paint

__all__ = ["SdlApp", "FONT", "MIN_COLS", "MIN_ROWS"]

FONT = Path(__file__).resolve().parent.parent / "desktop" / "fonts" / "DejaVuSansMono.ttf"

#: The smallest playable grid, matching the Qt build: every panel in the game is
#: laid out for at least this, and a window that fit fewer cells would not be a
#: smaller game but a broken one.
MIN_COLS = 76
MIN_ROWS = 24


class KeyPress:
    """A key press, in the shape the screens already ask for.

    They want two things a name cannot carry: whether the key is *held* -- which
    the hold bars count -- and the character it types. Making the same two
    questions answerable here is the whole of what a front end owes a screen.
    """

    def __init__(self, repeat: bool = False, text: str = "") -> None:
        self._repeat = repeat
        self._text = text

    def isAutoRepeat(self) -> bool:  # noqa: N802 - Qt's spelling, and the screens'
        return self._repeat

    def text(self) -> str:
        return self._text


class _NoEffects:
    """The sparkle, for a session that has not ported it yet."""

    active = False

    def clear(self) -> None:
        return None

    def spark(self, *args, **kwargs) -> None:
        return None


class _NoView:
    """The glass, for a session whose glass is a plain window."""

    def shake(self, **kwargs) -> None:
        return None

    def is_shaking(self) -> bool:
        return False


class SdlApp:
    """A window, a stack of screens, and the run they are about."""

    def __init__(
        self,
        *,
        seed: int = 3,
        cols: int = 96,
        rows: int = 27,
        scale: int = 2,
        screen=None,
        headline: bool = True,
        no_sound: bool = True,
    ) -> None:
        import pygame

        pygame.init()
        self.font = SdlFont(str(FONT))
        self.progress = load_meta()
        self.seed = seed
        self.run = None
        #: The premise, told once in the Qt build between the choice and the
        #: floor. Ported screens come next; until then a run starts on the floor,
        #: and this says so rather than pretending the prologue happened.
        self.prologue_seen = True
        self.scale = max(1, scale)
        if screen is not None:
            self.screens = [screen]
        else:
            from ..desktop.screens.title import TitleScreen

            self.screens = [TitleScreen()]
        self.cols = max(MIN_COLS, cols)
        self.rows = max(MIN_ROWS, rows)
        self.effects = _NoEffects()
        self.view = _NoView()
        #: The same sound system the Qt build plays through, or nothing when the
        #: machine has no audio -- which is its own kind of honest.
        try:
            from ..desktop.audio import Sfx

            self.sfx = None if no_sound else Sfx()
        except Exception:
            self.sfx = None
        #: What the game asked to be heard. A front end with no sound is still a
        #: front end that was asked, and a test can read this.
        self.played: list[str] = []
        self.headline = headline
        self._window = None
        self._surface = None

    # -- the stack ---------------------------------------------------------
    def push(self, screen) -> None:
        self.screens.append(screen)

    def pop(self) -> None:
        if len(self.screens) > 1:
            self.screens.pop()

    def swap(self, screen) -> None:
        self.screens[-1:] = [screen]

    def return_to_title(self) -> None:
        from ..desktop.screens.title import TitleScreen

        self.screens = [TitleScreen()]

    # -- what the screens ask of an application ------------------------------
    def has_saved_run(self) -> bool:
        from ..persistence import load_run

        return load_run() is not None

    def play(self, name: str = "hit") -> None:
        """Make the noise. The same sound system the Qt build uses, and the same
        files -- it never knew about a window either."""
        self.played.append(name)
        if self.sfx is not None:
            self.sfx.play(name)

    def play_after(self, before: tuple[int, int, int]) -> None:
        """Make the noise the last thing that happened deserves.

        The port of the Qt build's own rules, and the rules are the game's: a new
        floor beats a level, a level beats a kill, and the loudest line in the log
        says what the rest sounded like.
        """
        run = self.run
        if run is None or run.over:
            return
        from ..desktop.audio import loudest_kind, sound_for_kind

        before_log, before_depth, before_level = before
        if run.depth != before_depth:
            self.play("stairs")
            return
        if run.level != before_level:
            self.play("level")
            return
        kind = loudest_kind(entry.kind for entry in run.log[before_log:])
        sound = sound_for_kind(kind)
        if sound:
            self.play(sound)

    def save_progress(self) -> None:
        from ..persistence import save_meta

        try:
            save_meta(self.progress)
        except OSError:
            pass

    def show_game_over(self, won: bool = False) -> None:
        from ..desktop.screens.game_over import GameOverScreen

        self.push(GameOverScreen(self.run, won=won))

    def open_encounter(self) -> bool:
        """The floor handed a fight over: the arena goes on top of the room.

        Two things differ from the Qt build, and both are because of what is not
        ported yet. The *turning* -- the step, the letter coming at the camera,
        the white -- is painted in pixels, so the fight opens without it; and
        because there is no turning screen in between, the arena is *pushed* on
        top of the floor rather than swapped over it. Under Qt the arena replaces
        the turning screen and the floor is already underneath; pushing is the
        same stack with the missing screen left out.

        What is not skipped is the fight: the same ``open_fight`` builds the same
        room, with the same rules, and the player fights it.
        """
        if self.run is None or self.run.encounter is None:
            return False
        from ..game.battle import open_fight

        fight = open_fight(self.run)
        if fight is None:
            return False
        from .arena import SdlArena

        self.push(SdlArena(fight))
        return True

    def leave_battle(self) -> None:
        """The fight is over: back to the floor, or home if there is no floor."""
        if len(self.screens) > 1:
            self.pop()
        else:
            self.return_to_title()
        screen = self.screens[-1] if self.screens else None
        if screen is not None:
            catch_up = getattr(screen, "catch_up", None)
            if catch_up is not None:
                catch_up(self)

    def screen_point(self, position):
        """Where a cell is in pixels. ``None`` until the effects layer exists."""
        return None

    def open_shop(self) -> None:
        self.play("deny")

    def open_scoreboard(self) -> None:
        self.play("deny")

    def open_chronicle(self) -> None:
        self.play("deny")

    def open_hero_select(self) -> None:
        from ..desktop.screens.hero_select import HeroSelectScreen

        self.push(HeroSelectScreen())

    def begin_run(self, hero_key: str) -> None:
        from ..desktop.screens.game import GameScreen
        from ..game.actors import HEROES
        from ..game.shop import loadout_from
        from ..game.state import start_run

        if not self.seed:
            self.seed = random.SystemRandom().randrange(2**32)
        self.run = start_run(
            HEROES[hero_key], self.seed, loadout=loadout_from(self.progress)
        )
        self.effects.clear()
        self.screens = [GameScreen(self.run)]
        self.redraw()

    def continue_run(self) -> None:
        from ..desktop.screens.game import GameScreen
        from ..persistence import load_run

        payload = load_run()
        if payload is None:
            return
        from ..game.state import RunState

        self.run = RunState.from_dict(payload)
        self.screens = [GameScreen(self.run)]
        self.redraw()

    # -- the picture --------------------------------------------------------
    def redraw(self) -> None:
        """Draw the stack into the grid, and the grid onto the window."""
        from ..desktop.pattern import PatternBuffer

        self.grid = PatternBuffer(self.cols, self.rows, self.font)
        # An opaque modal: nothing under it is drawn. A menu is a panel, not a
        # window onto the dungeon, so the topmost modal roots the stack -- the
        # same rule the Qt build keeps, and the reason a dialog is not a
        # see-through ghost of the fight behind it.
        start = 0
        for index, screen in enumerate(self.screens):
            if getattr(screen, "modal", False):
                start = index
        for screen in self.screens[start:]:
            screen.draw(self.grid, self)
        self._surface = paint(self.grid, self.font)
        self._present()

    def _present(self) -> None:
        """Put the picture on the screen, whole-number scaled, or nowhere.

        Nowhere is a real answer: a headless run of this -- which is how the
        tests drive it -- has no window to put it on, and drawing is still done
        so that everything above it is exercised.
        """
        import pygame

        if not pygame.display.get_init() or self._window is None:
            return
        surface = self._window
        surface.fill((0, 0, 0))
        scaled = pygame.transform.scale(
            self._surface,
            (self._surface.get_width() * self.scale, self._surface.get_height() * self.scale),
        )
        surface.blit(scaled, (0, 0))
        pygame.display.flip()

    # -- the keys -----------------------------------------------------------
    def key(self, name: str, event=None, text: str = "") -> bool:
        """Hand a key to the top screen. Returns whether it was used."""
        if not name:
            return False
        screen = self.screens[-1]
        used = screen.key(name, event or KeyPress(text=text), self)
        self.redraw()
        return bool(used)

    def open_window(self, *, title: str = "Neverdead's Revenge") -> None:
        """A real window, and the loop that feeds it.

        Not used by the tests, which drive ``key`` and ``redraw`` directly: the
        loop is the part that cannot be tested headless, and it is deliberately
        the smallest part of this file.
        """
        import pygame

        self._window = pygame.display.set_mode(
            (self.cols * self.font.cell_w * self.scale,
             self.rows * self.font.cell_h * self.scale)
        )
        pygame.display.set_caption(title)
        self.redraw()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self.key(name_of(event), KeyPress(event, typed(event)), typed(event))
                elif event.type == pygame.VIDEORESIZE:
                    self.redraw()
