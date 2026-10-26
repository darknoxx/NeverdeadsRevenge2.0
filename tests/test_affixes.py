"""The aspects: one word, one rule, and a name the player can read."""

from __future__ import annotations

from neverdeads_revenge.game.actors import ENEMIES, HEROES, make_enemy
from neverdeads_revenge.game.actions.combat import resolve_enemy_attack
from neverdeads_revenge.world.affixes import AFFIXES
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
            for one in state.enemies:
                if one.affixes:
                    assert len(one.affixes) == 1
                    assert one.affixes[0] in AFFIXES
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


def test_a_frostbound_blow_chills():
    state = start_run(HEROES["noxx"], seed=3)
    enemy = make_enemy(ENEMIES["ghoul"], (1, 0), affixes=("frostbound",))
    enemy.stats.accuracy = 99
    state.player.stats.evasion = 0

    outcome = resolve_enemy_attack(state, enemy, state.player)

    assert outcome is not None and outcome.hit
    assert "chill" in state.player.statuses, "the frost did not take"


def test_the_darkness_touched_leaves_the_room_smaller():
    from neverdeads_revenge.game.actions.life import _on_death

    state = start_run(HEROES["noxx"], seed=3)
    enemy = make_enemy(ENEMIES["ghoul"], state.player.position, affixes=("darkness_touched",))
    enemy.stats.hp = 0
    state.enemies = [enemy]
    before = state.sight_penalty

    _on_death(state, enemy)

    assert state.sight_penalty == before + 1, "the dark left no shadow"
    assert any("smaller" in entry.text for entry in state.log)


def test_the_darkness_touched_depthless_deepens_its_wound():
    from neverdeads_revenge.game.actions.combat import resolve_player_attack
    from neverdeads_revenge.world.items import ITEMS, make_item

    state = start_run(HEROES["noxx"], seed=3)
    blade = make_item(ITEMS["depthless_dark"])
    state.player.equipment["weapon"] = blade
    state.player.stats.accuracy = 99
    target = make_enemy(ENEMIES["ghoul"], (1, 0))
    target.stats.hp = 999
    target.stats.evasion = 0

    assert blade.name == "the darkness-touched depthless"
    assert blade.affixes == ("darkness_touched",)

    outcome = resolve_player_attack(state, target)

    assert outcome.hit, "the blade has to land to open the wound"
    assert target.status_stacks.get("bleed", 0) >= 2, (
        "the dark did not deepen the bleeding"
    )


def test_deep_dice_name_blades_but_not_bottles_or_armour():
    from neverdeads_revenge.core.rng import Rng
    from neverdeads_revenge.world.affixes import weapon_affixes

    rng = Rng(11)
    marks = [weapon_affixes(rng, 10, "weapon") for _ in range(120)]

    assert any(marks), "the deep dice never marked a blade"
    assert all(len(one) <= 1 for one in marks), "two aspects on one blade"
    assert all(not one or one[0] in AFFIXES for one in marks)
    assert weapon_affixes(rng, 5, "weapon") == (), "the shallow floors are clean"
    assert weapon_affixes(rng, 10, "draught") == ()
    assert weapon_affixes(rng, 10, "armour") == ()


def test_a_deep_floor_can_hand_over_a_named_blade():
    from neverdeads_revenge.core.rng import Rng
    from neverdeads_revenge.world.generator import generate_floor

    floor = generate_floor(
        Rng(3),
        depth=7,
        affix_rng=Rng(3 * 1013 + 7 * 101),
    )

    marked = [item for item in floor.items.values() if item.affixes]
    assert marked, "the deep floor had no marked blade"
    assert all(item.kind == "weapon" for item in marked)


def test_the_marked_light_breathes_instead_of_standing_still():
    import math

    import pygame

    from neverdeads_revenge.sdl_front.stage import Stage

    class Figure:
        size = 64
        cx = 100
        row = 6
        phase = 0.0

    stage = Stage()
    surface = pygame.Surface((240, 200), pygame.SRCALPHA)
    stage.affix_glow(surface, Figure(), "#ff7a2a", 0.0, 16)
    first = set(stage._auras)

    stage.affix_glow(surface, Figure(), "#ff7a2a", math.pi / 2, 16)

    assert len(stage._auras) > len(first), "the aura reused one still frame"
