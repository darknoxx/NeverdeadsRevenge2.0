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

#: Which sound each hero's ultimate makes. Kept here rather than in the audio
#: layer because it is a casting decision -- the sound module only knows how
#: to play a name.
ULTIMATE_SOUND: dict[str, str] = {
    "noxx": "void",
    "yeti": "ice",
    "walkyrion": "bell",
}

__all__ = ["GameScreen", "REWIND"]

#: The answer that takes the ending back, if there is a borrowed hour in hand.
REWIND = "rewind"


class GameScreen(Screen):
    """The run, drawn and played.

    ``smaller_face`` says the frame this screen owns wants the log and the
    legend pasted on afterwards in their own smaller face -- see
    :meth:`DesktopApp.redraw`.
    """

    smaller_face = True

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
        if name == "l":
            from .menus import LegendScreen

            app.push(LegendScreen(self.state))
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
        curse_keys = {curse.key for curse in run.curses}
        equipment = dict(run.player.equipment)
        ultimate_ready = run.ultimate_available

        result = perform_action(run, action)
        if action is Action.ULTIMATE and ultimate_ready and not run.ultimate_available:
            # The dark answers with its own note, not the log's second reading
            # -- and its own note per hero, because the three asks sound like
            # three different things.
            app.play(ULTIMATE_SOUND.get(run.hero.key, "void"))
        app.play_after(before)
        self._effects(app, hp, gold, gifts, curses, before[2])
        self._file_pages(app)

        if result.prompt is not None:
            self._ask(result, app)
            return
        if result.died or result.escaped:
            self._game_over(app, won=result.escaped)
            return
        self._announce(
            app,
            gifts,
            curse_keys,
            equipment,
        )

    def _announce(self, app, gifts_before, curse_keys_before, equipment_before) -> None:
        """Read out what just arrived: the pickup dialog.

        The log scrolls in four turns and the sidebar is decoration, so a thing
        whose shape is its own price gets a page: a blade picked up says what
        it is and what it does, a curse says its sentence, a gift says its
        rule. Old enders are skipped -- there is no more dark left to yell
        into once the run is over.
        """
        from neverdeads_revenge.game.gifts import gift_by_key
        from neverdeads_revenge.game.shop import describe_item
        from neverdeads_revenge.world.items import ITEMS

        from .dialogs import InfoScreen

        run = self.state
        for key in sorted(run.gifts - gifts_before):
            gift = gift_by_key(key)
            if gift is not None:
                app.push(InfoScreen("A GIFT", gift.name, gift.blurb))
        for curse in run.curses:
            if curse.key in curse_keys_before:
                continue
            # The curse's own price is the sentence the chest dialog reads;
            # the modifier list is the fine print where one exists.
            text = curse.price
            extra = ", ".join(curse.modifiers.describe())
            if extra:
                text = f"{text}. {extra}."
            app.push(InfoScreen("A CURSE", curse.name, text))
        for slot, item in run.player.equipment.items():
            worn = equipment_before.get(slot)
            if worn is not None and worn.item_id == item.item_id:
                continue
            template = ITEMS.get(item.item_id)
            if template is None:
                continue
            article = "AN" if template.kind in ("armour", "amulet") else "A"
            app.push(
                InfoScreen(
                    f"{article} {template.kind.upper()}",
                    item.name,
                    describe_item(template),
                )
            )

    def _effects(self, app, hp, gold, gifts, curses, level_before) -> None:
        """The moving pixels: what just happened, thrown at the screen.

        Read off the differences and off ``state.deaths``, which the domain
        fills with the exact square a thing stopped moving on. Every square is
        then translated through the camera, because the buffer is not the
        dungeon -- a player at (38, 9) is drawn wherever the camera says, and a
        particle that skipped that step drew in the wrong place, every time.
        """
        run = self.state
        fx = app.effects

        for position in run.deaths:
            point = app.screen_point(position)
            if point is not None:
                fx.blood(point)

        here = app.screen_point(run.player.position)
        if here is None:
            return
        if run.player.hp < hp:
            fx.blood(here, count=8)
            app.view.shake()
            if run.over:
                app.view.shake(strength=10, seconds=0.4)
        if run.gold > gold:
            fx.coin(here)
        if run.level > level_before:
            fx.spark(here, "bright_white", count=20)
        if run.gifts - gifts:
            fx.spark(here, "bright_green", count=28)
        if len(run.curses) > curses:
            fx.spark(here, "#c81e1e", count=16)

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
        run = self.state
        gifts_before = set(run.gifts)
        curse_keys_before = {curse.key for curse in run.curses}
        equipment_before = dict(run.player.equipment)
        result = perform_action(run, action)
        app.play_after((len(run.log), run.depth, run.level))
        if result.died or result.escaped:
            self._game_over(app, won=result.escaped)
            return
        self._announce(
            app,
            gifts_before,
            curse_keys_before,
            equipment_before,
        )

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
