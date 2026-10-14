"""The fight: the round order, the five verbs, and the blow by blow.

These drive the domain and nothing else -- no keyboard, no screen -- because
that is what a battle *is*: a small state machine over the rules the dungeon
already has. The tests that matter most here are the ones that check the fight
has not grown an opinion of its own: a blow is resolved where every other blow
is resolved, a refused verb costs nothing, and a kill pays out the way a kill
pays out on the map.
"""

from __future__ import annotations

from neverdeads_revenge.game.actions import (
    Action,
    advance_world,
    perform_action,
    resolve_enemy_attack,
    take_turn,
)
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.battle import (
    ATTACK,
    DEFEND,
    FLEE,
    ITEM,
    ROOM,
    SPECIAL,
    STAGE,
    Battle,
    Guarded,
    Over,
    Said,
    Struck,
    encounter_around,
)
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.world.items import ITEMS, make_item


def run(seed: int = 1, *, level: int = 1, ultimate_level: int = 1):
    """A fresh run, with the dark answering from the start."""
    return start_run(HEROES["noxx"], seed, ultimate_level=ultimate_level)


def take(state, count: int = 1):
    """The first ``count`` monsters the floor put out, as a fight."""
    return list(state.enemies[:count])


def strikes(events):
    return [event for event in events if isinstance(event, Struck)]


def lines(events):
    return [event.text for event in events if isinstance(event, Said)]


def test_a_blow_is_the_dungeons_own():
    """The fight swings with the dungeon's dice, and knows what they rolled.

    The words of a blow are the rules' words -- the same sentence the map writes
    -- and the damage the event carries is the damage the monster actually lost.
    A fight with its own arithmetic would have to say those two things
    separately, and would eventually say them differently.
    """
    state = run()
    enemy = take(state)[0]
    hp_before = enemy.stats.hp
    battle = Battle(state, [enemy])

    events = battle.choose(ATTACK, enemy)
    blow = strikes(events)[0]

    assert blow.actor is state.player and blow.target is enemy
    if blow.outcome.killed:
        # A killing blow reports the *hit*; what is left of the monster is
        # nothing, which is the one case where the two are not the same number.
        assert enemy.stats.hp == 0, "a killing blow left the monster standing"
    else:
        assert enemy.stats.hp == hp_before - blow.outcome.damage, (
            "the number does not add up"
        )
    assert lines(events), "a blow says nothing at all"

    outcome = blow.outcome
    if outcome.hit:
        assert any(
            str(outcome.damage) in line for line in lines(events)
        ), "a landed blow did not say what it did"
    else:
        assert any("miss" in line for line in lines(events))


def test_the_quickest_acts_first():
    """Speed is the turn order, and it is felt in the first beat of the fight.

    A monster quicker than the hero hits before the player has made a single
    choice: that is what the number is for, and a round order that ignored it
    would make speed a stat that only shows up on the character sheet.
    """
    state = run()
    enemy = take(state)[0]
    enemy.stats.speed = state.player.speed + 10.0
    enemy.stats.damage = (2, 2)
    enemy.behaviour = "aggressive"
    battle = Battle(state, [enemy])

    opening = battle.begin()

    assert strikes(opening), "the quicker monster did not get to move first"
    assert strikes(opening)[0].actor is enemy


def test_the_slowest_waits_its_turn():
    """...and the other way round: a slow hero swings before the ooze does."""
    state = run()
    enemy = take(state)[0]
    enemy.stats.speed = 0.0
    battle = Battle(state, [enemy])

    assert battle.begin() == [], "a slower monster moved first"


def test_guarding_halves_what_lands():
    """Setting your feet is the same half the grave ward takes.

    Asserted on the rules rather than through the fight, because the fight's
    version of it would need the dice to fall the same way twice: two identical
    runs are asked for the same blow, one guarded and one not.
    """
    plain, guarded = run(seed=7), run(seed=7)
    plain_enemy, guarded_enemy = take(plain)[0], take(guarded)[0]

    without = resolve_enemy_attack(plain, plain_enemy, plain.player)
    with_guard = resolve_enemy_attack(
        guarded, guarded_enemy, guarded.player, guard=True
    )

    assert without is not None and with_guard is not None
    assert with_guard.hit == without.hit, "the guard changed whether it landed"
    if without.hit:
        assert with_guard.damage <= without.damage, "guarding did not help"


def test_defending_is_a_turn_the_fight_takes():
    """The verb says it was set, and the round moves on behind it."""
    state = run()
    battle = Battle(state, take(state))

    events = battle.choose(DEFEND)

    assert any(isinstance(event, Guarded) for event in events)


def test_the_dark_answers_once_and_everything_takes_it():
    """The hero's ask, in the arena: one blow on everybody, one per floor.

    The price is the dungeon's own -- ``ultimate_available`` is spent here the
    way ``f`` spends it on the map -- which is what keeps a floor from being
    asked twice for the same favour.
    """
    state = run(ultimate_level=1)
    enemies = take(state, 3)
    battle = Battle(state, enemies)
    battle.begin()

    events = battle.choose(SPECIAL)

    hit = [blow for blow in strikes(events) if blow.actor is state.player]
    assert [blow.target for blow in hit] == enemies, "the ask missed somebody"
    assert not state.ultimate_available, "the dark was not spent"

    again = battle.choose(SPECIAL)
    assert not strikes(again), "the dark answered twice"
    assert any("does not ask twice" in line for line in lines(again))


def test_a_refused_verb_costs_nothing():
    """A hero who could not do the thing has not taken a turn.

    The floor does not get to move because a verb was refused -- which is the
    difference between a menu that teaches a rule and a menu that taxes the
    player for asking. The fight is opened first, so what is counted is the
    refusal's own consequences and not the round the hero entered.
    """
    state = run(ultimate_level=99)
    enemy = take(state)[0]
    enemy.stats.speed = state.player.speed + 5.0
    battle = Battle(state, [enemy])
    battle.begin()
    before = len(battle.state.log)

    events = battle.choose(SPECIAL)

    assert any("Not yet" in line for line in lines(events))
    assert not strikes(events), "the floor moved after a refusal"
    assert len(battle.state.log) > before, "the refusal was not said"


def test_drinking_is_the_packs_own_arithmetic():
    """ITEM is the dungeon's mouthful, from the dungeon's pack.

    The smallest draught that covers the wound, the curse's share taken off it,
    the bottle gone afterwards: all of it already decided in one place, and the
    fight only asks for it.
    """
    state = run()
    state.inventory.append(make_item(ITEMS["potion"]))
    state.player.stats.hp = 5
    battle = Battle(state, take(state))

    events = battle.choose(ITEM)

    assert any("drink the potion" in line for line in lines(events))
    assert state.player.stats.hp > 5, "the potion mended nothing"
    assert not state.inventory, "the bottle is still in the pack"


def test_nothing_to_drink_is_not_a_turn():
    """An empty pack is a refusal, and a refusal is free."""
    state = run()
    state.inventory.clear()
    state.player.stats.hp = max(1, state.player.max_hp // 2)
    battle = Battle(state, take(state))
    hp = state.player.stats.hp

    events = battle.choose(ITEM)

    assert lines(events), "the fight said nothing about an empty pack"


def test_fleeing_costs_a_round_of_blows():
    """Running away always works, and always costs: the floor gets your back."""
    state = run()
    enemies = take(state, 2)
    for enemy in enemies:
        enemy.behaviour = "aggressive"
        enemy.stats.speed = state.player.speed + 5.0
    battle = Battle(state, enemies)

    events = battle.choose(FLEE)

    over = [event for event in events if isinstance(event, Over)]
    assert over and over[0].escaped and not over[0].won
    assert battle.escaped and battle.over
    assert any("turn your back" in line for line in lines(events)), (
        "the fight did not say the hero was running"
    )


def test_a_kill_is_paid_out_where_the_monster_was():
    """Winning the fight finishes the monster: coins, corpse and all.

    The kill happens in the rules, on the actor, where every other kill in this
    game happens -- so the arena cannot quietly become a place where monsters die
    without paying, or where a corpse is left standing on the floor.
    """
    state = run()
    enemy = take(state)[0]
    enemy.stats.hp = 1
    enemy.stats.armor = 0
    gold_before = state.gold
    battle = Battle(state, [enemy])

    events = battle.choose(ATTACK, enemy)

    assert battle.over and battle.won
    assert isinstance(events[-1], Over) and events[-1].won
    assert enemy not in state.enemies, "the corpse is still on the floor"
    assert any("quiet again" in line for line in lines(events))
    assert state.gold >= gold_before


def test_a_dead_hero_has_lost():
    """The fight knows when it is over, and says which way."""
    state = run()
    state.player.stats.hp = 0
    battle = Battle(state, take(state))

    events = battle.begin()

    assert battle.over and not battle.won
    assert isinstance(events[-1], Over) and not events[-1].won


def test_the_menu_offers_all_five_verbs():
    """Every verb is always there: a refusal teaches, a missing verb does not."""
    state = run(ultimate_level=99)
    battle = Battle(state, take(state))

    assert battle.commands() == [ATTACK, SPECIAL, ITEM, DEFEND, FLEE]
    assert not battle.special_ready(), "the menu would not dim the ask"


# -- the floor hands a fight over (M2) ---------------------------------------
def place_beside(state, enemy):
    """Put ``enemy`` next to the hero and hand back the verb that walks into it."""
    from neverdeads_revenge.core.direction import Direction

    for direction, action in (
        (Direction.EAST, Action.MOVE_EAST),
        (Direction.WEST, Action.MOVE_WEST),
        (Direction.NORTH, Action.MOVE_NORTH),
        (Direction.SOUTH, Action.MOVE_SOUTH),
    ):
        spot = direction.step(state.player.position)
        if state.dungeon_map.is_walkable(spot) and state.actor_at(spot) is None:
            enemy.position = spot
            return action
    raise AssertionError("nowhere beside the hero to stand")


def test_walking_into_a_monster_is_a_fight_not_a_blow():
    """The floor stops resolving fights. It hands them over instead.

    Walking into something used to swing at it there and then. Now it raises the
    encounter, and the arena does the swinging -- which is the whole of what
    "the dungeon's combat is replaced" means, and the thing that has to be true
    before any of the arena matters.
    """
    state = run()
    enemy = take(state)[0]
    action = place_beside(state, enemy)
    hp_before = enemy.stats.hp

    perform_action(state, action)

    assert state.encounter is enemy, "the walk did not hand over a fight"
    assert enemy.stats.hp == hp_before, "the floor swung at it on the way"


def test_the_floor_stands_still_while_a_fight_is_owed():
    """Nothing else moves while the hero is about to be in a room.

    The monsters in the fight are the ones he is about to meet, and the ones
    outside it have no business crossing the floor behind his back -- a fight
    that carried on around him would be two turns happening at once.
    """
    state = run()
    enemy = take(state)[0]
    action = place_beside(state, enemy)
    others = [other for other in state.enemies if other is not enemy]
    before = {id(other): other.position for other in others}
    hp = state.player.stats.hp

    perform_action(state, action)
    assert state.encounter is not None

    advance_world(state)

    assert state.player.stats.hp == hp, "the floor hit the hero during a fight"
    assert {id(other): other.position for other in others} == before, (
        "the floor walked around while the hero was in a fight"
    )


def test_a_monster_reaching_the_hero_is_a_fight_too():
    """The other half of the same rule: contact is a fight, whichever way it is
    made. A monster that arrives used to take its blow; now it takes him to the
    arena, where he gets to answer."""
    state = run()
    enemy = take(state)[0]
    enemy.behaviour = "aggressive"
    place_beside(state, enemy)
    hp = state.player.stats.hp

    took = take_turn(state, enemy)

    assert took, "the monster did nothing at all"
    assert state.encounter is enemy, "arriving was not a fight"
    assert state.player.stats.hp == hp, "the monster landed a blow on the floor"


def test_a_fight_takes_whoever_is_standing_with_it():
    """The monster he walked into, and whoever is in the room with him.

    A fight is about the room it happens in -- and the room is where the *hero*
    is, not where the monster he bumped into happens to be standing. One that let
    the neighbours watch would make walking into a crowd the safest thing a
    player could do.
    """
    state = run()
    enemies = take(state, 4)
    trigger = enemies[0]
    hero = state.player.position
    # Two of them near the hero, and one on the far side of the floor.
    for enemy, offset in zip(enemies[1:], ((1, 0), (0, 1))):
        enemy.position = (hero[0] + offset[0], hero[1] + offset[1])
    far = state.enemies[4] if len(state.enemies) > 4 else None
    if far is not None:
        far.position = (hero[0] + ROOM + 4, hero[1] + ROOM + 4)

    group = encounter_around(state, trigger)

    assert group[0] is trigger
    assert enemies[1] in group and enemies[2] in group, "the room was left out"
    assert len(group) <= STAGE, "the fight is bigger than the stage holds"
    if far is not None:
        assert far not in group, "a monster across the floor joined in"
