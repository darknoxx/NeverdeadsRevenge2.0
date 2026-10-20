"""The blades whose worth is a rule, and the ones that ask a price.

Every weapon in this game is a sentence before it is a number -- and the newest
ones are sentences the fight has to *read*: a first blow worth seven once, an edge
that wants the hero above half his blood, a ledger that fills as the floor does, a
debt paid in coin, a price paid in blood, a fire that does not stop with the thing
it started on, and a point of armour gone *through* rather than around.

The tests here are the sentences, one each, because a rule that is only written
down in a comment is a rule the next change is free to break.
"""

from __future__ import annotations

from dataclasses import replace

from neverdeads_revenge.game.actors import HEROES, Stats
from neverdeads_revenge.game.actions import _weapon_rule_bonus, resolve_player_attack
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.world.items import ITEMS


def _run():
    """A run, with a hero who cannot miss, so a test is about the rule."""
    state = start_run(HEROES["noxx"], 7)
    state.player.stats.accuracy = 99
    return state


def _wield(state, key: str):
    state.player.equipment["weapon"] = ITEMS[key]
    return ITEMS[key]


# -- through armour -----------------------------------------------------------
def test_the_needle_goes_through_the_coat_rather_than_around_it():
    """Pierce is subtracted from what armour *is*, in the one place armour is."""
    plate = Stats(max_hp=30, hp=30, armor=3)

    assert plate.hurt(10) == 7, "armour stopped nothing it should have"
    assert plate.hurt(10, pierce=2) == 9, "two points of coat still stopped the blow"
    assert plate.hurt(10, pierce=9) == 10, "pierce went through more than the armour"

    state = _run()
    assert state.player.pierce == 0, "a fist pierces nothing"
    _wield(state, "needle")
    assert state.player.pierce == 2


# -- the first blow ----------------------------------------------------------
def test_the_first_blow_is_worth_seven_once():
    """The fight already knows which blow was first; the blade just reads it.

    Two runs of the same seed, one with the rule and one with the same blade and
    no rule: the first blow is seven apart and the second is the same. The target
    is given a deep well of health so the comparison is about damage and not
    about which blow finished it.
    """
    plain = replace(ITEMS["first_blow"], rule="")
    damages: dict[str, tuple[int, int]] = {}
    for label, template in (("plain", plain), ("rule", ITEMS["first_blow"])):
        state = _run()
        state.player.equipment["weapon"] = template
        target = state.enemies[0]
        target.stats.max_hp = target.stats.hp = 999
        damages[label] = (
            resolve_player_attack(state, target).damage,
            resolve_player_attack(state, target).damage,
        )

    assert damages["rule"][0] == damages["plain"][0] + 7, damages
    assert damages["rule"][1] == damages["plain"][1], "the blade paid out twice"


# -- the coward's edge -------------------------------------------------------
def test_the_cowards_edge_is_worth_four_only_above_half():
    state = _run()
    _wield(state, "coward")
    assert _weapon_rule_bonus(state, first=False) == 4

    state.player.stats.hp = state.player.max_hp // 2
    assert _weapon_rule_bonus(state, first=False) == 0, "it paid a dying hero"

    state.player.stats.hp = state.player.max_hp
    _wield(state, "tooth")
    assert _weapon_rule_bonus(state, first=False) == 0, "the rusted tooth has no rule"


# -- the ledger --------------------------------------------------------------
def test_the_ledger_counts_the_floor_and_forgets_it_below():
    """One a kill, to five, and a new floor starts the page empty."""
    state = _run()
    _wield(state, "ledger")

    state.floor_kills = 0
    assert _weapon_rule_bonus(state, first=False) == 0
    state.floor_kills = 3
    assert _weapon_rule_bonus(state, first=False) == 3
    state.floor_kills = 99
    assert _weapon_rule_bonus(state, first=False) == 5, "the ledger ran past its cap"

    state.floor_kills = 7
    state.build_floor(2)
    assert state.floor_kills == 0, "the ledger carried a kill onto the next floor"


# -- the price in blood ------------------------------------------------------
def test_the_blood_price_bleeds_the_hand_that_swings_it():
    state = _run()
    _wield(state, "blood_price")
    target = state.enemies[0]
    target.stats.max_hp = target.stats.hp = 999

    resolve_player_attack(state, target)

    assert state.player.statuses.get("bleed", 0) > 0, "the price was never charged"
    assert target.statuses.get("bleed", 0) == 0, "the blade bled the wrong one"


# -- the debt ----------------------------------------------------------------
def test_the_debtor_takes_a_coin_for_every_kill():
    from neverdeads_revenge.game.actions import _on_death

    state = _run()
    _wield(state, "debtor")
    state.gold = 3

    _on_death(state, state.enemies[0])
    assert state.gold == 2, "the debtor did not take its coin"

    state.gold = 0
    _on_death(state, state.enemies[1])
    assert state.gold == 0, "the debtor took a coin that was not there"


# -- the fire that spreads ---------------------------------------------------
def test_the_ash_kiss_passes_the_fire_to_another_of_them():
    """A kill passes the burn on -- to *one* of them, and not to the corpse."""
    from neverdeads_revenge.game.actions import _on_death

    state = _run()
    _wield(state, "kiss")
    dying = state.enemies[0]

    _on_death(state, dying)

    burning = [
        one for one in state.enemies if one is not dying and one.statuses.get("burn", 0)
    ]
    assert len(burning) == 1, f"the fire went to {len(burning)} of them"
    assert dying.statuses.get("burn", 0) == 0, "the corpse is burning"


# -- the two new statuses ----------------------------------------------------
def test_the_patient_and_the_numb_are_the_sharpest_of_their_kind():
    from neverdeads_revenge.game.statuses import status_by_key

    patient = status_by_key("taint")
    numb = status_by_key("numb")
    poison = status_by_key("poison")
    chill = status_by_key("chill")

    assert patient is not None and patient.turns > poison.turns
    assert patient.damage == poison.damage, "the long rot is a different wound"
    assert numb is not None and numb.speed_factor < chill.speed_factor
    assert numb.turns < chill.turns, "the deeper cold is also the shorter one"


# -- what the card says ------------------------------------------------------
def test_every_rule_blade_says_what_its_rule_does_and_what_it_costs():
    """The card is where a blade is met, so the card may not lie by omission.

    THE FIRST BLOW has no modifiers at all: a card built out of numbers alone
    told the player it does nothing. And the numbers in the words are the ones
    the fight reads -- seven, four and five live in ``actions``, and a sentence
    that drifted away from them would be a rumour.
    """
    from neverdeads_revenge.game.actions import COWARD_EDGE, FIRST_BLOW, LEDGER_CAP
    from neverdeads_revenge.game.shop import RULE_TEXT, describe_item
    from neverdeads_revenge.world.items import ITEMS

    for template in ITEMS.values():
        if template.kind != "weapon" or not template.rule:
            continue
        assert template.rule in RULE_TEXT, f"{template.key} says nothing about its rule"
        assert RULE_TEXT[template.rule] in describe_item(template)

    assert str(FIRST_BLOW) in RULE_TEXT["first_blow"]
    assert str(COWARD_EDGE) in RULE_TEXT["coward"]
    assert str(LEDGER_CAP) in RULE_TEXT["ledger"]
    assert "bleeding" in describe_item(ITEMS["blood_price"]), "the price is not a secret"
