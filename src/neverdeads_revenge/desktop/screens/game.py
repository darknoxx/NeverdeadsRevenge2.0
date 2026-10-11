"""The dungeon screen.

Wraps the run and turns keys into verbs. Everything the domain says is a
*decision* comes back as a prompt, and this is where a prompt becomes a dialog
and an answer becomes a second verb -- the same shape the terminal screen had,
with the dialogs swapped for boxes.
"""

from __future__ import annotations

import time

from neverdeads_revenge.game.actions import (
    Action,
    perform_action,
)
from neverdeads_revenge.game.lore import page
from neverdeads_revenge.game.pace import action_gap
from neverdeads_revenge.game.state import GameState

from ..keys import KEY_BINDINGS
from .base import Screen
from .dialogs import (
    FAME,
    OPEN,
    ChestScreen,
    NpcScreen,
    PageScreen,
    SpringScreen,
)
from .game_over import GameOverScreen, NameEntryScreen

__all__ = ["GameScreen", "REWIND"]

#: The answer that takes the ending back, if there is a borrowed hour in hand.
REWIND = "rewind"


class GameScreen(Screen):
    """The run, drawn and played."""

    def __init__(self, state: GameState) -> None:
        self.state = state
        self._last_move: dict[str, float] = {}

    # -- drawing ------------------------------------------------------------
    def draw(self, buffer, app) -> None:
        from ..render import draw_game

        draw_game(buffer, self.state)

    # -- input --------------------------------------------------------------
    def key(self, name: str, event, app) -> bool:
        if name == "escape":
            from .pause import PauseScreen

            app.push(PauseScreen())
            return True
        if name in ("?", "f1"):
            from .menus import HelpScreen

            app.push(HelpScreen())
            return True
        if name == "c":
            from .menus import CharacterScreen

            app.push(CharacterScreen(self.state))
            return True
        if name == "i":
            from .menus import PackScreen

            app.push(PackScreen(self.state))
            return True

        action = KEY_BINDINGS.get(name)
        if action is None:
            return False

        if action.direction.name != "NONE":
            # A held direction is one gesture; its repeats are allowed, no faster
            # than the hero's own pace.
            if event.isAutoRepeat():
                gap = action_gap(self.state.player.speed)
                if time.monotonic() - self._last_move.get(name, 0.0) < gap:
                    return True
            self._last_move[name] = time.monotonic()
        elif event.isAutoRepeat():
            return True  # every other verb is a fresh press

        self._do(action, app)
        return True

    # -- the verbs ----------------------------------------------------------
    def _do(self, action: Action, app) -> None:
        run = self.state
        before = (len(run.log), run.depth, run.level)
        hp = run.player.hp
        gold = run.gold
        gifts = set(run.gifts)
        curses = len(run.curses)

        result = perform_action(run, action)
        app.play_after(before)
        self._effects(app, hp, gold, gifts, curses, before[2])
        self._file_pages(app)

        if result.prompt is not None:
            self._ask(result, app)
            return
        if result.died or result.escaped:
            self._game_over(app, won=result.escaped)

    def _effects(self, app, hp, gold, gifts, curses, level_before) -> None:
        """The moving pixels: what just happened, thrown at the screen.

        Read off the differences and off ``state.deaths``, which the domain
        fills with the exact square a thing stopped moving on. Everything a rule
        grants or a wound takes is a difference the run notices on its own, so
        no hook into the domain is needed.
        """
        run = self.state
        fx = app.effects
        for position in run.deaths:
            fx.blood(position)
        if run.player.hp < hp:
            fx.blood(run.player.position, count=8)
            app.view.shake()
            if run.over:
                app.view.shake(strength=10, seconds=0.4)
        if run.gold > gold:
            fx.coin(run.player.position)
        if run.level > level_before:
            fx.spark(run.player.position, "bright_white", count=20)
        if run.gifts - gifts:
            fx.spark(run.player.position, "bright_green", count=28)
        if len(run.curses) > curses:
            fx.spark(run.player.position, "#c81e1e", count=16)

    def _ask(self, result, app) -> None:
        if result.prompt_kind == "spring":
            app.push(SpringScreen(result.prompt, lambda v: self._spring(app, v)))
        elif result.prompt_kind == "npc":
            app.push(NpcScreen(result.speaker, result.prompt))
        else:
            app.push(ChestScreen(result.prompt, lambda v: self._chest(app, v)))

    def _spring(self, app, wash_it) -> None:
        if not wash_it:
            return
        result = perform_action(self.state, Action.CLEANSE)
        app.play_after((len(self.state.log), self.state.depth, self.state.level))
        if result.died or result.escaped:
            self._game_over(app, won=result.escaped)

    def _chest(self, app, answer) -> None:
        if not answer:
            return
        app.play("chest")
        action = Action.OPEN_CHEST if answer == OPEN else Action.TAKE_FAME
        result = perform_action(self.state, action)
        app.play_after((len(self.state.log), self.state.depth, self.state.level))
        if result.died or result.escaped:
            self._game_over(app, won=result.escaped)

    def _file_pages(self, app) -> None:
        """Bank a found page at once, and open it.

        A page is knowledge, so it goes into the book the moment it is picked up
        -- and it opens, because prose in the log scrolls away in four turns.
        """
        for number in self.state.found_pages:
            if not app.progress.record_page(number):
                continue
            app.play("item")
            app.save_progress()
            text = page(number)
            if text is not None:
                app.push(PageScreen(number, text))

    # -- the end ------------------------------------------------------------
    def _game_over(self, app, won: bool = False) -> None:
        state = self.state
        app.play("victory" if won else "death")
        best = max(app.progress.best_score, state.score)
        app.push(
            GameOverScreen(
                state=state,
                won=won,
                best=best,
                can_rewind=state.rewind_ready and not won,
                on_done=lambda answer: self._after_summary(app, answer),
            )
        )

    def _after_summary(self, app, answer) -> None:
        if answer != REWIND:
            app.push(
                NameEntryScreen(
                    self.state.score,
                    app.progress.last_name,
                    on_done=lambda name: self._record(app, name),
                )
            )
            return
        perform_action(self.state, Action.REWIND)
        app.redraw()

    def _record(self, app, name: str) -> None:
        app.record_run(self.state, name or "???")
        app.return_to_title()
