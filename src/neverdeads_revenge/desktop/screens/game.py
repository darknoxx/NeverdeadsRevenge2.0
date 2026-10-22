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
from .pages import the_page, write_the_page, write_the_weapon
from .dialogs import (
    KindlyScreen,
    FAME,
    OPEN,
    ChestScreen,
    NpcScreen,
    PageScreen,
    SpringScreen,
)
from .game_over import REWIND as REWIND

#: Which sound each hero's ultimate makes. Kept here rather than in the audio
#: layer because it is a casting decision -- the sound module only knows how
#: to play a name.
ULTIMATE_SOUND: dict[str, str] = {
    "noxx": "fire_burst",
    "yeti": "ice_shatter",
    "walkyrion": "dark_bell",
}

#: What a card calls what was just picked up. The kind is the game's own word for
#: it, and a bottle is a draught and not a potion -- "A STRANGE" was never a
#: sentence.
CARD_TITLES: dict[str, str] = {
    "weapon": "A WEAPON",
    "armour": "AN ARMOUR",
    "amulet": "AN AMULET",
    "draught": "A DRAUGHT",
    "strange": "A STRANGE BOTTLE",
}

__all__ = ["GameScreen", "REWIND"]


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
        #: What the floor looked like when it handed a fight over, so that it can
        #: catch up when the fight is done: the coins a kill dropped, the blood
        #: it left, the level it paid. Kept here rather than on the state because
        #: it is a *view* of two moments, not a rule about either.
        self._pending: tuple | None = None
        #: Whether the key being handled was refused. Read by ``key_sound``, so
        #: the refusal beeps instead of clicking.
        self._denied = False
        #: The monsters this screen has already filed a page for, so a step does
        #: not re-read the whole list of the run's dead on every keypress.
        self._filed: set[str] = set()
        #: The same for the Armory's blades, and the keys whose card should say
        #: that a page was just written -- one card, not two.
        self._filed_weapons: set[str] = set()
        self._new_weapons: set[str] = set()

    def key_sound(self, name: str) -> str | None:
        """The sound this press makes: a refusal has one, a click has another."""
        if self._denied:
            self._denied = False
            return "error_locked"
        return super().key_sound(name)

    # -- drawing ------------------------------------------------------------
    def draw(self, buffer, app) -> None:
        from ..render import draw_game

        draw_game(buffer, self.state)

    # -- input --------------------------------------------------------------
    #: The floor, and the one screen whose arrows are silent.
    #:
    #: A step is not punctuation and it is not rare: it is the most repeated
    #: action in the game, held keys repeat it at the platform's own pace, and a
    #: footstep every sixtieth of a second is not a game that sounds like a walk,
    #: it is a game that buzzes. It was a nice idea and it lasted one playtest.
    UI_SOUNDS = {
        "enter": "cursor_confirm",
        "space": "cursor_confirm",
        "escape": "cursor_back",
        "backspace": "cursor_back",
        "?" : "cursor_confirm",
        "f1": "cursor_confirm",
    }

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
        carried = list(run.inventory)
        ultimate_ready = run.ultimate_available

        result = perform_action(run, action)
        # A refusal is its own sound and not also a click: the log says *why*,
        # and the ear is on the map rather than on the fourth line of the log --
        # a pickup that silently did nothing reads as a broken key. Played by
        # ``key_sound`` with every other press, so one press is one sound.
        self._denied = result.denied
        if (
            run.encounter is not None
            and run.encounter.behaviour == "kindly"
            and run.encounter.stats.alive
        ):
            # THE KINDLY ONE asks before the arena opens. It is the one monster
            # whose whole fight is a question, and a question is a dialog.
            from neverdeads_revenge.game.actions import KINDLY_PRICE, pay_the_kindly_one

            def answered(paid: bool) -> None:
                if paid and pay_the_kindly_one(run):
                    return
                app.open_encounter()

            app.push(KindlyScreen(KINDLY_PRICE, on_done=answered))
            return
        if run.encounter is not None:
            # The step walked into something. The floor hands the fight over,
            # and everything the map would have done about it -- the blow, the
            # blood, the log line -- is the arena's business from here. What the
            # numbers are *now* is kept, because the fight will move them and the
            # floor still has a coin to throw and a stain to lay down.
            self._pending = (hp, gold, gifts, curses, before[2])
            app.open_encounter()
            return
        if action is Action.ULTIMATE and ultimate_ready and not run.ultimate_available:
            # The dark answers with its own note, not the log's second reading
            # -- and its own note per hero, because the three asks sound like
            # three different things.
            app.play(ULTIMATE_SOUND.get(run.hero.key, "void"))
        app.play_after(before)
        self._effects(app, hp, gold, gifts, curses, before[2])
        self._file_pages(app)
        self._file_monsters(app)
        self._file_weapons(app)

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
            carried,
        )

    def _card(self, app, template, name: str) -> None:
        """One page for one thing: what it is called, what it does, what it looks like."""
        from neverdeads_revenge.game.shop import describe_item

        from ..art import item_icon
        from .dialogs import InfoScreen

        text = describe_item(template)
        if template.key in self._new_weapons:
            # The blade's page and the blade's card are one moment: a second
            # window on the same find would be the game saying the same thing
            # twice and asking to be dismissed twice.
            text = f"{text}\n\nA page has been written in the Armory."
            self._new_weapons.discard(template.key)
        app.push(
            InfoScreen(
                CARD_TITLES.get(template.kind, "A THING"),
                name,
                text,
                picture=item_icon(template),
            )
        )

    def _announce(
        self,
        app,
        gifts_before,
        curse_keys_before,
        equipment_before,
        carried_before=(),
    ) -> None:
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

        from ..art import curse_icon, gift_icon
        from .dialogs import InfoScreen

        run = self.state
        for key in sorted(run.gifts - gifts_before):
            gift = gift_by_key(key)
            if gift is not None:
                app.push(
                    InfoScreen(
                        "A GIFT", gift.name, gift.blurb, picture=gift_icon(key)
                    )
                )
        for curse in run.curses:
            if curse.key in curse_keys_before:
                continue
            # The curse's own price is the sentence the chest dialog reads;
            # the modifier list is the fine print where one exists.
            text = curse.price
            extra = ", ".join(curse.modifiers.describe())
            if extra:
                text = f"{text}. {extra}."
            app.push(
                InfoScreen("A CURSE", curse.name, text, picture=curse_icon(curse.key))
            )
        for slot, item in run.player.equipment.items():
            worn = equipment_before.get(slot)
            if worn is not None and worn.item_id == item.item_id:
                continue
            template = ITEMS.get(item.item_id)
            if template is None:
                continue
            self._card(app, template, item.name)
        # And the pack: a bottle is not worn, so the equipment loop above never
        # sees one, and a potion that said nothing about itself was a potion the
        # player had to remember the colour of.
        seen = {id(one) for one in carried_before}
        for item in run.inventory:
            if id(item) in seen:
                continue
            template = ITEMS.get(item.item_id)
            if template is None:
                continue
            self._card(app, template, item.name)

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

    def catch_up(self, app) -> None:
        """The fight is over: show what it did to the floor.

        What a fight moved -- the coins a kill dropped, the blood it left, the
        level it paid -- is drawn by the *map*, because the map is where it
        happened. The snapshot was taken when the floor handed the fight over,
        because by the time it is over the numbers have already moved and the
        state does not keep the past. No sound: the arena made its own, and the
        floor answering a blow it did not see would be a second report of it.
        """
        pending = self._pending
        self._pending = None
        run = self.state
        if pending is None or run is None or run.over:
            return
        hp, gold, gifts, curses, level = pending
        self._effects(app, hp, gold, gifts, curses, level)
        app.redraw()

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
        app.play("ritual_chime")
        result = perform_action(self.state, Action.CLEANSE)
        app.play_after((len(self.state.log), self.state.depth, self.state.level))
        if result.died or result.escaped:
            self._game_over(app, won=result.escaped)

    def _chest(self, app, answer) -> None:
        if not answer:
            return
        app.play("chest_open")
        action = Action.OPEN_CHEST if answer == OPEN else Action.TAKE_FAME
        run = self.state
        hp = run.player.hp
        gold = run.gold
        gifts_before = set(run.gifts)
        curse_keys_before = {curse.key for curse in run.curses}
        equipment_before = dict(run.player.equipment)
        carried_before = list(run.inventory)
        level_before = run.level
        result = perform_action(run, action)
        app.play_after((len(run.log), run.depth, run.level))
        if run.encounter is not None:
            # THE LID. The chest was a jaw, and the answer that lifted the lid is
            # the answer that starts the fight: the floor hands it over here, on
            # the same keypress. Nothing is said about a curse that was never
            # charged, and there is no page to dismiss before the room turns.
            self._pending = (
                hp,
                gold,
                gifts_before,
                len(curse_keys_before),
                level_before,
            )
            app.open_encounter()
            return
        if result.died or result.escaped:
            self._game_over(app, won=result.escaped)
            return
        self._announce(
            app,
            gifts_before,
            curse_keys_before,
            equipment_before,
            carried_before,
        )

    def _file_monsters(self, app) -> None:
        """Write the page of anything the *floor* killed outright.

        Fights file their own dead, in the arena, where the death is played out.
        The floor can kill too -- the hungry road's glass, an ultimate -- and a
        page left until the next fight would arrive attached to the wrong
        moment. Here it arrives when the thing died.
        """
        for key in self.state.defeated:
            if key in self._filed:
                continue
            self._filed.add(key)
            if not write_the_page(app, key):
                continue
            card = the_page(key)
            if card is not None:
                app.push(card)

    def _file_weapons(self, app) -> None:
        """Write the Armory page of anything just taken up.

        A blade is known when it is in the hand -- mid-swing, mid-run, with the
        old one lying on the floor beside it. The card that already announces a
        pickup says the page was written; this only does the writing.
        """
        for key in self.state.found_weapons:
            if key in self._filed_weapons:
                continue
            self._filed_weapons.add(key)
            if write_the_weapon(app, key):
                self._new_weapons.add(key)

    def _file_pages(self, app) -> None:
        """Bank a found page at once, and open it.

        A page is knowledge, so it goes into the book the moment it is picked up
        -- and it opens, because prose in the log scrolls away in four turns.
        """
        for number in self.state.found_pages:
            if not app.progress.record_page(number):
                continue
            app.play("rare_item")
            app.save_progress()
            text = page(number)
            if text is not None:
                app.push(PageScreen(number, text))

    # -- the end ------------------------------------------------------------
    def _game_over(self, app, won: bool = False) -> None:
        """The run ended. The app owns the ending, because the arena ends runs
        too, and a fight that killed the hero has to be followed by exactly the
        ending a monster on the floor would have given him."""
        app.show_game_over(won=won)
