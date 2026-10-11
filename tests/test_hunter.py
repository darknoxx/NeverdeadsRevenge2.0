"""Tests for the thing that comes looking for you.

Everything else in the dungeon waits to be walked into, or drifts at the player
once it can see them. The hunter knows where they are from the moment the floor
is built -- which is the whole of what it is, and the thing that has to be
tested: a hunter that only acted when it was visible would be a monster standing
still in the dark.
"""

from __future__ import annotations

from neverdeads_revenge.core.direction import chebyshev
from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.game.actions import advance_world, take_turn
from neverdeads_revenge.game.actors import ENEMIES, HEROES, NOXX, make_enemy
from neverdeads_revenge.game.gifts import GIFTS
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.world.generator import (
    ESCAPE_DEPTH,
    generate_floor,
    hunter_chance,
)


def _far_from_player(state):
    """A walkable cell as far from the player as the floor allows."""
    return max(
        state.dungeon_map.walkable_positions(),
        key=lambda pos: chebyshev(pos, state.player.position),
    )


def _hunter(state):
    """Put a hunter a long way from the player, out of sight."""
    hunter = make_enemy(ENEMIES["hunter"], _far_from_player(state))
    state.enemies = [hunter]
    state.turn_queue = type(state.turn_queue)([hunter])
    return hunter


# -- where it comes from -----------------------------------------------------
def test_the_hunter_never_stands_on_the_first_floor():
    """Floor one is where a player learns what a monster looks like, and the
    first thing they learn should not be something they cannot kill."""
    for seed in range(200):
        floor = generate_floor(Rng(seed), depth=1)
        assert floor.hunter is None


def test_the_chance_climbs_with_the_floor():
    """Deeper floors carry more of a decision, and never less of one."""
    chances = [hunter_chance(depth) for depth in range(1, ESCAPE_DEPTH + 1)]

    assert chances[0] == 0.0, "floor one teaches what a monster is"
    assert chances == sorted(chances), "the curve dipped somewhere"
    assert chances[-1] == 0.5, "the bottom of the dungeon is half hunter"
    assert hunter_chance(ESCAPE_DEPTH + 5) == 0.5, (
        "past the last floor the odds fell off a cliff"
    )


def test_the_odds_on_the_table_are_the_odds_on_the_floor():
    """The curve is not decoration: the generator rolls it."""
    floors = 400
    found = sum(
        1 for seed in range(floors) if generate_floor(Rng(seed), depth=5).hunter
    )

    assert abs(found / floors - hunter_chance(5)) < 0.06, found


def test_a_hunter_that_turns_up_is_at_the_floor_strength_and_not_floor_one():
    """It is not drawn from the table, so the potency curve has to be applied
    by hand -- and a hunter that skipped it would be a floor-one monster on
    floor nine."""
    from neverdeads_revenge.game.actors import scale_template

    base = ENEMIES["hunter"].stats.max_hp
    seen = 0
    for seed in range(60):
        state = start_run(NOXX, seed=seed)
        state.build_floor(8)
        for hunter in (e for e in state.enemies if e.glyph == "X"):
            seen += 1
            assert hunter.hp == scale_template(ENEMIES["hunter"], 8).stats.max_hp
            assert hunter.hp > base

    assert seen, "no hunter turned up in sixty floors"


# -- what it does ------------------------------------------------------------
def test_it_walks_at_the_player_from_out_of_sight():
    state = start_run(NOXX, seed=3)
    hunter = _hunter(state)
    before = chebyshev(hunter.position, state.player.position)
    assert not state.dungeon_map.is_visible(hunter.position)

    take_turn(state, hunter)

    assert chebyshev(hunter.position, state.player.position) < before, (
        "the hunter did not come"
    )


def test_an_ordinary_monster_still_waits_in_the_dark():
    """The fairness rule is only lifted for the hunter."""
    state = start_run(NOXX, seed=3)
    ghoul = make_enemy(ENEMIES["ghoul"], _far_from_player(state))
    before = ghoul.position

    take_turn(state, ghoul)

    assert ghoul.position == before, "a ghoul hunted from out of sight"


def test_it_is_still_slower_than_the_fastest_hero():
    """The one hard constraint in the balance. A hunter that outran Noxx would
    turn every other stat he has into decoration."""
    for depth in range(1, 12):
        from neverdeads_revenge.game.actors import scale_template

        assert scale_template(ENEMIES["hunter"], depth).stats.speed < NOXX.stats.speed


def test_the_glyph_is_free_and_is_not_a_hero_or_a_monster_letter():
    """``X`` reads as a warning without being any of the letters already on the
    map."""
    taken = {hero.glyph for hero in HEROES.values()}
    taken |= {t.glyph for key, t in ENEMIES.items() if key != "hunter"}
    taken |= {"8"}

    assert ENEMIES["hunter"].glyph == "X"
    assert ENEMIES["hunter"].glyph not in taken


def test_a_floor_with_a_hunter_is_still_winnable_by_leaving():
    """It is a decision, not a wall: it can be left behind on the stairs."""
    state = start_run(NOXX, seed=3)
    hunter = _hunter(state)
    hunter.stats.hp = 9999  # it is not going to be killed

    # Walk the player onto the exit and take it.
    state.player.position = state.exit_pos
    from neverdeads_revenge.game.actions import Action, perform_action

    perform_action(state, Action.DESCEND)

    assert state.depth == 2
    assert all(e.glyph != "X" for e in state.enemies), (
        "the hunter followed through the stairs"
    )


def test_a_floor_with_a_hunter_says_so_in_red():
    """A threat nobody was told about is not a decision, it is an ambush.

    Everything else on a floor can be met by walking into it. This one is
    already on its way, and the warning is the whole difference between a
    floor that has a decision on it and a floor that has a nasty surprise.
    """
    from neverdeads_revenge.game.state import LogKind

    for seed in range(60):
        state = start_run(NOXX, seed=seed)
        state.build_floor(8)
        if not any(e.glyph == "X" for e in state.enemies):
            continue

        warnings = [
            entry
            for entry in state.log
            if entry.kind is LogKind.BAD and "knows where you are" in entry.text
        ]
        assert warnings, "the hunter arrived unannounced"
        return

    raise AssertionError("no hunter turned up in sixty floors")


def test_a_floor_without_one_says_nothing():
    for seed in range(60):
        state = start_run(NOXX, seed=seed)
        before = len(state.log)
        state.build_floor(8)
        if any(e.glyph == "X" for e in state.enemies):
            continue

        assert not any(
            "knows where you are" in entry.text for entry in state.log[before:]
        )
        return

    raise AssertionError("every floor had a hunter")


# -- what killing it leaves behind -------------------------------------------
def _kill_adjacent(state, template, hp: int = 1):
    """Put a monster east of the player and hit it until it dies.

    Its own damage is zeroed for the duration: a miss is still possible at the
    hit-chance ceiling (0.97), and this helper is not about the fight, it is
    about what the fight pays.
    """
    from neverdeads_revenge.game.actions import Action, perform_action
    from neverdeads_revenge.world.tiles import Tile

    pos = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(pos, Tile.FLOOR)
    enemy = make_enemy(template, pos)
    enemy.stats.hp = hp
    enemy.stats.damage = (0, 0)
    state.enemies = [enemy]
    state.turn_queue = type(state.turn_queue)([state.player, enemy])

    for _ in range(20):
        perform_action(state, Action.MOVE_EAST)
        if state.kills:
            break
    assert state.kills, f"the {template.key} would not die"
    return enemy


def test_killing_it_pays_a_purse_and_a_rule():
    """It is the only monster in the dungeon with a rule to leave behind.

    Everything else drops coin and maybe a wound. The hunter is the floor's
    decision, and beating a decision is supposed to change what the player can
    do, not just what they carry.
    """
    state = start_run(NOXX, seed=3)
    before = set(state.gifts)

    hunter = _kill_adjacent(state, ENEMIES["hunter"])

    assert state.gifts - before, "the hunter left no rule"
    assert state.gifts - before <= set(GIFTS)
    coins = state.dungeon_map.item_at(hunter.position)
    assert coins is not None and coins.kind == "coin"
    assert coins.gold >= ENEMIES["hunter"].gold[0], (
        f"a purse of {coins.gold} is not 'a great deal'"
    )


def test_the_rule_is_never_one_already_in_hand():
    """Drawn from the unheld ones, the way a chest's is."""
    state = start_run(NOXX, seed=3)
    state.gifts = {next(iter(GIFTS))}
    held = set(state.gifts)

    _kill_adjacent(state, ENEMIES["hunter"])

    assert state.gifts - held, "the hunter paid nothing"
    assert not (state.gifts - held) & held


def test_when_there_is_nothing_left_to_teach_it_says_so():
    """All eight rules in hand: the kill cannot invent a ninth."""
    from neverdeads_revenge.game.state import LogKind

    state = start_run(NOXX, seed=3)
    state.gifts = set(GIFTS)
    held = set(state.gifts)

    _kill_adjacent(state, ENEMIES["hunter"])

    assert state.gifts == held, "the hunter duplicated a rule"
    assert any(
        entry.kind is LogKind.PLAIN and "nothing left" in entry.text
        for entry in state.log
    ), "the empty-handed kill was silent about it"


def test_an_ordinary_monster_leaves_no_rule():
    """The gift is the hunter's, not a kill's."""
    state = start_run(NOXX, seed=3)
    before = set(state.gifts)

    _kill_adjacent(state, ENEMIES["ghoul"])

    assert state.gifts == before, "a ghoul handed out a rule"


def test_it_has_more_health_than_anything_else_on_the_floor():
    """The strength is the point: killing it is a commitment, not a lucky round."""
    hunter = ENEMIES["hunter"].stats.max_hp
    others = max(
        template.stats.max_hp for key, template in ENEMIES.items() if key != "hunter"
    )

    assert hunter > others


def test_a_rule_a_chest_already_owes_is_not_the_hunter_s_to_give():
    """The chest was stocked before the player saw either of them.

    A hunter that spent that lid's gift would turn the chest into a second copy
    of a rule -- the one thing a chest's own docstring refuses to be.
    """
    from neverdeads_revenge.world.items import make_chest
    from neverdeads_revenge.world.tiles import Tile

    state = start_run(NOXX, seed=3)
    owed = next(iter(GIFTS))
    state.gifts = set(GIFTS) - {owed}

    chest_pos = (state.player.position[0] - 1, state.player.position[1])
    state.dungeon_map.set_tile(chest_pos, Tile.FLOOR)
    state.dungeon_map.add_item(chest_pos, make_chest("dim", None, gift=owed))

    _kill_adjacent(state, ENEMIES["hunter"])

    assert owed not in state.gifts, "the hunter spent the chest's own gift"
    assert state.gifts == set(GIFTS) - {owed}
