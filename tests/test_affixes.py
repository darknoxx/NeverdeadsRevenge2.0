"""The aspects: one word, one rule, and a name the player can read."""

from __future__ import annotations

from neverdeads_revenge.game.actors import ENEMIES, HEROES, make_enemy
from neverdeads_revenge.game.actions.combat import resolve_enemy_attack
from neverdeads_revenge.game.affixes import AFFIXES
from neverdeads_revenge.game.state import start_run


def test_the_name_reads_as_one_phrase():
    enemy = make_enemy(ENEMIES["ghoul"], (0, 0), affixes=("fire_kissed",))

    assert enemy.name == "fire-kissed ghoul"
    assert enemy.base_name == "ghoul", "the sheets still know what to draw"
    assert enemy.key == "ghoul", "the book still knows what to file it under"
    assert enemy.affixes == ("fire_kissed",)


def test_every_aspect_has_the_parts_the_book_and_the_painter_need():
    for key, affix in AFFIXES.items():
        assert affix.key == key
        assert affix.adjective and " " not in affix.adjective
        assert affix.colour.startswith("#")
        assert affix.particle
        assert affix.blurb
        assert affix.threat > 0


def test_a_fire_kissed_blow_leaves_burning():
    state = start_run(HEROES["noxx"], seed=3)
    enemy = make_enemy(ENEMIES["ghoul"], (1, 0), affixes=("fire_kissed",))
    enemy.stats.accuracy = 99
    state.player.stats.evasion = 0

    outcome = resolve_enemy_attack(state, enemy, state.player)

    assert outcome is not None and outcome.hit, "the blow has to land to burn"
    assert "burn" in state.player.statuses, "the fire-kissed touch did not burn"


def test_only_the_deep_floors_are_touched():
    shallow = start_run(HEROES["noxx"], seed=3)
    assert not any(one.affixes for one in shallow.enemies)

    for seed in range(30):
        state = start_run(HEROES["noxx"], seed=seed)
        state.build_floor(6)
        if any(one.affixes for one in state.enemies):
            assert all(one.affixes == ("fire_kissed",) for one in state.enemies if one.affixes)
            break
    else:
        raise AssertionError("thirty deep floors and not one touched monster")


def test_the_affix_comes_back_from_the_save():
    from neverdeads_revenge.game.savegame import dump, load

    state = start_run(HEROES["noxx"], seed=3)
    marked = make_enemy(ENEMIES["ghoul"], state.enemies[0].position, affixes=("fire_kissed",))
    state.enemies = [marked]

    back = load(dump(state)).enemies[0]

    assert back.name == "fire-kissed ghoul"
    assert back.base_name == "ghoul"
    assert back.affixes == ("fire_kissed",)
    assert back.key == "ghoul"


def test_the_painter_gives_a_marked_figure_light_on_the_floor():
    """The aura is light, not a tint: the sprite stays the monster's own."""
    import pygame

    from neverdeads_revenge.sdl_front.stage import Stage

    class Figure:
        size = 64
        cx = 100
        row = 6
        phase = 0.0

    surface = pygame.Surface((240, 200), pygame.SRCALPHA)
    before = surface.get_at((100, 6 * 16))
    Stage().affix_glow(surface, Figure(), "#ff7a2a", 0.0, 16)
    assert surface.get_at((100, 6 * 16)) != before, "the aura painted nothing"
