"""The echo: the best run, worn by a monster on the last floor of a ring."""

from __future__ import annotations

from neverdeads_revenge.game.actors import ENEMIES, HEROES, make_enemy, scale_template
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.persistence import ScoreEntry
from neverdeads_revenge.sdl_front.app_shared import dress_the_echo


def _door_run():
    return start_run(
        HEROES["noxx"],
        seed=3,
        tenth_door=True,
        start_depth=10,
    )


def test_the_last_floor_of_a_ring_holds_an_echo():
    state = _door_run()

    state.build_floor(20)

    assert any(enemy.behaviour == "echo" for enemy in state.enemies)
    assert any("echo waits" in entry.text for entry in state.log)


def test_the_echo_is_scaled_to_the_floor_it_is_met_on():
    enemy = make_enemy(ENEMIES["echo"], (1, 1))
    best = ScoreEntry(
        name="ASH",
        score=1000,
        depth=10,
        hero="noxx",
        won=False,
        weapon="",
        armour="",
    )

    dress_the_echo([enemy], [best], depth=30)

    expected = scale_template(ENEMIES["echo"], 30)
    assert enemy.name == "ASH"
    assert enemy.stats.max_hp == expected.stats.max_hp
    assert enemy.stats.damage == expected.stats.damage
