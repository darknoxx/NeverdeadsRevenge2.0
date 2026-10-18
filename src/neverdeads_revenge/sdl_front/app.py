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
import time
from pathlib import Path

from ..persistence import load_meta
from ..desktop.theme import BACKGROUND, Colour
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
#: smaller game but a broken one. (These said 76 for a while, which is a *different*
#: number from the one the Qt build derives its grid with -- so the same window had
#: two answers about how many cells fit.)
MIN_COLS = 80
MIN_ROWS = 24

#: How wide the grid wants to be on a big screen. The scale is chosen to land near
#: this, and then the leftover room becomes *cells* rather than black bars -- which
#: is the whole difference between a 1440p monitor full of dungeon and one with a
#: couple of hundred pixels of nothing on every side.
TARGET_COLS = 110


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
        fps: bool = False,
        timings: bool = False,
        backdrop: bool = True,
    ) -> None:
        import pygame

        pygame.init()
        # The screens decide what a *held* key means -- the floor walks on one, a
        # shelf scrolls on one, and everything else refuses the repeats -- but SDL
        # does not make any unless it is asked, so holding a direction did nothing
        # at all. Delay and interval are the terminal's own feel: a pause long
        # enough that a tap is a tap, then the key's own pace.
        pygame.key.set_repeat(400, 60)
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
        #: A frame counter, for the flag that asks for one. Smoothed, because a
        #: number that jitters by ten a frame tells you nothing.
        self.show_fps = fps
        #: And where the frame's milliseconds go, for the other flag. Printed once
        #: a second and never drawn: a breakdown is a thing to read in a terminal,
        #: not a thing to put in the picture.
        self.show_timings = timings
        self._timing: dict[str, tuple[float, int]] = {}
        self._timing_since = time.monotonic()
        #: The grid, made once and cleared from then on. It is *this* app's, so it
        #: is made here rather than on the first frame -- a screen is handed a
        #: blank grid and never has to ask whose turn it is.
        from ..desktop.pattern import PatternBuffer

        self.grid = PatternBuffer(cols, rows, self.font)
        #: Whether the arena is one painted room or the game's own tiles. The
        #: reference build has no painting, so this is a dial for looking at art.
        self.backdrop = backdrop
        self.frames = 0.0
        self.seed = seed
        self.run = None
        #: The premise, told once between the choice and the floor -- the same
        #: once-per-session the Qt build means, and the same screen. It needs a
        #: key *release* to tell a tap from a hold, which is why this waited for
        #: one: see ``feed``.
        self.prologue_seen = False
        #: What a glass key just did, for as long as it takes to read.
        self.glass_note: tuple[str, float] | None = None
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
        #: And the music, which is a bed and not a voice: one mute for the whole
        #: game, its own stream at the rate the loop was written at.
        from ..desktop.music import Music

        self.music = Music(muted=self.sfx.muted)
        #: And when it gives up mid-session, the record has to agree -- or the
        #: next toggle writes the give-up back down as "unmuted".
        self.sfx.on_mute = self._sound_gave_up
        #: What the game asked to be heard. A front end with no sound is still a
        #: front end that was asked, and a test can read this.
        self.played: list[str] = []
        self.headline = headline
        self._window = None
        self._surface = None
        self._last_frame: float | None = None
        #: Whether the window is the whole screen, and where the picture sits in
        #: whatever size the window has now. Both move on F11 and on a resize.
        self._fullscreen = False
        #: Keys that are *down* right now, and the ones that were already down
        #: when the screen on top changed. A held key repeats thirty times a
        #: second, and a new screen must not be answered by a press that happened
        #: before it existed -- holding enter to start used to run straight
        #: through the name entry behind the death screen.
        self._down: set[str] = set()
        self._stale: set[str] = set()
        self._shown = self._buffer_size()
        self._shown_at = (0, 0)
        self._title = "Neverdead's Revenge"
        #: Whether the window loop should keep going. Only ``quit`` clears it --
        #: there is no window object to ask on this front end.
        self._running = True
        if battle_scene:
            self.open_battle_scene()

    # -- the stack ---------------------------------------------------------
    def _forget_presses(self) -> None:
        """A new screen has to be told the key is already down, and not by a press.

        The houses rule in this game is that a screen answers a *press*: a key
        held from the screen before this one must not choose anything here. Holds
        keep their repeats -- they live on them -- but the first press on a new
        screen has to be a fresh one.
        """
        self._stale |= self._down

    def push(self, screen) -> None:
        self.screens.append(screen)
        self._forget_presses()

    def pop(self) -> None:
        if len(self.screens) > 1:
            self.screens.pop()
        self._forget_presses()

    def swap(self, screen) -> None:
        self.screens[-1:] = [screen]
        self._forget_presses()

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
            self.play("door_creak")
            return
        if run.level != before_level:
            self.play("level_up")
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

        self.music.stop()
        self.play("quest_complete" if won else "death_game_over")
        self.push(
            GameOverScreen(
                state=self.run,
                won=won,
                best=max(self.progress.best_score, self.run.score),
                can_rewind=self.run.rewind_ready and not won,
                on_done=lambda answer: self.after_summary(answer),
            )
        )

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

        self.swap(SdlArena(battle, backdrop=self.backdrop))

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
        """Where a cell is, in the frame's own pixels -- or ``None``.

        The grid is the *camera* and not the dungeon, so this is the game's own
        translation and not a multiplication: a square at ``(38, 9)`` is somewhere
        else on the screen unless the camera happens to say so. Everything that
        skipped it drew in the wrong place, which is exactly what happened to the
        coins here -- sprayed over a wall while the hero picked them up on the
        other side of it.
        """
        from ..desktop.render import screen_point

        if self.run is None:
            return None
        return screen_point(
            self.run,
            position,
            self.cols,
            self.rows,
            self.font.cell_w,
            self.font.cell_h,
        )

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
            self.run = start_run(HEROES["noxx"], self._a_seed())
        self.screens = [
            SdlArena(Battle(self.run, self.run.enemies[:3]), backdrop=self.backdrop)
        ]
        # The dev door opens *into* the game, so the music belongs here too.
        self.music.start()
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
        """The audio session quit on its own; the record has to agree.

        The music is *not* told, on purpose: it has its own stream and its own
        device, and a machine where the effects cannot open a player may still
        have one for the loop -- or the other way round. Each of them gives up
        on its own, which is the promise audio here always makes.
        """
        self.progress.muted = muted
        self.save_progress()

    def toggle_sound(self) -> None:
        """Turn the sound over, and write the answer down: a player who mutes a
        game expects it to *stay* muted the next time they open it."""
        self.sfx.toggle()
        self.music.set_muted(self.sfx.muted)
        self.progress.muted = self.sfx.muted
        self.save_progress()

    def open_hero_select(self) -> None:
        from ..desktop.screens.hero_select import HeroSelectScreen

        self.push(HeroSelectScreen())

    def _a_seed(self) -> int:
        """The seed for the run about to begin.

        Fresh per run -- *not* stored: keeping the roll would make every NEW RUN
        in one session the same dungeon wearing yesterday's clothes, which is the
        bug the Qt build has a comment about. A seed the player pinned with
        ``--seed`` is the exception, and ``is None`` and not a truth test,
        because seed 0 is a seed.
        """
        if self.seed is not None:
            return self.seed
        return random.SystemRandom().randrange(2**32)

    def begin_run(self, hero_key: str) -> None:
        from ..desktop.screens.game import GameScreen

        if not self.prologue_seen:
            # The premise, told once, between the choice and the floor. A held
            # enter lets it go; escape skips it; and every run after the first
            # starts without it being repeated.
            self.prologue_seen = True
            from ..desktop.screens.prologue import PrologueScreen

            self.push(PrologueScreen(on_done=lambda: self.begin_run(hero_key)))
            return
        from ..game.actors import HEROES
        from ..game.lore import PAGE_COUNT
        from ..game.shop import loadout_from
        from ..game.state import start_run

        loadout = loadout_from(self.progress)
        self.save_progress()
        self.run = start_run(
            HEROES[hero_key],
            self._a_seed(),
            loadout=loadout,
            # The pages this book is still missing, so a run knows what is out
            # there -- the same tuple the Qt build hands over.
            pages=tuple(
                number
                for number in range(1, PAGE_COUNT + 1)
                if number not in self.progress.pages
            ),
        )
        self.effects.clear()
        self.screens = [GameScreen(self.run)]
        self.music.start()
        self.redraw()

    def continue_run(self) -> None:
        """Pick a saved run back up -- and let go of the file once it is open.

        The same shape as the Qt build's, and for the same reason: a run that is
        being played lives in memory, and a copy left lying on disk would be the
        run the player *had* the next time they sat down. A save this build cannot
        read -- written by another version, or half written when the machine went
        down -- is thrown away rather than thrown, because a dungeon that will not
        open is not a crash, it is an empty slot.
        """
        from ..desktop.screens.game import GameScreen
        from ..game.savegame import load
        from ..persistence import clear_run, load_run

        payload = load_run()
        if not payload:
            return
        try:
            state = load(payload)
        except Exception:
            clear_run()
            return
        clear_run()
        self.run = state
        self.screens = [GameScreen(state)]
        self.music.start()
        self.redraw()

    # -- the picture --------------------------------------------------------
    def feed(self, event) -> None:
        """Hand one event from the window to the game: all the loop does.

        Its own method, and not three lines inside the loop, because this is the
        only place where a *real* key press is turned into what a screen answers
        -- and that is exactly the seam a test could not reach while it lived in
        a `while` that never returns. It was wrong there for a while: the event
        object itself was passed where a bool belonged, so every key looked like
        an auto-repeat, and the menus -- which answer one press and not thirty a
        second -- swallowed the lot.
        """
        import pygame

        if event.type == pygame.QUIT:
            self.quit()
        elif event.type == pygame.KEYDOWN:
            text = typed(event)
            name = name_of(event)
            if name is not None and name in self._stale:
                # Down before this screen existed: it has to come up and be
                # pressed again before anything here hears it.
                return
            if name is not None:
                self._down.add(name)
            self.key(
                name_of(event),
                # ``repeat`` and not the event: the screens ask whether the key
                # is being *held*, and anything truthy answers yes.
                KeyPress(bool(getattr(event, "repeat", False)), text),
                text,
            )
        elif event.type == pygame.KEYUP:
            # Which half of a hold: a screen that runs a hold bar has to be told
            # when the key comes *up*, or a tap banks itself and a screen walked
            # through on a press nobody held. Not every platform pairs its
            # repeats with a release; this one does, so it is passed on.
            name = name_of(event)
            if name is not None:
                self._down.discard(name)
                self._stale.discard(name)
            screen = self.screens[-1]
            if name and screen.key_up(name, KeyPress(False, typed(event)), self):
                self.redraw()
        elif event.type == pygame.VIDEORESIZE:
            # The window manager's answer, not ours: the picture is fitted to
            # whatever it says, and the glass hears about it.
            self._fit()
            self.redraw()

    def tick(self, dt: float) -> None:
        """A frame went by: let the screen play, let the pixels move, repaint.

        Called by the window loop and by anything driving this headless. A screen
        that is *moving* is asked every frame -- a fight breathes whether or not it
        is talking, and this is the only clock the second front end has -- and one
        that is busy is asked until it is done.
        """
        now = time.monotonic()
        if self._last_frame is not None:
            # Measured here and not from ``dt``: the loop clamps its step to a
            # thirtieth of a second so the *game* keeps its pace, and a counter
            # reading that would report thirty forever.
            gap = max(1e-4, now - self._last_frame)
            self.frames = (self.frames * 9.0 + (1.0 / gap)) / 10.0
        self._last_frame = now
        screen = self.screens[-1]
        if getattr(screen, "busy", False) or getattr(screen, "animating", False):
            screen.step(dt, self)
        self.effects.step(dt)
        self.redraw()
        self._report_timings(time.monotonic())

    def redraw(self) -> None:
        """Draw the stack into the grid, and the grid onto the window."""
        from ..desktop.pattern import PatternBuffer

        # The grid is reused and cleared rather than rebuilt. A frame of this game
        # is two thousand six hundred cells, and a fresh buffer every frame was two
        # thousand six hundred cells and their styles made again to hold the same
        # blanks. The *shape* can change -- the window moves, and the grid is
        # derived from it -- so the shape is what is checked.
        if (self.grid.cols, self.grid.rows) != (self.cols, self.rows):
            self.grid = PatternBuffer(self.cols, self.rows, self.font)
        else:
            self.grid.font = self.font
            self.grid.clear()
        mark = time.perf_counter() if self.show_timings else 0.0
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
        mark = self._note("cells", mark)
        # A screen may bring its own paper: the arena's painted room goes *under*
        # the cells, so the panels, the log and the sidebar sit on it instead of
        # on a black field beside it.
        base = BACKGROUND
        paper = getattr(self.screens[-1], "paper", None)
        if paper is not None:
            # A screen with no painting to show answers None, and flat paper is
            # what the frame wanted all along.
            base = paper(self.cols, self.rows, self.font) or BACKGROUND
        self._surface = paint(self.grid, self.font, base)
        mark = self._note("paint", mark)
        self._small_face()
        # And a screen may paint straight onto the frame once the grid is drawn:
        # that is where the art lives -- sprites do not fit in a character cell.
        # It is called `paint_over` and not `paste`, which is Qt's name for the
        # same pass, because the Qt screens in this same stack have a `paste` too
        # and it wants a QImage: one name for two media is one crash waiting.
        paint_over = getattr(self.screens[-1], "paint_over", None)
        if paint_over is not None:
            paint_over(self._surface, self)
        mark = self._note("art", mark)
        self._blit_art()
        # And the pixels that are not the room: sparks thrown by whatever just
        # happened, drawn last so they land on top of everything.
        self.effects.draw(self._surface)
        self._draw_note()
        if self.show_fps:
            self._draw_fps()
        self._present()
        self._note("present", mark)

    def _note(self, name: str, mark: float) -> float:
        """Book the milliseconds since ``mark`` under ``name``, and pass it on.

        Nothing but two clock reads when ``--timings`` was not asked for, which is
        why it can stand in the middle of the frame at all.
        """
        if not self.show_timings:
            return mark
        now = time.perf_counter()
        spent, frames = self._timing.get(name, (0.0, 0))
        self._timing[name] = (spent + (now - mark), frames + 1)
        return now

    def _report_timings(self, now: float) -> None:
        """Once a second: what each stage of the frame cost, in milliseconds."""
        if not self.show_timings or now - self._timing_since < 1.0:
            return
        self._timing_since = now
        if not self._timing:
            return
        # Milliseconds per stage, from seconds spent -- and per *frame*, so a
        # second of running and a second of standing still read the same.
        parts = "  ".join(
            f"{name} {spent / frames * 1000.0:.2f}"
            for name, (spent, frames) in self._timing.items()
            if frames
        )
        done = sum(
            spent / frames * 1000.0 for spent, frames in self._timing.values() if frames
        )
        print(f"{self.frames:5.1f} fps   {parts}   ({done:.2f} ms drawn)")
        self._timing.clear()

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

    def _draw_fps(self) -> None:
        """How fast this is going, in the corner, when ``--fps`` asked for it.

        Bottom right, on its own dark patch so it can be read over a sidebar: it
        is a developer's number and not part of the fiction, so it is allowed to
        sit on top of one.
        """
        import pygame

        from ..desktop.theme import BACKGROUND

        text = f"{self.frames:4.1f} fps"
        face = self.font_small
        width = len(text) * face.cell_w + 6
        height = face.cell_h + 4
        left = max(0, self._surface.get_width() - width)
        top = max(0, self._surface.get_height() - height)
        self._surface.fill(tuple(BACKGROUND), pygame.Rect(left, top, width, height))
        for index, char in enumerate(text):
            glyph = face.glyph(char, Colour(0xC8, 0xC8, 0xC8))
            if glyph is not None:
                self._surface.blit(
                    glyph, (left + 3 + index * face.cell_w, top + 2)
                )

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

    def _max_scale(self, width: int, height: int) -> int:
        """The largest whole-number scale that still leaves a playable grid."""
        return max(
            1,
            min(
                width // (MIN_COLS * self.font.cell_w),
                height // (MIN_ROWS * self.font.cell_h),
            ),
        )

    def _scale_for(self, width: int, height: int) -> int:
        """The one scale: the biggest that lands the grid near the target width."""
        ceiling = self._max_scale(width, height)
        target = max(1, round(width / (TARGET_COLS * self.font.cell_w)))
        return max(1, min(target, ceiling))

    def _grid_size(self, width: int, height: int) -> tuple[int, int]:
        """How many cells fit in a window of this size, at that scale.

        The Qt build's rule, number for number, because it is the rule the game's
        panels were laid out for -- and because a second front end with its own
        idea of how much room there is would draw a different game at the same
        size. At 960x540 it comes out at the 96x27 both front ends start with;
        at 2560x1440 it comes out at 128x36, which is a full screen and no bars.
        """
        scale = self._scale_for(width, height)
        cols = max(MIN_COLS, width // (self.font.cell_w * scale))
        rows = max(MIN_ROWS, height // (self.font.cell_h * scale))
        return cols, rows

    @property
    def cells(self) -> tuple[int, int]:
        """How big the frame is, in cells -- the same question the Qt app answers.

        A fixed grid here (the window scales, the grid does not), which is why
        this is two numbers and not a computation.
        """
        return (self.cols, self.rows)

    def _buffer_size(self) -> tuple[int, int]:
        """The picture's own size, in pixels: a cell is ten by twenty, always."""
        return (self.cols * self.font.cell_w, self.rows * self.font.cell_h)

    def _open_window(self) -> None:
        """Make the window, once, before the loop starts.

        The GL attributes have to be set *before* the display exists -- pygame
        refuses them afterwards -- so the whole of the window's creation is here
        and a full screen toggle never comes back through it. Any of this
        failing -- no driver, no context, a profile that will not take the shader
        -- is a plain window and no CRT: the game goes on either way.
        """
        import pygame

        base = self._buffer_size()
        size = (base[0] * self.scale, base[1] * self.scale)
        if self.crt.scanlines or self.crt.bloom or self.crt.geometry:
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
                from .glass import SdlGlass

                self.glass = SdlGlass(
                    self.crt,
                    base,
                    self._window.get_size(),
                    context=moderngl.create_context(),
                )
                self._fit()
                return
            except Exception:
                self.glass = None
        self._window = pygame.display.set_mode(size)
        self._fit()

    def _toggle_fullscreen(self) -> None:
        """F11: the window's own full screen, then the fit and the viewport.

        Not ``set_mode`` again, which is what this did first: that makes a *new*
        GL context, and the shader program -- with every texture in it -- belongs
        to the old one, so the object that was dropped took the process with it.
        SDL's own toggle keeps the window and its context alive. What it does
        *not* do is move the GL viewport or re-fit the picture, and that is the
        whole of what went wrong: the game stayed in the bottom left corner --
        the viewport's origin -- with the rest of the screen black.
        """
        import pygame

        self._fullscreen = not self._fullscreen
        if self.glass is not None:
            # SDL's own toggle keeps the window *and its context*: a `set_mode`
            # here would make a new context and leave the shader program behind
            # in the old one. What SDL does not do is move the GL viewport or
            # tell the shader that the window changed -- which is the whole of
            # what went wrong.
            pygame.display.toggle_fullscreen()
        else:
            # No glass: the surface itself is what gets blitted, so full screen
            # means a full-screen surface, and there is no context to lose.
            base = self._buffer_size()
            if self._fullscreen:
                size = pygame.display.get_desktop_sizes()[0]
                self._window = pygame.display.set_mode(size, pygame.FULLSCREEN)
            else:
                self._window = pygame.display.set_mode(
                    (base[0] * self.scale, base[1] * self.scale)
                )
        self._fit()

    def _fit(self) -> None:
        """How big the picture is on this window, and where it sits.

        Reckoned from the window's *current* size and not from the one that was
        asked for: full screen is a different window, and the whole-number scale
        that fits it is a different number. Without this the picture stays in the
        corner it was first drawn in -- the GL viewport's own origin, which is the
        bottom left.
        """
        import pygame

        # The *window's* size and not the surface's, which are two different
        # numbers: pygame keeps the display surface at the size it was made at,
        # so a full-screen window still reports 960x540 and the picture stays
        # that size in the corner of a black screen. The window knows.
        if pygame.display.get_init() and pygame.display.get_surface() is not None:
            width, height = pygame.display.get_window_size()
        elif self._window is not None:
            width, height = self._window.get_size()
        else:
            return
        # The grid comes from the window, the way the Qt build's does: whatever
        # is left over after the biggest whole-number scale becomes *cells* and
        # not black bars.
        cols, rows = self._grid_size(width, height)
        if (cols, rows) != (self.cols, self.rows):
            self.cols, self.rows = cols, rows
            if self.glass is not None:
                self.glass.resize(self._buffer_size())
        buffer_w, buffer_h = self._buffer_size()
        fit = max(1, min(width // buffer_w, height // buffer_h))
        self._shown = (fit * buffer_w, fit * buffer_h)
        self._shown_at = ((width - self._shown[0]) // 2, (height - self._shown[1]) // 2)
        if self.glass is not None:
            self.glass.fit((width, height), fit, self._shown_at)

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
        fit = max(1, self._shown[0] // max(1, self._buffer_size()[0]))
        if self.glass is not None:
            # The glass has the whole picture and the whole window: it is the
            # thing that scales, so the shake goes in as part of its offset.
            self.glass.draw(
                self._surface, (offset[0] * fit, offset[1] * fit)
            )
            pygame.display.flip()
            return
        surface.fill((0, 0, 0))
        scaled = pygame.transform.scale(
            self._surface,
            (self._surface.get_width() * fit, self._surface.get_height() * fit),
        )
        surface.blit(
            scaled,
            (self._shown_at[0] + offset[0] * fit, self._shown_at[1] + offset[1] * fit),
        )
        pygame.display.flip()

    # -- the keys -----------------------------------------------------------
    def key(self, name: str, event=None, text: str = "") -> bool:
        """Hand a key to the top screen. Returns whether it was used."""
        if not name:
            return False
        if self._glass_key(name):
            return True
        screen = self.screens[-1]
        press = event or KeyPress(text=text)
        used = screen.key(name, press, self)
        self._interface_sound(name, bool(used), press)
        self.redraw()
        return bool(used)

    def _interface_sound(self, name: str, used: bool, event) -> None:
        """The click of the interface, from the one place a key is delivered.

        Which sound is the *screen's* to say -- the floor's arrows walk a body
        and a menu's arrows walk a cursor, and only the screen knows which it
        just did. This end knows two things instead, and both of them are about
        *one* press: whether anything wanted it, and whether it was a repeat.

        A repeat is not a second click. Holding a key down is one gesture -- the
        hold-to-continue screens are built on exactly that -- and a click on
        every auto-repeat is a stutter of thirty confirmations for one decision.
        The screens that *are* a hold play their own confirm when the hold
        completes, which is the moment the player made it.
        """
        if not used:
            return
        if getattr(event, "isAutoRepeat", None) is not None and event.isAutoRepeat():
            return
        sound = getattr(self.screens[-1], "key_sound", None)
        if sound is None:
            return
        played = sound(name)
        if played:
            self.play(played)

    def _glass_key(self, name: str) -> bool:
        """The four keys that belong to the glass and not to a screen.

        The same four the Qt build answers, under the same names, because a key
        that turns the scanlines off should do it in either front end. The
        settings are written down as they change, so the choice survives the
        window.
        """
        import pygame

        if name == "f11":
            self._toggle_fullscreen()
            self.redraw()
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
        self._note_glass(
            {
                "scanlines": "SCANLINES",
                "bloom": "BLOOM",
                "geometry": "CRT CURVE",
            }[turned]
            + (" ON" if getattr(self.crt, turned) else " OFF")
        )
        return True

    def _note_glass(self, note: str) -> None:
        """Say what a glass key just did, for as long as it takes to read.

        The Qt build writes its note *into* the pattern buffer before the frame
        is rendered; this one has a picture already, so it goes on the picture --
        same words, same two seconds, same place at the top. A CRT setting that
        changed with no acknowledgement is a key that might not have worked.
        """
        self.glass_note = (note, time.monotonic() + 2.0)

    def _draw_note(self) -> None:
        import pygame

        if self.glass_note is None:
            return
        note, until = self.glass_note
        if time.monotonic() > until:
            self.glass_note = None
            return
        from ..desktop.chrome import BONE
        from ..desktop.theme import parse_style

        face = self.font
        left = max(0, (self._surface.get_width() - len(note) * face.cell_w) // 2)
        band = pygame.Rect(0, 0, self._surface.get_width(), face.cell_h)
        self._surface.fill((0, 0, 0), band)
        colour = parse_style(f"bold {BONE}").fg
        for index, char in enumerate(note):
            glyph = face.glyph(char, colour, bold=True)
            if glyph is not None:
                self._surface.blit(glyph, (left + index * face.cell_w, 0))

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

        self._title = title
        pygame.display.set_caption(title)
        self._open_window()
        self.redraw()
        clock = pygame.time.Clock()
        self._running = True
        while self._running:
            # Every beat in this game is written against a thirtieth of a second,
            # so that is the frame this loop asks for: a fight that played faster
            # on a quicker machine would be a different fight.
            self.tick(min(clock.tick(60) / 1000.0, 1 / 30.0))
            for event in pygame.event.get():
                self.feed(event)
        self.music.close()
        pygame.quit()
