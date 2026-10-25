"""The Tenth Door: the mode's first slice.

The door is an *answer to a stair*, not a second dungeon. These tests hold the
three facts that make it a mode: it opens only for someone who has escaped once,
the run starts at the tenth floor with the house's credit, and the stair at a
door floor asks a question instead of descending.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.savegame import dump, load
from neverdeads_revenge.game.state import (
    CREDIT_LEVEL,
    RunState,
    start_run,
)
from neverdeads_revenge.persistence import MetaProgress
from neverdeads_revenge.world.tiles import Tile


def _begin(seed: int = 3):
    return start_run(
        HEROES["noxx"],
        seed=seed,
        tenth_door=True,
        start_depth=10,
    )


# -- the unlock -------------------------------------------------------------
def _title_items(app):
    from neverdeads_revenge.desktop.screens.title import TitleScreen

    return [key for key, _label in TitleScreen().items(app)]


def test_the_door_is_not_on_the_title_before_an_escape():
    app = SimpleNamespace(progress=MetaProgress(), has_saved_run=lambda: False)

    assert "t" not in _title_items(app)


def test_the_door_opens_after_one_escape():
    progress = MetaProgress()
    progress.runs_won = 1
    app = SimpleNamespace(progress=progress, has_saved_run=lambda: False)

    assert "t" in _title_items(app)


def test_the_title_line_opens_the_roster_in_door_mode():
    class FakeApp:
        progress = MetaProgress()
        tenth_door = False

        def has_saved_run(self):
            return False

        def open_hero_select(self, *, tenth_door=False):
            self.tenth_door = tenth_door

    app = FakeApp()
    from neverdeads_revenge.desktop.screens.title import TitleScreen

    screen = TitleScreen()
    screen._choose("t", app)

    assert app.tenth_door is True


def test_the_roster_carries_the_mode_into_the_run():
    class FakeApp:
        called = None

        def begin_run(self, key, *, tenth_door=False):
            self.called = (key, tenth_door)

    from neverdeads_revenge.desktop.screens.hero_select import HeroSelectScreen

    screen = HeroSelectScreen(tenth_door=True)
    app = FakeApp()
    screen.key("enter", SimpleNamespace(isAutoRepeat=lambda: False), app)

    assert app.called == ("noxx", True)


# -- the credit -------------------------------------------------------------
def test_the_run_starts_at_the_door_with_the_house_credit():
    state = _begin()

    assert state.depth == 10
    assert state.tenth_door is True
    assert state.level == CREDIT_LEVEL
    assert state.at_a_door
    # Three pieces, worn or carried; the loan is not a single sword.
    gear = [
        item
        for slot in ("weapon", "armour", "amulet")
        if (item := state.player.equipment.get(slot)) is not None
    ]
    assert len(gear) + len(state.inventory) >= 3


def test_the_tenth_floor_has_stairs_and_not_the_rift():
    state = _begin()

    assert state.dungeon_map.tile_at(state.exit_pos) is Tile.STAIRS_DOWN
    assert not state.at_the_rift
    assert not state.dungeon_map.find_tile(Tile.RIFT)


# -- the door ---------------------------------------------------------------
def test_stepping_onto_the_stairs_asks_the_door_question():
    state = _begin()
    state.player.position = state.exit_pos

    result = perform_action(state, Action.DESCEND)

    assert not result.escaped
    assert state.door_pending is True
    assert state.depth == 10, "the door must not descend before it is answered"


def test_pushing_on_multiplies_the_run_and_descends():
    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)

    state.continue_through_the_door()

    assert state.depth == 11
    assert state.door_pending is False
    assert state.risk_multiplier == 1.25
    assert state.coin_multiplier == 1.25
    assert state.door_ring == 2
    assert state.dungeon_map.tile_at(state.exit_pos) is Tile.STAIRS_DOWN


def test_banking_keeps_the_score_it_had_and_does_not_pay_the_rift_bonus():
    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    before = state.score

    state.gold = 40
    state.bank()

    assert state.run_state is RunState.ESCAPED
    assert state.banked is True
    assert state.score == before, "banking must not invent a new score"
    assert state.gold_kept == 40, "banking must keep the purse"


def test_death_takes_the_purse_and_the_coin_multiplier_raises_it():
    from neverdeads_revenge.game.state import RunState

    state = _begin()
    state.gold = 40
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    state.continue_through_the_door()
    state.gold = 60

    assert state.coin_multiplier == 1.25
    assert state.gold_kept == 0, "only a bank keeps the Tenth Door purse"

    state.run_state = RunState.DEAD
    assert state.gold_kept == 0

    state.tenth_door = False
    assert state.gold_kept == 60, "an ordinary run still banks its purse"


def test_the_summary_shows_what_the_door_kept_and_what_it_took():
    from neverdeads_revenge.desktop.screens.game_over import _summary_lines

    state = _begin()
    state.gold = 40
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    state.continue_through_the_door()
    state.gold = 60
    state.run_state = RunState.DEAD

    text = " ".join(line for line, _style in _summary_lines(state))

    assert "Coins banked    0" in text
    assert "Coins lost      60" in text
    assert "Coin multiplier 1.25x" in text


def test_the_door_fields_survive_a_save():
    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    state.continue_through_the_door()

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert reloaded.tenth_door is True
    assert reloaded.door_ring == 2
    assert reloaded.risk_multiplier == 1.25
    assert reloaded.banked is False
    assert reloaded.depth == 11


def test_the_door_screen_banks_or_pushes_on():
    from neverdeads_revenge.desktop.screens.door import DoorScreen

    class FakeApp:
        def __init__(self):
            self.played = []
            self.popped = False
            self.game_over = None

        def play(self, name):
            self.played.append(name)

        def pop(self):
            self.popped = True

        def redraw(self):
            pass

        def show_game_over(self, *, won=False):
            self.game_over = won

    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    app = FakeApp()

    door = DoorScreen(state)
    door._choose(1, app)  # push on -> the boon shelf
    assert door.mode == "boons"
    door._choose(0, app)  # take the first boon and descend

    assert state.depth == 11
    assert len(state.boons) == 1
    assert app.popped is True
    assert "door_creak" in app.played

    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    app = FakeApp()

    DoorScreen(state)._choose(0, app)

    assert state.banked is True
    assert app.game_over is True
    assert "door_unlock" in app.played


def test_the_summary_says_banked_and_not_escaped():
    from neverdeads_revenge.desktop.screens.game_over import _summary_lines

    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    state.bank()

    text = " ".join(line for line, _style in _summary_lines(state))

    assert "Banked at the door" in text
    assert "Out of the dark" not in text


# -- the rings --------------------------------------------------------------
def test_ring_two_gets_a_rule_and_consecutive_rings_do_not_repeat():
    from neverdeads_revenge.game import rings

    assert rings.rule_for(3, 1) is None
    first = rings.rule_for(3, 2)
    second = rings.rule_for(3, 3)

    assert first is not None and second is not None
    assert first.key != second.key, "a run met the same weather twice in a row"


def test_the_gloom_ring_takes_two_cells_of_sight():
    state = _begin()
    state.ring_rule = "gloom"

    state.build_floor(11)

    assert state.sight_penalty == 2


def test_the_iron_ring_puts_a_plate_on_every_monster():
    plain = _begin()
    plain.build_floor(11)

    iron = _begin()
    iron.ring_rule = "iron"
    iron.build_floor(11)

    assert iron.enemies and len(iron.enemies) == len(plain.enemies)
    assert all(
        ringed.stats.armor == bare.stats.armor + 1
        for bare, ringed in zip(plain.enemies, iron.enemies, strict=True)
    )


def test_the_fever_ring_is_faster_and_the_greed_ring_pays_more():
    from neverdeads_revenge.game import rings

    plain = _begin()
    plain.build_floor(11)

    fever = _begin()
    fever.ring_rule = "fever"
    fever.build_floor(11)
    assert all(
        ringed.stats.speed > bare.stats.speed
        for bare, ringed in zip(plain.enemies, fever.enemies, strict=True)
    )

    greed = _begin()
    before = greed.coin_multiplier
    rings.enter_ring(greed, rings.RING_BY_KEY["greed"])
    assert greed.coin_multiplier > before
    greed.build_floor(11)
    assert all(
        ringed.stats.max_hp > bare.stats.max_hp
        for bare, ringed in zip(plain.enemies, greed.enemies, strict=True)
    )


def test_pushing_through_sets_the_next_rings_rule():
    from neverdeads_revenge.game import rings

    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    state.continue_through_the_door()

    assert state.ring_rule == rings.rule_for(state.seed, 2).key


# -- the boons --------------------------------------------------------------
def test_a_door_offers_three_different_boons():
    from neverdeads_revenge.game import boons

    offered = boons.offers(3, 1)

    assert len(offered) == 3
    assert len(set(offered)) == 3


def test_a_boon_is_taken_once_and_stays_for_the_run():

    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    key = state.boon_offers[0]
    before = state.player.stats.max_hp if key == "iron_heart" else None

    assert state.take_boon(key)
    assert state.boons == [key]
    assert state.boon_offers == ()
    assert not state.take_boon(key), "a boon was taken twice"

    if key == "iron_heart":
        assert state.player.stats.max_hp == before + 8


def test_the_door_changes_to_the_boon_shelf_before_it_descends():
    from neverdeads_revenge.desktop.screens.door import DoorScreen

    class FakeApp:
        def __init__(self):
            self.popped = False
            self.redraws = 0

        def play(self, name):
            pass

        def pop(self):
            self.popped = True

        def redraw(self):
            self.redraws += 1

        def show_game_over(self, *, won=False):
            raise AssertionError("pushing on must not show the summary")

    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)
    app = FakeApp()
    screen = DoorScreen(state)

    screen._choose(1, app)
    assert screen.mode == "boons"
    assert state.depth == 10 and state.door_pending

    screen._choose(0, app)
    assert state.depth == 11
    assert len(state.boons) == 1
    assert app.popped and app.redraws == 1


# -- the wardens ------------------------------------------------------------
def test_the_middle_of_a_ring_has_one_warden():
    state = _begin()
    state.build_floor(15)

    wardens = [enemy for enemy in state.enemies if enemy.warden]
    assert len(wardens) == 1
    assert wardens[0].name.startswith("warden ")
    assert wardens[0].stats.max_hp > 0


def test_the_door_floors_do_not_add_a_warden():
    state = _begin()
    state.build_floor(20)

    assert not any(enemy.warden for enemy in state.enemies)


def test_the_warden_and_the_ring_survive_a_save():
    state = _begin()
    state.build_floor(15)
    state.ring_rule = "iron"
    state.boons = ["whetstone"]
    state.boon_offers = ("lantern", "plated", "quickstep")

    reloaded = load(json.loads(json.dumps(dump(state))))

    assert any(enemy.warden for enemy in reloaded.enemies)
    assert reloaded.ring_rule == "iron"
    assert reloaded.boons == ["whetstone"]
    assert reloaded.boon_offers == ("lantern", "plated", "quickstep")


def test_the_door_floor_is_smaller_than_the_ordinary_tenth():
    from neverdeads_revenge.game.state import door_enemy_count

    state = _begin()

    assert door_enemy_count(10) < 33, "the endless floor kept the boss-sized crowd"
    assert door_enemy_count(35) == 20
    assert len(state.enemies) <= 22, "the budget did not hold"


def test_the_bitter_ring_poisons_and_the_thorn_ring_bites():
    state = _begin()
    state.ring_rule = "bitter"
    state.build_floor(11)

    assert state.enemies
    assert all("poison" in enemy.inflicts for enemy in state.enemies)

    state.ring_rule = "thorn"
    state.build_floor(11)

    assert all(enemy.thorns >= 1 for enemy in state.enemies)


def test_the_new_boons_are_real_and_stack():
    from neverdeads_revenge.game import boons

    state = _begin()
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)

    before_lives = state.extra_lives
    before_armour = state.player.stats.armor
    boons.apply(state, "second_wind")
    boons.apply(state, "iron_skin")
    boons.apply(state, "carrier")

    assert state.extra_lives == before_lives + 1
    assert state.player.stats.armor == before_armour + 2
    assert state.pack_capacity >= 4
