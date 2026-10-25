"""AppStack: one part of the SDL application."""

from __future__ import annotations

import os
import random


from .app_shared import (
    dress_the_echo,
)


class AppStack:
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
        self.pad.forget()

    def pop(self) -> None:
        if len(self.screens) > 1:
            self.screens.pop()
        self._forget_presses()
        self.pad.forget()

    def swap(self, screen) -> None:
        self.screens[-1:] = [screen]
        self._forget_presses()
        self.pad.forget()

    def return_to_title(self) -> None:
        from ..desktop.screens.title import TitleScreen

        self.screens = [TitleScreen()]
        self._forget_presses()
        self.pad.forget()

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
        enemies = encounter_around(self.run, trigger)
        # THE ONE WHO DID NOT COME BACK. The chronicle's best run puts its name
        # on the echo and fights with the numbers it got furthest with: a hero's
        # record is the only thing in this dungeon that has ever beaten him.
        dress_the_echo(enemies, getattr(self.progress, "scores", ()))
        battle = Battle(self.run, enemies)
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
        from ..desktop.render import FIELD_ZOOM

        return screen_point(
            self.run,
            position,
            self.cols,
            self.rows,
            self.font.cell_w,
            self.font.cell_h,
            zoom=FIELD_ZOOM if self.field_zoom else 1,
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
        self.redraw()

    def open_shop(self) -> None:
        """The shop: the same screen the Qt build pushes, on this stack."""
        from ..desktop.screens.menus import ShopScreen

        self.push(ShopScreen())

    def open_scoreboard(self) -> None:
        from ..desktop.screens.menus import ScoreboardScreen

        self.push(ScoreboardScreen())

    def run_cheat(self) -> None:
        """The word typed on the title: the purse and the whole book at once.

        The same grant as ``--testrun``, through the same function, so a cheat
        and a flag that both claim "everything" cannot disagree about what that
        is. Saved at once -- a cheat that has to be typed again after a crash is
        a cheat with a chore attached.
        """
        from ..persistence import unlock_everything

        unlock_everything(self.progress)
        self.save_progress()
        self.play("secret_found")
        self._note_glass("CHEAT: 9999 coin, every page")

    def open_almanac(self, tab: int = 0) -> None:
        """The book, opened at the half the question belongs to.

        The chronicle by default; a fight opens the bestiary, because there the
        question is always "what does *this* do to me".
        """
        from ..desktop.screens.almanac import AlmanacScreen

        self.push(AlmanacScreen(tab=tab))

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

        gear = state.player.equipment

        def key(slot: str) -> str:
            item = gear.get(slot)
            return item.item_id if item is not None else ""

        self.progress.record_run(
            depth=state.depth,
            score=state.score,
            kills=state.kills,
            gold=state.gold_kept,
            won=state.run_state is RunState.ESCAPED,
            name=name,
            hero=state.hero.key,
            # What the run was carrying: the echo wears it.
            weapon=key("weapon"),
            armour=key("armour"),
            daily=state.daily,
        )
        if state.daily:
            # The day is answered when the run is written down, not when it is
            # started: a player who closes the window has not spent it.
            self.progress.daily_date = state.daily
        from ..game.feats import award

        award(self.progress, state)
        self.progress.reroll_shelves(Rng(random.SystemRandom().randrange(2**32)))
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
                before = set(self.progress.feats)
                if state is not None:
                    self.record_run(state, name or "???")
                new = [key for key in self.progress.feats if key not in before]
                if new:
                    from ..game.feats import FEAT_BY_KEY
                    from ..desktop.screens.dialogs import InfoScreen

                    text = "\n\n".join(
                        f"{FEAT_BY_KEY[key].name}\n{FEAT_BY_KEY[key].blurb}"
                        for key in new
                    )
                    self.push(
                        InfoScreen(
                            "A FEAT",
                            "The house remembers.",
                            text,
                            on_done=lambda _value=None: self.return_to_title(),
                        )
                    )
                    return
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

    def open_hero_select(
        self, *, tenth_door: bool = False, daily_mode: bool = False
    ) -> None:
        from ..desktop.screens.hero_select import HeroSelectScreen

        self.push(
            HeroSelectScreen(tenth_door=tenth_door, daily_mode=daily_mode)
        )

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

    def begin_run(
        self,
        hero_key: str,
        *,
        tenth_door: bool = False,
        daily_mode: bool = False,
    ) -> None:
        from ..desktop.screens.game import GameScreen

        if not self.prologue_seen:
            # The premise, told once, between the choice and the floor. A held
            # enter lets it go; escape skips it; and every run after the first
            # starts without it being repeated.
            self.prologue_seen = True
            from ..desktop.screens.prologue import PrologueScreen

            self.push(
                PrologueScreen(
                    on_done=lambda: self.begin_run(
                        hero_key,
                        tenth_door=tenth_door,
                        daily_mode=daily_mode,
                    )
                )
            )
            return
        from ..game import daily as daily_rules
        from ..game.actors import HEROES
        from ..game.lore import PAGE_COUNT
        from ..game.shop import loadout_from
        from ..game.state import DOOR_EVERY, start_run

        loadout = loadout_from(self.progress)
        day = daily_rules.today() if daily_mode else ""
        seed = (
            daily_rules.seed_for(day) if daily_mode else self._a_seed()
        )
        self.save_progress()
        self.run = start_run(
            HEROES[hero_key],
            seed,
            loadout=loadout,
            # The pages this book is still missing, so a run knows what is out
            # there -- the same tuple the Qt build hands over.
            pages=tuple(
                number
                for number in range(1, PAGE_COUNT + 1)
                if number not in self.progress.pages
            ),
            tenth_door=tenth_door,
            start_depth=DOOR_EVERY if tenth_door else 1,
            daily=day,
        )
        self.effects.clear()
        self.screens = [GameScreen(self.run)]
        self.redraw()

    def continue_run(self) -> None:
        """Pick a saved run back up -- and let go of the file once it is open.

        The same shape as the Qt build's, and for the same reason: a run that is
        being played lives in memory, and a copy left lying on disk would be the
        run the player *had* the next time they sat down. A save this build cannot
        read -- written by another version, or half written when the machine went
        down -- is set aside rather than thrown: the slot opens empty, and the
        file is still there to be looked at.
        """
        from ..desktop.screens.game import GameScreen
        from ..game.savegame import load
        from ..persistence import clear_run, load_run, run_path

        payload = load_run()
        if not payload:
            return
        try:
            state = load(payload)
        except Exception:
            # A loader that fails is a bug until proven otherwise, and deleting
            # the run would hide it. The slot is emptied; the file is kept.
            path = run_path()
            try:
                os.replace(path, path.with_name(path.name + ".bak"))
            except OSError:
                clear_run()
            return
        clear_run()
        self.run = state
        self.screens = [GameScreen(state)]
        self.redraw()

    def _open_run_log(self):
        """The last launch, in a file beside the save.

        A game started by a launcher has no terminal: Steam keeps the output to
        itself, and a flag in a shortcut is one more thing that can be left out.
        So every launch writes the same short record -- build, display server,
        grid, glass, and what the launcher put in front of it -- and a launcher's
        first seconds of frame reports. Truncated each time: this run, not a pile.
        """
        from ..persistence import data_dir

        try:
            path = data_dir() / "run.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            return path.open("w", encoding="utf-8")
        except OSError:
            return None
