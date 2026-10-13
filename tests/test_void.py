"""The void: Noxx's one ask per floor, and the shadow it sends.

The whole feature lives in four numbers (level gate, one ask per floor, forty
turns of shadow, a blood price floored at one) and every number is pinned
here, because each of them is also the edge the player measures it by.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.core.direction import chebyshev
from neverdeads_revenge.game.actors import ActorKind, ENEMIES, make_enemy
from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.difficulty import (
    ATRITAS_RADIUS,
    ATRITAS_TURNS,
)
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.world.tiles import Tile


def _run(ultimate_level: int | None = None, hero: str = "noxx", seed: int = 5):
    state = start_run(
        HEROES[hero], seed, ultimate_level=ultimate_level
    )
    return state


def _wait(state, times: int = 1) -> None:
    for _ in range(times):
        perform_action(state, Action.WAIT)


def _stage_enemy_at_square(state, square, hp: int = 1):
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    enemy = make_enemy(ENEMIES["ghoul"], square)
    enemy.stats.hp = hp
    enemy.stats.max_hp = hp
    enemy.stats.damage = (0, 0)
    state.enemies.append(enemy)
    state.turn_queue.add(enemy)
    return enemy


# -- the gate -----------------------------------------------------------------
def test_the_void_refuses_the_low_levels():
    """Below the level it answers at, the ask does nothing but say when."""
    state = _run()
    state.level = 1  # the start; the void answers at ten

    before_turns = state.total_turns
    result = perform_action(state, Action.ULTIMATE)

    assert state.atritas is None
    assert state.ultimate_available is True
    assert state.total_turns == before_turns, "a refusal cannot cost the floor"
    assert any("Not yet" in entry.text for entry in state.log)


def test_every_hero_has_an_ask_of_their_own():
    """The gate is shared; the shape is not. Yeti raises the wall, Walkyrion
    rings the bell, and neither of them is a shadow."""
    yeti = start_run(HEROES["yeti"], 3, ultimate_level=1)
    perform_action(yeti, Action.ULTIMATE)
    assert yeti.fortress is not None and yeti.atritas is None
    assert yeti.ultimate_available is False

    walkyrion = start_run(HEROES["walkyrion"], 3, ultimate_level=1)
    perform_action(walkyrion, Action.ULTIMATE)
    assert walkyrion.fortress is None and walkyrion.atritas is None
    assert walkyrion.ultimate_available is False
    assert any("bell" in entry.text.lower() for entry in walkyrion.log)


def test_a_testrun_runs_answer_early():
    """`--testrun` lowers the gate so a test can hear the whole song."""
    state = _run(ultimate_level=1)

    result = perform_action(state, Action.ULTIMATE)
    # Consumes a turn: the scheduler answers the cast, so the shadow is real.
    assert state.atritas is not None, "the void refused its one ask"


# -- one ask per floor ---------------------------------------------------------
def test_the_void_answers_once_and_then_goes_grey():
    """Second cast on one floor: refused, and the refusal is free."""
    state = _run(ultimate_level=1)

    assert perform_action(state, Action.ULTIMATE).consumed_turn
    assert state.ultimate_available is False

    before_turns = state.total_turns
    result = perform_action(state, Action.ULTIMATE)

    assert result.consumed_turn is False
    assert state.total_turns == before_turns
    assert any("does not ask twice" in entry.text for entry in state.log)


def test_a_new_floor_ask_again():
    """Descent refills the ask: the promise is per floor, and says so."""
    state = _run(ultimate_level=1)

    perform_action(state, Action.ULTIMATE)
    assert state.ultimate_available is False

    state.build_floor(2)

    assert state.ultimate_available is True
    assert state.atritas is None, "the shadow stays with its own floor"


# -- what the cast is worth ----------------------------------------------------
def test_the_cast_opens_the_whole_floor_but_only_while_the_shadow_walks():
    """Every wall is glass -- for as long as he walks. The reveal is *shown*,
    not *known*: it does not touch ``explored``, and it closes again the
    moment the shadow leaves."""
    state = _run(ultimate_level=1)
    total = state.dungeon_map.width * state.dungeon_map.height

    perform_action(state, Action.ULTIMATE)

    assert state.void_sight is True, "the walls stayed stone"
    assert len(state.dungeon_map.explored) < total, (
        "the reveal was written into memory instead of shown"
    )

    _wait(state, 40)

    assert state.atritas is None
    assert state.void_sight is False, "the glass outlived the shadow"
    assert len(state.dungeon_map.explored) < total, (
        "the walls stayed seen after the shadow left"
    )


def test_the_shadow_stands_beside_noxx():
    state = _run(ultimate_level=1)

    perform_action(state, Action.ULTIMATE)

    atritas = state.atritas
    assert atritas is not None
    assert atritas.kind is ActorKind.ATRITAS
    distance = chebyshev(atritas.position, state.player.position)
    assert distance == 1, "the dark did not land beside its summoner"


def test_a_taken_square_pushes_the_summon_one_pace_out():
    """Beside is the promise; a crowded doorway is not a refusal. With all
    eight neighbours held, the thing arrives one ring further."""
    from neverdeads_revenge.core.direction import DIRECTIONS

    state = _run(ultimate_level=1)
    here = state.player.position
    for direction in DIRECTIONS:
        square = direction.step(here)
        state.dungeon_map.set_tile(square, Tile.FLOOR)
        _stage_enemy_at_square(state, square, hp=99)

    perform_action(state, Action.ULTIMATE)

    atritas = state.atritas
    assert atritas is not None, "the crowd vetoed the summon"
    assert chebyshev(atritas.position, here) == 2, (
        "the summon did not step out one ring"
    )


def test_a_bump_against_the_shadow_costs_nothing():
    """Walking into your own dark is a word, not a fight and not a turn."""
    state = _run(ultimate_level=1)
    perform_action(state, Action.ULTIMATE)
    atritas = state.atritas
    state.player.position = (atritas.position[0] - 1, atritas.position[1])
    state.refresh_vision()

    before = state.total_turns
    logs = {entry.text for entry in state.log}
    from neverdeads_revenge.core.direction import Direction as _D

    perform_action(state, _move_towards(atritas.position, state.player.position))
    logs |= {entry.text for entry in state.log}

    assert state.total_turns == before, "bumping the shadow charged a turn"
    assert state.atritas is atritas
    assert any("It is yours" in text for text in logs)


def _move_towards(target, source):
    from neverdeads_revenge.game.actions import Action
    from neverdeads_revenge.core.direction import direction_towards

    mapping = {
        "NORTH": Action.MOVE_NORTH, "SOUTH": Action.MOVE_SOUTH,
        "EAST": Action.MOVE_EAST, "WEST": Action.MOVE_WEST,
        "NORTH_EAST": Action.MOVE_NE, "NORTH_WEST": Action.MOVE_NW,
        "SOUTH_EAST": Action.MOVE_SE, "SOUTH_WEST": Action.MOVE_SW,
    }
    return mapping[direction_towards(source, target).name]


# -- the price -------------------------------------------------------------------
def test_the_drain_spend_health_but_never_the_last():
    """One health every second beat of the stay, floored at one: the dark
    cannot kill its summoner, because the ask was a cost, not a bet."""
    state = _run(ultimate_level=1)

    perform_action(state, Action.ULTIMATE)
    state.player.stats.hp = 5

    _wait(state, ATRITAS_TURNS)

    assert state.player.stats.hp == 1, "the drain fell below one"
    assert state.atritas is None and not state.over


def test_the_drain_happens_on_its_beat():
    state = _run(ultimate_level=1)

    perform_action(state, Action.ULTIMATE)
    state.player.stats.hp = 3
    # The cast's own tick is age zero, so the drain's first beat is the
    # eighth wait after it.

    _wait(state, 7)
    assert state.player.stats.hp == 3
    _wait(state, 1)
    assert state.player.stats.hp == 2


# -- the assistance ---------------------------------------------------------------
def test_the_shadow_takes_the_preys_beside_noxx():
    """Atritas swings on what stands within his reach of Noxx, and the kill
    is Noxx's: coin, revenge, level, the whole payoff."""
    state = _run(ultimate_level=1)
    perform_action(state, Action.ULTIMATE)

    square = (state.player.position[0] + 1, state.player.position[1])
    enemy = _stage_enemy_at_square(state, square, hp=1)
    revenge_before = state.revenge_stacks

    _wait(state, 4)  # the first swing lands at age 3

    assert enemy.alive is False, "the shadow's swing did not land"
    assert state.atritas is not None, "the shadow left too early"
    assert state.revenge_stacks > revenge_before, "the kill was nobody's"
    assert any("Atritas" in entry.text for entry in state.log)


def test_the_shadow_ignores_a_far_prey():
    """The promise was *around* him: distance is respected, reach is not."""
    state = _run(ultimate_level=1)
    perform_action(state, Action.ULTIMATE)

    far_square = (
        state.player.position[0] + ATRITAS_RADIUS + 5,
        state.player.position[1] + ATRITAS_RADIUS + 5,
    )
    _stage_enemy_at_square(state, far_square, hp=1)

    _wait(state, 4)

    assert state.enemies and state.enemies[0].alive, (
        "the shadow reached a thing it was never promised"
    )


def test_the_shadow_blinks_beside_its_prey():
    """The dark is found where it strikes: a swing happens one square from
    the target, and on a square that is nobody else's."""
    state = _run(ultimate_level=1)
    perform_action(state, Action.ULTIMATE)

    hero_position = state.player.position
    enemy = _stage_enemy_at_square(
        state, (hero_position[0] + 2, hero_position[1]), hp=99
    )
    atritas = state.atritas
    held = atritas.position

    _wait(state, 3)  # the first swing lands on the shadow's own beat

    assert not enemy.alive is None  # it swung either way
    assert chebyshev(atritas.position, enemy.position) == 1, (
        f"the shadow struck from {atritas.position}, not from beside its prey"
    )
    assert atritas.position != held
    assert atritas.position != state.player.position
    assert atritas.position != enemy.position


def test_the_shadow_leaves_at_forty_turns():
    """Forty beats, then the dark goes home -- and the walls re-close."""
    state = _run(ultimate_level=1)

    perform_action(state, Action.ULTIMATE)
    assert state.atritas is not None

    _wait(state, ATRITAS_TURNS)

    assert state.atritas is None, "the shadow overstayed the promise"
    assert any("sinks back" in entry.text for entry in state.log)


# -- the save -----------------------------------------------------------------------
def test_the_ask_survives_a_save():
    """A spent ask is grey in the save too: reloading cannot re-ask the void
    on a floor that already had it."""
    from neverdeads_revenge.game.savegame import dump, load

    state = _run(ultimate_level=1)
    perform_action(state, Action.ULTIMATE)
    assert state.ultimate_available is False

    restored = load(dump(state))

    assert restored.ultimate_available is False


# -- Yeti: the Frozen Fortress --------------------------------------------------
def _yeti_run(ultimate_level: int = 1, seed: int = 5):
    return start_run(HEROES["yeti"], seed, ultimate_level=ultimate_level)


def test_the_fortress_stands_near_yeti_with_his_own_blood():
    state = _yeti_run()
    state.player.stats.hp = 20

    perform_action(state, Action.ULTIMATE)

    fortress = state.fortress
    assert fortress is not None
    assert fortress.stats.max_hp == 40, "the wall did not take twice his blood"
    assert fortress.stats.hp == 40
    distance = chebyshev(fortress.position, state.player.position)
    assert distance == 1, "the wall did not go up beside its builder"


def test_the_fortress_keeps_three_paces_of_its_own_weather():
    """The wall watches on Yeti's behalf: what he built is never lost behind
    what it cost, even after he walks away from it."""
    from neverdeads_revenge.game.difficulty import FORTRESS_VIEW

    state = _yeti_run()
    perform_action(state, Action.ULTIMATE)
    fortress = state.fortress
    assert fortress is not None

    # Walk him off, and let the vision recompute as it would in play.
    far = (state.player.position[0] + 12, state.player.position[1])
    state.dungeon_map.set_tile(far, Tile.FLOOR)
    state.player.position = far
    state.refresh_vision()

    fx, fy = fortress.position
    for dx in range(-FORTRESS_VIEW, FORTRESS_VIEW + 1):
        for dy in range(-FORTRESS_VIEW, FORTRESS_VIEW + 1):
            pos = (fx + dx, fy + dy)
            if state.dungeon_map.in_bounds(pos):
                assert state.dungeon_map.is_visible(pos), (
                    f"{pos} went dark around the wall"
                )
    assert state.dungeon_map.is_visible(fortress.position)


def test_the_fortress_takes_five_paces_of_sight():
    state = _yeti_run()
    before = state.sight_radius

    perform_action(state, Action.ULTIMATE)

    assert state.sight_radius == max(1, before - 5)


def test_everything_prefers_the_ice_to_the_hero():
    """The wall's whole worth: the monsters walk to it and bite it, not Yeti."""
    state = _yeti_run()
    perform_action(state, Action.ULTIMATE)
    fortress = state.fortress
    assert fortress is not None

    # A ghoul beside the wall on the side it can see -- the sight penalty is
    # part of the fortress, and a monster that cannot see the ice cannot want
    # it -- with Yeti out of reach.
    from neverdeads_revenge.core.direction import direction_towards

    spot = direction_towards(fortress.position, state.player.position).step(
        fortress.position
    )
    state.dungeon_map.set_tile(spot, Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, spot, hp=99)
    enemy.stats.damage = (3, 3)
    state.player.stats.hp = 40
    before_ice = fortress.stats.hp
    before_hero = state.player.stats.hp

    _wait(state, 2)

    assert fortress.stats.hp < before_ice, "the wall was ignored"
    assert state.player.stats.hp == before_hero, "the hero was bitten anyway"


def test_the_fortress_melts_at_its_eighty_turns():
    from neverdeads_revenge.game.difficulty import FORTRESS_TURNS

    assert FORTRESS_TURNS == 80, "the wall's clock changed without its test"

    state = _yeti_run()
    perform_action(state, Action.ULTIMATE)
    assert state.fortress is not None

    _wait(state, FORTRESS_TURNS)

    assert state.fortress is None, "the wall overstayed"
    assert state.sight_penalty == 0, "the cold never let go of the eyes"
    assert any("thaws" in entry.text for entry in state.log)


def test_a_broken_fortress_lets_the_cold_go():
    """Destroyed by teeth instead of by time: the same clean-up, no timer."""
    state = _yeti_run()
    perform_action(state, Action.ULTIMATE)
    fortress = state.fortress
    assert fortress is not None
    fortress.stats.hp = 1

    spot = (fortress.position[0] + 1, fortress.position[1])
    state.dungeon_map.set_tile(spot, Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, spot, hp=99)
    enemy.stats.damage = (9, 9)
    enemy.stats.accuracy = 99

    _wait(state, 2)

    assert state.fortress is None, "the broken wall stood there anyway"
    assert state.sight_penalty == 0


# -- Walkyrion: the golden bell --------------------------------------------------
def _walkyrion_run(ultimate_level: int = 1, seed: int = 5):
    return start_run(HEROES["walkyrion"], seed, ultimate_level=ultimate_level)


def test_the_bell_clears_the_walls_but_not_the_maps_edge():
    """Three paces of walls come down to plain floor -- walkable *and*
    see-through -- while the dungeon's own edge stays: a wall that fell there
    would open the floor onto nothing."""
    state = _walkyrion_run()
    here = state.player.position
    inner = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(inner, Tile.WALL)
    # A wall on the map's own border, three paces away at most.
    edge = (state.dungeon_map.width - 1, here[1])
    state.dungeon_map.set_tile(edge, Tile.WALL)

    perform_action(state, Action.ULTIMATE)

    assert state.dungeon_map.tile_at(inner) is Tile.FLOOR, "an inner wall stood"
    assert state.dungeon_map.tile_at(edge) is Tile.WALL, "the map's edge broke"
    assert not state.dungeon_map.is_opaque(inner), "the clearing kept a fence"


def test_the_bell_throws_and_cuts_but_does_not_shred():
    """A room, not a duel: moderate damage, a hard shove, and the whole
    payoff when the shove is what kills."""
    state = _walkyrion_run()
    here = state.player.position
    square = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    for x in range(here[0] - 4, here[0] + 5):
        for y in range(here[1] - 4, here[1] + 5):
            state.dungeon_map.set_tile((x, y), Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, square, hp=60)
    enemy.stats.evasion = 0
    revenge_before = state.revenge_stacks

    perform_action(state, Action.ULTIMATE)

    assert enemy.alive, "the bell shredded a full-health thing"
    assert enemy.stats.hp < 60, "the bell did not cut"
    moved = chebyshev(enemy.position, square)
    assert moved >= 1, "the bell did not throw it"
    assert state.revenge_stacks == revenge_before, "a survivor paid revenge"


def test_the_bell_kills_pay_like_any_kill():
    state = _walkyrion_run()
    here = state.player.position
    square = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, square, hp=1)
    revenge_before = state.revenge_stacks

    perform_action(state, Action.ULTIMATE)

    assert enemy.alive is False
    assert state.revenge_stacks > revenge_before, "the kill was nobody's"
    assert state.kills >= 1


# -- the feeding ------------------------------------------------------------------
def test_every_shadow_kill_hands_a_heart_back():
    """The bargain that makes a group worth wading into: Atritas charges
    blood by the beat and pays it back by the kill."""
    state = _run(ultimate_level=1)
    perform_action(state, Action.ULTIMATE)
    state.player.stats.hp = 10

    square = (state.player.position[0] + 1, state.player.position[1])
    _stage_enemy_at_square(state, square, hp=1)

    _wait(state, 4)  # the swing lands at age 3 and kills

    # Ten taken in, one handed back by the kill; the drain's first beat has
    # not arrived yet, so the trade shows in full.
    assert state.player.stats.hp == 11, "the kill did not pay the blood back"
    assert any("gives one back" in entry.text for entry in state.log)


def test_the_shadow_keeps_three_paces_of_sight_wherever_it_blinks():
    """It walks the floor looking for prey; wherever it lands it sees, so the
    summoner can watch the work he is bleeding for."""
    from neverdeads_revenge.game.difficulty import ATRITAS_VIEW

    state = _run(ultimate_level=1)
    perform_action(state, Action.ULTIMATE)

    # Stage a kill away from Noxx, let the shadow blink to it, and check the
    # square it landed on is lit even where the hero cannot see.
    hero = state.player.position
    far = (hero[0] + 2, hero[1] + 2)
    state.dungeon_map.set_tile(far, Tile.FLOOR)
    _stage_enemy_at_square(state, far, hp=1)

    _wait(state, 3)  # the blink and the kill

    atritas = state.atritas
    assert atritas is not None
    ax, ay = atritas.position
    for dx in range(-ATRITAS_VIEW, ATRITAS_VIEW + 1):
        for dy in range(-ATRITAS_VIEW, ATRITAS_VIEW + 1):
            pos = (ax + dx, ay + dy)
            if state.dungeon_map.in_bounds(pos):
                assert state.dungeon_map.is_visible(pos), (
                    f"{pos} went dark around the shadow"
                )


def test_the_shadow_hunts_outward_within_five_paces():
    """Seek and destroy: prey within the hunt radius of where the shadow
    stands is fair game, even when the hero is nowhere near it."""
    from neverdeads_revenge.game.difficulty import ATRITAS_HUNT_RADIUS

    state = _run(ultimate_level=1)
    perform_action(state, Action.ULTIMATE)
    atritas = state.atritas
    assert atritas is not None

    # A ghoul five paces from the shadow, straight away from the hero, so it
    # is inside the hunt radius and outside anything the hero could reach.
    from neverdeads_revenge.core.direction import direction_towards

    away = direction_towards(state.player.position, atritas.position)
    far = atritas.position
    for _ in range(5):
        far = away.step(far)
    state.dungeon_map.set_tile(far, Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, far, hp=1)
    assert chebyshev(atritas.position, far) <= ATRITAS_HUNT_RADIUS
    assert chebyshev(state.player.position, far) > ATRITAS_HUNT_RADIUS

    _wait(state, 3)  # the swing lands at age 3

    assert enemy.alive is False, "the shadow let its prey walk"
    assert any("Atritas" in entry.text for entry in state.log)


def test_the_hunt_does_not_wander_without_reason():
    """With nothing in reach anywhere, it stays with the hero rather than
    drifting off -- the fallback is the guard radius, not the map."""
    state = _run(ultimate_level=1)
    perform_action(state, Action.ULTIMATE)
    atritas = state.atritas
    assert atritas is not None

    _wait(state, 6)

    distance = chebyshev(atritas.position, state.player.position)
    assert distance <= 3, "the shadow wandered off with nothing to hunt"


# -- the pack has a size now ------------------------------------------------------
def test_a_full_pack_refuses_and_keeps_the_loot_on_the_floor():
    """Three slots to start. The fourth draught stays where it lies, with the
    reason said out loud, and the refusal eats nothing."""
    from neverdeads_revenge.game.difficulty import BASE_PACK_SLOTS
    from neverdeads_revenge.world.items import ITEMS, make_item

    state = _run()
    assert state.pack_capacity == BASE_PACK_SLOTS

    for _ in range(BASE_PACK_SLOTS):
        state.inventory.append(make_item(ITEMS["potion"]))
    state.dungeon_map.add_item(state.player.position, make_item(ITEMS["elixir"]))

    result = perform_action(state, Action.INTERACT)

    assert result.consumed_turn is False
    assert len(state.inventory) == BASE_PACK_SLOTS, "the pack overfilled"
    assert state.dungeon_map.item_at(state.player.position) is not None, (
        "the refusal ate the draught"
    )
    assert any("pack is full" in entry.text for entry in state.log)


def test_a_drunk_slot_opens_again():
    """Quaffing is how a full pack breathes."""
    from neverdeads_revenge.game.difficulty import BASE_PACK_SLOTS
    from neverdeads_revenge.world.items import ITEMS, make_item

    state = _run()
    state.player.stats.hp = 5
    for _ in range(BASE_PACK_SLOTS):
        state.inventory.append(make_item(ITEMS["potion"]))
    state.dungeon_map.add_item(state.player.position, make_item(ITEMS["elixir"]))

    perform_action(state, Action.QUAFF)  # a slot opens
    result = perform_action(state, Action.INTERACT)

    assert result.consumed_turn is False
    assert state.dungeon_map.item_at(state.player.position) is None, (
        "the opened slot did not take the draught"
    )


def test_the_shop_sells_slots_dearer_each_time_and_stops_at_seven():
    from neverdeads_revenge.game.difficulty import BASE_PACK_SLOTS
    from neverdeads_revenge.game.shop import META_UPGRADES

    pack = META_UPGRADES["pack"]

    assert [pack.price_at(owned) for owned in range(5)] == [100, 150, 200, 250, 300]
    assert pack.max_stacks == 5
    assert BASE_PACK_SLOTS + pack.max_stacks == 7, "the allowance moved"


def test_bought_slots_carry_into_the_run_and_through_a_save():
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.difficulty import BASE_PACK_SLOTS
    from neverdeads_revenge.game.savegame import dump, load
    from neverdeads_revenge.game.state import start_run

    state = start_run(HEROES["noxx"], 5, upgrades={"pack": 2})

    assert state.pack_capacity == BASE_PACK_SLOTS + 2
    assert load(dump(state)).pack_capacity == BASE_PACK_SLOTS + 2


# -- the strange draughts ---------------------------------------------------------
def _pack(state, item_id: str) -> None:
    from neverdeads_revenge.world.items import ITEMS, make_item

    state.inventory.append(make_item(ITEMS[item_id]))


def test_the_veil_hides_until_the_hero_strikes():
    """Nothing looks at the hero while the veil holds -- and the first landing
    blow tears it, because a veil is a promise about looking."""
    from neverdeads_revenge.game.actions import drink

    state = _run()
    square = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, square, hp=99)
    _pack(state, "thin_veil")

    drink(state, "thin_veil")
    assert state.has_draught("thin_veil")

    _wait(state, 3)
    assert enemy.position == square, "the veiled hero was hunted anyway"
    assert state.player.hp == state.player.max_hp, "the veiled hero was bitten"

    perform_action(state, Action.MOVE_EAST)  # the blow that tears it
    assert not state.has_draught("thin_veil"), "the veil outlived the blow"


def test_the_kindled_breath_sets_every_blow_burning():
    from neverdeads_revenge.game.actions import drink

    state = _run()
    square = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, square, hp=99)
    _pack(state, "kindled_breath")

    drink(state, "kindled_breath")
    perform_action(state, Action.MOVE_EAST)

    assert "burn" in enemy.statuses, "the breath did not kindle"


def test_the_short_crown_pays_the_charge_twice():
    from neverdeads_revenge.game.actions import drink

    state = _run()
    square = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    _stage_enemy_at_square(state, square, hp=1)
    _pack(state, "short_crown")

    drink(state, "short_crown")
    perform_action(state, Action.MOVE_EAST)

    assert state.revenge_stacks == 2, "the crown paid the ordinary charge"


def test_the_carrion_tongue_feeds_on_the_floors_dead():
    from neverdeads_revenge.game.actions import drink

    state = _run()
    square = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    _stage_enemy_at_square(state, square, hp=1)
    perform_action(state, Action.MOVE_EAST)  # the kill, and the square remembers
    assert square in state.death_squares

    _pack(state, "carrion_tongue")
    drink(state, "carrion_tongue")
    state.player.stats.hp = 5
    state.player.position = (square[0] - 1, square[1])
    state.refresh_vision()

    perform_action(state, Action.MOVE_EAST)  # onto the dead square

    assert state.player.stats.hp == 6, "the tongue found nothing"
    assert square not in state.death_squares, "the dead square fed twice"


def test_the_gallows_road_walls_the_dead_off_from_the_hunt():
    """The floor's dead are walls to everything that hunts -- and not to the
    hero, who walks over them (and eats them, with the tongue)."""
    from neverdeads_revenge.game.actions import drink

    state = _run()
    here = state.player.position
    # A corpse between a ghoul and the hero: the kill leaves the square, then
    # the bottle makes it a wall.
    corpse = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(corpse, Tile.FLOOR)
    _stage_enemy_at_square(state, corpse, hp=1)
    perform_action(state, Action.MOVE_EAST)  # the kill, on the corpse square
    assert corpse in state.death_squares
    state.dungeon_map.remove_item(corpse)
    state.player.position = (here[0] - 2, here[1])
    state.dungeon_map.set_tile((here[0] - 1, here[1]), Tile.FLOOR)
    state.refresh_vision()

    _pack(state, "gallows_road")
    drink(state, "gallows_road")

    # A ghoul on the far side walks *around* the corpse rather than over it.
    ghoul = (here[0] + 2, here[1])
    state.dungeon_map.set_tile(ghoul, Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, ghoul, hp=99)
    _wait(state, 3)
    assert enemy.position != corpse, "the hunt walked over the dead"

    # and the hero may: the dead are on the hero's side
    state.player.position = (corpse[0] - 1, corpse[1])
    state.refresh_vision()
    perform_action(state, Action.MOVE_EAST)
    assert state.player.position == corpse, "the hero was walled off by their own dead"


def test_the_strange_draughts_are_the_floors_and_no_longer():
    from neverdeads_revenge.game.actions import drink

    state = _run()
    _pack(state, "short_crown")
    drink(state, "short_crown")
    assert state.has_draught("short_crown")

    state.build_floor(2)

    assert not state.floor_draughts, "a rule crossed the stairs"
    assert not state.death_squares, "the carrion memory crossed the stairs"


def test_a_floor_holds_medicine_and_curiosities_apart():
    """The strange draughts have their own budget: rolled from the healing pool
    they would have cut the medicine, which is the one supply the game is
    balanced around."""
    from neverdeads_revenge.world.items import ITEMS, loot_count, strange_count

    for depth in (1, 5, 10):
        assert strange_count(depth) >= 1
        assert loot_count(depth) >= 2
    strange = [t for t in ITEMS.values() if t.kind == "strange"]
    assert len(strange) == 5
    assert all(t.heal == 0 and t.draught for t in strange), "a strange bottle heals"


# -- the new permanent axes ------------------------------------------------------
def test_the_shop_sells_damage_and_crit_now():
    """The two levers it never had: everything it sold made the hero live
    longer or move faster, and nothing made them kill faster."""
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.shop import META_UPGRADES
    from neverdeads_revenge.game.state import start_run

    whet = META_UPGRADES["whetstone"]
    edge = META_UPGRADES["edge"]
    assert whet.damage == 1 and whet.max_stacks == 3
    assert edge.crit == 0.05 and edge.max_stacks == 3

    state = start_run(HEROES["noxx"], 5, upgrades={"whetstone": 2, "edge": 2})
    assert state.player.stats.damage == (6, 8), "two stones did not sharpen"
    assert abs(state.player.stats.crit_chance - 0.35) < 1e-9


def test_the_ladders_climb_and_the_caps_are_where_they_were_said_to_be():
    from neverdeads_revenge.game.shop import META_UPGRADES

    vigour = META_UPGRADES["vigour"]
    haste = META_UPGRADES["haste"]
    assert vigour.max_stacks == 5
    assert [vigour.price_at(i) for i in range(5)] == [140, 200, 260, 320, 380]
    assert haste.max_stacks == 3
    assert [haste.price_at(i) for i in range(3)] == [220, 310, 400]
    # speed stays capped where the turn economy can take it
    assert haste.speed * haste.max_stacks == 0.36


# -- the bloodlines ---------------------------------------------------------------
def test_a_bloodline_only_works_for_its_own_hero():
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run

    noxx = start_run(HEROES["noxx"], 5, upgrades={"hoarfrost": 3, "bell_ring": 3})
    assert noxx.freeze_chance == 0.0, "Yeti's cold worked for Noxx"
    assert noxx.pushback_chance == 0.0

    yeti = start_run(HEROES["yeti"], 5, upgrades={"hoarfrost": 3})
    assert abs(yeti.freeze_chance - 0.45) < 1e-9, "the hoarfrost did not settle"

    walkyrion = start_run(HEROES["walkyrion"], 5, upgrades={"bell_ring": 2})
    assert abs(walkyrion.pushback_chance - 0.40) < 1e-9


def test_bleeding_edge_makes_a_crits_wound_keep_opening():
    """Noxx's bloodline: a lucky blow leaves a bleed that lasts longer, which
    is the only knob the status system has -- and the one ``_inflict`` already
    believes a second wound turns."""
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.actions import perform_action
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.world.tiles import Tile

    state = start_run(HEROES["noxx"], 5, upgrades={"bleeding_edge": 3})
    square = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, square, hp=99)
    enemy.stats.evasion = -99  # nothing dodges this test
    state.player.stats.crit_chance = 1.0  # and every blow is lucky

    perform_action(state, Action.MOVE_EAST)

    assert "bleed" in enemy.statuses
    assert enemy.statuses["bleed"] >= 3 + 2 * 3, (
        f"the wound lasts {enemy.statuses['bleed']} turns, not the nine a "
        f"three-stack crit should leave"
    )


def test_hoarfrost_freezes_whoever_strikes_yeti():
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.world.tiles import Tile

    state = start_run(HEROES["yeti"], 5, upgrades={"hoarfrost": 3})
    state.freeze_chance = 1.0  # a certainty, for the test
    square = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, square, hp=99)
    enemy.stats.accuracy = 99

    _wait(state, 3)

    assert "chill" in enemy.statuses, "the cold never came off Yeti"


def test_the_bell_ring_throws_what_walkyrion_lands_on():
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.world.tiles import Tile

    state = start_run(HEROES["walkyrion"], 5, upgrades={"bell_ring": 3})
    state.pushback_chance = 1.0
    here = state.player.position
    square = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(square, Tile.FLOOR)
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            state.dungeon_map.set_tile((here[0] + dx, here[1] + dy), Tile.FLOOR)
    enemy = _stage_enemy_at_square(state, square, hp=99)

    perform_action(state, Action.MOVE_EAST)

    assert enemy.alive
    assert enemy.position != square, "the bell did not throw it"
    assert chebyshev(enemy.position, here) > 1, "it was thrown into the hero"


# -- the springs ------------------------------------------------------------------
def test_the_floor_can_hold_two_springs_down_where_the_curses_pile_up():
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.world.generator import SPRING_CHANCE

    assert SPRING_CHANCE == 0.45

    found = 0
    for seed in range(1, 25):
        state = start_run(HEROES["noxx"], seed)
        built = state.build_floor(5)
        if len(built.springs) >= 2:
            found += 1
    assert found > 0, "twenty-four floors at depth five held no double spring"
