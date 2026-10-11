"""Tests for the people on the floors.

They carry no mechanics -- no quest, no trade, no reward -- so what there is to
test is everything *around* that: that they never fight, never get fought, never
block the turn queue, never stand on the way out, and never wear a glyph or a
colour that already means something else on the map.

The two uniqueness tests live with the other registries and now include them; the
colour one is in ``test_game.py`` beside the heroes, and the glyph one in
``test_world.py`` beside the tiles.
"""

from __future__ import annotations

from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import (
    ENEMIES,
    HEROES,
    NOXX,
    ActorKind,
    make_enemy,
    make_npc,
)
from neverdeads_revenge.game.npcs import NPCS, NPC_COLOR, NPC_GLYPH, npc_by_key
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.world.generator import NPC_CHANCE, generate_floor
from neverdeads_revenge.world.items import ITEMS
from neverdeads_revenge.world.tiles import Tile


def _beside(state, key: str = "vesper"):
    """Put somebody next to the player."""
    npc = make_npc(
        NPCS[key], (state.player.position[0] + 1, state.player.position[1])
    )
    state.npcs = [npc]
    state.refresh_vision()
    return npc


# -- the table ---------------------------------------------------------------
def test_everybody_has_a_name_and_something_to_say():
    for key, npc in NPCS.items():
        assert npc.name, key
        assert npc.lines, key
        assert all(line.strip() for line in npc.lines), key


def test_everybody_has_a_name_of_their_own():
    """Two people called the same thing is a dialog with the wrong name on it."""
    names = [npc.name for npc in NPCS.values()]
    assert len(set(names)) == len(names)


def test_nobody_is_named_after_something_else_in_the_game():
    """A person called "the marrow" would be a person the player thinks is an
    amulet they have already read about."""
    taken = {hero.name.lower() for hero in HEROES.values()}
    taken |= {enemy.name.lower() for enemy in ENEMIES.values()}
    taken |= {item.name.lower() for item in ITEMS.values()}

    for npc in NPCS.values():
        assert npc.name.lower() not in taken, npc.key


def test_an_unknown_key_is_not_a_person():
    assert npc_by_key(None) is None
    assert npc_by_key("nobody") is None


def test_the_glyph_is_not_a_letter():
    """The convention here is that capitals are heroes and lowercase are
    monsters, and neither is true of these."""
    assert not NPC_GLYPH.isalpha()
    assert len(NPC_GLYPH) == 1


def test_the_colour_is_not_already_on_the_map():
    """The palette is genuinely full: this clears the perceptual-distance test
    by about four thousand six hundred against its nearest neighbour."""
    from neverdeads_revenge.world.items import ITEMS as ALL
    from tests.palette import distance

    for other in [hero.color for hero in HEROES.values()]:
        assert distance(NPC_COLOR, other) > 4000, other
    for template in ALL.values():
        assert distance(NPC_COLOR, template.color) > 4000, template.key


# -- where they turn up ------------------------------------------------------
def test_the_first_floor_has_nobody_on_it():
    """Floor one is where the player learns what a monster looks like. A person
    standing in the first room would teach the wrong lesson."""
    for seed in range(60):
        floor = generate_floor(Rng(seed), depth=1, npc_keys=tuple(NPCS))
        assert floor.npcs == []


def test_somebody_turns_up_but_not_every_floor():
    floors = [
        generate_floor(Rng(seed), depth=5, npc_keys=tuple(NPCS))
        for seed in range(200)
    ]
    with_npc = sum(1 for floor in floors if floor.npcs)
    assert 0 < with_npc < len(floors), f"{with_npc} floors out of 200 had somebody"
    assert 0 < NPC_CHANCE < 1


def test_everybody_can_be_met():
    seen: set[str] = set()
    for seed in range(400):
        for depth in (2, 5, 9):
            floor = generate_floor(Rng(seed * 7 + depth), depth=depth, npc_keys=tuple(NPCS))
            seen |= {key for _, key in floor.npcs}
    assert seen == set(NPCS), f"never met: {set(NPCS) - seen}"


def test_nobody_stands_on_the_way_out_or_on_the_spring():
    """A conversation on the exit is a conversation you walk past twice."""
    for seed in range(200):
        floor = generate_floor(Rng(seed), depth=6, npc_keys=tuple(NPCS))
        for position, _ in floor.npcs:
            assert position != floor.stairs_down
            assert floor.map.tile_at(position) is Tile.FLOOR
            assert position not in floor.items


def test_a_floor_with_no_keys_has_nobody_on_it():
    for seed in range(40):
        assert generate_floor(Rng(seed), depth=5, npc_keys=()).npcs == []


# -- what they do to a run ---------------------------------------------------
def test_a_person_is_not_a_monster():
    state = start_run(NOXX, seed=3)
    state.build_floor(5)
    for npc in state.npcs:
        assert npc.kind is ActorKind.NPC
        assert npc not in state.enemies
        assert npc not in state.living_enemies


def test_a_person_never_gets_a_turn():
    state = start_run(NOXX, seed=3)
    npc = _beside(state)
    assert npc not in state.turn_queue


def test_a_person_beside_you_is_not_something_to_swing_at():
    """``enemy_beside_player`` is what the revenge path and the bot ask, and a
    person standing next to the player is not a fight."""
    state = start_run(NOXX, seed=3)
    _beside(state)
    assert state.enemy_beside_player() is None

    # And a monster beside them is still found.
    state.enemies = [
        make_enemy(ENEMIES["ghoul"], (state.player.position[0], state.player.position[1] - 1))
    ]
    assert state.enemy_beside_player() is not None


def test_walking_into_a_person_is_not_an_attack():
    state = start_run(NOXX, seed=3)
    npc = _beside(state)
    before = state.player.position

    result = perform_action(state, Action.MOVE_EAST)

    assert state.player.position == before, "the player walked through them"
    assert npc.alive, "the player attacked somebody"
    assert result.consumed_turn is False, "bumping into somebody cost a turn"
    assert "in the way" in state.log[-1].text


def test_enter_next_to_somebody_talks_to_them():
    state = start_run(NOXX, seed=3)
    npc = _beside(state, "sexton")

    result = perform_action(state, Action.INTERACT)

    assert result.prompt_kind == "npc"
    assert result.speaker == "the Sexton"
    assert result.prompt in NPCS["sexton"].lines
    assert result.consumed_turn is False, "a conversation cost a turn"
    assert npc.name in result.speaker


def test_the_stairs_win_over_the_person_standing_next_to_them():
    """The stairs are a decision the player already made by walking onto them."""
    state = start_run(NOXX, seed=3)
    state.player.position = state.exit_pos
    _beside(state)

    result = perform_action(state, Action.INTERACT)

    assert result.prompt_kind != "npc", "a conversation blocked the stairs"
    assert state.depth == 2


def test_enter_with_nobody_about_still_says_so():
    state = start_run(NOXX, seed=3)
    state.npcs = []

    result = perform_action(state, Action.INTERACT)

    assert result.prompt is None
    assert "nothing here" in state.log[-1].text


def test_the_same_person_can_say_two_different_things():
    """One line per meeting, picked at random: hearing the same sentence twice
    from the same person is the moment a person becomes furniture."""
    said: set[str] = set()
    for seed in range(60):
        state = start_run(NOXX, seed=seed)
        _beside(state, "tally")
        said.add(perform_action(state, Action.INTERACT).prompt)

    assert len(said) > 1, "they only ever said one thing"
    assert said <= set(NPCS["tally"].lines)


def test_a_person_is_drawn_and_blocks_the_map():
    """``actor_at`` finds them, which is what the renderer and the drop-the-old-
    weapon path both ask."""
    state = start_run(NOXX, seed=3)
    npc = _beside(state)

    assert state.actor_at(npc.position) is npc
    assert state.npc_beside_player() is npc
