"""Tests for the amulets.

One test per ability, because the abilities are the point: a slot that only ever
added two to a stat would be a third number, and the game already has two of
those. Each one is checked where it happens -- a kill, a drink, a blow landed, a
floor entered -- so a test failing here says which rule broke rather than that
the numbers moved.

The other half of the file is the table itself: every amulet has an item, every
item has an amulet, the two agree on the name, and the two drop tiers partition
the list. An amulet in neither tier is an amulet nobody can ever find.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.game.actions import Action, perform_action, take_turn
from neverdeads_revenge.game.amulets import (
    AMULETS,
    FOUND_ON_THE_FLOOR,
    FROM_THE_STRONG_TIER,
    amulet_by_key,
    blurb_for,
)
from neverdeads_revenge.game.actors import ENEMIES, NOXX, make_enemy, make_hero
from neverdeads_revenge.game.shop import Loadout, describe_item
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.world.items import ITEMS, make_item
from neverdeads_revenge.world.tiles import Tile


def wearing(key: str | None = None, seed: int = 3):
    """A run with this amulet on, or none."""
    loadout = Loadout(pending=(key,)) if key else None
    return start_run(NOXX, seed=seed, loadout=loadout)


def land_one_blow(state, brute) -> int:
    """Let ``brute`` swing until one lands, and report what it cost.

    Driving the enemy turn directly rather than waiting on the queue: the tests
    that need a blow to land are about the blow, and a monster that acts once
    every hundred player turns makes them about the scheduler instead.
    """
    brute.stats.accuracy = 99
    state.player.stats.evasion = 0
    state.player.stats.hp = state.player.max_hp
    for _ in range(200):
        take_turn(state, brute)
        if state.player.hp < state.player.max_hp:
            return state.player.max_hp - state.player.hp
    raise AssertionError("never landed a blow")


def duel(key: str | None, *, brute_hp: int = 400, brute_damage=(6, 6), seed: int = 3):
    """A run with one nearly-motionless monster right beside the player.

    Nearly motionless rather than frozen: the turn queue refuses a speed of zero,
    and a monster that never acts cannot answer anything.
    """
    state = wearing(key, seed)
    player = state.player
    brute = make_enemy(ENEMIES["bone"], (player.position[0] + 1, player.position[1]))
    brute.stats.hp = brute_hp
    brute.stats.speed = 0.01
    brute.stats.damage = brute_damage
    state.enemies = [brute]
    state.turn_queue = type(state.turn_queue)([player, brute])
    state.refresh_vision()
    return state, brute


def kill_it(state, target) -> None:
    """Walk into ``target`` until it dies."""
    for _ in range(40):
        if not target.alive:
            return
        perform_action(state, Action.MOVE_EAST)
    raise AssertionError("the player never landed the killing blow")


# -- the table ---------------------------------------------------------------
def test_every_amulet_has_an_item_and_the_two_agree_on_the_name():
    """The name is written twice -- once for the map, once for the rules.

    Duplication with a test is cheaper than a layer that would have to import the
    other one to build a template, and this is the test.
    """
    for key, passive in AMULETS.items():
        assert key in ITEMS, f"{key} has no item"
        assert ITEMS[key].name == passive.name, key
        assert ITEMS[key].amulet == key, key
        assert ITEMS[key].slot == "amulet", key


def test_no_item_claims_an_amulet_that_does_not_exist():
    for template in ITEMS.values():
        if template.amulet is not None:
            assert template.amulet in AMULETS, template.key


def test_the_two_drop_tiers_partition_the_table():
    """An amulet in neither tier is an amulet nobody can ever find."""
    assert set(FOUND_ON_THE_FLOOR) | set(FROM_THE_STRONG_TIER) == set(AMULETS)
    assert not set(FOUND_ON_THE_FLOOR) & set(FROM_THE_STRONG_TIER)


def test_the_floor_tier_is_the_weak_half():
    for key in FOUND_ON_THE_FLOOR:
        assert not ITEMS[key].chest_only, key
        assert ITEMS[key].weight > 0, key
    for key in FROM_THE_STRONG_TIER:
        assert ITEMS[key].chest_only, key


def test_an_amulet_describes_its_ability_not_its_numbers():
    for key, passive in AMULETS.items():
        assert describe_item(ITEMS[key]) == passive.blurb, key


def test_an_unknown_key_is_not_an_amulet():
    assert amulet_by_key(None) is None
    assert amulet_by_key("nothing") is None
    assert blurb_for(None) == ""


# -- wearing one -------------------------------------------------------------
def test_a_run_with_no_amulet_has_no_passive():
    state = wearing()
    assert state.amulet is None
    assert not state.has_passive("ember")


def test_the_amulet_slot_holds_one_amulet():
    """A second one displaces the first, the way any other slot behaves."""
    state = wearing("ember")
    assert state.has_passive("ember")

    state.player.equipment["amulet"] = make_item(ITEMS["mirror"])
    assert state.has_passive("mirror")
    assert not state.has_passive("ember")


def test_an_amulet_can_be_picked_up_off_the_floor_like_anything_else():
    state = wearing()
    state.dungeon_map.add_item(state.player.position, make_item(ITEMS["ember"]))

    perform_action(state, Action.PICK_UP)

    assert state.player.equipment["amulet"].item_id == "ember"
    assert state.has_passive("ember")


# -- ember -------------------------------------------------------------------
def test_the_ember_puts_health_back_on_every_kill():
    state, brute = duel("ember", brute_hp=1)
    state.player.stats.hp = 20

    kill_it(state, brute)

    assert state.player.hp == 22


def test_the_ember_never_heals_past_the_wound():
    state, brute = duel("ember", brute_hp=1)
    kill_it(state, brute)
    assert state.player.hp == state.player.max_hp


def test_without_the_ember_a_kill_puts_nothing_back():
    state, brute = duel(None, brute_hp=1)
    state.player.stats.hp = 20
    kill_it(state, brute)
    assert state.player.hp == 20


# -- coin hand ---------------------------------------------------------------
def test_the_coin_hand_makes_every_pile_worth_more():
    plain, _ = duel(None, brute_hp=1)
    greedy, _ = duel("coin_hand", brute_hp=1)

    assert plain.coin_factor == 1.0
    assert greedy.coin_factor == pytest.approx(1.25)


def test_the_coin_hand_stacks_with_a_wild_offer():
    """The pact multiplies and the hand multiplies on top, which is the point of
    keeping them apart."""
    state = start_run(
        NOXX, seed=3, loadout=Loadout(pending=("coin_hand",), wilds=("greed",))
    )
    assert state.coin_factor == pytest.approx(2.5)


def test_the_coin_hand_reaches_the_pile_on_the_floor():
    from neverdeads_revenge.game.actions import _drop_coins

    state, brute = duel("coin_hand")
    brute.gold = (10, 10)
    _drop_coins(state, brute)

    assert state.dungeon_map.item_at(brute.position).gold == 12


# -- marrow ------------------------------------------------------------------
def test_the_marrow_makes_a_draught_worth_half_again_as_much():
    assert wearing("marrow").heal_scale == pytest.approx(1.5)
    assert wearing().heal_scale == 1.0


def test_the_marrow_and_famine_meet_in_the_middle():
    """The two are worded to meet: halved and half again is a whole."""
    from neverdeads_revenge.game.curses import CURSES

    state = wearing("marrow")
    state.add_curse(CURSES["famine"])
    assert state.heal_scale == pytest.approx(0.75)


# -- wayfarer ----------------------------------------------------------------
def test_the_wayfarer_knows_where_the_way_out_is_from_the_first_step():
    state = wearing("wayfarer")
    assert state.exit_pos is not None
    assert state.dungeon_map.is_explored(state.exit_pos)


def test_without_the_wayfarer_the_exit_is_a_surprise():
    state = wearing()
    assert state.exit_pos is not None
    assert not state.dungeon_map.is_explored(state.exit_pos)


# -- rune heart --------------------------------------------------------------
def test_the_rune_heart_pays_on_the_way_down_and_not_on_floor_one():
    state = wearing("rune_heart")
    before = state.player.max_hp
    assert before == NOXX.stats.max_hp, "it paid out before the first descent"

    state.build_floor(2)
    assert state.player.max_hp == before + 1

    state.build_floor(3)
    assert state.player.max_hp == before + 2


def test_the_rune_heart_does_not_hand_out_the_floor_it_is_bought_on():
    """Bought in the shop, worn on floor one: no free health for arriving."""
    state = wearing("rune_heart")
    assert state.player.max_hp == NOXX.stats.max_hp


# -- mirror ------------------------------------------------------------------
def test_the_mirror_gives_two_back_to_whatever_struck_you():
    state, brute = duel("mirror")
    before = brute.stats.hp

    land_one_blow(state, brute)

    assert before - brute.stats.hp == 2


def test_the_mirror_goes_through_armour():
    """A reflection is not a blow. Saying two and delivering one against anything
    armoured is an amulet that lied."""
    from neverdeads_revenge.game.actors import Stats

    armoured = Stats(max_hp=10, hp=10, armor=5)
    assert armoured.reflect(2) == 2
    assert armoured.hp == 8


def test_the_mirror_can_finish_something_off():
    state, brute = duel("mirror", brute_hp=1)

    for _ in range(60):
        if not brute.alive:
            break
        land_one_blow(state, brute)

    assert not brute.alive
    assert brute not in state.enemies, "the body was left on the floor"


# -- grave ward --------------------------------------------------------------
def test_the_grave_ward_halves_the_first_blow_of_each_floor():
    state, brute = duel("grave_ward", brute_damage=(20, 20))
    armour = state.player.armor

    assert land_one_blow(state, brute) == 10 - armour, "the first blow was not halved"
    assert land_one_blow(state, brute) == 20 - armour, "the ward covered two blows"


def test_the_grave_ward_is_armed_again_on_the_next_floor():
    state, brute = duel("grave_ward")
    land_one_blow(state, brute)
    assert not state.ward_ready

    state.build_floor(2)
    assert state.ward_ready


def test_a_missed_swing_does_not_spend_the_ward():
    """It says the first *blow*, and a swing that missed was not one."""
    state, brute = duel("grave_ward")
    # The floor on hit chance is 30%, so a miss cannot be forced -- only waited
    # for. Misses are the common case at this accuracy.
    brute.stats.accuracy = 0
    state.player.stats.evasion = 99

    # A blow that lands before the first miss is the ward doing exactly what it
    # says it does; that one is spent by it, so it is re-armed and the wait for
    # the miss this test is about goes on. Breaking on the first *landing* blow
    # instead made the whole thing a coin toss on the dice.
    for _ in range(400):
        state.player.stats.hp = state.player.max_hp
        before = state.player.hp
        take_turn(state, brute)
        if state.player.hp < before:
            state.ward_ready = True
            continue
        assert state.ward_ready, "a miss spent the ward"
        break
    else:
        pytest.fail("it never missed, so this proved nothing")

    # And the first blow that does land spends it.
    state.player.stats.hp = state.player.max_hp
    for _ in range(400):
        before = state.player.hp
        take_turn(state, brute)
        if state.player.hp < before:
            break
    else:
        pytest.fail("it never landed a blow")

    assert not state.ward_ready, "the ward survived the blow that landed"


def test_without_the_ward_nothing_is_halved():
    state, brute = duel(None, brute_damage=(20, 20))
    assert land_one_blow(state, brute) == 20 - state.player.armor


# -- deathwatch --------------------------------------------------------------
def test_the_deathwatch_arms_itself_when_you_are_nearly_gone():
    state = wearing("deathwatch")
    base = state.player.armor

    state.player.stats.hp = state.player.max_hp // 4
    state.refresh_passives()
    assert state.player.armor == base + 3

    state.player.stats.hp = state.player.max_hp
    state.refresh_passives()
    assert state.player.armor == base, "the armour stayed after the danger passed"


def test_the_deathwatch_armour_actually_stops_a_hit():
    state = wearing("deathwatch")
    state.player.stats.hp = 2
    state.refresh_passives()
    assert state.player.hurt(5) < 5


# -- long hunger -------------------------------------------------------------
def test_the_long_hunger_feeds_revenge_a_stack_for_every_kill():
    state, brute = duel("long_hunger", brute_hp=1)
    kill_it(state, brute)
    assert state.revenge_stacks == 2, "one kill, two stacks"


def test_without_it_a_kill_is_worth_one_stack():
    state, brute = duel(None, brute_hp=1)
    kill_it(state, brute)
    assert state.revenge_stacks == 1


def test_the_long_hunger_respects_the_hero_cap():
    """The cap is the hero's, and an amulet does not get to raise it."""
    from neverdeads_revenge.game.actors import REVENGE_MAX_STACKS
    from neverdeads_revenge.game.combat import apply_revenge

    state = wearing("long_hunger")
    cap = REVENGE_MAX_STACKS[NOXX.trait]
    assert apply_revenge(state.player, cap + 5) == cap


# -- patience ----------------------------------------------------------------
def test_patience_pays_for_lingering_and_stops_paying():
    state = wearing("patience")
    base = state.player.damage_range

    state.refresh_passives()
    assert state.player.damage_range == base, "it paid out on the first turn"

    state.turn = 25
    state.refresh_passives()
    assert state.player.damage_range == (base[0] + 2, base[1] + 2)

    state.turn = 400
    state.refresh_passives()
    assert state.player.damage_range == (base[0] + 4, base[1] + 4), "uncapped"


def test_patience_starts_over_on_the_next_floor():
    state = wearing("patience")
    state.turn = 100
    state.refresh_passives()
    assert state.player.passive_damage == 4

    state.build_floor(2)
    assert state.player.passive_damage == 0, "the floor's patience came with it"


# -- second mouth ------------------------------------------------------------
def test_the_second_mouth_keeps_what_a_draught_could_not_heal():
    state = wearing("second_mouth")
    state.inventory.append(make_item(ITEMS["potion"]))
    state.player.stats.hp = state.player.max_hp - 2
    before = state.player.armor

    perform_action(state, Action.QUAFF)

    assert state.player.armor > before


def test_the_second_mouth_will_not_bank_a_whole_elixir():
    """Uncapped, one elixir drunk while barely hurt is nineteen armour."""
    from neverdeads_revenge.game.actions import second_mouth_cap

    state = wearing("second_mouth")
    for _ in range(6):
        state.inventory.append(make_item(ITEMS["elixir"]))

    for _ in range(6):
        state.player.stats.hp = state.player.max_hp - 1
        perform_action(state, Action.QUAFF)

    assert state.player.stored_armor == second_mouth_cap(state.depth)


def test_the_second_mouth_holds_more_the_deeper_you_are():
    """A flat cap is a floor-three trinket: armour is a flat subtraction, so
    what it is worth depends on what is hitting you."""
    from neverdeads_revenge.game.actions import second_mouth_cap

    assert second_mouth_cap(2) < second_mouth_cap(9)
    assert second_mouth_cap(1) > 0


def test_the_second_mouth_empties_when_the_floor_changes():
    state = wearing("second_mouth")
    state.player.stored_armor = 3
    state.build_floor(2)
    assert state.player.stored_armor == 0


def test_without_it_the_spill_is_simply_lost():
    state = wearing()
    state.inventory.append(make_item(ITEMS["potion"]))
    state.player.stats.hp = state.player.max_hp - 2
    before = state.player.armor
    perform_action(state, Action.QUAFF)
    assert state.player.armor == before


# -- dead weight -------------------------------------------------------------
def test_the_dead_weight_throws_what_it_hits():
    state, brute = duel("dead_weight")
    state.player.stats.accuracy = 99
    brute.stats.evasion = 0
    before = brute.position

    perform_action(state, Action.MOVE_EAST)

    assert brute.position != before, "nothing was thrown back"


def test_the_dead_weight_is_slower():
    assert wearing("dead_weight").player.speed < wearing().player.speed


def test_the_dead_weight_does_not_throw_anything_through_a_wall():
    """Nowhere to go means nowhere to go, and the blow still lands."""
    state, brute = duel("dead_weight")
    state.player.stats.accuracy = 99
    brute.stats.evasion = 0
    # Wall the monster in on every side but the player's.
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if (dx, dy) != (0, 0):
                state.dungeon_map.set_tile(
                    (brute.position[0] + dx, brute.position[1] + dy), Tile.WALL
                )
    state.dungeon_map.set_tile(state.player.position, Tile.FLOOR)
    hp_before = brute.stats.hp

    perform_action(state, Action.MOVE_EAST)

    assert brute.stats.hp < hp_before, "the blow was lost with the throw"


# -- patient knife -----------------------------------------------------------
def test_the_patient_knife_crits_the_first_blow_and_only_that_one():
    state, brute = duel("patient_knife")
    state.player.stats.accuracy = 99
    state.player.stats.damage = (10, 10)
    state.player.stats.crit_multiplier = 3.0
    # No crits of the hero's own, or "every blow was a crit" is a coin toss:
    # Noxx crits a quarter of the time, so the second blow had a one in four
    # chance of looking like the knife had done it.
    state.player.stats.crit_chance = 0.0
    brute.stats.evasion = 0

    # Waits for two blows that *land*, rather than assuming the first two swings
    # both connect. The hit chance is capped at 97%, so a miss is possible and
    # this test failed about once in thirty runs of the suite -- and a miss is
    # exactly what the knife is supposed to ignore, so waiting for a landing
    # blow is the honest version of the question anyway.
    dealt: list[int] = []
    for _ in range(40):
        brute.stats.hp = 400
        perform_action(state, Action.MOVE_EAST)
        if brute.stats.hp < 400:
            dealt.append(400 - brute.stats.hp)
        if len(dealt) == 2:
            break

    assert len(dealt) == 2, "never landed two blows"
    # Through the skeleton's armour, which is one point off every blow.
    assert dealt[0] == 30 - brute.stats.armor, "the first blow was not a crit"
    assert dealt[1] == 10 - brute.stats.armor, "every blow was a crit"


def test_the_patient_knife_is_ready_again_for_a_new_monster():
    state, brute = duel("patient_knife")
    state.player.stats.accuracy = 99
    state.player.stats.damage = (10, 10)
    state.player.stats.crit_multiplier = 3.0
    state.player.stats.crit_chance = 0.0
    brute.stats.evasion = 0
    perform_action(state, Action.MOVE_EAST)

    fresh = make_enemy(ENEMIES["bone"], brute.position)
    fresh.stats.evasion = 0
    state.enemies = [fresh]
    state.turn_queue = type(state.turn_queue)([state.player, fresh])
    state.refresh_vision()

    # Again, waits for a blow that lands: a swing can miss, and a missed swing
    # is not the question this test is asking.
    for _ in range(40):
        fresh.stats.hp = 400
        perform_action(state, Action.MOVE_EAST)
        if fresh.stats.hp < 400:
            break

    assert 400 - fresh.stats.hp == 30 - fresh.stats.armor, (
        "the knife was spent on the last one"
    )


def test_a_miss_does_not_spend_the_patient_knife():
    """A swing that missed was not a blow.

    The grave ward is worded the same way -- "the first blow" -- and is read the
    same way, spending itself only on one that lands. The two amulets disagreeing
    about what that phrase means was a bug rather than a rule.
    """
    state, brute = duel("patient_knife", brute_hp=100_000, brute_damage=(0, 0))
    state.player.stats.damage = (10, 10)
    state.player.stats.crit_multiplier = 3.0
    # Pinned to the 30% floor, so misses happen and hits still happen.
    state.player.stats.accuracy = -99
    brute.stats.evasion = 99
    brute.stats.armor = 0

    missed = False
    for _ in range(600):
        brute.stats.hp = 100_000
        perform_action(state, Action.MOVE_EAST)
        if 100_000 - brute.stats.hp == 0:
            assert not brute.struck, "a miss spent the knife"
            missed = True
            break
        # A landing blow before any miss is the knife working as intended, and
        # it legitimately spends it -- re-arm and keep waiting for the miss this
        # test is about.
        brute.struck = False
    assert missed, "the test never missed, so it proved nothing"

    # Now land the next blow. It has to be the crit the miss did not take.
    for _ in range(600):
        brute.stats.hp = 100_000
        perform_action(state, Action.MOVE_EAST)
        dealt = 100_000 - brute.stats.hp
        if dealt:
            assert dealt == 30, "the miss spent the knife"
            return
    pytest.fail("never landed a blow after the miss")


# -- borrowed face -----------------------------------------------------------
def _a_brute_beside(player, *, hp: int = 400):
    """Something fast and certain, one square off, that will answer a kill.

    Certain on purpose: the hit chance floor is 30%, so at a normal accuracy the
    monster misses often enough that a test about whether a blow lands is really
    a test about the dice.
    """
    brute = make_enemy(ENEMIES["bone"], (player.position[0], player.position[1] - 1))
    brute.stats.hp = hp
    brute.stats.speed = 3.0
    brute.stats.accuracy = 99
    player.stats.evasion = 0
    return brute


def test_the_borrowed_face_shrouds_you_for_the_turn_after_a_kill():
    state = wearing("borrowed_face")
    player = state.player
    weak = make_enemy(ENEMIES["ghoul"], (player.position[0] + 1, player.position[1]))
    weak.stats.hp = 1
    brute = _a_brute_beside(player)
    brute.stats.damage = (6, 6)
    state.enemies = [weak, brute]
    state.turn_queue = type(state.turn_queue)([player, weak, brute])
    state.refresh_vision()
    before = player.hp

    kill_it(state, weak)

    assert player.hp == before, "something landed through the borrowed face"
    assert state.shrouded == 0, "the shrouding did not wear off"


def test_without_it_the_answer_to_a_kill_lands():
    """A kill is answered by whatever was waiting for it.

    Repeated until a blow lands, because the hit chance is capped at 97% and a
    monster that missed is not "nothing answered" -- it is the dice. The test
    assumed the first answer connects and failed about once in thirty runs of
    the suite, which is the kind of failure that gets blamed on whatever was
    edited most recently.
    """
    state = wearing()
    player = state.player
    brute = _a_brute_beside(player)
    brute.stats.damage = (6, 6)
    before = player.hp

    for _ in range(60):
        weak = make_enemy(
            ENEMIES["ghoul"], (player.position[0] + 1, player.position[1])
        )
        weak.stats.hp = 1
        state.enemies = [weak, brute]
        state.turn_queue = type(state.turn_queue)([weak, brute, player])
        state.refresh_vision()
        kill_it(state, weak)
        if player.hp < before:
            return

    pytest.fail("nothing ever got to answer")


# -- the sidebar and the sheet ----------------------------------------------




def test_a_bare_hero_has_no_passive_armour_or_damage():
    state = wearing()
    player = state.player
    assert player.passive_armor == 0
    assert player.passive_damage == 0
    assert player.stored_armor == 0


def test_the_legend_gives_amulets_a_row():
    """The wearable kinds share one row of glyphs, so the amulet's is inside a
    row rather than a row of its own -- which is what makes it fit at all."""
    from neverdeads_revenge.game.prologue import item_legend

    glyphs = "".join(glyph for glyph, _ in item_legend())
    assert ITEMS["ember"].glyph in glyphs
    assert any("amulet" in meaning for _, meaning in item_legend())


def test_a_fresh_hero_equipped_by_hand_starts_clean():
    """The helpers in the other test files build heroes directly; the passive
    fields have to default to nothing or every one of them changes meaning."""
    hero = make_hero(NOXX, (0, 0))
    assert hero.armor == NOXX.stats.armor
    assert hero.damage_range == NOXX.stats.damage


def test_a_name_that_already_has_an_article_does_not_get_two():
    """Every amulet is called "the something", and "You start with the the
    patient knife" is the sort of thing that makes a screen look unfinished."""
    state = wearing("patient_knife")
    assert not any("the the" in entry.text for entry in state.log)
    assert any("the patient knife" in entry.text for entry in state.log)

    state.dungeon_map.add_item(state.player.position, make_item(ITEMS["ember"]))
    perform_action(state, Action.PICK_UP)

    assert not any("the the" in entry.text for entry in state.log)
    assert any("the last ember" in entry.text for entry in state.log)


def test_a_kill_the_mirror_finishes_is_still_a_kill():
    """It skipped straight to the corpse, so it counted for nothing at all.

    No coin, no REVENGE, no level, no ember -- an amulet quietly costing the
    player a handful of things it had never mentioned. The mirror is worn, not
    found, so what it kills is the player's doing.
    """
    state, brute = duel("mirror", brute_hp=1)
    brute.gold = (10, 10)

    for _ in range(60):
        if not brute.alive:
            break
        land_one_blow(state, brute)

    assert not brute.alive
    assert state.kills == 1, "the kill was not counted"
    assert state.dungeon_map.item_at(brute.position) is not None, "no coins"
    assert state.revenge_stacks == 1, "no REVENGE"


def test_the_mirror_teaches_like_any_other_kill():
    """The same bug from the other end: the kill count feeds the levels, and a
    kill that was not counted was a level the player never got."""
    from neverdeads_revenge.game.levels import KILLS_PER_LEVEL

    state = wearing("mirror")
    player = state.player
    before = player.max_hp

    for _ in range(KILLS_PER_LEVEL):
        brute = _a_brute_beside(player, hp=1)
        state.enemies = [brute]
        state.turn_queue = type(state.turn_queue)([player, brute])
        state.refresh_vision()
        for _ in range(60):
            if not brute.alive:
                break
            land_one_blow(state, brute)
        assert not brute.alive, "the mirror never finished one"

    assert state.kills == KILLS_PER_LEVEL
    assert state.level == 2
    assert player.max_hp == before + 2
