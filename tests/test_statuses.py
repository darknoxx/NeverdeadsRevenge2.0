"""Tests for what a blow leaves behind.

A status is the one kind of damage that does not need a second swing, so most of
what there is to test is *when* it runs: on the victim's own turn, for as many of
the victim's turns as it says, and not twice as hard because it was applied
twice.
"""

from __future__ import annotations

from neverdeads_revenge.game.actions import (
    inflict,
    _inflicts_of,
    _thorns_of,
    tick_statuses,
)
from neverdeads_revenge.game.actors import ENEMIES, NOXX, make_enemy
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.game.statuses import STATUSES
from neverdeads_revenge.world.items import ITEMS, make_item


def _enemy(state, key: str = "ghoul"):
    enemy = make_enemy(ENEMIES[key], (state.player.position[0] + 2, state.player.position[1]))
    state.enemies = [enemy]
    return enemy


# -- the clock ---------------------------------------------------------------
def test_a_bleeding_thing_loses_health_on_its_own_turn():
    state = start_run(NOXX, seed=3)
    enemy = _enemy(state)
    before = enemy.hp

    inflict(state, enemy, ("bleed",))
    tick_statuses(state, enemy)

    assert enemy.hp == before - STATUSES["bleed"].damage


def test_a_status_runs_out_after_the_turns_it_promises():
    state = start_run(NOXX, seed=3)
    enemy = _enemy(state)
    before = enemy.hp

    inflict(state, enemy, ("bleed",))
    for _ in range(STATUSES["bleed"].turns):
        tick_statuses(state, enemy)

    assert "bleed" not in enemy.statuses, "it never wore off"
    # Every one of its turns hurt, including the last.
    assert enemy.hp == before - STATUSES["bleed"].damage * STATUSES["bleed"].turns

    # And then it is over.
    tick_statuses(state, enemy)
    assert enemy.hp == before - STATUSES["bleed"].damage * STATUSES["bleed"].turns


def test_a_second_wound_deepens_the_bleeding():
    """Two cuts open a deeper wound, three is the ceiling, and four does nothing.

    It used to be the other way round -- a second wound only refreshed the same
    shallow cut, which made a fast cheap blade a way to keep a wound *alive*
    rather than a way to open one. The ceiling is what keeps the other reading
    from happening: three stacks is a wound that is a problem, and a fourth is
    not a sentence.
    """
    state = start_run(NOXX, seed=3)
    enemy = _enemy(state)

    inflict(state, enemy, ("bleed",))
    assert enemy.status_stacks["bleed"] == 1, "one cut was already two deep"
    enemy.statuses["bleed"] = 1  # nearly over
    inflict(state, enemy, ("bleed",))

    assert enemy.statuses["bleed"] == STATUSES["bleed"].turns, "the clock restarted"
    assert enemy.status_stacks["bleed"] == 2

    before = enemy.hp
    tick_statuses(state, enemy)
    assert enemy.hp == before - 2 * STATUSES["bleed"].damage, "it bled once, not twice"

    for _ in range(4):
        inflict(state, enemy, ("bleed",))
    assert enemy.status_stacks["bleed"] == 3, "the wound went past its ceiling"


def test_a_poison_refreshes_and_never_deepens():
    """Only the wounds stack. The viper already punishes a slow kill, and a
    poison that deepened as well would make it a damage multiplier instead."""
    state = start_run(NOXX, seed=3)
    enemy = _enemy(state)

    inflict(state, enemy, ("poison",))
    inflict(state, enemy, ("poison",))

    assert enemy.status_stacks.get("poison", 1) == 1


def test_chill_slows_the_victim_and_then_lets_it_go():
    state = start_run(NOXX, seed=3)
    enemy = _enemy(state)
    normal = enemy.speed

    inflict(state, enemy, ("chill",))

    assert enemy.speed < normal
    assert enemy.speed == normal * STATUSES["chill"].speed_factor

    for _ in range(STATUSES["chill"].turns):
        tick_statuses(state, enemy)

    assert enemy.speed == normal, "the chill never let go"


# -- who it kills ------------------------------------------------------------
def test_a_monster_that_bleeds_to_death_is_still_a_kill():
    """The coins, the level and the REVENGE all still belong to the player."""
    state = start_run(NOXX, seed=3)
    enemy = _enemy(state)
    enemy.stats.hp = 1
    kills = state.kills

    inflict(state, enemy, ("bleed",))
    tick_statuses(state, enemy)

    assert not enemy.alive
    assert state.kills == kills + 1
    assert enemy not in state.enemies


def test_the_player_can_bleed_to_death():
    state = start_run(NOXX, seed=3)
    state.player.stats.hp = 1

    inflict(state, state.player, ("bleed",))
    tick_statuses(state, state.player)

    assert state.over


# -- where it comes from -----------------------------------------------------
def test_a_blade_inflicts_what_its_template_says():
    state = start_run(NOXX, seed=3)

    assert _inflicts_of(state.player) == ()

    state.player.equipment["weapon"] = make_item(ITEMS["wound"])
    assert _inflicts_of(state.player) == ("bleed",)

    state.player.equipment["weapon"] = make_item(ITEMS["depthless"])
    assert _inflicts_of(state.player) == ("bleed", "poison")


def test_a_monster_inflicts_what_its_template_says():
    state = start_run(NOXX, seed=3)
    enemy = _enemy(state)

    assert _inflicts_of(enemy) == enemy.inflicts


def test_a_coat_gives_back_what_its_template_says():
    state = start_run(NOXX, seed=3)

    assert _thorns_of(state.player) == 0

    state.player.equipment["armour"] = make_item(ITEMS["thorn_coat"])
    assert _thorns_of(state.player) == ITEMS["thorn_coat"].thorns


# -- and it is on the screen -------------------------------------------------


# -- and it is said where the player looks -----------------------------------
def test_a_blade_says_what_it_leaves_behind():
    """The sheet, the pack and the shop all read ``describe_item``, so this one
    function is the only place a status can be mentioned -- and a blade that
    opens a wound without saying so is a blade the player has to work out by
    watching a monster lose health it was not being hit for."""
    from neverdeads_revenge.game.shop import describe_item
    from neverdeads_revenge.world.items import ITEMS

    assert "bleeding" in describe_item(ITEMS["wound"])
    assert "poisoned" in describe_item(ITEMS["rot"])
    assert "burning" in describe_item(ITEMS["kiss"])
    assert "chilled" in describe_item(ITEMS["winter"])

    # The one that does two.
    both = describe_item(ITEMS["depthless"])
    assert "bleeding" in both and "poisoned" in both


def test_a_coat_says_what_it_gives_back():
    from neverdeads_revenge.game.shop import describe_item
    from neverdeads_revenge.world.items import ITEMS

    assert "thorns 2" in describe_item(ITEMS["thorn_coat"])
    assert "thorns 3" in describe_item(ITEMS["ashfall"])


def test_a_plain_blade_is_described_exactly_as_it_was_before():
    """Nothing gained a word it did not need."""
    from neverdeads_revenge.game.shop import describe_item
    from neverdeads_revenge.world.items import ITEMS

    assert describe_item(ITEMS["tooth"]) == "+1 damage"
    assert describe_item(ITEMS["edge"]) == "+4 damage, +10% crit"


def test_the_last_tick_of_a_wound_is_worth_every_stack_it_had():
    """A three-stack bleed deals its three stacks on the turn it runs out too.

    It used to deal six, six, then two: the stacks were popped before the last
    tick was counted, and the wound that had been deepest on the turn before was
    a scratch on the turn it ended.
    """
    state = start_run(NOXX, seed=3)
    enemy = _enemy(state)
    enemy.stats.hp = 999
    before = enemy.hp

    from neverdeads_revenge.game.statuses import STATUSES

    inflict(state, enemy, ("bleed", "bleed", "bleed"))
    dealt = []
    while enemy.statuses.get("bleed"):
        hp = enemy.hp
        tick_statuses(state, enemy)
        dealt.append(hp - enemy.hp)

    assert dealt == [STATUSES["bleed"].damage * 3] * 3, dealt
    assert before - enemy.hp == sum(dealt)
