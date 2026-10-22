"""The monsters whose rule is a question, and the systems they needed.

Seven of them, and not one is a bigger number: a chest that is a jaw, a thing
that bleeds itself, a thorn that answers speed, a silence that stops the purse, a
thief who leaves with what he came for, a hand held out, and a hero out of the
chronicle. What each one *means* lives in a rule, and these tests are the rules.
"""

from __future__ import annotations

from neverdeads_revenge.game.actions import (
    KINDLY_PRICE,
    pay_the_kindly_one,
    resolve_enemy_attack,
    resolve_player_attack,
)
from neverdeads_revenge.game.actors import ENEMIES, HEROES, make_enemy
from neverdeads_revenge.game.battle import Battle
from neverdeads_revenge.game.state import start_run


def _run(seed: int = 5):
    state = start_run(HEROES["noxx"], seed)
    state.player.stats.accuracy = 99
    return state


def _monster(state, template: str, key: str):
    """A monster, in the fight, with a deep well of health."""
    enemy = make_enemy(ENEMIES[template], state.player.position)
    enemy.stats.max_hp = enemy.stats.hp = 999
    state.enemies.append(enemy)
    return enemy


# -- the briar -------------------------------------------------------------
def test_the_briar_gives_back_what_it_takes():
    state = _run()
    briar = _monster(state, "briar", "briar")
    before = state.player.hp

    resolve_player_attack(state, briar)

    assert state.player.hp == before - ENEMIES["briar"].thorns, "the thorns never bit"


# -- the already-dying -----------------------------------------------------
def test_the_already_dying_bleeds_itself_when_it_strikes():
    state = _run()
    dying = _monster(state, "dying", "dying")
    dying.stats.hp = dying.stats.max_hp = 999
    dying.stats.accuracy = 99

    resolve_enemy_attack(state, dying, state.player)

    assert dying.statuses.get("bleed", 0) > 0, "the blow cost it nothing"


# -- the hush --------------------------------------------------------------
def test_a_hush_stops_the_purse_while_it_stands():
    state = _run()
    hush = _monster(state, "hush", "hush")
    battle = Battle(state, [hush])

    assert battle._hushed(), "a hush that does not hush"

    hush.stats.hp = 0
    hush.alive = False
    assert not battle._hushed(), "the silence outlived the thing that made it"


# -- the picker ------------------------------------------------------------
def test_a_picker_takes_coin_and_leaves():
    state = _run()
    picker = _monster(state, "picker", "picker")
    picker.stats.accuracy = 99
    state.gold = 20

    resolve_enemy_attack(state, picker, state.player)

    assert state.gold < 20, "the purse was never touched"
    assert picker.stolen, "it does not remember what it took"

    # And in the arena, hurt enough, it goes -- taking the coin with it.
    battle = Battle(state, [picker])
    picker.stats.hp = 1
    battle._enemy_acts(picker, [])
    assert picker not in battle.enemies, "the picker stayed to be killed"


# -- the kindly one --------------------------------------------------------
def test_the_kindly_one_leaves_when_it_is_paid():
    state = _run()
    kindly = _monster(state, "kindly", "kindly")
    state.encounter = kindly
    state.gold = KINDLY_PRICE + 2

    assert pay_the_kindly_one(state)
    assert state.gold == 2, "the price was not the price"
    assert kindly not in state.enemies and state.encounter is None

    # And an empty purse cannot buy it off.
    state.encounter = _monster(state, "kindly", "kindly")
    state.gold = 0
    assert not pay_the_kindly_one(state)


# -- the lid ---------------------------------------------------------------
def test_a_mimic_chest_is_a_jaw():
    from neverdeads_revenge.game.actions import perform_action
    from neverdeads_revenge.game.actions import Action
    from neverdeads_revenge.world.items import make_chest

    state = _run()
    chest = make_chest("rot", None, mimic=True)
    state.dungeon_map.items[state.player.position] = chest

    perform_action(state, Action.OPEN_CHEST)

    assert state.encounter is not None, "the lid did not bite"
    assert state.encounter.behaviour == "mimic"
    assert state.encounter.name == "lid"
    # It is a monster encounter and not a bargain: nothing was ever on offer, so
    # nothing is charged. A curse here read as the chest's price and made the
    # jaw look like a chest that had simply gone wrong.
    assert state.curses == [], "the lid charged a price it never named"


def test_the_wager_opens_the_same_lid_and_pays_no_fame_for_it():
    """`f` opens the lid exactly as `enter` does: the jaw does not take wagers.

    Without this the fame answer was a way to make a mimic chest vanish for free
    -- no curse, no fight, no sword -- which is the one answer to a chest that
    should never be the safe one.
    """
    from neverdeads_revenge.game.actions import Action, perform_action
    from neverdeads_revenge.world.items import make_chest

    state = _run()
    state.dungeon_map.items[state.player.position] = make_chest(
        "rot", None, mimic=True
    )
    fame = state.fame

    perform_action(state, Action.TAKE_FAME)

    assert state.encounter is not None and state.encounter.name == "lid"
    assert state.curses == [], "the lid charged a price it never named"
    assert state.fame == fame, "there was no courage in it, and no coin"


# -- the echo --------------------------------------------------------------
def test_the_echo_waits_for_the_deep_floors_and_never_takes_a_walk():
    from neverdeads_revenge.core.rng import Rng
    from neverdeads_revenge.game.actors import pick_enemy_template

    shallow = {pick_enemy_template(Rng(seed), 1).key for seed in range(200)}
    assert "echo" not in shallow, "the boss was on the first floor"

    deep = {pick_enemy_template(Rng(seed), 6).key for seed in range(400)}
    assert "echo" in deep, "the boss never comes at all"


# -- the picker ------------------------------------------------------------
def test_the_picker_is_a_purse_worth_catching_and_not_worth_the_chase():
    """More gold, far more health, and much rarer than it was.

    The picker is not a fight, it is a decision: forty-five coins is a run's
    economy, and sixty health is three turns of standing still while the rest of
    the room closes. Both numbers are the choice, so both are held here -- and so
    is the rarity, because a purse that turns up as often as a ghoul is a purse
    and not a decision at all.
    """
    picker = ENEMIES["picker"]

    assert picker.gold[1] >= 25, "chasing it is not worth the turns"
    assert picker.stats.max_hp >= 50, "it dies before the choice is made"

    shallow = [
        template.weight
        for template in ENEMIES.values()
        if template.weight and template.key != "picker" and template.min_depth <= 2
    ]
    assert picker.weight < min(shallow), "the purse is as common as the monsters"


def test_the_lid_is_in_the_queue_and_not_only_in_the_room():
    """A mimic that is not scheduled can never take a turn.

    Fleeing the ambush used to leave the lid standing on the floor forever: it
    was in ``enemies`` but never in the queue, so the floor had a jaw on it that
    could not move.
    """
    from neverdeads_revenge.game.actions import Action, perform_action
    from neverdeads_revenge.world.items import make_chest

    state = _run()
    state.dungeon_map.items[state.player.position] = make_chest(
        "rot", None, mimic=True
    )

    perform_action(state, Action.OPEN_CHEST)

    lid = state.encounter
    assert lid is not None and lid.name == "lid"
    assert lid in state.turn_queue, "the lid was never scheduled"


# -- the ten that ask about the room ---------------------------------------
def _battle(state, foes):
    from neverdeads_revenge.game.battle import Battle

    battle = Battle(state, foes)
    battle.begin()
    return battle


def test_the_idle_sleeps_until_it_is_woken():
    """A sleeper that acts is a monster you cannot leave. Hit it or stand by it."""
    from neverdeads_revenge.game.actions import take_turn
    from neverdeads_revenge.world.tiles import Tile

    state = _run()
    sleeper = _monster(state, "idle", "idle")
    spot = (state.player.position[0] + 2, state.player.position[1])
    state.dungeon_map.set_tile(spot, Tile.FLOOR)
    sleeper.position = spot
    state.refresh_vision()

    assert take_turn(state, sleeper) is False, "the idle spent a turn asleep"
    assert sleeper.awake is False

    resolve_player_attack(state, sleeper)
    assert sleeper.awake is True, "a blow did not wake it"


def test_the_twin_that_is_left_stops_grieving():
    from neverdeads_revenge.game.actions import _on_death
    from neverdeads_revenge.game.actors import Stats

    state = _run()
    first = _monster(state, "twin", "twin")
    second = _monster(state, "twin", "twin")
    first.stats.max_hp = first.stats.hp = 40
    low, high = first.stats.damage

    _on_death(state, second)

    assert first.stats.hp == first.stats.max_hp, "the survivor did not get up"
    assert first.stats.damage == (low * 2, high * 2), "the survivor did not get angry"


def test_the_debt_is_paid_by_the_next_room():
    from neverdeads_revenge.game.actions import _on_death
    from neverdeads_revenge.game.battle import encounter_around

    state = _run()
    debtor = _monster(state, "debt", "debt")
    _on_death(state, debtor)
    assert state.debt == 1, "the debt was cancelled by dying"

    trigger = _monster(state, "ghoul", "ghoul")
    low, high = trigger.stats.damage
    group = encounter_around(state, trigger)

    assert state.debt == 0, "the debt was never collected"
    assert trigger in group
    assert trigger.stats.damage == (low + 2, high + 2), "the room did not pay"


def test_the_judge_reads_every_curse_aloud():
    from neverdeads_revenge.game.actions import perform_action, Action
    from neverdeads_revenge.game.curses import CURSES

    state = _run()
    state.add_curse(CURSES["wither"])
    state.add_curse(CURSES["famine"])
    judge = _monster(state, "judge", "judge")
    judge.stats.hp = judge.stats.max_hp = 999
    battle = _battle(state, [judge])
    hp = state.player.hp

    battle.choose("attack", judge)

    assert state.player.hp <= hp - 2, "two curses cost less than two health"


def test_the_leech_barely_feels_steel_and_comes_apart_at_a_wound():
    from neverdeads_revenge.game.actions import inflict, tick_statuses
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run

    def one(template: str) -> int:
        state = start_run(HEROES["noxx"], seed=3)
        state.player.stats.accuracy = 99
        foe = make_enemy(ENEMIES[template], state.player.position)
        foe.stats.max_hp = foe.stats.hp = 999
        state.enemies = [foe]
        return resolve_player_attack(state, foe).damage

    though = one("leech")
    plain = one("ghoul")

    assert though == max(1, round(plain * 0.25)), (though, plain)

    state = _run()
    leech = _monster(state, "leech", "leech")
    leech.stats.max_hp = leech.stats.hp = 999
    inflict(state, leech, ("bleed",), source=state.player)
    before = leech.stats.hp
    tick_statuses(state, leech)
    assert before - leech.stats.hp == 4, "a bleed is not double on the leech"


def test_the_quiet_keeps_the_bottle_corked():
    from neverdeads_revenge.world.items import ITEMS, make_item

    state = _run()
    state.inventory.append(make_item(ITEMS["potion"]))
    state.player.stats.hp = 5
    quiet = _monster(state, "quiet", "quiet")
    battle = _battle(state, [quiet])

    assert battle.drinks_refused, "the rule is not askable before the refusal"

    battle.choose("item")

    assert len(state.inventory) == 1, "the bottle was drunk anyway"

    quiet.stats.hp = 0
    assert not battle.drinks_refused, "the rule outlived the quiet"


def test_the_unbroken_never_swings_and_gives_half_back():
    state = _run()
    state.player.stats.accuracy = 99
    stone = _monster(state, "unbroken", "unbroken")
    stone.stats.max_hp = stone.stats.hp = 999

    hp = state.player.hp
    outcome = resolve_player_attack(state, stone)
    assert state.player.hp == hp - max(1, round(outcome.damage * 0.5)), (
        "the unbroken did not give half of it back"
    )

    from neverdeads_revenge.game.battle import Battle

    hp = state.player.hp
    battle = Battle(state, [stone])
    events = battle.choose("attack", stone)
    swung = [
        event
        for event in events
        if getattr(event, "actor", None) is stone and type(event).__name__ == "Struck"
    ]
    assert not swung, "the unbroken swung at somebody"


def test_the_eater_takes_a_wound_off_its_friend():
    state = _run()
    eater = _monster(state, "eater", "eater")
    friend = _monster(state, "ghoul", "ghoul")
    friend.stats.hp = friend.stats.max_hp = 999
    friend.statuses["bleed"] = 5
    friend.status_stacks["bleed"] = 2
    eater.stats.hp = 10
    battle = _battle(state, [eater, friend])

    battle.choose("attack", friend)

    assert friend.status_stacks.get("bleed") == 1, "the eater took no stack"
    assert eater.stats.hp > 10, "the eater did not grow on it"


def test_the_notary_bills_the_floor_and_is_fed_by_it():
    from neverdeads_revenge.game.actions import _on_death

    state = _run()
    state.floor_kills = 5
    notary = _monster(state, "notary", "notary")
    notary.stats.hp = notary.stats.max_hp = 999
    state.enemies = [notary]

    from neverdeads_revenge.game.battle import Battle

    Battle(state, [notary])
    assert notary.stats.max_hp == 20, "the bill was not the floor's kills"

    notary.stats.hp = 10
    ghoul = make_enemy(ENEMIES["ghoul"], state.player.position)
    state.enemies.append(ghoul)
    _on_death(state, ghoul)
    assert notary.stats.hp == 14, "a kill on the floor did not feed it"


def test_the_reaver_takes_the_blade_and_gives_it_back():
    from neverdeads_revenge.game.battle import Battle
    from neverdeads_revenge.world.items import ITEMS, make_item

    state = _run()
    state.player.equipment["weapon"] = make_item(ITEMS["tooth"])
    reaver = _monster(state, "reaver", "reaver")

    battle = Battle(state, [reaver])
    assert "weapon" not in state.player.equipment, "the reaver took nothing"

    battle.begin()
    battle._close_the_fight()

    assert state.player.equipment["weapon"].item_id == "tooth", "the blade never came back"
