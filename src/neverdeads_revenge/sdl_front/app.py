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
from .effects import SdlEffects
from .keys import name_of, typed
from .paint import paint

__all__ = ["SdlApp", "FONT", "MIN_COLS", "MIN_ROWS", "SMALL_PIXELS"]

#: The size of the smaller face the sidebar and the log are drawn in, one step
#: down from the grid: the Qt build uses the same number, which is what makes the
#: two layouts come out the same.
SMALL_PIXELS = 11

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
        battle_scene: bool = False,
    ) -> None:
        import pygame

        pygame.init()
        self.font = SdlFont(str(FONT))
        #: The same smaller face the Qt build uses for the sidebar and the log:
        #: one size down, which is the one place a mixed size pays for itself.
        self.font_small = SdlFont(str(FONT), SMALL_PIXELS)
        self.progress = load_meta()
        #: The glass: the same settings the Qt build reads out of the same file,
        #: so a player who turned the scanlines off keeps them off. The shader and
        #: the settings are shared; only the context is this front end's.
        from ..desktop.crt_gl import CrtSettings
        from ..desktop.settings import load_settings

        saved = load_settings()
        self.crt = CrtSettings(
            scanlines=bool(saved.get("scanlines", True)),
            bloom=bool(saved.get("bloom", True)),
            geometry=bool(saved.get("geometry", False)),
        )
        self.glass = None
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
        self.effects = SdlEffects()
        #: The glass, which is the same object: a landed blow shakes the *frame*,
        #: and the frame is this application's own. The arena asks ``view.shake``
        #: exactly as it does under Qt, and what it gets is a surface drawn a few
        #: pixels off centre -- which is what a shaken glass is.
        self.view = self.effects
        #: The same sound system the Qt build plays through, and always an
        #: object: a screen asks it whether it is muted, and a *missing* mixer is
        #: not the same answer as a quiet one. Where a machine has no audio the
        #: mixer gives up on its own and says so.
        from ..desktop.audio import Sfx

        self.sfx = Sfx(muted=no_sound or self.progress.muted)
        #: And when it gives up mid-session, the record has to agree -- or the
        #: next toggle writes the give-up back down as "unmuted".
        self.sfx.on_mute = self._sound_gave_up
        #: What the game asked to be heard. A front end with no sound is still a
        #: front end that was asked, and a test can read this.
        self.played: list[str] = []
        self.headline = headline
        self._window = None
        self._surface = None
        #: Whether the window loop should keep going. Only ``quit`` clears it --
        #: there is no window object to ask on this front end.
        self._running = True
        if battle_scene:
            self.open_battle_scene()

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
        from ..game.battle import Battle, encounter_around
        from .turning import SdlTurning

        trigger = self.run.encounter
        # Cleared before the arena opens: the domain is done with it the moment
        # it is set, and a fight that is asked for twice would be two fights.
        self.run.encounter = None
        battle = Battle(self.run, encounter_around(self.run, trigger))
        self.push(SdlTurning(trigger, battle))
        return True

    def enter_battle(self, battle) -> None:
        """The arena, in the place of whoever was turning the room over."""
        from .arena import SdlArena

        self.swap(SdlArena(battle))

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
        """Where a cell is, in the frame's own pixels.

        Sparks are thrown in buffer pixels in both builds, and a cell is a
        rectangle of them: the corner is where a spray comes from.
        """
        return (position[0] * self.font.cell_w, position[1] * self.font.cell_h)

    def open_battle_scene(self) -> None:
        """The dev door: a fight against the first monsters of a fresh floor.

        The same door the Qt build has, and for the same reason: a run starts on
        the floor and a fight is reached by walking into one, which is the game
        and not a shortcut -- but looking at the arena should not cost a walk.
        """
        from ..game.actors import HEROES
        from ..game.battle import Battle
        from ..game.state import start_run
        from .arena import SdlArena

        if self.run is None:
            self.run = start_run(HEROES["noxx"], self.seed)
        self.screens = [SdlArena(Battle(self.run, self.run.enemies[:3]))]
        self.redraw()

    def open_shop(self) -> None:
        """The shop: the same screen the Qt build pushes, on this stack."""
        from ..desktop.screens.menus import ShopScreen

        self.push(ShopScreen())

    def open_scoreboard(self) -> None:
        from ..desktop.screens.menus import ScoreboardScreen

        self.push(ScoreboardScreen())

    def open_chronicle(self) -> None:
        from ..desktop.screens.menus import ChronicleScreen

        self.push(ChronicleScreen())

    def open_delete_progress(self) -> None:
        """Ask for the word, then erase everything.

        The dialog is the whole safety: it answers ``True`` only when DELETE was
        typed, and anything else leaves the profile exactly where it was.
        """
        from ..desktop.screens.dialogs import DeleteProgressScreen

        self.push(
            DeleteProgressScreen(
                on_done=lambda confirmed: self.delete_progress() if confirmed else None
            )
        )

    def delete_progress(self) -> None:
        """Wipe the profile and the saved run. Nothing is kept back."""
        from ..persistence import clear_run
        from ..persistence import MetaProgress

        self.progress = MetaProgress()
        self.save_progress()
        clear_run()
        self.run = None

    def record_run(self, state, name: str = "") -> int:
        """Put the run on the board -- the board outlives the window, so it is
        the *progress*'s business and not this application's."""
        from ..core.rng import Rng
        from ..game.state import RunState

        self.progress.record_run(
            depth=state.depth,
            score=state.score,
            kills=state.kills,
            gold=state.gold,
            won=state.run_state is RunState.ESCAPED,
            name=name,
            hero=state.hero.key,
        )
        self.progress.reroll_wilds(Rng(random.SystemRandom().randrange(2**32)))
        self.save_progress()
        return self.progress.best_score

    def after_summary(self, answer) -> None:
        """The summary is answered: a name for the board, or the hour back.

        The same two doors the Qt build has, and the same screens behind them: a
        run that escaped may be written down, and one that ended in the dark may
        spend the hour it borrowed to be here.
        """
        from ..desktop.screens.game_over import REWIND, NameEntryScreen
        from ..game.actions import Action, perform_action

        state = self.run
        if state is None:
            return
        if answer != REWIND:

            def done(name: str) -> None:
                if state is not None:
                    self.record_run(state, name or "???")
                self.return_to_title()

            self.push(
                NameEntryScreen(state.score, self.progress.last_name, on_done=done)
            )
            return
        perform_action(state, Action.REWIND)
        self.redraw()

    def save_and_quit(self) -> None:
        """Put the run down and go back to the title, keeping it for later."""
        from ..game.savegame import dump
        from ..persistence import save_run

        if self.run is not None:
            save_run(dump(self.run))
        self.return_to_title()

    def quit(self) -> None:
        """Close the window: the loop stops at the end of this frame."""
        self._running = False

    def quit_requested(self) -> None:
        from ..desktop.screens.dialogs import ConfirmScreen

        self.push(
            ConfirmScreen(
                "QUIT NEVERDEAD'S REVENGE?",
                "The dungeon will still be here when you come back.",
                on_done=lambda yes: self.quit() if yes else None,
            )
        )

    def confirm_quit_to_title(self) -> None:
        from ..desktop.screens.dialogs import ConfirmScreen

        self.push(
            ConfirmScreen(
                "QUIT TO THE TITLE?",
                "The run does not come back. It is not written down.",
                on_done=lambda yes: self.return_to_title() if yes else None,
            )
        )

    def _sound_gave_up(self, muted: bool) -> None:
        """The audio session quit on its own; the record has to agree."""
        self.progress.muted = muted
        self.save_progress()

    def toggle_sound(self) -> None:
        """Turn the sound over, and write the answer down: a player who mutes a
        game expects it to *stay* muted the next time they open it."""
        self.sfx.toggle()
        self.progress.muted = self.sfx.muted
        self.save_progress()

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
    def tick(self, dt: float) -> None:
        """A frame went by: let the screen play, let the pixels move, repaint.

        Called by the window loop and by anything driving this headless. A screen
        that is *moving* is asked every frame -- a fight breathes whether or not it
        is talking, and this is the only clock the second front end has -- and one
        that is busy is asked until it is done.
        """
        screen = self.screens[-1]
        if getattr(screen, "busy", False) or getattr(screen, "animating", False):
            screen.step(dt, self)
        self.effects.step(dt)
        self.redraw()

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
        self._small_face()
        # And a screen may paint straight onto the frame once the grid is drawn:
        # that is where the art lives -- sprites do not fit in a character cell.
        # It is called `paint_over` and not `paste`, which is Qt's name for the
        # same pass, because the Qt screens in this same stack have a `paste` too
        # and it wants a QImage: one name for two media is one crash waiting.
        paint_over = getattr(self.screens[-1], "paint_over", None)
        if paint_over is not None:
            paint_over(self._surface, self)
        self._blit_art()
        # And the pixels that are not the room: sparks thrown by whatever just
        # happened, drawn last so they land on top of everything.
        self.effects.draw(self._surface)
        self._present()

    def _small_face(self) -> None:
        """The sidebar's lower rows and the combat log, one size down.

        The Qt build draws these straight onto the frame after the grid, and this
        is the same pass with a pygame painter: the *rows* come from the shared
        specs in ``desktop/render.py`` -- what to say, where, in which colour --
        and only the blitting is this application's. That is why the two front
        ends can show the same sidebar without one of them owning the layout.
        """
        import pygame

        from ..desktop.render import log_text, sidebar_text
        from ..desktop.theme import BACKGROUND, parse_style

        screen = self.screens[-1]
        if not getattr(screen, "smaller_face", False) or self.run is None:
            return
        face = self.font_small
        surface = self._surface
        rect, rows = log_text(
            self.run,
            self.grid.cols,
            self.grid.rows,
            self.font.cell_w,
            self.font.cell_h,
            face.cell_w,
            face.cell_h,
        )
        # The log's own panel, drawn solid: nothing is underneath it now that the
        # cells above it are clear.
        surface.fill(tuple(BACKGROUND), pygame.Rect(*rect))
        for ink in rows:
            self._put_small(surface, face, ink)
        out, rule = sidebar_text(
            self.run,
            self.grid.cols,
            self.grid.rows,
            self.font.cell_w,
            self.font.cell_h,
            face.cell_w,
            face.cell_h,
        )
        for ink in out:
            self._put_small(surface, face, ink)
        if rule is not None:
            surface.fill(
                tuple(parse_style("grey30").fg),
                pygame.Rect(rule[0], rule[2], rule[1] - rule[0], 1),
            )

    def _put_small(self, surface, face, ink) -> None:
        """One row of the small face: a string, blitted a glyph at a time."""
        from ..desktop.theme import parse_style

        colour = parse_style(ink.colour).fg
        for index, char in enumerate(ink.text):
            if char == " ":
                continue
            glyph = face.glyph(char, colour)
            if glyph is not None:
                surface.blit(glyph, (ink.x + index * face.cell_w, ink.y))

    def _blit_art(self) -> None:
        """The pictures a screen asked for, put where it asked for them.

        The same ``Placed`` records the Qt build blits, read by a painter that has
        never heard of Qt: the screen says what and where, and this puts it down.
        Which is the whole reason the records exist -- one roster, two frames.
        """
        import pygame

        from .paint import load

        for piece in self.screens[-1].art(self):
            art = load(piece.art)
            if art is None:
                continue
            width = max(
                1, round(art.get_width() * piece.height / max(1, art.get_height()))
            )
            scaled = pygame.transform.smoothscale(art, (width, piece.height))
            self._surface.blit(
                scaled,
                (
                    round(piece.centre - width / 2),
                    round(piece.bottom - piece.height),
                ),
            )

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
        offset = self.effects.offset()
        if self.glass is not None:
            # The glass has the whole picture and the whole window: it is the
            # thing that scales, so the shake goes in as part of its offset.
            self.glass.draw(self._surface, (offset[0] * self.scale, offset[1] * self.scale))
            pygame.display.flip()
            return
        surface.fill((0, 0, 0))
        scaled = pygame.transform.scale(
            self._surface,
            (self._surface.get_width() * self.scale, self._surface.get_height() * self.scale),
        )
        surface.blit(scaled, (offset[0] * self.scale, offset[1] * self.scale))
        pygame.display.flip()

    # -- the keys -----------------------------------------------------------
    def key(self, name: str, event=None, text: str = "") -> bool:
        """Hand a key to the top screen. Returns whether it was used."""
        if not name:
            return False
        if self._glass_key(name):
            return True
        screen = self.screens[-1]
        used = screen.key(name, event or KeyPress(text=text), self)
        self.redraw()
        return bool(used)

    def _glass_key(self, name: str) -> bool:
        """The four keys that belong to the glass and not to a screen.

        The same four the Qt build answers, under the same names, because a key
        that turns the scanlines off should do it in either front end. The
        settings are written down as they change, so the choice survives the
        window.
        """
        import pygame

        if name == "f11":
            pygame.display.toggle_fullscreen()
            return True
        turned = {
            "f2": "scanlines",
            "f3": "bloom",
            "f4": "geometry",
        }.get(name)
        if turned is None:
            return False
        setattr(self.crt, turned, not getattr(self.crt, turned))
        self._remember_glass()
        return True

    def _remember_glass(self) -> None:
        from ..desktop.settings import save_settings

        save_settings(
            {
                "scanlines": self.crt.scanlines,
                "bloom": self.crt.bloom,
                "geometry": self.crt.geometry,
            }
        )

    def open_window(self, *, title: str = "Neverdead's Revenge") -> None:
        """A real window, and the loop that feeds it.

        Not used by the tests, which drive ``key`` and ``redraw`` directly: the
        loop is the part that cannot be tested headless, and it is deliberately
        the smallest part of this file.
        """
        import pygame

        size = (
            self.cols * self.font.cell_w * self.scale,
            self.rows * self.font.cell_h * self.scale,
        )
        if self.crt.scanlines or self.crt.bloom or self.crt.geometry:
            # A GL window, and the glass in it. Any of this failing -- no driver,
            # no context, a profile that will not take the shader -- is a plain
            # window and no CRT: the game goes on either way.
            try:
                import moderngl

                pygame.display.gl_set_attribute(
                    pygame.GL_CONTEXT_MAJOR_VERSION, 2
                )
                pygame.display.gl_set_attribute(
                    pygame.GL_CONTEXT_MINOR_VERSION, 1
                )
                self._window = pygame.display.set_mode(
                    size, pygame.OPENGL | pygame.DOUBLEBUF
                )
                self.redraw()
                from .glass import SdlGlass

                self.glass = SdlGlass(
                    self.crt,
                    (self._surface.get_width(), self._surface.get_height()),
                    size,
                    context=moderngl.create_context(),
                )
            except Exception:
                self.glass = None
                self._window = pygame.display.set_mode(size)
        else:
            self._window = pygame.display.set_mode(size)
        pygame.display.set_caption(title)
        self.redraw()
        clock = pygame.time.Clock()
        self._running = True
        while self._running:
            # Every beat in this game is written against a thirtieth of a second,
            # so that is the frame this loop asks for: a fight that played faster
            # on a quicker machine would be a different fight.
            self.tick(min(clock.tick(60) / 1000.0, 1 / 30.0))
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self.key(name_of(event), KeyPress(event, typed(event)), typed(event))
                elif event.type == pygame.VIDEORESIZE:
                    self.redraw()
