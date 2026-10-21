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
