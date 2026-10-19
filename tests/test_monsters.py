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


# -- the echo --------------------------------------------------------------
def test_the_echo_waits_for_the_deep_floors_and_never_takes_a_walk():
    from neverdeads_revenge.core.rng import Rng
    from neverdeads_revenge.game.actors import pick_enemy_template

    shallow = {pick_enemy_template(Rng(seed), 1).key for seed in range(200)}
    assert "echo" not in shallow, "the boss was on the first floor"

    deep = {pick_enemy_template(Rng(seed), 6).key for seed in range(400)}
    assert "echo" in deep, "the boss never comes at all"
