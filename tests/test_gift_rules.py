"""Tests for the nine gifts that change what a turn is.

A gift is a rule, so each test is a sentence about the rule: the road cuts what
follows you, the walk loads the blow, the debt is owed back, the cornered hero
hits twice, the dark shows what is behind the wall, the circle holds, the wound
pays, a stranger gives, and the glass does not go to waste.

They are the loudest gifts in the game, so each one is also tested for the thing
that keeps it fair: what happens *without* it.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.core.direction import Direction
from neverdeads_revenge.game import actions as actions_module
from neverdeads_revenge.game.actions import (
    HUNGRY_ROAD_DAMAGE,
    HUNGRY_ROAD_TRAIL,
    LAST_BREATH_EVASION,
    MOMENTUM_MAX,
    SALT_CIRCLE_WAITS,
    Action,
    _player_takes_damage,
    _resolve_player_attack,
    _talk,
    perform_action,
    take_turn,
)
from neverdeads_revenge.game.actors import ENEMIES, NOXX, make_enemy, make_npc
from neverdeads_revenge.game.combat import AttackOutcome
from neverdeads_revenge.game.npcs import NPCS
from neverdeads_revenge.game.state import LAST_BREATH_HP, LogKind, start_run
from neverdeads_revenge.world.items import ITEMS, make_coin, make_item
from neverdeads_revenge.world.tiles import Tile


# -- helpers ------------------------------------------------------------------
def _run(*gifts: str, seed: int = 3):
    """A run with these gifts and room to walk around the player."""
    state = start_run(NOXX, seed=seed)
    state.gifts |= set(gifts)
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            state.dungeon_map.set_tile(
                (state.player.position[0] + dx, state.player.position[1] + dy),
                Tile.FLOOR,
            )
    return state


def _beside(state, key: str = "ghoul", hp: int = 999, damage=(0, 0)):
    """A monster next to the player that cannot miss and cannot be missed."""
    enemy = make_enemy(
        ENEMIES[key], (state.player.position[0] + 1, state.player.position[1])
    )
    enemy.stats.hp = enemy.stats.max_hp = hp
    enemy.stats.armor = 0
    enemy.stats.evasion = 0
    enemy.stats.damage = damage
    state.enemies = [enemy]
    state.turn_queue = type(state.turn_queue)([state.player, enemy])
    state.refresh_vision()
    return enemy


def _blade(state, damage: int = 10) -> None:
    """A fixed, unmissable blow, so the dice stop arguing with the rule."""
    state.player.stats.damage = (damage, damage)
    state.player.stats.accuracy = 99
    state.player.stats.crit_chance = 0.0


# -- THE HUNGRY ROAD ----------------------------------------------------------
def test_the_hungry_road_leaves_glass_where_the_step_began():
    state = _run("hungry_road")
    left_behind = state.player.position

    perform_action(state, Action.MOVE_EAST)

    assert state.trail.get(left_behind) == HUNGRY_ROAD_DAMAGE


def test_the_glass_cuts_whatever_walks_onto_it():
    state = _run("hungry_road")
    glass = state.player.position
    perform_action(state, Action.MOVE_EAST)

    walker = make_enemy(ENEMIES["ghoul"], (glass[0] - 1, glass[1]))
    state.enemies = [walker]
    state.turn_queue = type(state.turn_queue)([walker])

    take_turn(state, walker)

    assert walker.hp == walker.max_hp - HUNGRY_ROAD_DAMAGE
    assert "bleed" in walker.statuses, "the glass does not just cut, it stays in"
    assert glass not in state.trail, "the glass was not spent"


def test_the_trail_is_bounded_so_the_floor_is_not_salted():
    """A path behind the hero, not a minefield they set and forgot."""
    state = _run("hungry_road")

    for _ in range(HUNGRY_ROAD_TRAIL + 6):
        perform_action(state, Action.MOVE_EAST)

    assert len(state.trail) == HUNGRY_ROAD_TRAIL


def test_the_hero_can_cross_their_own_glass():
    """It is the hero's own rule; a floor that cut them would be a floor they
    could not retreat across."""
    state = _run("hungry_road")
    start = state.player.position
    perform_action(state, Action.MOVE_EAST)
    before = state.player.hp

    perform_action(state, Action.MOVE_WEST)  # back over the glass

    assert state.player.hp == before
    assert start in state.trail, "walking over it unset it"


def test_without_the_gift_nothing_is_left_on_the_floor():
    state = _run()

    perform_action(state, Action.MOVE_EAST)

    assert state.trail == {}


# -- MOMENTUM -----------------------------------------------------------------
def test_momentum_loads_on_a_straight_line():
    state = _run("momentum")

    for _ in range(3):
        perform_action(state, Action.MOVE_EAST)

    assert state.momentum == 3
    assert state.momentum_direction is Direction.EAST


def test_turning_starts_a_new_line():
    state = _run("momentum")
    for _ in range(3):
        perform_action(state, Action.MOVE_EAST)

    perform_action(state, Action.MOVE_WEST)

    assert state.momentum == 1, "the new line starts with the step that began it"
    assert state.momentum_direction is Direction.WEST


def test_the_charge_is_spent_on_the_blow():
    state = _run("momentum")
    _blade(state, damage=10)
    for _ in range(2):
        perform_action(state, Action.MOVE_EAST)
    enemy = _beside(state, hp=999)

    perform_action(state, Action.MOVE_EAST)  # the attack, into the monster

    assert enemy.hp == 999 - (10 + 2), "the walk did not load the blow"
    assert state.momentum == 0, "the charge was not spent"


def test_the_charge_stops_at_the_ceiling():
    state = _run("momentum")

    for _ in range(MOMENTUM_MAX + 4):
        perform_action(state, Action.MOVE_EAST)

    assert state.momentum == MOMENTUM_MAX


def test_waiting_loses_the_charge():
    state = _run("momentum")
    for _ in range(2):
        perform_action(state, Action.MOVE_EAST)

    perform_action(state, Action.WAIT)

    assert state.momentum == 0


def test_without_the_gift_the_walk_loads_nothing():
    state = _run()

    for _ in range(3):
        perform_action(state, Action.MOVE_EAST)

    assert state.momentum == 0


# -- THE DEBT OF BLOOD --------------------------------------------------------
def test_the_debt_is_owed_back_on_the_next_blow():
    state = _run("blood_debt")
    _blade(state, damage=10)
    state.blood_debt = 7
    enemy = _beside(state, hp=999)

    _resolve_player_attack(state, enemy)

    assert enemy.hp == 999 - (10 + 7)
    assert state.blood_debt == 0, "the debt was not cleared"


def test_a_blow_you_take_is_what_the_debt_is():
    state = _run("blood_debt")
    enemy = _beside(state)

    _player_takes_damage(
        state, enemy, AttackOutcome(hit=True, crit=False, damage=6, killed=False)
    )

    assert state.blood_debt == 6


def test_a_miss_does_not_spend_the_debt():
    state = _run("blood_debt")
    state.blood_debt = 9
    state.player.stats.accuracy = -99  # a swing that cannot land
    enemy = _beside(state, hp=999)
    enemy.stats.evasion = 99

    for _ in range(5):
        _resolve_player_attack(state, enemy)

    assert state.blood_debt == 9, "a swing that missed is not the blow it was owed on"


def test_the_debt_starts_the_floor_at_nothing():
    state = _run("blood_debt")
    state.blood_debt = 12

    state.build_floor(2)

    assert state.blood_debt == 0


# -- THE LAST BREATH ----------------------------------------------------------
def test_a_cornered_blow_lands_twice():
    state = _run("last_breath")
    _blade(state, damage=10)
    state.player.stats.hp = LAST_BREATH_HP
    enemy = _beside(state, hp=999)

    _resolve_player_attack(state, enemy)

    assert enemy.hp == 999 - 20


def test_above_the_line_the_blow_is_ordinary():
    state = _run("last_breath")
    _blade(state, damage=10)
    state.player.stats.hp = LAST_BREATH_HP + 1
    enemy = _beside(state, hp=999)

    _resolve_player_attack(state, enemy)

    assert enemy.hp == 999 - 10


def test_the_cornered_hero_is_harder_to_hit(monkeypatch):
    """The defensive half, checked at the seam: what the enemy's swing is told."""
    seen: dict = {}

    def spy(attacker, defender, rng, **kwargs):
        seen.update(kwargs)
        return AttackOutcome(hit=False, crit=False, damage=0, killed=False, dodged=True)

    monkeypatch.setattr(actions_module, "attack", spy)

    state = _run("last_breath")
    enemy = _beside(state)

    state.player.stats.hp = LAST_BREATH_HP
    actions_module._resolve_enemy_attack(state, enemy, state.player)
    assert seen["evasion_bonus"] == LAST_BREATH_EVASION

    seen.clear()
    state.player.stats.hp = LAST_BREATH_HP + 1
    actions_module._resolve_enemy_attack(state, enemy, state.player)
    assert seen["evasion_bonus"] == 0


# -- THE SALT CIRCLE ----------------------------------------------------------
def test_three_waits_in_a_row_close_the_circle():
    state = _run("salt_circle")
    state.player.stats.hp = 500
    enemy = _beside(state, damage=(5, 5))

    for _ in range(SALT_CIRCLE_WAITS):
        perform_action(state, Action.WAIT)

    assert any(
        "cannot find you" in entry.text and entry.kind is LogKind.PLAIN
        for entry in state.log
    ), "the third wait did not raise the ward"


def test_a_step_breaks_the_run_of_waits():
    state = _run("salt_circle")
    state.player.stats.hp = 500
    _beside(state, damage=(5, 5))

    perform_action(state, Action.WAIT)
    perform_action(state, Action.WAIT)
    perform_action(state, Action.MOVE_EAST)
    perform_action(state, Action.WAIT)

    assert not any("cannot find you" in entry.text for entry in state.log)
    assert state.waits_in_a_row == 1


def test_without_the_gift_waiting_buys_nothing():
    state = _run()
    state.player.stats.hp = 500
    _beside(state, damage=(5, 5))

    for _ in range(SALT_CIRCLE_WAITS):
        perform_action(state, Action.WAIT)

    assert state.salt_ward == 0
    assert not any("cannot find you" in entry.text for entry in state.log)


# -- THE BLOOD PRICE ----------------------------------------------------------
def test_a_blow_you_take_scatters_coin():
    state = _run("blood_price")
    enemy = _beside(state)

    _player_takes_damage(
        state, enemy, AttackOutcome(hit=True, crit=False, damage=6, killed=False)
    )

    pile = state.dungeon_map.item_at(state.player.position)
    assert pile is not None and pile.kind == "coin"
    assert pile.gold == 6


def test_the_coin_merges_with_a_pile_already_there():
    state = _run("blood_price")
    enemy = _beside(state)
    state.dungeon_map.add_item(state.player.position, make_coin(4))

    _player_takes_damage(
        state, enemy, AttackOutcome(hit=True, crit=False, damage=6, killed=False)
    )

    pile = state.dungeon_map.item_at(state.player.position)
    assert pile is not None and pile.kind == "coin"
    assert pile.gold == 10, "two piles in one square should be one bigger pile"


def test_coin_never_overwrites_something_lying_there():
    """Same rule as a monster's purse: loot is not thrown away to make room."""
    state = _run("blood_price")
    enemy = _beside(state)
    state.dungeon_map.add_item(state.player.position, make_item(ITEMS["potion"]))

    _player_takes_damage(
        state, enemy, AttackOutcome(hit=True, crit=False, damage=6, killed=False)
    )

    lying = state.dungeon_map.item_at(state.player.position)
    assert lying is not None and lying.kind == "draught", "the potion was overwritten"


def test_without_the_gift_a_wound_pays_nothing():
    state = _run()
    enemy = _beside(state)

    _player_takes_damage(
        state, enemy, AttackOutcome(hit=True, crit=False, damage=6, killed=False)
    )

    assert state.dungeon_map.item_at(state.player.position) is None


# -- THE DARK KNOWS -----------------------------------------------------------






# -- THE KINDNESS -------------------------------------------------------------
def test_whoever_you_meet_hands_you_a_draught():
    state = _run("kindness")
    npc = make_npc(NPCS["tally"], (state.player.position[0] + 1, state.player.position[1]))
    state.npcs = [npc]

    _talk(state, npc)

    assert [item.name for item in state.inventory] == ["potion"]


def test_the_same_person_gives_once():
    state = _run("kindness")
    npc = make_npc(NPCS["tally"], (state.player.position[0] + 1, state.player.position[1]))
    state.npcs = [npc]

    _talk(state, npc)
    _talk(state, npc)

    assert len(state.inventory) == 1, "a person is not a well"


def test_without_the_gift_nobody_gives():
    state = _run()
    npc = make_npc(NPCS["tally"], (state.player.position[0] + 1, state.player.position[1]))
    state.npcs = [npc]

    _talk(state, npc)

    assert state.inventory == []


# -- NOTHING WASTED -----------------------------------------------------------
def test_a_draught_shatters_into_what_is_beside_you():
    state = _run("nothing_wasted")
    state.player.stats.hp = 5
    state.inventory.append(make_item(ITEMS["potion"]))
    enemy = _beside(state, hp=999)

    perform_action(state, Action.QUAFF)

    assert enemy.hp == 999 - 4


def test_without_the_gift_the_glass_is_only_glass():
    state = _run()
    state.player.stats.hp = 5
    state.inventory.append(make_item(ITEMS["potion"]))
    enemy = _beside(state, hp=999)

    perform_action(state, Action.QUAFF)

    assert enemy.hp == 999


def test_the_shards_can_finish_something():
    """A kill is a kill: the glass counts for the coins and the level like any
    other blow."""
    state = _run("nothing_wasted")
    state.player.stats.hp = 5
    state.inventory.append(make_item(ITEMS["potion"]))
    _beside(state, hp=3)

    perform_action(state, Action.QUAFF)

    assert state.kills == 1
    assert state.enemies == []


# -- what the player is shown -------------------------------------------------




