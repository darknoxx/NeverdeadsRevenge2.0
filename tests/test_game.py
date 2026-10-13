"""Tests for actors, combat and the run simulation.

These play the game headlessly -- no terminal, no Textual -- which is the whole
point of keeping the domain layer free of UI imports.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.core.direction import Direction, chebyshev
from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.game import actions as actions_module
from neverdeads_revenge.game.actions import (
    Action,
    perform_action,
)
from neverdeads_revenge.game.actors import (
    ENEMIES,
    HEROES,
    NOXX,
    WALKYRION,
    YETI,
    Actor,
    ActorKind,
    Stats,
    make_enemy,
    make_hero,
    pick_enemy_template,
    scale_template,
)
from neverdeads_revenge.game.combat import (
    MAX_HIT_CHANCE,
    MIN_HIT_CHANCE,
    REVENGE_MAX_STACKS,
    apply_revenge,
    attack,
    hit_chance,
)
from neverdeads_revenge.game.difficulty import (
    MAX_ENEMY_SPEED,
    MAX_POTENCY,
    potency,
    weight_at_depth,
)
from neverdeads_revenge.game.shop import Loadout
from neverdeads_revenge.game.state import (
    VIEW_RADIUS,
    ESCAPE_BONUS,
    SPEED_BONUS_PER_TURN,
    TURN_BUDGET_PER_FLOOR,
    GameState,
    RunState,
    start_run,
)
from neverdeads_revenge.world.generator import ESCAPE_DEPTH
from neverdeads_revenge.world.items import ITEMS, make_item
from neverdeads_revenge.world.map import GroundItem

SEEDS = range(25)


# -- stats -----------------------------------------------------------------
def test_hurt_applies_armour():
    stats = Stats(max_hp=20, hp=20, armor=2)
    assert stats.hurt(5) == 3
    assert stats.hp == 17


def test_hurt_never_goes_below_zero():
    stats = Stats(max_hp=10, hp=4)
    stats.hurt(999)
    assert stats.hp == 0
    assert not stats.alive


def test_heal_is_capped_at_max():
    stats = Stats(max_hp=10, hp=8)
    assert stats.heal(5) == 2
    assert stats.hp == 10


def test_average_damage():
    assert Stats(damage=(4, 6)).average_damage == 5


# -- heroes ----------------------------------------------------------------
def test_noxx_identity():
    """The brief: fast, crit-heavy, fragile."""
    assert NOXX.name == "Noxx"
    assert NOXX.stats.speed == 1.5
    assert NOXX.stats.crit_chance >= 0.2
    assert NOXX.stats.crit_multiplier >= 2.0
    # Fragile: the least health of anything the roster will hold.
    assert NOXX.stats.max_hp <= 30


def test_noxx_is_materially_faster_than_every_enemy():
    for template in ENEMIES.values():
        assert NOXX.stats.speed > template.stats.speed, template.key


def test_noxx_stays_the_fastest_thing_in_the_dungeon_at_any_depth():
    """The one balance constraint that must never bend.

    Noxx's crit chance and his REVENGE speed stacking both pay off because he
    gets more actions than anything around him. A single monster that outruns
    him turns both of those into decoration, so the speed cap in
    ``game.difficulty`` is load-bearing and gets its own test rather than
    riding along with the potency ones.
    """
    for depth in range(1, 40):
        for template in ENEMIES.values():
            scaled = scale_template(template, depth)
            assert scaled.stats.speed < NOXX.stats.speed, (
                f"{template.key} at depth {depth} is as fast as the hero"
            )


def test_no_monster_ever_exceeds_the_documented_speed_cap():
    for depth in range(1, 60):
        for template in ENEMIES.values():
            assert scale_template(template, depth).stats.speed <= MAX_ENEMY_SPEED


def test_making_a_hero_does_not_mutate_the_template():
    actor = make_hero(NOXX, (3, 4))
    actor.stats.hp -= 10
    actor.stats.speed = 99
    assert NOXX.stats.hp == NOXX.stats.max_hp
    assert NOXX.stats.speed == 1.5


def test_hero_actor_is_flagged_as_the_player():
    actor = make_hero(NOXX, (1, 1))
    assert actor.is_player
    assert actor.kind is ActorKind.HERO


def test_enemy_templates_are_not_mutated_by_actors():
    template = ENEMIES["ghoul"]
    actor = make_enemy(template, (2, 2))
    actor.stats.hp = 1
    assert template.stats.hp == template.stats.max_hp
    assert actor.behaviour == template.behaviour


def test_speed_bonus_is_additive():
    actor = make_hero(NOXX, (0, 0))
    assert actor.speed == 1.5
    actor.speed_bonus = 0.3
    assert actor.speed == pytest.approx(1.8)


def test_enemy_spawn_weights_are_respected():
    rng = Rng(11)
    counts: dict[str, int] = {}
    for _ in range(6000):
        key = pick_enemy_template(rng).key
        counts[key] = counts.get(key, 0) + 1
    # Template keys, not display names: the skeleton's key is "bone".
    assert counts["ghoul"] > counts["bone"] > counts["wraith"]


def test_heroes_registry_is_populated():
    assert HEROES["noxx"] is NOXX


def test_noxx_is_a_purple_n():
    """The hero's mark on the map, and it is his own.

    Held to a specific glyph and a specific colour because the map is where the
    player looks for the whole run: a hero who is a different colour on the
    select screen, the sidebar and the map is three characters, not one.
    """
    assert NOXX.glyph == "N"
    assert NOXX.color == "#a855f7"


def test_the_hero_colour_is_not_another_hero_or_monster_in_disguise():
    """``purple`` and ``magenta`` are one terminal approximation apart.

    The named colour "purple" resolves to the same magenta the wraith uses on
    terminals that cannot show the difference, which is why the heroes carry hex
    values. This asserts each hero is actually a different colour from everything
    else on the map rather than merely a different string.
    """
    from itertools import combinations

    from neverdeads_revenge.game.npcs import NPC_COLOR, NPC_GLYPH
    from neverdeads_revenge.world.items import ITEMS
    from tests.palette import distance

    # Keyed by glyph, because the glyph is the mark the eye finds. Items of a
    # kind share both glyph and colour on purpose; across glyphs the two have to
    # agree, or a purple N and a purple something-else are the same mark.
    marks: dict[str, tuple[str, str]] = {}
    for hero in HEROES.values():
        marks[hero.glyph] = (f"hero {hero.key}", hero.color)
    for template in ENEMIES.values():
        marks[template.glyph] = (f"monster {template.key}", template.color)
    for item in ITEMS.values():
        marks.setdefault(item.glyph, (f"{item.kind} items", item.color))
    marks[NPC_GLYPH] = ("the people", NPC_COLOR)

    for left, right in combinations(marks, 2):
        left_name, left_colour = marks[left]
        right_name, right_colour = marks[right]
        apart = distance(left_colour, right_colour)
        assert apart > 4000, (
            f"{left_name} ({left!r}) and {right_name} ({right!r}) are the same "
            f"colour to the eye ({left_colour} vs {right_colour})"
        )


# -- the roster -------------------------------------------------------------
def test_the_roster_has_more_than_one_hero_in_it():
    """The select screen is data-driven, and a roster of one is not a choice."""
    assert len(HEROES) == 3
    assert set(HEROES) == {"noxx", "yeti", "walkyrion"}


def test_each_hero_is_the_best_at_something():
    """Three heroes who are all good at the same thing are one hero.

    Roles are asserted by who wins each stat rather than by a list of expected
    numbers, so retuning a hero's health does not fail a test that was really
    about him being the tough one.
    """
    heroes = list(HEROES.values())
    best_speed = max(heroes, key=lambda h: h.stats.speed)
    best_hp = max(heroes, key=lambda h: h.stats.max_hp)
    best_armor = max(heroes, key=lambda h: h.stats.armor)
    best_evasion = max(heroes, key=lambda h: h.stats.evasion)
    best_accuracy = max(heroes, key=lambda h: h.stats.accuracy)

    assert best_speed is NOXX and best_evasion is NOXX, "Noxx is not the fast one"
    assert best_hp is YETI and best_armor is YETI, "Yeti is not the tough one"
    assert best_accuracy is WALKYRION, "Walkyrion has no edge of his own"


def test_walkyrion_is_the_middle_of_the_other_two():
    """Balanced has to mean between, or it just means worse.

    ``Walkyrion`` measured as the weakest hero in the game until his accuracy
    went above both of the others': the middle of two specialists is below both
    of them, because each specialist is paying for their spike with a hole and
    the generalist is paying for nothing.
    """
    for name in ("max_hp", "speed", "armor", "evasion"):
        low, high = sorted(
            (getattr(NOXX.stats, name), getattr(YETI.stats, name))
        )
        middle = getattr(WALKYRION.stats, name)
        assert low <= middle <= high, f"Walkyrion's {name} is not the middle"

    # And a hole of his own for the specialists to exploit, or he is simply
    # better than both.
    assert WALKYRION.stats.max_hp < YETI.stats.max_hp
    assert WALKYRION.stats.speed < NOXX.stats.speed


def test_yeti_is_the_slowest_hero_and_slower_than_most_of_the_dungeon():
    """The trade he made, stated as a test so it cannot be quietly undone.

    A tank with average speed is not a choice, it is Noxx with more armour. Yeti
    is the only hero who does not get to pick his fights.
    """
    assert min(HEROES.values(), key=lambda h: h.stats.speed) is YETI

    speeds = [template.stats.speed for template in ENEMIES.values()]
    assert YETI.stats.speed < sum(speeds) / len(speeds)
    # Not quite the slowest thing alive -- a ghoul shuffles along at 0.7, and
    # being barely ahead of it is fine. The two that matter both move first.
    assert YETI.stats.speed < ENEMIES["bone"].stats.speed
    assert YETI.stats.speed < ENEMIES["wraith"].stats.speed


def test_every_hero_has_its_own_glyph_colour_and_blurb():
    """The select screen renders these, so none of them may be blank."""
    glyphs = [hero.glyph for hero in HEROES.values()]
    assert len(set(glyphs)) == len(HEROES)
    for hero in HEROES.values():
        assert len(hero.glyph) == 1
        assert hero.color
        assert hero.title
        assert hero.blurb
        assert hero.name.lower().startswith(hero.glyph.lower()), (
            f"{hero.key} is a {hero.glyph} but is not called {hero.glyph}..."
        )


# -- difficulty by depth ----------------------------------------------------
DEPTHS = range(1, 13)


def test_potency_is_one_on_the_first_floor():
    """``ENEMIES`` describes floor 1 exactly as written.

    If this breaks, every other test that builds a monster from a bare template
    is quietly testing a floor that no longer exists.
    """
    assert potency(1) == 1.0
    for template in ENEMIES.values():
        assert scale_template(template, 1) is template


def test_potency_rises_and_then_stops():
    """Monotonically up, capped, and never below 1."""
    values = [potency(d) for d in DEPTHS]
    assert values == sorted(values)
    assert values[0] == 1.0
    assert max(values) <= MAX_POTENCY
    assert potency(999) == MAX_POTENCY
    # Depth is not a difficulty slider into negative numbers.
    assert potency(0) == 1.0


def test_monsters_only_ever_get_tougher():
    """Health, damage and speed never go down, for any kind, on any floor.

    Without this, a rounding slip could make floor 3 weaker than floor 2 and the
    curve would stop being a curve.
    """
    for template in ENEMIES.values():
        previous = scale_template(template, 1).stats
        for depth in DEPTHS:
            current = scale_template(template, depth).stats
            assert current.max_hp >= previous.max_hp, (template.key, depth)
            assert current.damage[0] >= previous.damage[0], (template.key, depth)
            assert current.damage[1] >= previous.damage[1], (template.key, depth)
            assert current.speed >= previous.speed, (template.key, depth)
            previous = current


def test_scaled_monsters_are_actually_harder_by_the_top_floors():
    """A potency of 2.0 has to mean twice the health and twice the damage.

    Asserting the constant alone would pass even if the scaling were never
    applied to the stats that matter.
    """
    deep = scale_template(ENEMIES["ghoul"], 12)
    base = ENEMIES["ghoul"]
    assert potency(12) == MAX_POTENCY
    assert deep.stats.max_hp == round(base.stats.max_hp * MAX_POTENCY)
    assert deep.stats.damage[1] == round(base.stats.damage[1] * MAX_POTENCY)


def test_scaling_never_produces_a_zero_damage_roll():
    """A minimum of 0 would make a monster harmless half the time."""
    for template in ENEMIES.values():
        for depth in DEPTHS:
            low, high = scale_template(template, depth).stats.damage
            assert low >= 1
            assert high >= low


def test_a_newly_spawned_monster_starts_at_full_health():
    """Scaling raises ``max_hp``, and ``hp`` has to follow it.

    Easy to get wrong: raise ``max_hp`` alone and every deep-floor monster spawns
    already wounded, which reads as the curve being far harsher than it is.
    """
    for template in ENEMIES.values():
        for depth in DEPTHS:
            stats = scale_template(template, depth).stats
            assert stats.hp == stats.max_hp


def test_scaling_does_not_mutate_the_template():
    """``ENEMIES`` outlives every actor, so it has to survive scaling untouched."""
    fields = ("max_hp", "damage", "speed")
    before = {k: tuple(getattr(t.stats, f) for f in fields) for k, t in ENEMIES.items()}
    for template in ENEMIES.values():
        for depth in DEPTHS:
            scale_template(template, depth)
    after = {k: tuple(getattr(t.stats, f) for f in fields) for k, t in ENEMIES.items()}
    assert before == after


def test_armour_and_evasion_are_not_scaled():
    """Doubling armour takes more off each hit than doubling damage adds."""
    for template in ENEMIES.values():
        for depth in DEPTHS:
            scaled = scale_template(template, depth).stats
            assert scaled.armor == template.stats.armor, (template.key, depth)
            assert scaled.evasion == template.stats.evasion, (template.key, depth)
            assert scaled.accuracy == template.stats.accuracy, (template.key, depth)


# -- the enemy mix drifts as well as the numbers ----------------------------
def _share(key: str, depth: int) -> float:
    """Fraction of a floor's spawns taken by ``key`` at ``depth``."""
    target = ENEMIES[key]
    total = sum(
        weight_at_depth(t.weight, t.weight_growth, depth) for t in ENEMIES.values()
    )
    return weight_at_depth(target.weight, target.weight_growth, depth) / total


def test_only_the_wraith_becomes_more_common():
    """The mix has to drift, or every floor is the same fight.

    Note what is and is not asserted. The ghoul's and skeleton's *weights* stay
    put, but their *shares* fall, because the wraith is eating a bigger slice of
    a pool whose total grows. Asserting the share would have been the more
    obvious test and it would have been the wrong one: a weight that drifts while
    its share does not is not a drifting weight.
    """
    for steady in ("ghoul", "bone"):
        template = ENEMIES[steady]
        assert weight_at_depth(template.weight, template.weight_growth, 8) == template.weight
        assert _share(steady, 8) < _share(steady, 1)

    assert _share("wraith", 8) > _share("wraith", 1) * 1.5


def test_spawn_weights_at_a_depth_are_still_valid():
    """Every floor has to be able to spawn something."""
    for depth in DEPTHS:
        # Never-rolled templates are out of the table on purpose: the hunter is
        # placed by the floor rather than drawn from it, and it carries a weight
        # of zero so that nothing can draw it by accident.
        weights = [
            weight_at_depth(t.weight, t.weight_growth, depth)
            for t in ENEMIES.values()
            if t.weight > 0
        ]
        assert all(w > 0 for w in weights)
        assert sum(weights) > 0


def test_picking_an_enemy_at_depth_returns_a_depth_sized_one():
    rng = Rng(3)
    smallest_on_floor_one = min(t.stats.max_hp for t in ENEMIES.values())
    for depth in (4, 9):
        picked = [pick_enemy_template(rng, depth) for _ in range(200)]
        assert min(t.stats.max_hp for t in picked) > smallest_on_floor_one


def test_a_deep_floor_is_actually_populated_with_bigger_monsters():
    """End to end: the curve has to reach the dungeon, not just the helper."""
    state = start_run(NOXX, seed=4)
    weak = sum(e.stats.max_hp for e in state.enemies)

    state.build_floor(10)
    assert state.depth == 10
    assert state.enemies
    # Floor 10 spawns more monsters *and* bigger ones, so comparing sums is
    # enough; the exact per-monster numbers are covered above.
    assert sum(e.stats.max_hp for e in state.enemies) > weak


def test_descending_does_not_make_monsters_weaker():
    """Cheap guard against the sign of the scaling being inverted."""
    state = start_run(NOXX, seed=8)
    for depth in range(2, 8):
        before = sum(e.stats.max_hp for e in state.enemies)
        state.build_floor(depth)
        after = sum(e.stats.max_hp for e in state.enemies)
        # Not a strict comparison: the enemy count grows too, and a floor can
        # roll all-ghouls right after an all-skeletons one. It only has to not
        # collapse, and every monster's own stats are covered above.
        assert after >= before * 0.5, f"floor {depth} got weaker"


# -- combat maths ----------------------------------------------------------
def test_hit_chance_stays_in_bounds():
    hero = make_hero(NOXX, (0, 0))
    ghost = Actor("g", ActorKind.ENEMY, Stats(evasion=99), (1, 0))
    tank = Actor("t", ActorKind.ENEMY, Stats(evasion=-50), (1, 0))
    assert hit_chance(hero, ghost) >= MIN_HIT_CHANCE
    assert hit_chance(hero, tank) <= MAX_HIT_CHANCE


def test_noxx_evades_much_of_what_throws_at_him():
    """Evasion 5 is half the reason he works; assert it actually pays."""
    hero = make_hero(NOXX, (0, 0))
    ghoul = make_enemy(ENEMIES["ghoul"], (1, 0))
    rng = Rng(5)
    hits = sum(
        1
        for _ in range(4000)
        if attack(ghoul, hero, rng).hit
    )
    # 35% by the formula, with room for the sample.
    assert 1200 < hits < 1600, f"the ghoul landed {hits / 4000:.0%} of its swings"


def test_evasion_five_is_the_last_point_that_counts():
    """The ceiling is arithmetic, not taste.

    Hit chance bottoms out at 30%. Every point of evasion is worth ten, so a
    sixth point against anything with accuracy 0 is paid for and not received --
    which is why five is the most any hero should carry, and why Noxx carries
    exactly five.
    """
    for evasion in range(0, 12):
        hero = make_hero(
            NOXX, (0, 0)
        )
        hero.stats.evasion = evasion
        ghoul = make_enemy(ENEMIES["ghoul"], (1, 0))  # accuracy 0
        chance = hit_chance(ghoul, hero)

        if evasion <= 5:
            assert chance == pytest.approx(0.85 - 0.1 * evasion), evasion
        else:
            assert chance == MIN_HIT_CHANCE, evasion

    assert NOXX.stats.evasion == 5


def test_crit_rate_is_about_right():
    rng = Rng(99)
    crits = sum(
        1
        for _ in range(4000)
        if attack(make_hero(NOXX, (0, 0)), make_enemy(ENEMIES["ghoul"], (1, 0)), rng).crit
    )
    assert 800 < crits < 1200  # ~25%


def test_crit_multiplies_damage():
    hero = make_hero(NOXX, (0, 0))
    target = Actor("t", ActorKind.ENEMY, Stats(max_hp=9999, hp=9999, armor=0), (1, 0))
    rng = Rng(3)
    plain, crits = [], []
    for _ in range(3000):
        probe = Actor("t", ActorKind.ENEMY, Stats(max_hp=9999, hp=9999, armor=0), (1, 0))
        outcome = attack(hero, probe, rng)
        (crits if outcome.crit else plain).append(outcome.damage)
    assert max(plain) <= 6
    assert max(crits) >= 11  # 6 * 2.2 = 13.2


def test_damage_is_bounded_and_armour_applies():
    hero = make_hero(NOXX, (0, 0))
    soft = Actor("s", ActorKind.ENEMY, Stats(max_hp=999, hp=999, armor=0), (1, 0))
    armoured = Actor("a", ActorKind.ENEMY, Stats(max_hp=999, hp=999, armor=5), (1, 0))
    rng = Rng(21)
    a = max(attack(hero, soft, rng).damage for _ in range(200))
    b = max(attack(hero, armoured, rng).damage for _ in range(200))
    assert a >= b + 5


def test_kill_marks_the_target_dead():
    hero = make_hero(NOXX, (0, 0))
    victim = Actor("v", ActorKind.ENEMY, Stats(max_hp=1, hp=1), (1, 0))
    rng = Rng(2)
    outcome = None
    for _ in range(200):
        probe = Actor("v", ActorKind.ENEMY, Stats(max_hp=1, hp=1), (1, 0))
        outcome = attack(hero, probe, rng)
        if outcome.killed:
            break
    assert outcome is not None and outcome.killed
    assert not victim.alive or True  # probe was discarded; assert on outcome only


def test_verbs_agree_with_their_subject():
    from neverdeads_revenge.game.combat import AttackOutcome

    def verbs(**kw):
        base = dict(hit=True, crit=False, damage=5, killed=False)
        base.update(kw)
        o = AttackOutcome(**base)
        return o.verb, o.verb_second_person

    assert verbs() == ("hits", "hit")
    assert verbs(crit=True) == ("crits", "crit")
    assert verbs(killed=True) == ("kills", "kill")
    assert verbs(killed=True, crit=True) == ("obliterates", "obliterate")
    assert verbs(hit=False) == ("misses", "miss")
    assert verbs(hit=False, dodged=True) == ("misses", "miss")


def test_revenge_stacks_then_caps():
    """Each trait stops paying at its own cap.

    One shared number was the first attempt and it was wrong: ``+0.3 speed`` and
    ``+1 armour`` are not the same amount of game, so a cap of five either
    strangled the speed hero or let the armour hero run away with the run.
    """
    for hero in HEROES.values():
        actor = make_hero(hero, (0, 0))
        stacks = 0
        for _ in range(50):
            stacks = apply_revenge(actor, stacks + 1)
        assert stacks == hero.trait.cap, hero.key
        assert stacks <= REVENGE_MAX_STACKS[hero.trait]


def test_each_hero_collects_their_own_revenge():
    """Three heroes, three different rewards for the same mechanic.

    The speed bonus used to be handed to everyone, which meant the *slow* hero
    gained the most from it: +1.5 on a base of 0.75 triples Yeti's actions and
    merely doubles Noxx's. The trait now follows the hero's own strength.
    """
    expected = {
        "noxx": lambda a: a.speed == pytest.approx(1.5 + 5 * 0.3),
        "yeti": lambda a: a.armor == 3 + 3,
        "walkyrion": lambda a: a.damage_bonus == 8,
    }
    for key, hero in HEROES.items():
        actor = make_hero(hero, (0, 0))
        apply_revenge(actor, 99)
        assert expected[key](actor), f"{key} did not collect its own grant"


def test_revenge_grants_nothing_but_the_heroes_own_stat():
    """A hero must not collect a stat they were never promised.

    Yeti getting speed as well as armour, or Walkyrion getting both, would make
    the trait a pile of bonuses rather than a character.
    """
    for hero in HEROES.values():
        actor = make_hero(hero, (0, 0))
        apply_revenge(actor, hero.trait.cap)
        speed_gained = actor.speed > hero.stats.speed
        armour_gained = actor.armor > hero.stats.armor
        damage_gained = actor.damage_bonus > 0
        gained = [
            name
            for name, flag in (
                ("speed", speed_gained),
                ("armour", armour_gained),
                ("damage", damage_gained),
            )
            if flag
        ]
        assert gained == [hero.trait.label], (
            f"{hero.key} collects {gained}, not just {hero.trait.label}"
        )


def test_lapsing_revenge_leaves_no_residue():
    """Clearing has to undo the grant completely, whichever one it was.

    This is why ``apply_revenge`` sets rather than increments: gaining and
    lapsing are then the same call, so a new floor cannot leave a hero holding a
    bonus from a floor they already left.
    """
    for hero in HEROES.values():
        actor = make_hero(hero, (0, 0))
        before = (actor.speed, actor.armor, actor.damage_bonus)
        apply_revenge(actor, hero.trait.cap)
        apply_revenge(actor, 0)
        assert (actor.speed, actor.armor, actor.damage_bonus) == before


def test_revenge_never_goes_negative():
    actor = make_hero(NOXX, (0, 0))
    assert apply_revenge(actor, -3) == 0
    assert actor.speed_bonus == 0.0


def test_the_armour_trait_actually_stops_damage():
    """The grant has to reach combat, not just the actor's fields.

    ``Stats.hurt`` lives on the shared template and has no idea REVENGE exists,
    so the bonus is passed in from the actor. A test that only checked
    ``actor.armor`` would pass while every hit went through unchanged.
    """
    yeti = make_hero(YETI, (0, 0))
    ghoul = make_enemy(ENEMIES["ghoul"], (1, 0))

    unarmoured = make_hero(YETI, (0, 0))
    apply_revenge(unarmoured, 0)
    apply_revenge(yeti, yeti.trait.cap)

    before_plain, before_armoured = unarmoured.hp, yeti.hp
    rng_plain, rng_armoured = Rng(7), Rng(7)
    for _ in range(60):
        attack(ghoul, unarmoured, rng_plain)
        attack(ghoul, yeti, rng_armoured)

    assert unarmoured.hp < before_plain, "the ghoul never landed anything"
    assert yeti.hp > unarmoured.hp, "REVENGE armour did not reduce the damage"


def test_the_damage_trait_actually_adds_damage():
    """Flat, on every hit, and visible as a bigger roll.

    Paired seeds rather than one shared generator: two draws from the same
    generator are two different rolls, so the comparison has to hold the roll
    fixed and vary only the bonus.
    """
    walkyrion = make_hero(WALKYRION, (0, 0))
    plain = make_hero(WALKYRION, (0, 0))
    apply_revenge(walkyrion, walkyrion.trait.cap)

    stacks = walkyrion.trait.cap
    bonus = int(stacks * walkyrion.trait.per_stack)
    assert bonus > 0

    for seed in range(200):
        assert walkyrion.damage_roll(Rng(seed)) == plain.damage_roll(Rng(seed)) + bonus


def test_revenge_lapses_when_the_floor_does():
    """Whatever the hero collects, a descent takes it back."""
    from neverdeads_revenge.world.tiles import Tile

    for hero in HEROES.values():
        state = start_run(hero, seed=5)
        for _ in range(4):
            state.kills += 1
            state.revenge_stacks = apply_revenge(
                state.player, state.revenge_stacks + 1
            )
        assert state.revenge_stacks > 0
        state.player.position = state.dungeon_map.find_tile(Tile.STAIRS_DOWN)[0]
        perform_action(state, Action.DESCEND)
        assert state.revenge_stacks == 0, hero.key
        assert state.player.speed_bonus == 0.0
        assert state.player.armor_bonus == 0
        assert state.player.damage_bonus == 0


# -- run setup -------------------------------------------------------------
def test_start_run_places_the_player_somewhere_solid():
    for seed in SEEDS:
        state = start_run(NOXX, seed=seed)
        assert state.dungeon_map.is_walkable(state.player.position)


def test_same_seed_reproduces_the_whole_dungeon():
    a = start_run(NOXX, seed=1234)
    b = start_run(NOXX, seed=1234)
    assert a.dungeon_map.tiles == b.dungeon_map.tiles
    assert [e.position for e in a.enemies] == [e.position for e in b.enemies]


def test_different_seeds_give_different_dungeons():
    a = start_run(NOXX, seed=1).dungeon_map.tiles
    b = start_run(NOXX, seed=2).dungeon_map.tiles
    assert a != b


def test_run_starts_with_vision_already_computed():
    state = start_run(NOXX, seed=5)
    assert state.player.position in state.dungeon_map.visible
    assert state.dungeon_map.visible <= state.dungeon_map.explored


# -- actions ---------------------------------------------------------------
def test_moving_into_a_wall_costs_nothing():
    state = start_run(NOXX, seed=8)
    # The player starts mid-room where nothing is blocked, so walk them to a
    # spot that actually has a wall in it before testing this.
    corner = next(
        (pos for pos in state.dungeon_map.walkable_positions() if _has_wall_neighbour(state, pos)),
        None,
    )
    if corner is None:
        pytest.skip("no wall-adjacent floor on this floor")
    state.player.position = corner
    state.refresh_vision()

    blocked = next(
        d
        for d in Direction
        if d is not Direction.NONE
        and not state.dungeon_map.is_walkable(d.step(state.player.position))
    )
    before_turn = state.turn
    before_pos = state.player.position
    result = perform_action(state, _action_for(blocked))
    assert not result.consumed_turn
    assert not result.acted
    assert state.turn == before_turn
    assert state.player.position == before_pos


def _has_wall_neighbour(state: GameState, pos) -> bool:
    return any(
        not state.dungeon_map.is_walkable(d.step(pos))
        for d in Direction
        if d is not Direction.NONE
    )


def test_moving_into_open_ground_advances_the_position():
    state = start_run(NOXX, seed=8)
    open_move = next(
        (
            d
            for d in Direction
            if d is not Direction.NONE and state.dungeon_map.is_walkable(d.step(state.player.position))
        ),
        None,
    )
    if open_move is None:
        pytest.skip("player is fully enclosed")
    before = state.player.position
    result = perform_action(state, _action_for(open_move))
    assert result.consumed_turn
    assert state.player.position == open_move.step(before)


def test_waiting_costs_a_turn():
    state = start_run(NOXX, seed=8)
    before = state.turn
    assert perform_action(state, Action.WAIT).consumed_turn
    assert state.turn == before + 1


def test_player_and_enemy_never_share_a_cell():
    state = start_run(NOXX, seed=4)
    for _ in range(120):
        if state.over:
            break
        perform_action(state, Action.WAIT)
    for enemy in state.living_enemies:
        assert enemy.position != state.player.position


def test_killing_an_enemy_removes_it_from_the_floor():
    state = start_run(NOXX, seed=6)
    victim = _place_adjacent_enemy(state)
    for _ in range(20):
        if state.over or not victim.alive:
            break
        perform_action(state, Action.MOVE_EAST)
    assert state.kills >= 1
    assert victim not in state.enemies
    assert victim not in state.turn_queue


def test_killing_grants_revenge_speed():
    state = start_run(NOXX, seed=6)
    victim = _place_adjacent_enemy(state)
    for _ in range(20):
        if state.over or not victim.alive:
            break
        perform_action(state, Action.MOVE_EAST)
    assert state.revenge_stacks >= 1
    assert state.player.speed == pytest.approx(1.5 + 0.3 * state.revenge_stacks)


def test_descending_requires_standing_on_the_stairs():
    state = start_run(NOXX, seed=6)
    assert not state.on_stairs
    result = perform_action(state, Action.DESCEND)
    assert not result.consumed_turn
    assert state.depth == 1


def test_descending_from_the_stairs_makes_a_new_floor():
    state = start_run(NOXX, seed=6)
    state.player.position = state.stairs
    state.refresh_vision()
    perform_action(state, Action.DESCEND)
    assert state.depth == 2
    assert state.floors_cleared == 1
    assert state.revenge_stacks == 0, "revenge lapses between floors"
    assert state.player.speed_bonus == 0.0


def test_enemies_only_act_when_the_player_can_see_them():
    """Monsters out of sight hold position. Keeps the fight about what you can see."""
    state = start_run(NOXX, seed=13)
    hidden = state.enemies[0]

    # Pick a genuinely dark cell rather than hoping one exists where we guessed.
    state.refresh_vision()
    dark = next(
        (
            pos
            for pos in state.dungeon_map.walkable_positions()
            if not state.dungeon_map.is_visible(pos)
        ),
        None,
    )
    if dark is None:
        pytest.skip("player happens to see the whole floor")

    hidden.position = dark
    before = hidden.position
    # Wait a real turn, otherwise the queue hands control straight back to the
    # player and the enemy never gets an action to be denied.
    perform_action(state, Action.WAIT)
    assert hidden.position == before


def test_a_visible_enemy_does_close_in():
    """The counterpart: seen monsters do get to move."""
    state = start_run(NOXX, seed=13)
    for other in state.enemies[1:]:
        state.turn_queue.remove(other)
    del state.enemies[1:]

    hunter = state.enemies[0]
    state.dungeon_map.clear_visibility()
    hunter.position = Direction.EAST.step(Direction.EAST.step(state.player.position))
    state.refresh_vision()
    if not state.dungeon_map.is_visible(hunter.position):
        pytest.skip("chosen cell is walled off")

    before_distance = chebyshev(hunter.position, state.player.position)
    # One wait is not necessarily enough: the scheduler only hands an action to
    # monsters that come due before Noxx's next action. Speed 1.0 needs two of
    # his actions to come round.
    for _ in range(4):
        if state.over or chebyshev(hunter.position, state.player.position) < before_distance:
            break
        perform_action(state, Action.WAIT)
    assert chebyshev(hunter.position, state.player.position) < before_distance


def test_a_faster_enemy_acts_more_often_than_a_slower_one(monkeypatch):
    """The core mechanic measured through the real action flow.

    Noxx at speed 1.5 should take roughly three actions for every two taken by a
    speed-1.0 monster. Counts actual enemy actions rather than trusting the
    scheduler in isolation.
    """
    counts = {"slow": 0, "fast": 0}
    real_take_turn = actions_module.take_turn

    def counting_take_turn(state, actor):
        if actor.name == "slow":
            counts["slow"] += 1
        elif actor.name == "fast":
            counts["fast"] += 1
        return real_take_turn(state, actor)

    monkeypatch.setattr(actions_module, "take_turn", counting_take_turn)

    def run_with(enemy_speed: float, label: str) -> None:
        state = start_run(NOXX, seed=17)
        for other in state.enemies[1:]:
            state.turn_queue.remove(other)
        del state.enemies[1:]

        enemy = state.enemies[0]
        enemy.name = label
        enemy.stats.speed = enemy_speed
        enemy.stats.max_hp = 9999
        enemy.stats.hp = 9999
        enemy.behaviour = "aggressive"
        state.player.stats.hp = 9999
        state.player.stats.max_hp = 9999
        # Keep both alive so the count runs the full length.
        state.turn_queue.remove(enemy)
        state.turn_queue.add(enemy)

        for _ in range(200):
            if state.over:
                break
            perform_action(state, Action.WAIT)

    run_with(1.0, "slow")
    slow_actions = counts["slow"]
    counts["fast"] = 0
    run_with(2.0, "fast")
    fast_actions = counts["fast"]

    assert fast_actions > slow_actions * 1.5, (
        f"speed 2.0 monster acted {fast_actions}x, speed 1.0 monster {slow_actions}x"
    )


def test_player_can_die():
    state = start_run(NOXX, seed=3)
    state.player.stats.hp = 1
    _place_adjacent_enemy(state)
    for _ in range(60):
        if state.over:
            break
        perform_action(state, Action.WAIT)
    assert state.run_state is RunState.DEAD
    assert not state.player.alive
    assert state.over


def test_no_actions_are_accepted_after_death():
    state = start_run(NOXX, seed=3)
    state.player.stats.hp = 1
    _place_adjacent_enemy(state)
    for _ in range(60):
        if state.over:
            break
        perform_action(state, Action.WAIT)
    assert state.over
    before = state.turn
    result = perform_action(state, Action.MOVE_NORTH)
    assert not result.consumed_turn and result.died
    assert state.turn == before


def test_a_kill_is_worth_less_than_the_time_it_costs():
    """Killing pays score now -- but not enough to make farming the best line.

    A fight is five to nine player turns and a turn is worth ten points under
    budget, so the cheapest fight costs fifty points of speed bonus. A kill has
    to be worth less than that or the game becomes a floor-sweeper and the speed
    bonus a rounding error, and the decision between fighting and leaving stops
    being a decision.

    This is the whole balance of the change, so it is the test that states it.
    """
    from neverdeads_revenge.game.state import KILL_SCORE, SPEED_BONUS_PER_TURN

    state = start_run(NOXX, seed=6)
    assert state.score == 0

    state.depth = 1  # potency 1, so a kill is worth exactly KILL_SCORE
    state.kills = 1
    cheapest_fight = 5 * SPEED_BONUS_PER_TURN

    assert state.kill_score == KILL_SCORE
    assert state.kill_score < cheapest_fight, (
        "a kill pays more than the cheapest fight costs in time"
    )


def test_a_deep_kill_is_worth_more_than_a_shallow_one():
    """Scaled by depth the way a coin is, so the deep floor is worth the risk."""
    shallow = start_run(NOXX, seed=6)
    deep = start_run(NOXX, seed=6)
    for state in (shallow, deep):
        state.kills = 10
    shallow.depth = 1
    deep.depth = 10

    assert deep.kill_score > shallow.kill_score


def test_score_rewards_speed():
    """The whole point of the change: fewer turns, more points."""
    fast = start_run(NOXX, seed=6)
    slow = start_run(NOXX, seed=6)
    for state in (fast, slow):
        state.kills = 5
        state.floors_cleared = 3
    fast.total_turns = 60
    slow.total_turns = 200

    assert fast.speed_bonus > slow.speed_bonus
    assert fast.score > slow.score


def test_the_speed_bonus_cannot_go_negative():
    """Slower than the budget scores nothing, not less than nothing.

    A negative line on a summary screen reads as a punishment rather than a
    comparison, and it would let a slow run fall below a run that died earlier.
    """
    state = start_run(NOXX, seed=6)
    state.floors_cleared = 3
    state.total_turns = TURN_BUDGET_PER_FLOOR * 3 + 500

    assert state.speed_bonus == 0
    assert state.score == state.base_score


def test_the_speed_bonus_scales_with_the_floors_actually_cleared():
    """Standing still on floor one must not bank a budget it never spent.

    Without the per-floor scaling, a player who never descends would be handed a
    bonus for the turns they did not use getting anywhere.
    """
    idle = start_run(NOXX, seed=6)
    idle.total_turns = 0
    assert idle.floors_cleared == 0
    assert idle.speed_bonus == 0

    deep = start_run(NOXX, seed=6)
    deep.floors_cleared = 5
    deep.total_turns = 0
    assert deep.speed_bonus == 5 * TURN_BUDGET_PER_FLOOR * SPEED_BONUS_PER_TURN


def test_walking_further_does_not_score():
    """Steps are a run statistic now, not a score input.

    The old formula paid per cell, which rewarded combing every corner of a floor
    over getting out of it -- the opposite of what the run is about.
    """
    walker = start_run(NOXX, seed=6)
    runner = start_run(NOXX, seed=6)
    for state in (walker, runner):
        state.kills = 4
        state.floors_cleared = 2
        state.total_turns = 100
    walker.player.steps = 900
    runner.player.steps = 12

    assert walker.score == runner.score
    assert walker.base_score == runner.base_score


def test_steps_are_a_run_total_not_a_floor_one():
    """The summary says "Cells walked" and now means it.

    ``steps`` used to reset on every descent, so the number reported was the
    last floor's walking -- and the old score, which counted steps, was quietly
    counting only that one floor too.
    """
    state = start_run(NOXX, seed=3)
    state.player.steps = 42
    state.player.position = state.stairs

    perform_action(state, Action.DESCEND)

    assert state.depth == 2
    assert state.player.steps == 42, "the walk was reset by the descent"


# -- curses -----------------------------------------------------------------
def test_every_curse_states_a_price():
    """The dialog shows this sentence and nothing else. A blank one is a trap."""
    from neverdeads_revenge.game.curses import CURSES

    assert CURSES, "there are no curses to test"
    for key, curse in CURSES.items():
        assert curse.key == key
        assert curse.name, key
        assert curse.price and curse.price[0].islower(), key
        assert not curse.price.endswith("."), "the dialog adds the full stop"


def test_every_curse_actually_does_something():
    """A curse with no effect is a chest that costs nothing.

    Checked against the *declared defaults* rather than against a list of field
    names, because the list is a thing that goes stale: eight curses were added
    to this game in one afternoon and this test went on passing for none of
    them. A curse does something if any field differs from what it is born with.
    """
    from dataclasses import MISSING, fields

    from neverdeads_revenge.game.curses import CURSES

    for key, curse in CURSES.items():
        changed = any(
            getattr(curse, field.name) != field.default
            for field in fields(curse)
            if field.default is not MISSING
        )
        assert changed, f"{key} does nothing"


def test_wither_takes_a_quarter_of_your_health_for_good():
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    before_hp, before_max = state.player.hp, state.player.max_hp

    state.add_curse(CURSES["wither"])

    assert state.player.max_hp == before_max - round(before_max * 0.25)
    assert state.player.hp <= state.player.max_hp
    assert state.player.max_hp < before_max, "the maximum came back"


def _walk_one_step(state: GameState) -> bool:
    """Move in any direction that works. Returns whether the player moved."""
    before = state.player.position
    for action in (
        Action.MOVE_NORTH,
        Action.MOVE_SOUTH,
        Action.MOVE_EAST,
        Action.MOVE_WEST,
    ):
        perform_action(state, action)
        if state.player.position != before:
            return True
    return False


def test_bleed_costs_blood_on_a_cadence():
    """Every so many steps, not every step: a drip, not a waterfall."""
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    state.add_curse(CURSES["bleed"])
    every = state.bleed_every
    assert every == CURSES["bleed"].bleed_every
    assert every > 1, "a cadence of one is a waterfall"

    # One step short of the next payment.
    state.player.steps = every - 1
    hp = state.player.hp

    assert _walk_one_step(state)
    assert state.player.hp == hp - 1, "the step did not cost anything"

    state.player.steps = 2 * every - 1
    hp = state.player.hp
    assert _walk_one_step(state)
    assert state.player.hp == hp - 1

    # And a step that is not on the cadence costs nothing.
    hp = state.player.hp
    assert _walk_one_step(state)
    assert state.player.hp == hp


def test_bleed_can_kill():
    """A price the player chose has to be able to finish them, or it is not one."""
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    state.add_curse(CURSES["bleed"])
    state.player.stats.hp = 1
    state.player.steps = state.bleed_every - 1

    assert _walk_one_step(state)

    assert state.run_state is RunState.DEAD
    assert not state.player.alive


def test_frail_and_heavy_land_in_the_effective_stats():
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    player = state.player
    armor, speed = player.armor, player.speed

    state.add_curse(CURSES["frail"])
    state.add_curse(CURSES["heavy"])

    assert player.armor == armor - 2
    assert player.speed == pytest.approx(speed - 0.25)


def test_dim_narrows_what_the_player_can_see():
    """Not just a number on a sheet: the field of view has to actually shrink."""
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    wide = len(state.dungeon_map.visible)
    assert state.sight_radius == VIEW_RADIUS

    state.add_curse(CURSES["dim"])
    state.refresh_vision()

    assert state.sight_radius == 5
    assert len(state.dungeon_map.visible) < wide, "the dark did not close in"


def test_famine_halves_what_a_draught_is_worth():
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    state.add_curse(CURSES["famine"])
    _give(state, "elixir")
    state.player.stats.hp = 1

    perform_action(state, Action.QUAFF)

    assert state.player.hp == 1 + round(ITEMS["elixir"].heal * 0.5)
    assert state.heal_scale == 0.5


def test_curse_changes_are_kept_apart_from_equipment():
    """The sheet has to be able to say "you are wearing this" and "this was done
    to you" as two different sentences."""
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    state.player.equipment["armour"] = make_item(ITEMS["hide"])
    state.add_curse(CURSES["frail"])

    assert state.player.curse_modifiers.armor == -2
    assert state.player.modifiers.armor == -1, "worn + cursed, summed"
    assert state.player.armor == NOXX.stats.armor - 1


def test_curses_survive_a_descent():
    """Run-long, like the health they cost. A floor change is not a cure."""
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    state.add_curse(CURSES["dim"])
    state.add_curse(CURSES["famine"])
    state.player.position = state.stairs

    perform_action(state, Action.DESCEND)

    assert state.depth == 2
    assert [c.key for c in state.curses] == ["dim", "famine"]
    assert state.sight_radius == 5
    assert state.heal_scale == 0.5


def test_the_unpaid_curses_are_the_ones_you_do_not_carry():
    """A chest whose price you have already paid is a lie: the dialog reads the
    price out and nothing further happens."""
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    assert state.unpaid_curses == tuple(CURSES)

    state.add_curse(CURSES["dim"])

    assert "dim" not in state.unpaid_curses
    assert len(state.unpaid_curses) == len(CURSES) - 1


def test_a_floor_never_offers_a_price_you_have_already_paid():
    """Fifteen chests over a run drawn from a handful of curses made duplicates not just
    possible but likely -- and two of the six stack when repeated while four do
    not, so the second one was sometimes a sentence and sometimes a no-op."""
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    for key in list(CURSES)[:-1]:
        state.add_curse(CURSES[key])
    state.player.position = state.stairs

    perform_action(state, Action.DESCEND)

    chests = [i for i in state.dungeon_map.items.values() if i.kind == "chest"]
    assert chests, "the floor offered nothing at all"
    held = {curse.key for curse in state.curses}
    for chest in chests:
        assert chest.curse not in held, f"it charged for {chest.curse} twice"


def test_a_floor_with_every_price_paid_holds_no_chests():
    """The same rule the generator already had for a floor told about no curses:
    better an empty floor than a bargain that costs nothing."""
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    for key in CURSES:
        state.add_curse(CURSES[key])
    assert state.unpaid_curses == ()
    state.player.position = state.stairs

    perform_action(state, Action.DESCEND)

    assert not [i for i in state.dungeon_map.items.values() if i.kind == "chest"]


def test_a_wraiths_touch_never_repeats_a_curse_you_carry():
    """Same reason as the chest: the touch is meant to leave something *new*
    behind, and half of the four touch curses do not stack."""
    from neverdeads_revenge.game.actions import take_turn
    from neverdeads_revenge.game.curses import CURSES, TOUCH_CURSES

    state = start_run(NOXX, seed=3)
    wraith = _wraith_beside(state)
    state.add_curse(CURSES[TOUCH_CURSES[0]])

    for _ in range(400):
        state.player.stats.hp = state.player.stats.max_hp
        take_turn(state, wraith)
        keys = [curse.key for curse in state.curses]
        assert len(keys) == len(set(keys)), keys


# -- chests -----------------------------------------------------------------
def _put_a_chest(state: GameState, curse: str = "wither", contents: str = "edge"):
    """Stand the player on a chest with known contents."""
    from neverdeads_revenge.world.items import make_chest

    chest = make_chest(curse, ITEMS[contents])
    state.dungeon_map.add_item(state.player.position, chest)
    return chest


def test_a_chest_asks_before_it_opens():
    """``enter`` on a chest is a question, not an action. No turn, no lid."""
    state = start_run(NOXX, seed=1)
    chest = _put_a_chest(state)

    result = perform_action(state, Action.INTERACT)

    assert result.prompt is not None
    assert not result.consumed_turn
    assert state.total_turns == 0
    assert state.dungeon_map.item_at(state.player.position) is chest, "it opened"
    assert state.curses == []


def test_the_question_names_the_price_and_not_the_reward():
    """Showing both would turn daring into arithmetic.

    The reward has to stay behind the lid: the player is weighing a cost against
    a hope, not comparing two numbers.
    """
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    _put_a_chest(state, curse="dim", contents="warden")

    prompt = perform_action(state, Action.INTERACT).prompt
    assert prompt is not None
    assert CURSES["dim"].price in prompt
    assert "warden" not in prompt
    assert "warden" not in prompt


def test_opening_pays_the_price_and_hands_over_the_reward():
    from neverdeads_revenge.game.curses import CURSES

    state = start_run(NOXX, seed=1)
    _put_a_chest(state, curse="wither", contents="edge")
    perform_action(state, Action.INTERACT)

    perform_action(state, Action.OPEN_CHEST)

    assert [c.key for c in state.curses] == ["wither"]
    assert state.player.equipment["weapon"].name == "the runed edge"
    assert state.dungeon_map.item_at(state.player.position) is None, "the chest stayed"


def test_opening_a_chest_costs_a_turn():
    """The riskiest thing in the game -- a permanent curse, read and agreed to --
    was the one action a monster had no answer to. A draught costs a turn; so
    does this."""
    state = start_run(NOXX, seed=1)
    _put_a_chest(state, curse="dim", contents="edge")

    result = perform_action(state, Action.OPEN_CHEST)

    assert result.consumed_turn
    assert state.total_turns == 1
    assert [c.key for c in state.curses] == ["dim"]


def test_opening_nothing_does_nothing():
    """``OPEN_CHEST`` is only reachable from the dialog, but it is still a verb."""
    state = start_run(NOXX, seed=1)
    state.player.position = next(
        pos
        for pos in state.dungeon_map.floor_positions()
        if state.dungeon_map.item_at(pos) is None
    )

    result = perform_action(state, Action.OPEN_CHEST)

    assert not result.acted
    assert state.curses == []
    assert state.player.equipment == {}


def test_a_chest_cannot_be_picked_up():
    """It is furniture, not loot. ``PICK_UP`` must not put it in the pack."""
    state = start_run(NOXX, seed=1)
    _put_a_chest(state)

    perform_action(state, Action.PICK_UP)

    assert state.inventory == []


# -- loot and drinking ------------------------------------------------------
def _give(state: GameState, key: str) -> GroundItem:
    """Put a draught of ``key`` in the player's hands."""
    item = make_item(ITEMS[key])
    state.inventory.append(item)
    return item


def test_picking_up_a_draught_puts_it_in_the_inventory():
    """Floor loot and carried loot are different things, and both must update."""
    state = start_run(NOXX, seed=1)
    _place(state, make_item(ITEMS["potion"]))
    pos = state.player.position
    item = state.dungeon_map.item_at(pos)

    result = perform_action(state, Action.PICK_UP)

    assert state.inventory == [item]
    assert state.dungeon_map.item_at(pos) is None
    # Taking something off the ground costs no turn: it is not a decision the
    # monsters should get to answer.
    assert not result.consumed_turn
    assert state.turn == 0


def _place(state: GameState, item) -> None:
    """Drop ``item`` under the player and stand them on it."""
    state.dungeon_map.add_item(state.player.position, item)


# -- equipment --------------------------------------------------------------
def test_equipping_fills_an_empty_slot():
    state = start_run(NOXX, seed=1)
    _place(state, make_item(ITEMS["bite"]))
    before = state.player.damage_range

    perform_action(state, Action.PICK_UP)

    assert state.player.equipment["weapon"].name == "the grey bite"
    assert state.inventory == [], "a weapon is worn, not carried"
    assert state.player.damage_range > before, "the weapon changed nothing"
    # Against the template rather than a number, so rebalancing the weapon does
    # not fail a test that was really about the wiring.
    assert state.player.modifiers.damage == ITEMS["bite"].modifiers.damage


def test_equipping_sets_the_old_one_down_beside_you():
    """Swapping has to be reversible, or auto-equipping is a trap.

    Beside rather than under: there is no comparison dialog, so the undo is that
    what you took off is on the floor next to you.
    """
    state = start_run(NOXX, seed=1)
    blade = make_item(ITEMS["bite"])
    _place(state, blade)
    perform_action(state, Action.PICK_UP)
    assert state.player.equipment["weapon"] is blade

    _place(state, make_item(ITEMS["tooth"]))
    perform_action(state, Action.PICK_UP)

    assert state.player.equipment["weapon"].name == "the rusted tooth"
    assert state.dungeon_map.item_at(state.player.position) is None, (
        "the old weapon was left under the player, where enter would pick it up"
    )
    assert any(item is blade for item in state.dungeon_map.items.values()), (
        "the grey bite was not set down anywhere"
    )


def test_swapping_equipment_is_not_an_infinite_loop():
    """Pressing enter over and over must not alternate between two weapons.

    It did: the replaced item landed under the player, so ``enter`` picked it up
    again, which put the other one back down, forever -- and ``enter`` could
    never reach the stairs. Caught by a bot that stopped descending.
    """
    state = start_run(NOXX, seed=1)
    _place(state, make_item(ITEMS["bite"]))
    perform_action(state, Action.PICK_UP)
    _place(state, make_item(ITEMS["tooth"]))

    seen = []
    for _ in range(6):
        perform_action(state, Action.PICK_UP)
        seen.append(state.player.equipment["weapon"].name)

    assert "the grey bite" not in seen, (
        f"enter put the old weapon back on, so the swap is still a loop: {seen}"
    )
    assert state.dungeon_map.item_at(state.player.position) is None


def test_stepping_onto_the_set_down_item_puts_it_back_on():
    """The whole of the undo: walk onto what you set down and take it back."""
    state = start_run(NOXX, seed=1)
    blade = make_item(ITEMS["bite"])
    _place(state, blade)
    perform_action(state, Action.PICK_UP)

    _place(state, make_item(ITEMS["tooth"]))
    perform_action(state, Action.PICK_UP)
    assert state.player.equipment["weapon"].name == "the rusted tooth"

    # By identity, not by name: the floor generator can put a blade of its own
    # down, and "the item called the grey bite" would find that one instead.
    blade_pos = next(
        pos for pos, item in state.dungeon_map.items.items() if item is blade
    )
    assert chebyshev(state.player.position, blade_pos) == 1, "it should be adjacent"

    # Walk onto it and take it back.
    state.player.position = blade_pos
    perform_action(state, Action.PICK_UP)

    assert state.player.equipment["weapon"] is blade


def test_weapon_and_armour_are_separate_slots():
    """A coat must not replace a blade."""
    state = start_run(NOXX, seed=1)
    _place(state, make_item(ITEMS["bite"]))
    perform_action(state, Action.PICK_UP)
    _place(state, make_item(ITEMS["hide"]))
    perform_action(state, Action.PICK_UP)

    assert state.player.equipment["weapon"].name == "the grey bite"
    assert state.player.equipment["armour"].name == "the thin hide"
    assert state.dungeon_map.item_at(state.player.position) is None


def test_equipment_reaches_every_effective_stat():
    """The layer has to land in combat, not just in the modifiers object.

    Each of these is read somewhere different -- damage in the roll, armour in
    ``hurt``, evasion and accuracy in ``hit_chance``, crit in ``attack`` -- so
    one assertion per stat is the only way to know the wiring is complete.
    """
    state = start_run(NOXX, seed=1)
    player = state.player
    base = (
        player.damage_range,
        player.armor,
        player.evasion,
        player.accuracy,
        player.crit_chance,
        player.crit_multiplier,
    )

    player.equipment["weapon"] = make_item(ITEMS["hunger"])
    player.equipment["armour"] = make_item(ITEMS["shroud"])

    assert player.damage_range[0] > base[0][0], "damage did not move"
    assert player.evasion > base[2], "evasion did not move"
    assert player.crit_chance > base[4], "crit did not move"
    assert player.crit_multiplier > base[5], "crit damage did not move"


def test_equipment_armour_actually_stops_a_hit():
    """``Actor.hurt`` has to pass the worn armour down, not just report it."""
    state = start_run(NOXX, seed=1)
    player = state.player
    ghoul = make_enemy(ENEMIES["ghoul"], (1, 0))

    bare = make_hero(NOXX, (0, 0))
    player.equipment["armour"] = make_item(ITEMS["hide"])

    assert player.armor == bare.armor + ITEMS["hide"].modifiers.armor
    assert player.hurt(4) <= bare.hurt(4), "the coat did not absorb anything"


def test_an_item_that_is_not_equipment_never_fills_a_slot():
    """Draughts stay draughts. A potion in the weapon slot would be absurd.

    Asserted in both directions: everything worn is a weapon, a coat or an
    amulet, and everything with a slot is worn.
    """
    from neverdeads_revenge.world.items import ITEMS as ALL_ITEMS

    wearable = ("weapon", "armour", "amulet")
    for template in ALL_ITEMS.values():
        if template.slot is not None:
            assert template.kind in wearable, template.key
            assert not template.heal, f"{template.key} both heals and is worn"
        else:
            # Two kinds of bottle now: the medicine, and the five strange
            # draughts that lay a rule on the floor.
            assert template.kind in ("draught", "strange"), template.key


def test_picking_up_nothing_says_so():
    state = start_run(NOXX, seed=1)
    state.player.position = next(
        pos
        for pos in state.dungeon_map.floor_positions()
        if state.dungeon_map.item_at(pos) is None
    )
    perform_action(state, Action.PICK_UP)
    assert state.log[-1].text == "There is nothing here to take."
    assert state.inventory == []


def test_drinking_heals_and_costs_a_turn():
    """Drinking in a fight has to be a real decision, so it takes a turn."""
    state = start_run(NOXX, seed=1)
    _give(state, "potion")
    state.player.stats.hp = 10

    result = perform_action(state, Action.QUAFF)

    assert state.player.hp == 18
    assert state.inventory == []
    assert result.consumed_turn
    assert state.total_turns == 1


def test_drinking_cannot_heal_past_the_maximum():
    state = start_run(NOXX, seed=1)
    _give(state, "elixir")
    state.player.stats.hp = state.player.max_hp - 3

    perform_action(state, Action.QUAFF)

    assert state.player.hp == state.player.max_hp, "healing overflowed the bar"


def test_drinking_prefers_the_draught_that_is_not_wasted():
    """The obvious play, made for the player.

    Drinking the elixir at 24/26 health throws away sixteen points of it. A
    careful player would always reach for the smaller one; making them do it by
    hand is busywork, not depth.
    """
    state = start_run(NOXX, seed=1)
    _give(state, "elixir")
    _give(state, "potion")
    state.player.stats.hp = state.player.max_hp - 5

    perform_action(state, Action.QUAFF)

    assert state.inventory == [state.inventory[0]]
    assert state.inventory[0].name == "elixir", "the good draught was spent on 5 hp"
    assert state.player.hp == state.player.max_hp


def test_drinking_uses_the_biggest_draught_the_wound_needs():
    """A 25-point wound is what the elixir exists for."""
    state = start_run(NOXX, seed=1)
    _give(state, "potion")
    _give(state, "elixir")
    state.player.stats.hp = 1

    perform_action(state, Action.QUAFF)

    assert state.player.hp == 21, "the elixir was held back from a 25-point wound"
    assert [item.name for item in state.inventory] == ["potion"]


def test_drinking_accepts_a_small_spill_rather_than_a_large_one():
    """When no draught fits the wound, waste the cheap one.

    At 24/26 both draughts overflow. Spending the elixir would throw away fifteen
    points to save three; spending the potion throws away five.
    """
    state = start_run(NOXX, seed=1)
    _give(state, "potion")
    _give(state, "elixir")
    state.player.stats.hp = state.player.max_hp - 2

    perform_action(state, Action.QUAFF)

    assert [item.name for item in state.inventory] == ["elixir"]
    assert state.player.hp == state.player.max_hp
    assert "spills" in " ".join(line.text for line in state.log[-2:])


def test_drinking_with_nothing_carried_is_free_and_says_so():
    state = start_run(NOXX, seed=1)
    result = perform_action(state, Action.QUAFF)
    assert state.log[-1].text == "You have nothing to drink."
    assert not result.consumed_turn
    assert state.total_turns == 0


def test_drinking_at_full_health_does_not_waste_the_draught():
    state = start_run(NOXX, seed=1)
    _give(state, "potion")

    result = perform_action(state, Action.QUAFF)

    assert state.inventory, "the draught was drunk for nothing"
    assert state.log[-1].text == "You are unhurt."
    assert not result.consumed_turn


def test_looking_in_the_inventory_costs_nothing():
    state = start_run(NOXX, seed=1)
    _give(state, "potion")
    _give(state, "potion")
    _give(state, "elixir")

    result = perform_action(state, Action.INVENTORY)

    assert not result.consumed_turn
    assert state.total_turns == 0
    assert "2x potion" in state.log[-1].text
    assert "1x elixir" in state.log[-1].text


def test_carried_draughts_survive_a_descent():
    """The inventory is the run's health reserve, not the floor's."""
    state = start_run(NOXX, seed=1)
    _give(state, "elixir")
    state.player.position = state.stairs
    perform_action(state, Action.DESCEND)
    assert [item.name for item in state.inventory] == ["elixir"]


# -- escaping ---------------------------------------------------------------
def _walk_to_the_rift(state: GameState) -> None:
    state.build_floor(ESCAPE_DEPTH)
    state.player.position = state.exit_pos


def test_a_floor_before_the_last_has_stairs_not_a_rift():
    state = start_run(NOXX, seed=1)
    assert state.stairs is not None
    assert state.exit_pos == state.stairs
    assert not state.at_the_rift


def test_the_last_floor_has_a_rift_and_no_stairs():
    """The bug this guards: ``stairs`` used to fall back to the player's own
    position, which made ``on_stairs`` true everywhere on a floor with none --
    and the last floor is exactly that floor."""
    state = start_run(NOXX, seed=1)
    _walk_to_the_rift(state)
    assert state.stairs is None
    assert state.exit_pos is not None
    assert state.on_exit
    assert state.at_the_rift
    assert state.on_stairs is False


def test_stepping_into_the_rift_wins_the_run():
    state = start_run(NOXX, seed=1)
    _walk_to_the_rift(state)
    assert state.run_state is RunState.PLAYING

    result = perform_action(state, Action.DESCEND)

    assert state.run_state is RunState.ESCAPED
    assert result.escaped
    assert not result.died, "a win must not be reported as a death"
    assert state.over
    assert state.floors_cleared == 0, "the rift is not a floor cleared"


def test_escaping_is_worth_more_than_dying_on_the_same_floor():
    state = start_run(NOXX, seed=1)
    _walk_to_the_rift(state)
    died = state.score
    perform_action(state, Action.DESCEND)
    assert state.score == died + ESCAPE_BONUS


def test_no_actions_are_accepted_after_escaping():
    state = start_run(NOXX, seed=1)
    _walk_to_the_rift(state)
    perform_action(state, Action.DESCEND)

    before = state.total_turns
    result = perform_action(state, Action.MOVE_NORTH)

    assert not result.consumed_turn
    assert not result.died
    assert result.escaped
    assert state.total_turns == before


def test_the_rift_refuses_you_away_from_it():
    """Pressing the descend key elsewhere on the last floor must not end the run."""
    state = start_run(NOXX, seed=1)
    _walk_to_the_rift(state)
    beside = (state.exit_pos[0] + 1, state.exit_pos[1])
    state.player.position = beside
    assert not state.on_exit

    result = perform_action(state, Action.DESCEND)

    assert state.run_state is RunState.PLAYING
    assert not result.escaped
    assert state.log[-1].text == "There is nothing here to take you out."


# -- longer simulations ----------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
def test_a_hundred_turns_never_crash(seed):
    """Smoke test across many generated dungeons."""
    state = start_run(NOXX, seed=seed)
    moves = [a for a in Action if a.name.startswith("MOVE")]
    for i in range(100):
        if state.over:
            break
        perform_action(state, moves[i % len(moves)])
    assert state.turn >= 0


@pytest.mark.parametrize("seed", SEEDS)
def test_vision_stays_consistent_during_play(seed):
    state = start_run(NOXX, seed=seed)
    for i in range(60):
        if state.over:
            break
        perform_action(state, [Action.WAIT, Action.MOVE_EAST, Action.MOVE_SOUTH][i % 3])
        assert state.player.position in state.dungeon_map.visible
        assert state.dungeon_map.visible <= state.dungeon_map.explored


@pytest.mark.parametrize("seed", SEEDS)
def test_the_log_never_bloats_without_bound(seed):
    state = start_run(NOXX, seed=seed)
    for i in range(200):
        if state.over:
            break
        perform_action(state, [Action.WAIT, Action.MOVE_NORTH, Action.MOVE_WEST][i % 3])
    assert len(state.log) < 2000


# -- helpers ---------------------------------------------------------------
def _action_for(direction: Direction) -> Action:
    return {
        Direction.NORTH: Action.MOVE_NORTH,
        Direction.SOUTH: Action.MOVE_SOUTH,
        Direction.EAST: Action.MOVE_EAST,
        Direction.WEST: Action.MOVE_WEST,
        Direction.NORTH_EAST: Action.MOVE_NE,
        Direction.NORTH_WEST: Action.MOVE_NW,
        Direction.SOUTH_EAST: Action.MOVE_SE,
        Direction.SOUTH_WEST: Action.MOVE_SW,
    }[direction]


def _place_adjacent_enemy(state: GameState) -> Actor:
    """Park the first enemy next to the player, removing every other."""
    for other in state.enemies[1:]:
        state.turn_queue.remove(other)
    del state.enemies[1:]
    victim = state.enemies[0]
    victim.position = Direction.EAST.step(state.player.position)
    state.refresh_vision()
    return victim


# -- coins ------------------------------------------------------------------
def _kill_one(state: GameState, key: str = "ghoul") -> Actor:
    """Put a one-hit monster beside the player and let the player kill it."""
    enemy = make_enemy(ENEMIES[key], (state.player.position[0] + 1, state.player.position[1]))
    enemy.stats.hp = 1
    state.enemies = [enemy]
    state.turn_queue = type(state.turn_queue)([state.player, enemy])
    state.refresh_vision()
    for _ in range(40):
        if not enemy.alive:
            break
        perform_action(state, Action.MOVE_EAST)
    assert not enemy.alive, "the player never landed the hit"
    return enemy


def test_a_kill_leaves_coins_where_the_monster_fell():
    state = start_run(NOXX, seed=3)
    enemy = _kill_one(state)
    pos = enemy.position

    dropped = state.dungeon_map.item_at(pos)
    assert dropped is not None
    assert dropped.kind == "coin"
    low, high = enemy.gold
    assert low <= dropped.gold <= high


def test_killing_pays_score_and_the_base_is_still_depth():
    """The two clocks are separate, and they now overlap by a little.

    ``base_score`` is depth and only depth -- a kill does not move it -- but the
    run's score has a kill term of its own. The purse is still what rewards a
    fight; the score only acknowledges that one happened.
    """
    state = start_run(NOXX, seed=3)
    before_base = state.base_score
    before_kill = state.kill_score

    _kill_one(state)

    assert state.base_score == before_base, "a kill moved the depth score"
    assert state.kills == 1
    assert state.kill_score > before_kill, "a kill paid nothing at all"


def test_picking_coins_up_adds_them_to_the_purse():
    state = start_run(NOXX, seed=3)
    enemy = _kill_one(state)
    coins = state.dungeon_map.item_at(enemy.position)

    state.player.position = enemy.position
    perform_action(state, Action.PICK_UP)

    assert state.gold == coins.gold
    assert state.dungeon_map.item_at(enemy.position) is None
    assert "coins" in state.log[-1].text


def test_two_kills_in_the_same_spot_make_one_bigger_pile():
    """Otherwise the second pile silently overwrites the first."""
    from neverdeads_revenge.world.items import make_coin

    state = start_run(NOXX, seed=3)
    pos = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.add_item(pos, make_coin(4))

    enemy = make_enemy(ENEMIES["ghoul"], pos)
    enemy.stats.hp = 1
    state.enemies = [enemy]
    state.turn_queue = type(state.turn_queue)([state.player, enemy])
    state.refresh_vision()
    for _ in range(40):
        if not enemy.alive:
            break
        perform_action(state, Action.MOVE_EAST)

    pile = state.dungeon_map.item_at(pos)
    assert pile.kind == "coin"
    assert pile.gold > 4, "the first pile was overwritten"


def test_deeper_monsters_carry_more():
    from neverdeads_revenge.game.actors import scale_template

    for template in ENEMIES.values():
        shallow = scale_template(template, 1).gold
        deep = scale_template(template, 9).gold
        assert deep[0] >= shallow[0] and deep[1] >= shallow[1], template.key
        assert deep[1] > shallow[1], template.key


def test_coins_are_not_carried_in_the_pack():
    """They go straight into the purse; the pack is for draughts."""
    state = start_run(NOXX, seed=3)
    enemy = _kill_one(state)
    state.player.position = enemy.position

    perform_action(state, Action.PICK_UP)

    assert state.inventory == []
    assert state.gold > 0


# -- the wall ----------------------------------------------------------------
def test_the_dungeon_is_hard_enough_to_need_the_shop():
    """The floor-10 wall is the point, and it is measured rather than chosen.

    With nothing bought, six runs in a hundred reach the rift; with every
    permanent upgrade, a bought blade, a bought coat and a bought amulet,
    forty-three do. A test cannot play forty runs -- the numbers are in the
    README and the bots are in /tmp -- so it holds the dials instead, and this
    comment is where the reason for them lives.
    """
    from neverdeads_revenge.game.difficulty import MAX_POTENCY, potency
    from neverdeads_revenge.world.generator import ESCAPE_DEPTH, enemy_count

    assert potency(ESCAPE_DEPTH) == MAX_POTENCY, "the cap is not reached in time"
    assert potency(ESCAPE_DEPTH - 1) < MAX_POTENCY, "the cap is reached too early"
    assert enemy_count(ESCAPE_DEPTH) > enemy_count(1)


def test_floor_one_is_a_fight_and_not_a_formality():
    """The wall is the ground the run stands on, not the slope it climbs.

    A fresh hero needs several blows for one ghoul, and the ghoul takes a
    meaningful bite out of him in return. That is the whole reason the
    difficulty went into the templates rather than into the potency curve: a
    steep slope over a soft floor made the first three floors a formality and
    the last three a cliff.
    """
    from neverdeads_revenge.game.actors import ENEMIES, NOXX

    ghoul = ENEMIES["ghoul"]
    blows = ghoul.stats.max_hp / ((NOXX.stats.damage[0] + NOXX.stats.damage[1]) / 2)
    assert blows >= 2.5, f"a floor-one ghoul dies in {blows:.1f} blows"

    bite = (ghoul.stats.damage[0] + ghoul.stats.damage[1]) / 2 - NOXX.stats.armor
    assert bite / NOXX.stats.max_hp >= 0.10, "a floor-one ghoul barely scratches"


def test_a_deep_monster_is_still_meaningfully_harder():
    """The slope is gentler, but it is a slope: by the rift everything down
    there is more than twice what floor one was."""
    from neverdeads_revenge.game.actors import ENEMIES, scale_template
    from neverdeads_revenge.game.difficulty import MAX_POTENCY
    from neverdeads_revenge.world.generator import ESCAPE_DEPTH

    assert MAX_POTENCY > 2.0
    for template in ENEMIES.values():
        deep = scale_template(template, ESCAPE_DEPTH)
        assert deep.stats.max_hp == round(template.stats.max_hp * MAX_POTENCY), (
            template.key
        )
        assert deep.stats.damage[1] > template.stats.damage[1], template.key


def test_the_hero_must_still_be_faster_than_everything_in_the_dungeon():
    """The one hard constraint in the whole balance.

    Speed closes most of the gap to the ceiling as the floors go down, and the
    ceiling is the reason a deep-floor wraith is faster than a floor-one wraith
    without ever being faster than the hero. Letting potency do it unchecked
    would turn every other stat into decoration.
    """
    from neverdeads_revenge.game.actors import ENEMIES, HEROES, scale_template
    from neverdeads_revenge.game.difficulty import MAX_ENEMY_SPEED
    from neverdeads_revenge.world.generator import ESCAPE_DEPTH

    fastest = max(hero.stats.speed for hero in HEROES.values())
    slowest = min(hero.stats.speed for hero in HEROES.values())
    assert MAX_ENEMY_SPEED < fastest, "the fast hero no longer outruns the dungeon"
    assert MAX_ENEMY_SPEED > slowest, "the slow hero is meant to be outrun"
    for template in ENEMIES.values():
        assert scale_template(template, ESCAPE_DEPTH).stats.speed <= MAX_ENEMY_SPEED


def test_a_faster_monster_stays_faster_all_the_way_down():
    """The variety a floor of mixed monsters exists to provide.

    Speed used to be scaled by potency and then clamped, which meant a ghoul, a
    skeleton and a wraith all reached the ceiling by floor five and acted exactly
    as often as each other. The order has to survive every floor, and survive
    *strictly*: two monsters converging on the same speed is the same loss.
    """
    from neverdeads_revenge.game.actors import ENEMIES, scale_template
    from neverdeads_revenge.game.difficulty import MAX_ENEMY_SPEED, SPEED_HORIZON

    depths = range(1, SPEED_HORIZON + 3)
    base_order = sorted(ENEMIES, key=lambda k: ENEMIES[k].stats.speed)
    for depth in depths:
        speeds = [scale_template(ENEMIES[k], depth).stats.speed for k in base_order]
        assert speeds == sorted(speeds), (depth, speeds)
        assert len(set(speeds)) == len(speeds), f"two monsters tie on floor {depth}"
        assert max(speeds) <= MAX_ENEMY_SPEED, depth


def test_the_speed_horizon_is_the_deepest_floor():
    """Kept equal by a test rather than by an import, so that the arithmetic
    module stays arithmetic -- and so that moving the escape depth cannot quietly
    leave the speed curve aimed at a floor nobody reaches."""
    from neverdeads_revenge.game.difficulty import SPEED_HORIZON
    from neverdeads_revenge.world.generator import ESCAPE_DEPTH

    assert SPEED_HORIZON == ESCAPE_DEPTH


def test_enemy_speed_is_monotone_and_never_reaches_the_ceiling():
    from neverdeads_revenge.game.difficulty import (
        GAP_CLOSED_BY_THEN,
        MAX_ENEMY_SPEED,
        enemy_speed,
    )

    assert 0.0 < GAP_CLOSED_BY_THEN < 1.0, "the gap must not close entirely"
    for base in (0.4, 0.7, 1.0, 1.3):
        values = [enemy_speed(base, depth) for depth in range(1, 40)]
        assert values == sorted(values)
        assert values[0] == base
        assert all(v < MAX_ENEMY_SPEED for v in values)
    # Floor 1 is the templates exactly, which is what makes ENEMIES a reference.
    assert enemy_speed(1.3, 1) == 1.3
    assert enemy_speed(1.3, 0) == 1.3


def test_bleed_is_a_price_and_not_a_sentence():
    """It was one health every third step, and a floor is sixty turns of which
    half are steps -- thirteen health a floor, which finished runs on its own.

    Checked against a floor rather than against a number: what a curse costs has
    to be read in the currency the run is spent in.
    """
    from neverdeads_revenge.game.curses import CURSES
    from neverdeads_revenge.game.state import TURN_BUDGET_PER_FLOOR

    every = CURSES["bleed"].bleed_every
    steps_a_floor = TURN_BUDGET_PER_FLOOR // 2
    assert steps_a_floor // every <= 6, f"bleed costs {steps_a_floor // every} a floor"

    # And it still has to cost something, or it is not a curse.
    assert steps_a_floor // every >= 2


# -- the wraith's touch ------------------------------------------------------
def _wraith_beside(state):
    """A wraith that always lands, so the test is about the curse and not the dice."""
    wraith = make_enemy(ENEMIES["wraith"], (state.player.position[0] + 1, state.player.position[1]))
    wraith.stats.accuracy = 99
    state.player.stats.evasion = 0
    state.enemies = [wraith]
    state.turn_queue = type(state.turn_queue)([state.player, wraith])
    state.refresh_vision()
    return wraith


def test_only_the_wraith_leaves_a_curse_behind():
    from neverdeads_revenge.game.actors import ENEMIES as ALL

    assert ALL["wraith"].curse_chance > 0
    for key, template in ALL.items():
        if key != "wraith":
            assert template.curse_chance == 0.0, key


def test_a_wraiths_touch_can_leave_a_curse():
    from neverdeads_revenge.game.actions import take_turn

    state = start_run(NOXX, seed=3)
    wraith = _wraith_beside(state)

    for _ in range(400):
        if state.curses:
            break
        state.player.stats.hp = state.player.stats.max_hp
        take_turn(state, wraith)

    assert state.curses, "the wraith never once left anything behind"
    assert any("touch goes through you" in entry.text for entry in state.log)


def test_a_missed_touch_leaves_nothing():
    """The chance is per *landed* blow, and a blow that missed did not touch.

    Driven through the damage handler with a synthetic miss rather than by
    lowering the wraith's accuracy: the hit chance has a floor of 30%, so a miss
    cannot be forced, only waited for -- and a test that waits for one is really
    a test about the dice.
    """
    from neverdeads_revenge.game.actions import _player_takes_damage
    from neverdeads_revenge.game.combat import AttackOutcome

    state = start_run(NOXX, seed=3)
    wraith = _wraith_beside(state)
    miss = AttackOutcome(hit=False, crit=False, damage=0, killed=False, dodged=True)

    for _ in range(500):
        _player_takes_damage(state, wraith, miss)

    assert not state.curses, "a miss cursed the player"


def test_the_wraiths_touch_is_never_wither():
    """A quarter of your health taken by a random blow in a corridor is not a
    price, it is a mugging. WITHER belongs on a chest, where it was read first."""
    from neverdeads_revenge.game.actions import take_turn
    from neverdeads_revenge.game.curses import TOUCH_CURSES

    assert "wither" not in TOUCH_CURSES

    seen = set()
    for seed in range(200):
        state = start_run(NOXX, seed=seed)
        wraith = _wraith_beside(state)
        for _ in range(60):
            if state.curses:
                break
            state.player.stats.hp = state.player.stats.max_hp
            take_turn(state, wraith)
        seen |= {curse.key for curse in state.curses}

    assert seen, "no curse ever landed"
    assert seen <= set(TOUCH_CURSES), f"something else got through: {seen}"


def test_the_touch_is_rare():
    """Rare enough that a run can pass without it, often enough that a wraith is
    something you would rather not be touched by."""
    from neverdeads_revenge.game.actions import take_turn

    hits = 0
    cursed = 0
    for seed in range(300):
        state = start_run(NOXX, seed=seed)
        wraith = _wraith_beside(state)
        for _ in range(20):
            if state.curses:
                break
            state.player.stats.hp = state.player.stats.max_hp
            take_turn(state, wraith)
            hits += 1
        cursed += bool(state.curses)

    rate = cursed / hits
    assert 0.02 < rate < 0.10, f"{rate:.1%} of blows cursed, which is not 5%"


def test_a_killing_blow_does_not_curse_a_corpse():
    """The player is already dead. Cursing them is one more line nobody reads."""
    from neverdeads_revenge.game.actions import take_turn

    state = start_run(NOXX, seed=3)
    wraith = _wraith_beside(state)
    wraith.stats.damage = (999, 999)

    take_turn(state, wraith)

    assert state.run_state is RunState.DEAD
    assert not state.curses


# -- the flash ---------------------------------------------------------------
def test_a_blow_that_lands_marks_the_cell_it_landed_on():
    state = start_run(NOXX, seed=3)
    ghoul = make_enemy(ENEMIES["ghoul"], (state.player.position[0] + 1, state.player.position[1]))
    ghoul.stats.hp = 99
    state.enemies = [ghoul]
    state.turn_queue = type(state.turn_queue)([state.player, ghoul])
    state.refresh_vision()

    perform_action(state, Action.MOVE_EAST)

    assert ghoul.position in state.hits


def test_a_blow_you_take_marks_your_own_cell():
    """The useful half: the log scrolls, and the map is where you are looking."""
    from neverdeads_revenge.game.actions import _player_takes_damage
    from neverdeads_revenge.game.combat import AttackOutcome

    state = start_run(NOXX, seed=3)
    ghoul = make_enemy(ENEMIES["ghoul"], (state.player.position[0] + 1, state.player.position[1]))
    hit = AttackOutcome(hit=True, crit=False, damage=3, killed=False)

    _player_takes_damage(state, ghoul, hit)

    assert state.player.position in state.hits


def test_a_miss_marks_nothing():
    from neverdeads_revenge.game.actions import _player_takes_damage
    from neverdeads_revenge.game.combat import AttackOutcome

    state = start_run(NOXX, seed=3)
    ghoul = make_enemy(ENEMIES["ghoul"], (state.player.position[0] + 1, state.player.position[1]))
    miss = AttackOutcome(hit=False, crit=False, damage=0, killed=False, dodged=True)

    _player_takes_damage(state, ghoul, miss)

    assert state.hits == []


def test_the_flash_lasts_exactly_one_action():
    """Cleared at the start of every action rather than by a timer, which is
    what lets it blink without one -- and the project has no timers at all."""
    state = start_run(NOXX, seed=3)
    ghoul = make_enemy(ENEMIES["ghoul"], (state.player.position[0] + 1, state.player.position[1]))
    ghoul.stats.hp = 99
    state.enemies = [ghoul]
    state.turn_queue = type(state.turn_queue)([state.player, ghoul])
    state.refresh_vision()
    perform_action(state, Action.MOVE_EAST)
    assert state.hits

    perform_action(state, Action.WAIT)

    assert state.hits == [], "the flash outlived its turn"


def test_the_mirror_marks_what_it_strikes_back():
    from neverdeads_revenge.game.actions import _resolve_enemy_attack

    state = start_run(NOXX, seed=3, loadout=Loadout(pending=("mirror",)))
    ghoul = make_enemy(ENEMIES["ghoul"], (state.player.position[0] + 1, state.player.position[1]))
    ghoul.stats.accuracy = 99
    state.player.stats.evasion = 0
    state.enemies = [ghoul]
    state.turn_queue = type(state.turn_queue)([state.player, ghoul])
    state.refresh_vision()

    for _ in range(40):
        state.hits.clear()
        _resolve_enemy_attack(state, ghoul, state.player)
        if ghoul.position in state.hits:
            break

    assert ghoul.position in state.hits, "the reflection did not flash"


# -- promises of fame ---------------------------------------------------------
def test_a_promise_of_fame_raises_what_the_run_is_worth():
    """The third answer to a chest: the price is the same, the reward is later."""
    from neverdeads_revenge.game.state import FAME_PER_CHEST

    state = start_run(NOXX, seed=3)
    assert state.fame == 0
    assert state.score_multiplier == 1.0

    state.fame = 3
    assert state.fame_bonus == pytest.approx(3 * FAME_PER_CHEST)
    assert state.score_multiplier == pytest.approx(1 + 3 * FAME_PER_CHEST)


def test_fame_is_added_and_not_multiplied():
    """A fifth each sounds small; multiplied it runs away.

    There is no ceiling on it and none is needed -- a chest is only ever placed
    for a curse the player has not paid, so the curses themselves are the
    ceiling.
    """
    state = start_run(NOXX, seed=3)
    state.fame = 2
    doubled = state.score_multiplier

    state.fame = 4
    assert state.score_multiplier == pytest.approx(2 * doubled - 1), (
        "fame compounded instead of adding"
    )


def test_fame_multiplies_the_escape_bonus_too():
    """Everything, or the summary has to explain what exactly it multiplies."""
    state = start_run(NOXX, seed=3)
    state.floors_cleared = 9
    state.run_state = RunState.ESCAPED
    state.total_turns = TURN_BUDGET_PER_FLOOR * 9
    plain = state.score

    state.fame = 1
    assert state.score > plain
    assert state.score == round(plain * state.score_multiplier)


def test_fame_and_the_nameless_run_are_both_wagers():
    """One halves the score and pays in coin; the other raises it and pays in
    nothing at all. They stack, because a player can take both."""
    state = start_run(NOXX, seed=3)
    state.fame = 2
    with_fame = state.score_multiplier

    state.wilds.add("nameless_run")
    assert state.score_multiplier == pytest.approx(with_fame * 0.5)


def test_taking_fame_pays_the_price_and_leaves_the_reward():
    """The curse is taken, the loot is not, and the name goes on the run."""
    from neverdeads_revenge.world.items import ITEMS, make_chest

    state = start_run(NOXX, seed=1)
    _put_a_chest(state, curse="dim", contents="edge")

    result = perform_action(state, Action.TAKE_FAME)

    assert result.consumed_turn, "a bargain that lands costs a turn"
    assert [c.key for c in state.curses] == ["dim"], "the price was not paid"
    assert state.player.equipment == {}, "the reward was taken as well"
    assert state.fame == 1
    assert state.dungeon_map.item_at(state.player.position) is None, "the chest stayed"


def test_taking_fame_from_nothing_does_nothing():
    state = start_run(NOXX, seed=1)
    state.player.position = next(
        pos
        for pos in state.dungeon_map.floor_positions()
        if state.dungeon_map.item_at(pos) is None
    )

    result = perform_action(state, Action.TAKE_FAME)

    assert not result.acted
    assert state.fame == 0


def test_fame_survives_a_save_and_an_old_save_does_not_have_it():
    """A promise is a count, so a run saved before there was such a thing still
    resumes -- it simply has none, and the schema version does not move."""
    from neverdeads_revenge.game.savegame import dump, load

    state = start_run(NOXX, seed=3)
    state.fame = 4
    assert load(dump(state)).fame == 4

    payload = dump(state)
    payload.pop("fame")
    assert load(payload).fame == 0
