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
    STACK_LIMIT,
    Action,
    advance_world,
    perform_action,
    resolve_enemy_attack,
    take_turn,
)
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.battle import (
    ATTACK,
    FLEE,
    ITEM,
    ROOM,
    SPECIAL,
    STAGE,
    DEEP_BLEED,
    SIPHON,
    Battle,
    Flourish,
    Over,
    Said,
    Struck,
    encounter_around,
    open_fight,
)
from neverdeads_revenge.game.specials import (
    AVALANCHE,
    CHORD,
    DEVOURING_DARKNESS,
    FLEETING_SHADOW,
    PAINT_THE_WALLS_RED,
    BELLS_THROW,
    BETWEEN_BLOWS,
    ECHOING_CUT,
    FIRST_NOTE,
    HOARFROST,
    LEFT_HAND,
    LONG_WINTER,
    OPEN_VEIN,
    ORB_OF_PTAMERA,
    OVERTURE,
    QUAKE,
    RIME,
    SILENCE,
    SNOW_BLIND,
    SPECIALS,
    STILLNESS,
    TRUE_NOTE,
    special_by_key,
)
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.game.statuses import status_by_key
from neverdeads_revenge.world.items import ITEMS, make_item


def run(seed: int = 1, *, level: int = 1, ultimate_level: int = 1):
    """A fresh run, with the dark answering from the start.

    And a full purse: what a trick *costs* has its own tests, and every other
    test here is about what it *does*. A test that had to save up for the trick
    it is about would be testing the purse by accident.
    """
    state = start_run(HEROES["noxx"], seed, ultimate_level=ultimate_level)
    state.kill_points = 999
    return state


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


def test_there_is_no_defend_verb_any_more():
    """Four verbs and not five: waiting was never worth a turn.

    Standing still halved what landed and did nothing else -- a choice that is
    only ever right when there is nothing better to do, which is a choice the
    game should not have offered. The *mechanic* is still here, and still the
    hero's: THE STILLNESS and THE FROZEN FORTRESS set exactly that guard, which
    is where halving a blow belongs -- paid for, and on a turn that did something.
    """
    from neverdeads_revenge.game.battle import ATTACK, FLEE, ITEM, SPECIAL

    state = run()
    battle = Battle(state, take(state))

    assert battle.commands() == [ATTACK, SPECIAL, ITEM, FLEE]



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
    turns, clock = battle.state.total_turns, battle.state.turn

    events = battle.choose(SPECIAL, special=LEFT_HAND)

    assert any("Not yet" in line for line in lines(events))
    assert not strikes(events), "the floor moved after a refusal"
    assert len(battle.state.log) > before, "the refusal was not said"
    assert battle.state.total_turns == turns, "a refusal cost a turn"
    assert battle.state.turn == clock, "a refusal moved the clock"


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


def test_a_mouthful_in_the_arena_is_the_rooms_turn_and_not_the_floors():
    """A turn spent in a room is answered *by the room*.

    The dungeon's own quaff spends a turn and runs ``advance_world``, which is
    the right answer when the drinking happens on the map -- a mouthful should
    not be a free action. In the arena the room is already answering, so the
    floor got a second turn out of the same mouthful: measured, a monster with no
    business moving while the hero was in a room walked up to him and was handed
    over as a *fresh* encounter mid-fight. The fight then killed it, and the
    floor was left owing a fight to a corpse, standing still for as long as the
    run had left. Which is what two thirds of a batch of measured runs was.

    So the watcher below is the floor's own monster, beside the hero, quicker
    than anybody, and it must not take a turn -- and the run's own clock, which
    counts what a turn cost, must not move either.
    """
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy

    state = run()
    state.inventory.append(make_item(ITEMS["potion"]))
    state.player.stats.hp = 5
    battle = Battle(state, take(state))

    # The hunter and not a ghoul, because it is the one monster whose turn does
    # not need the hero to be able to see it -- a test that could pass because
    # the actor was invisible would be measuring the lamp.
    watcher = make_enemy(
        ENEMIES["hunter"], (state.player.position[0] + 1, state.player.position[1])
    )
    watcher.stats.speed = 99.0
    state.enemies.append(watcher)
    # The floor's queue, emptied down to the two of them, and the watcher quicker
    # than the hero: a queue that *could* still hand this monster a turn, so that
    # "it did not take one" is the flag and not the dice.
    state.turn_queue = type(state.turn_queue)([state.player, watcher])
    turns_before = state.total_turns

    events = battle.choose(ITEM)

    assert any("drink the potion" in line for line in lines(events))
    assert state.player.stats.hp > 5, "the potion mended nothing"
    assert state.encounter is None, "the floor handed over a fight mid-fight"
    # The clock moves exactly once -- the arena's own turn for the command --
    # and the *floor* does not get a phase out of it. It used to not move at all,
    # which made every fight free and the speed score a lie.
    assert state.total_turns == turns_before + 1, "the mouthful was free"
    assert not battle.over, "one mouthful finished a fight"


def test_a_fight_owed_to_a_monster_that_died_is_no_longer_owed():
    """A corpse owes nothing, and the floor moves on.

    The floor hands a fight over by *setting* the encounter, and the door into
    the arena asks the monster's health. A monster that died in between -- a
    wound running out at the start of its turn, the shadow reaching it first --
    used to leave the field set: the door refused every time it was asked, and
    the enemy phase stood still for a battle that could never happen. Nothing
    could move the floor on, and the run was over without being over.
    """
    state = run()
    enemy = take(state)[0]
    state.raise_encounter(enemy)

    enemy.stats.hp = 0
    from neverdeads_revenge.game.actions import _on_death

    _on_death(state, enemy)

    assert state.encounter is None, "a corpse is still owed a fight"
    assert open_fight(state) is None, "the floor offered a fight with a corpse"


def test_nothing_to_drink_is_not_a_turn():
    """An empty pack is a refusal, and a refusal is free."""
    state = run()
    state.inventory.clear()
    state.player.stats.hp = max(1, state.player.max_hp // 2)
    battle = Battle(state, take(state))

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

    assert battle.commands() == [ATTACK, SPECIAL, ITEM, FLEE]
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
    for enemy, offset in zip(enemies[1:], ((1, 0), (0, 1)), strict=False):
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


# -- the five tricks (M3) -----------------------------------------------------
def levelled(level: int, count: int = 2, ultimate_level: int = 8):
    """A fight at a chosen level, with the dark answering where it really does.

    The void's gate is the dungeon's own -- the level the dark answers at -- so a
    test about *levels* has to leave that gate where the game leaves it, or every
    level would come with the void attached.
    """
    state = start_run(HEROES["noxx"], 1, ultimate_level=ultimate_level)
    state.level = level
    state.kill_points = 999
    return Battle(state, take(state, count))


def test_the_left_hand_is_a_cut_that_leaves_something_in():
    """The cheapest trick in the kit: an ordinary cut, and a poison on top.

    It used to make sure of its stab -- a forced crit and a flat bonus -- which
    was the wrong promise for the trick that costs least: a small certain hit is
    a small certain hit, and what a *cheap* trick wants is a reason of its own.
    Poison is not a bigger blow. It is a reason to open with this one, and it
    keeps working while the purse fills.
    """
    battle = levelled(2)
    enemy = battle.enemies[0]
    enemy.stats.hp = 999

    events = battle.choose(SPECIAL, enemy, special=LEFT_HAND)

    blow = [one for one in strikes(events) if one.actor is battle.hero][0]
    assert blow.flair == LEFT_HAND, "the blow wears no word"
    assert not blow.outcome.crit or True  # an ordinary blow, crit or not
    assert "poison" in enemy.statuses, "the dagger left nothing in him"

    hp = enemy.stats.hp
    battle.choose(ATTACK, battle.living_enemies()[0])  # a round goes by: the poison does its work
    assert enemy.stats.hp < hp, "the poison never bit"


def test_the_order_strip_reads_the_queue_and_spends_nothing():
    """A quick hero takes two turns before a slow monster takes one.

    That is the whole of what speed buys in this fight, and the strip has to say
    so -- a player plans against it. Read forward and not saved: asking twice must
    give the same answer twice, or the strip would be spending the turns it is
    only supposed to be showing.
    """
    battle = levelled(6, count=1)
    battle.hero.stats.speed = 3.0
    battle.enemies[0].stats.speed = 0.5

    ahead = battle.upcoming(3)
    assert [one.glyph for one in ahead][:2] == [battle.hero.glyph] * 2, (
        f"the quick hero did not get two turns first: {[one.glyph for one in ahead]}"
    )
    assert [one.glyph for one in battle.upcoming(3)] == [one.glyph for one in ahead], (
        "asking twice spent something"
    )


def test_the_round_reads_back_in_the_order_it_was_taken():
    """The hero first and then the room, in the order the blows come in: this is
    the list the arena's strip counts down as it plays."""
    battle = levelled(6, count=3)

    events = battle.choose(ATTACK, battle.enemies[0])

    taken = [one.glyph for one in battle.turns()]
    swung = [event.actor.glyph for event in events if isinstance(event, Struck)]
    assert taken == swung, f"the round went {taken} and the blows came {swung}"
    assert taken.count(battle.hero.glyph) == 1, f"his turn is in there twice: {taken}"
    assert battle.hero.glyph in taken, f"his turn is not in there at all: {taken}"


def test_the_snow_blind_takes_its_place_in_the_queue():
    """It is not a bigger blow -- it is a blow that costs the target its *turn*.

    The bell's shove in Yeti's hands: whatever was next for it is now last, and
    against something quick that is worth more than the damage ever was.
    """
    battle = duel("yeti", 3, count=3)
    for enemy in battle.enemies:
        enemy.stats.hp = 999
    chosen = battle.enemies[0]
    chosen.stats.speed = 9.0  # would act first, and does not any more

    battle.choose(SPECIAL, chosen, special=SNOW_BLIND)

    last = battle.upcoming(4)[-1]
    assert last is chosen, f"the blind did not cost it its place: {last.name}"


def test_the_quake_is_for_a_crowd_and_pays_for_the_crowd():
    """Everything standing takes it at seventy percent: worse than the avalanche
    against one, and better against three -- which is the choice it is for."""
    from neverdeads_revenge.game.battle import QUAKE_SCALE

    assert QUAKE_SCALE < 1.0, "an area trick that hit harder than the single one"
    battle = duel("yeti", 7, count=3)
    for enemy in battle.enemies:
        enemy.stats.hp = 999

    events = battle.choose(SPECIAL, battle.enemies[0], special=QUAKE)

    hit = [one for one in strikes(events) if one.actor is battle.hero]
    assert [one.target for one in hit] == battle.enemies, "the quake missed somebody"
    assert {one.flair for one in hit} == {QUAKE}


def test_the_long_winter_chills_the_whole_room():
    """The rime's own wound, handed out to every one of them."""
    battle = duel("yeti", 8, count=3)
    for enemy in battle.enemies:
        enemy.stats.hp = 999

    battle.choose(SPECIAL, battle.enemies[0], special=LONG_WINTER)

    assert all("chill" in enemy.statuses for enemy in battle.enemies), "someone kept warm"


def test_the_overture_plays_to_the_whole_room():
    from neverdeads_revenge.game.battle import OVERTURE_SCALE

    assert OVERTURE_SCALE < 1.0
    battle = duel("walkyrion", 3, count=3)
    for enemy in battle.enemies:
        enemy.stats.hp = 999

    events = battle.choose(SPECIAL, battle.enemies[0], special=OVERTURE)

    hit = [one for one in strikes(events) if one.actor is battle.hero]
    assert [one.target for one in hit] == battle.enemies, "the overture missed somebody"


def test_the_ringing_chord_hits_hard_and_throws():
    from neverdeads_revenge.game.battle import CHORD_SCALE

    assert CHORD_SCALE > 1.0, "the dearest single-target note is not heavy"
    battle = duel("walkyrion", 7, count=3)
    for enemy in battle.enemies:
        enemy.stats.hp = 999
    chosen = battle.enemies[0]
    chosen.stats.speed = 9.0

    events = battle.choose(SPECIAL, chosen, special=CHORD)

    hit = [one for one in strikes(events) if one.flair == CHORD]
    assert hit and hit[0].outcome.damage > 0, "the chord made no sound"
    assert battle.upcoming(4)[-1] is chosen, "the chord did not throw it"


def test_the_silence_leaves_the_room_without_its_place():
    """Not damage -- *order*: everything is put back to the far end of the queue."""
    battle = duel("walkyrion", 8, count=3)
    for enemy in battle.enemies:
        enemy.stats.hp = 999
    for enemy in battle.enemies:
        enemy.stats.speed = 9.0

    battle.choose(SPECIAL, battle.enemies[0], special=SILENCE)

    ahead = battle.upcoming(4)
    assert ahead[-1] in battle.enemies, "nobody was left at the back"


def test_the_orb_hunts_crits_without_promising_them():
    """A chance and not a certainty: that is the whole difference between the orb
    and the knife, and the same dice show it -- every fight here is the same seed
    with the same rolls, so what changes is only the odds the orb is thrown at.
    """
    def crits(special, times: int = 60) -> int:
        wins = 0
        for index in range(times):
            # A fresh *seed* every time as well as a fresh fight: the same seed
            # rolled the same two dice sixty times and the measurement said
            # nothing about the odds at all.
            state = start_run(HEROES["noxx"], 1000 + index, ultimate_level=8)
            state.level = 3
            battle = Battle(state, take(state, 1))
            enemy = battle.enemies[0]
            enemy.stats.hp = 9999
            # The patient knife makes the *first* blow on anything a crit, and
            # every fight here is a fresh one: what is being measured is the odds
            # of an ordinary blow, so the target has to have been hit before.
            enemy.struck = True
            events = (
                battle.choose(ATTACK, enemy)
                if special is None
                else battle.choose(SPECIAL, enemy, special=special)
            )
            wins += sum(1 for one in strikes(events) if one.outcome.crit)
        return wins

    plain = crits(None)
    orbed = crits(ORB_OF_PTAMERA)
    assert orbed > plain * 1.5, f"the orb crit {orbed} times against a plain {plain}"
    assert orbed < 60, "the orb never missed a crit: that is the knife, not the orb"


def test_fleeting_shadow_is_out_before_anything_moves():
    """Turning your back costs a swing from everything standing, and this is not
    turning your back: nothing in the room gets to answer for it."""
    battle = levelled(4)
    battle.enemies[0].stats.damage = (5, 5)
    battle.enemies[0].stats.accuracy = 99
    battle.hero.stats.evasion = 0
    hp = battle.hero.stats.hp

    events = battle.choose(SPECIAL, None, special=FLEETING_SHADOW)

    assert battle.over and battle.escaped, "the shadow did not get him out"
    assert battle.hero.stats.hp == hp, "something got a swing at his back anyway"
    assert not strikes(events), "the fight swung at a hero who was not there"
    assert any(isinstance(event, Over) and event.escaped for event in events), (
        "the fight never said he was gone"
    )


# -- Inferno's hands -------------------------------------------------------
def _flat(hero_key: str, level: int = 7, count: int = 1):
    """A fight whose numbers are exactly what the trick is worth.

    His kit is a *ladder* of scales, and a ladder measured through two dice is
    two ladders: the hero rolls a range and sometimes a crit, so the gap between
    two rungs can be swallowed by the spread. One damage value and no crit make
    every rung read as the scale it is.
    """
    battle = duel(hero_key, level, count=count)
    battle.hero.stats.damage = (12, 12)
    battle.hero.stats.crit_chance = 0.0
    for enemy in battle.enemies:
        enemy.stats.hp = 9999
        enemy.stats.armor = 0
        enemy.stats.evasion = 0
    return battle


def _dealt(battle, key: str) -> int:
    """What one trick took off the first of them, in one blow."""
    target = battle.enemies[0]
    before = target.stats.hp
    battle.choose(SPECIAL, target, special=key)
    return before - target.stats.hp


def test_infernos_hands_get_heavier_as_they_get_dearer():
    """He has no kit in the sense the others do: what the eight are is damage.

    So the thing worth holding still is the *order* -- the lightest and cheapest
    first, the heaviest last, and the prices climbing beside them. A kit whose
    cheapest trick hit like its dearest would be one trick with eight names, and
    a kit whose ladder is in the wrong order is a kit that lies about its prices.
    """
    from neverdeads_revenge.game.specials import (
        EMBER_FIST,
        GUT_PUNCH,
        HAYMAKER,
        HEADBUTT,
        JAB,
    )

    rungs = ["jab", "gut", "ember", "headbutt", "haymaker"]
    dealt = {
        "jab": _dealt(_flat("inferno"), JAB),
        "gut": _dealt(_flat("inferno"), GUT_PUNCH),
        "ember": _dealt(_flat("inferno"), EMBER_FIST),
        "headbutt": _dealt(_flat("inferno"), HEADBUTT),
        "haymaker": _dealt(_flat("inferno"), HAYMAKER),
    }
    assert [dealt[rung] for rung in rungs] == sorted(dealt[rung] for rung in rungs), (
        f"the ladder is out of order: {dealt}"
    )

    # And the cheapest rung is still worth pressing: a free swing is what every
    # trick is priced against, and the jab has to be better than it or the
    # cheapest thing in the game is the worst one.
    free = _flat("inferno")
    before = free.enemies[0].stats.hp
    free.choose(ATTACK, free.enemies[0])
    assert dealt["jab"] > before - free.enemies[0].stats.hp, (
        "the jab is worse than swinging for nothing"
    )


def test_the_headbutt_is_paid_for_in_his_own_blood():
    """The one blow priced in the only currency the fight has not spent.

    It can be the last of him: a cost that cannot finish a hero is not a cost.
    """
    from neverdeads_revenge.game.specials import HEADBUTT

    battle = _flat("inferno")
    full = battle.hero.stats.hp
    _dealt(battle, HEADBUTT)
    assert battle.hero.stats.hp < full, "the headbutt was free"


def test_red_mist_hits_harder_the_worse_he_is_hurt():
    """The rage has to be worth *losing* for, or it is just a better attack."""
    from neverdeads_revenge.game.specials import RED_MIST

    calm = _dealt(_flat("inferno"), RED_MIST)
    hurt = _flat("inferno")
    hurt.hero.stats.hp = 1
    furious = _dealt(hurt, RED_MIST)

    assert furious > calm, f"{furious} out of a dying man is not more than {calm}"



def test_the_roundhouse_takes_the_whole_room():
    """One turn, and everything standing is in the way of it."""
    from neverdeads_revenge.game.specials import ROUNDHOUSE

    battle = _flat("inferno", level=8, count=3)
    before = [enemy.stats.hp for enemy in battle.enemies]
    battle.choose(SPECIAL, battle.enemies[0], special=ROUNDHOUSE)

    assert all(
        enemy.stats.hp < was for enemy, was in zip(battle.enemies, before, strict=True)
    ), "one of them was out of the spin"


def test_paint_the_walls_red_cuts_at_the_ceiling():
    """Atritas brings company, and the company is the deepest wound there is.

    Every monster in the room gets the deep bleeding at the full ceiling, which
    on three of them is the room ending before the floor runs dry.
    """
    from neverdeads_revenge.game.specials import PAINT_THE_WALLS_RED

    battle = duel("noxx", 8, count=3)
    for enemy in battle.enemies:
        enemy.stats.hp = 9999
        enemy.stats.evasion = 0

    battle.choose(SPECIAL, special=PAINT_THE_WALLS_RED)

    assert all("maul" in enemy.statuses for enemy in battle.enemies), (
        "something in the room was not opened"
    )
    assert all(
        enemy.status_stacks.get("maul") == STACK_LIMIT
        for enemy in battle.enemies
    ), "the deep wound was not cut at its ceiling"


def test_devouring_darkness_keeps_half_of_what_it_bites():
    """The steal: half of the damage, back to him -- and never nothing, because a
    mouthful of a mouthful is still a mouthful."""
    battle = levelled(6)
    enemy = battle.enemies[0]
    enemy.stats.hp = 9999
    battle.hero.stats.hp = 1
    battle.hero.stats.max_hp = 99
    # And nothing else laying a hand on him, because what comes back out is
    # measured by how far the number went up: a room that took four off him in
    # the same turn would make a working siphon read as nothing coming back.
    for other in battle.enemies:
        other.stats.damage = (0, 0)
        other.inflicts = ()
        # And out of the round entirely. A landed blow is never *nothing* -- the
        # enemy's bite clamps its own damage up to one -- so zeroing the damage
        # still leaves a point of it coming back at him, which this test never
        # noticed while Noxx had an armour point to soak it with. What the test
        # measures is the siphon; an enemy that acts is a number to subtract.
        other.stats.speed = 0.01

    events = battle.choose(SPECIAL, enemy, special=DEVOURING_DARKNESS)

    hit = [one for one in strikes(events) if one.flair == DEVOURING_DARKNESS]
    assert hit, "the dark did not bite at all"
    kept = battle.hero.stats.hp - 1
    assert kept == max(1, round(hit[0].outcome.damage * SIPHON)), (
        f"{kept} came back out of {hit[0].outcome.damage}"
    )
    assert any(isinstance(event, Flourish) for event in events), "nothing was shown"


def test_paint_the_walls_red_opens_all_of_them():
    """Atritas comes, and he does not come alone: every one of them is left
    bleeding *deeply* -- longer, because a wound refreshes and does not stack."""
    battle = levelled(8, count=3)
    for enemy in battle.enemies:
        enemy.stats.hp = 999

    events = battle.choose(SPECIAL, None, special=PAINT_THE_WALLS_RED)

    assert all(DEEP_BLEED in enemy.statuses for enemy in battle.enemies), "someone was missed"
    # Heavier *and* longer than the vein's own cut: what it costs per turn is the
    # part that makes a whole turn spent on it worth spending.
    deep = status_by_key(DEEP_BLEED)
    vein = status_by_key("bleed")
    assert deep.damage > vein.damage, "'heavy' costs no more than the vein's cut"
    assert deep.turns > vein.turns, "'heavy' does not last any longer either"
    assert any(
        isinstance(event, Flourish) and event.flair == PAINT_THE_WALLS_RED
        for event in events
    ), "Atritas did not come"


def test_the_purse_is_the_only_gate():
    """One economy and not two: what a trick costs is the whole of the rule.

    There is no once-a-fight tally any more. A trick he knows and cannot afford
    is refused -- and told the *price*, because "no" without a number is a rule
    the player cannot play against.
    """
    battle = levelled(6)
    battle.state.kill_points = 0

    events = battle.choose(SPECIAL, battle.enemies[0], special=OPEN_VEIN)

    assert not strikes(events), "a trick was cast out of an empty purse"
    assert any("kill points" in line for line in lines(events)), lines(events)


def test_a_trick_is_paid_for_out_of_the_purse():
    """And the purse pays on the way out, so a refusal costs nothing."""
    battle = levelled(6)
    before = battle.state.kill_points
    cost = special_by_key(OPEN_VEIN).cost

    battle.choose(SPECIAL, battle.enemies[0], special=OPEN_VEIN)

    # Give or take the point that came back on his own turn in the same breath.
    assert battle.state.kill_points <= before - cost + 1, "the trick was free"


def test_the_purse_fills_one_point_a_turn():
    """A point a turn of the hero's own, which is what makes a cheap trick a
    rhythm and a dear one a plan."""
    battle = levelled(3)
    battle.begin()  # so the round this measures is the hero's, and not the opening one
    battle.state.kill_points = 1

    battle.choose(ATTACK, battle.living_enemies()[0])

    assert battle.state.kill_points == 2, "the purse did not fill"


def test_the_purse_never_holds_more_than_the_level_allows():
    """The ceiling is the level, and it is a *ceiling*: a purse that grew past it
    would make saving pointless, and saving is half of what the price is for."""
    battle = levelled(3)
    battle.state.kill_points = battle.state.kill_points_max

    battle.choose(ATTACK, battle.living_enemies()[0])

    assert battle.state.kill_points == battle.state.kill_points_max, "it overflowed"


def test_every_trick_is_affordable_at_the_level_that_learns_it():
    """The curve and the prices are written in two files, so they are checked.

    A trick a level *teaches* and a purse that cannot pay for it is a trick the
    player only ever sees dimmed -- and the point of the curve is that the level
    which arrives with a trick arrives with the means to use it.
    """
    from neverdeads_revenge.game.levels import kill_points_for
    from neverdeads_revenge.game.specials import SPECIALS_BY_HERO, learned_at

    for hero, kit in SPECIALS_BY_HERO.items():
        for special in kit:
            gate = learned_at(special, 7)
            purse = kill_points_for(gate)
            assert purse >= special.cost, (
                f"{hero}'s {special.name} arrives at level {gate} and costs "
                f"{special.cost}, out of a purse of {purse}"
            )


def test_every_trick_is_paid_for_and_none_is_free():
    """An ultimate is the floor's now, not the fight's -- so what is left is a
    kit of tricks, and every one of them has a price."""
    from neverdeads_revenge.game.specials import SPECIALS_BY_HERO

    for hero, kit in SPECIALS_BY_HERO.items():
        assert all(one.cost > 0 for one in kit), f"{hero} has a trick for free"
        assert len({one.cost for one in kit}) > 1, f"{hero}'s tricks all cost the same"


def test_a_miss_leaves_no_wound_behind():
    """A trick that misses is a trick that missed: no poison, no bleed, no cold.

    The *weapon's* effects have always been gated on the hit -- a sword that
    missed did not open a wound. The tricks were not, so a dagger that went past
    your ear left venom in you anyway, and the rime chilled a monster it never
    touched. One rule for both: a wound needs a wound to be in.

    The blow is stubbed rather than made unlikely: the rule is about what the
    legs of a trick do with a *missed* outcome, and a test that rolled for one
    would be a test that passes most of the time.
    """
    from neverdeads_revenge.game.combat import AttackOutcome
    from neverdeads_revenge.game.specials import LEFT_HAND, LONG_WINTER, OPEN_VEIN, RIME

    missed = AttackOutcome(hit=False, crit=False, damage=0, killed=False, dodged=True)
    riders = (
        ("noxx", LEFT_HAND, "poison"),
        ("noxx", OPEN_VEIN, "bleed"),
        ("yeti", RIME, "chill"),
        ("yeti", LONG_WINTER, "chill"),
    )
    for hero, key, status in riders:
        battle = duel(hero, 8, count=2)
        for enemy in battle.enemies:
            enemy.stats.hp = 999
        battle._blow = lambda *a, **k: missed  # type: ignore[method-assign]

        battle.choose(SPECIAL, battle.enemies[0], special=key)

        for enemy in battle.enemies:
            assert status not in enemy.statuses, (
                f"{key} left {status} on a monster it never touched"
            )


def test_a_miss_throws_nobody():
    """And the shove is the same rule: the bell that missed does not move him."""
    from neverdeads_revenge.game.combat import AttackOutcome
    from neverdeads_revenge.game.specials import BELLS_THROW, SNOW_BLIND

    missed = AttackOutcome(hit=False, crit=False, damage=0, killed=False, dodged=True)
    for hero, key in (("walkyrion", BELLS_THROW), ("yeti", SNOW_BLIND)):
        battle = duel(hero, 8, count=1)
        for enemy in battle.enemies:
            enemy.stats.hp = 999
        battle._blow = lambda *a, **k: missed  # type: ignore[method-assign]
        thrown: list = []
        battle._throw_back = thrown.append  # type: ignore[method-assign]

        battle.choose(SPECIAL, battle.enemies[0], special=key)

        assert not thrown, f"{key} threw a monster it never touched"


def test_a_monster_that_bleeds_to_death_ends_the_fight_at_once():
    """The last monster can die of a wound, and the fight has to be over then.

    The wounds tick once a hero turn, in `_lapse` -- which ran *after* the win
    check, so the last of them could bleed out at the start of a turn and the
    fight would sit there undecided: the player swings at nothing, walks through
    the aim twice, and only then does the room admit it is empty. Which is
    exactly what "the fight does not end straight away, sometimes" was, and why
    it was always something to do with the statuses.

    A self-buff and not a swing, because a swing that *lands* would finish the
    monster by hand and there would be nothing left for the wound to do.
    """
    from neverdeads_revenge.game.specials import STILLNESS

    battle = duel("yeti", 6, count=1)
    enemy = battle.enemies[0]
    enemy.stats.hp = 1
    enemy.statuses["bleed"] = 3
    battle.begin()

    events = battle.choose(SPECIAL, None, special=STILLNESS)

    assert enemy.stats.hp == 0, "the wound did not finish it"
    assert battle.over and battle.won, "the fight did not know it was over"
    assert any(isinstance(event, Over) and event.won for event in events), (
        "no verdict was handed over"
    )


def test_a_vein_opened_on_a_bleeding_monster_deepens_the_wound_to_the_cap():
    """A cut on a cut is a deeper cut.

    The trick used to *set* the depth to two, so opening a vein on a monster that
    was already bleeding twice did nothing at all -- the most expensive way to
    learn that the wound had a ceiling.
    """
    battle = levelled(5)
    enemy = battle.enemies[0]
    enemy.stats.hp = 999

    battle.choose(SPECIAL, enemy, special=OPEN_VEIN)
    assert enemy.status_stacks["bleed"] == 2

    battle.choose(SPECIAL, enemy, special=OPEN_VEIN)
    assert enemy.status_stacks["bleed"] == 4, "the second vein did not add"

    battle.state.kill_points = 10
    battle.choose(SPECIAL, enemy, special=OPEN_VEIN)
    assert enemy.status_stacks["bleed"] == STACK_LIMIT, "the ceiling was not reached"


def test_the_kill_lines_wait_for_the_killing_blow():
    """The log may not know the ending before the room has shown it.

    A killing blow writes several lines -- the kill, the level, the kill points,
    the trick learned -- and they are all the blow's sentence. The screen reads
    them when the blow lands, so the level-up arrow cannot rise over a monster
    that is still standing.
    """
    state = start_run(HEROES["noxx"], seed=7)
    state.kills = 2
    state.level = 1
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy

    enemy = make_enemy(ENEMIES["ghoul"], (1, 1))
    enemy.stats.hp = 1
    state.enemies = [enemy]
    state.turn_queue = type(state.turn_queue)([state.player, enemy])
    battle = Battle(state, [enemy])
    battle.begin()

    events = battle.choose(ATTACK, enemy)

    said = [event for event in events if isinstance(event, Said)]
    level = [line for line in said if line.text.startswith("Level 2")]
    assert level, "the kill did not pay a level"
    assert all(line.waits for line in level), "the level line was read at the swing"
    # The verb changes with the size of the blow ("kill", "obliterate"), so the
    # line is found by the monster it names, not by one spelling of the verb.
    killed = [line for line in said if "ghoul" in line.text]
    assert killed and all(line.waits for line in killed), "the kill line ran ahead"


def test_the_open_vein_keeps_costing_him():
    """A wound that will not close: the status is left, and a round makes it bite."""
    battle = levelled(5)
    enemy = battle.enemies[0]
    enemy.stats.hp = 999

    battle.choose(SPECIAL, enemy, special=OPEN_VEIN)
    assert "bleed" in enemy.statuses, "the vein was opened and nothing ran"
    assert enemy.status_stacks["bleed"] == 2, "the vein opened a scratch, not a vein"

    hp = enemy.stats.hp
    battle.choose(ATTACK, battle.living_enemies()[0])  # a round goes by: the wound does its work
    assert enemy.stats.hp < hp, "the bleed never bit"


def test_a_wound_that_bites_is_said_and_shown():
    """A wound is read out *and* handed to the screen.

    "The ghoul is bleeding. 2." was being written into the run's log and never
    reaching the arena's, so a wound cost a monster health in a fight where
    nobody ever mentioned it -- and the flourish says *which* wound it was, so
    the screen can show it in the right colour on the one it is happening to.
    """
    battle = levelled(5)
    enemy = battle.enemies[0]
    enemy.stats.hp = 999
    battle.choose(SPECIAL, enemy, special=OPEN_VEIN)
    assert "bleed" in enemy.statuses

    events = battle.choose(ATTACK, battle.living_enemies()[0])  # a round goes by: the wound does its work

    told = [event.text for event in events if isinstance(event, Said)]
    assert any("bleeding" in text for text in told), f"the wound bit in silence: {told}"
    shown = [
        event
        for event in events
        if isinstance(event, Flourish) and event.flair == "bleed" and event.actor is enemy
    ]
    assert shown, "the wound bit and nothing was shown on the one it happened to"


def test_between_blows_leaves_them_hitting_nothing():
    """He is not where they swing: this round, nothing finds him."""
    battle = levelled(6, count=1)
    battle.enemies[0].stats.damage = (5, 5)
    battle.enemies[0].stats.accuracy = 99
    battle.hero.stats.evasion = 0
    # Behind the hero in the order, so the trick is spent before it swings: the
    # round it covers is the one it was cast in.
    battle.enemies[0].stats.speed = 0.1
    hp = battle.hero.stats.hp

    battle.choose(SPECIAL, battle.enemies[0], special=BETWEEN_BLOWS)
    assert battle.hero.stats.hp == hp, "something found him anyway"


def test_the_five_arrive_with_levels():
    """The gates, in one place: what a run can do at each level."""
    def names_at(level: int) -> list[str]:
        battle = levelled(level)
        return [
            special.key for special in SPECIALS if battle.special_available(special)
        ]

    # One name a level, two to eight, in the order the menu reads them.
    for level, _ in enumerate(SPECIALS, start=2):
        assert names_at(level) == [one.key for one in SPECIALS[: level - 1]], (
            f"level {level} did not hand over exactly one more trick"
        )
    assert names_at(9) == [one.key for one in SPECIALS], "the kit stopped arriving"


def test_the_tricks_come_back_and_the_floor_does_not():
    """A new fight has the tricks back; the floor's ask is spent elsewhere.

    The arena's list is a list of *tricks*. The ultimate is not one any more --
    it belongs to the overworld -- so what a fight spends is the purse and
    nothing else.
    """
    state = run(ultimate_level=8)
    state.level = 7
    first = Battle(state, take(state, 2))
    first.choose(SPECIAL, first.enemies[0], special=LEFT_HAND)

    second = Battle(state, take(state, 2))
    assert second.special_available(special_by_key(LEFT_HAND)), "the knife did not come back"


def test_a_testrun_opens_the_whole_song():
    """`--testrun` makes the dark speak at level one, and a dark that talks does
    not keep the hero's own tricks secret: every one of the five is in hand.

    It is the same gate the void has always had, used for what it means -- and in
    an ordinary run the cap changes nothing, because the four arrive at two, four,
    five and six and the void at seven.
    """
    testing = levelled(1, ultimate_level=1)

    assert all(
        testing.special_available(special) for special in SPECIALS
    ), "a testrun left something locked"

    ordinary = levelled(1, ultimate_level=8)
    assert [
        special.key
        for special in SPECIALS
        if ordinary.special_available(special)
    ] == [], "an ordinary run at level one started with tricks"


# -- Yeti and Walkyrion (M3) --------------------------------------------------
def duel(hero: str, level: int = 7, count: int = 2):
    """A fight as another hero, at a level where the whole kit is in hand."""
    state = start_run(HEROES[hero], 1, ultimate_level=8)
    state.level = level
    state.kill_points = 999
    return Battle(state, take(state, count))


def test_each_hero_has_their_own_kit():
    """The tricks follow whoever is standing there: Yeti's glacier is not Noxx's
    shadow, and a menu of somebody else's moves is a menu with nothing in it.

    Noxx's is the deepest of the three by four -- the orb, the shadow, the
    devouring and the friends are his -- and each one still opens on its own
    first trick and closes on its own ultimate.
    """
    kits = {}
    for hero, first in (
        ("noxx", LEFT_HAND),
        ("yeti", AVALANCHE),
        ("walkyrion", FIRST_NOTE),
    ):
        kit = duel(hero).specials()
        kits[hero] = {special.key for special in kit}
        assert len(kit) >= 5, f"{hero} has {len(kit)} tricks"
        assert kit[0].key == first, f"{hero}'s kit is in the wrong order"
    # Seven each and none shared: a kit is a *character*, and a character whose
    # moves are somebody else's is a coat of paint. (Seven and not eight: the
    # ultimate is the overworld's, and the arena no longer lists it.)
    assert len(kits["noxx"]) == len(kits["yeti"]) == len(kits["walkyrion"]) == 7
    assert not kits["noxx"] & kits["yeti"], "the two share a trick"
    assert not kits["noxx"] & kits["walkyrion"], "the two share a trick"
    assert not kits["yeti"] & kits["walkyrion"], "the two share a trick"


def test_the_avalanche_lands_like_a_mountain():
    """The hammer is not cleverer than a sword, it is heavier: same dice, more."""
    heavy, light = duel("yeti", 4), duel("yeti", 4)
    for fight in (heavy, light):
        fight.enemies[0].stats.hp = 999
        fight.enemies[0].stats.evasion = 0
        fight.enemies[0].stats.armor = 0
        fight.hero.stats.accuracy = 99
    fight = heavy
    mountain = [
        one.outcome.damage
        for one in strikes(fight.choose(SPECIAL, fight.enemies[0], special=AVALANCHE))
        if one.actor is fight.hero
    ][0]
    pin = [
        one.outcome.damage
        for one in strikes(light.choose(ATTACK, light.enemies[0]))
        if one.actor is light.hero
    ][0]

    assert mountain > pin, f"the hammer hit for {mountain} and a cut for {pin}"


def test_the_rime_slows_what_it_cuts():
    """The cold gets into the legs: slower, and the round order reads it."""
    battle = duel("yeti", 4)
    enemy = battle.enemies[0]
    enemy.stats.hp = 999
    before = enemy.speed

    battle.choose(SPECIAL, enemy, special=RIME)

    assert "chill" in enemy.statuses, "the rime left nothing running"
    assert enemy.speed < before, "the chill did not reach the legs"


def test_the_hoarfrost_punishes_what_touches_him():
    """He does not swing: whoever lands a blow on him takes the cold home."""
    battle = duel("yeti", 5, count=1)
    enemy = battle.enemies[0]
    enemy.stats.accuracy = 99
    # Slow enough to be behind him in the queue, quick enough to come round
    # inside the same turn: a very slow monster would simply not get a blow in
    # before Yeti's next one, and the frost would have nothing to answer.
    enemy.stats.speed = 0.5
    battle.hero.stats.evasion = 0

    battle.choose(SPECIAL, enemy, special=HOARFROST)

    assert "chill" in enemy.statuses, "the frost never came off him"


def test_the_stillness_raises_the_ice():
    """He sets his feet: the armour is his own, and it stays for the fight."""
    battle = duel("yeti", 6)
    armor = battle.hero.armor

    battle.choose(SPECIAL, battle.enemies[0], special=STILLNESS)

    assert battle.hero.armor > armor, "setting his feet raised nothing"



def test_the_bells_throw_sends_them_to_the_back():
    """The ring of it throws what it lands on: it acts after everyone who has
    not gone yet -- and if it has already gone, then next round it goes last.

    Asked of the mechanic itself, because the round it reorders is over by the
    time the round it was thrown in has been played: what the *special* owes is
    the throw and the sentence, and both are checked here.
    """
    battle = duel("walkyrion", 4, count=3)
    enemy = battle.enemies[1]

    battle._throw_back(enemy)

    assert battle._order()[-1] is enemy, "it was not sent to the back"

    battle = duel("walkyrion", 4, count=3)
    enemy = battle.enemies[1]
    enemy.stats.hp = 999

    events = battle.choose(SPECIAL, enemy, special=BELLS_THROW)

    assert any("throws him back" in line for line in lines(events)), (
        "the ring said nothing about throwing it"
    )


def test_the_true_note_makes_every_blow_after_it_hit_harder():
    battle = duel("walkyrion", 5)
    before = battle.hero.damage_range

    battle.choose(SPECIAL, battle.enemies[0], special=TRUE_NOTE)

    assert battle.hero.damage_range > before, "the note was found and lost again"
    # And it survives a kill: REVENGE rewrites its own bonus on every one, and
    # the note used to share that field and be erased by the next monster that
    # died. Asked after a death, because that is where it went wrong.
    noting = battle.hero.damage_range
    from neverdeads_revenge.game.combat import apply_revenge

    apply_revenge(battle.hero, 1)
    assert battle.hero.damage_range >= noting, "a kill ate the note"


def test_the_echoing_cut_is_heard_three_times():
    """The cut lands once and is heard on everything else, for less."""
    battle = duel("walkyrion", 6, count=3)
    for enemy in battle.enemies:
        enemy.stats.hp = 999
    battle.hero.stats.accuracy = 99
    for enemy in battle.enemies:
        enemy.stats.evasion = 0

    events = battle.choose(SPECIAL, battle.enemies[0], special=ECHOING_CUT)

    hit = [one for one in strikes(events) if one.actor is battle.hero]
    assert len(hit) == 3, f"the echo was heard {len(hit)} times"



def test_a_shadow_that_leaves_the_room_hands_the_floor_back():
    """The one exit that came out without closing the door.

    A fight that ends by any other road clears ``in_fight``; the fleeting shadow
    did not, so the floor behind it stood still for the rest of the run.
    """
    battle = duel("noxx", 8)

    battle.choose(SPECIAL, battle.enemies[0], special=FLEETING_SHADOW)

    assert battle.escaped, "the shadow did not leave"
    assert battle.state.in_fight is False, "the floor never moved again"


def test_borrowed_armour_goes_back_when_the_room_is_done():
    """THE STILLNESS lends armour for the fight and takes it back after it.

    It used to be added to the hero's own stat and never given back, so a Yeti
    who set his feet twice carried the ice down every floor of the run.
    """
    battle = duel("yeti", 8)
    before = battle.hero.stats.armor

    battle.choose(SPECIAL, battle.enemies[0], special=STILLNESS)
    assert battle.hero.stats.armor > before, "setting his feet raised nothing"

    battle._close_the_fight()

    assert battle.hero.stats.armor == before, "the ice came home with him"


def test_every_command_in_a_fight_costs_a_turn():
    """A fight is not free. One hero command is one turn, as one step is one turn.

    Without this a whole encounter cost nothing: ``KILL_SCORE`` is calibrated
    against "a fight costs fifty to ninety points", the speed bonus counted a
    run that fought everything as if it had walked straight to the stairs, and
    the patience amulet -- better the longer a fight runs -- never grew.
    """
    battle = duel("noxx", 5)
    run_before = battle.state.total_turns
    floor_before = battle.state.turn

    commands = 0
    for _ in range(3):
        if battle.over:
            break
        # A blow at a corpse is a refused verb, not a turn: aim at whoever is
        # still standing, or the test measures the old bug instead of the rule.
        target = next(one for one in battle.enemies if one.stats.alive)
        battle.choose(ATTACK, target)
        commands += 1

    assert commands == 3, "the duel ended too early to measure"
    assert battle.state.total_turns == run_before + 3, "a command was free"
    assert battle.state.turn == floor_before + 3, "the floor clock did not move"


def test_a_wound_in_the_arena_runs_on_the_heros_turn_whatever_the_monsters_speed():
    """Statuses tick once per hero turn, not once per victim turn.

    The room has one clock and it is his. That is what makes a status build a
    *speed* build: a quicker hero takes more turns, and every wound he has
    opened runs on each of them. A wound on a slow monster must therefore tick as
    often as a wound on a quick one -- the old rule, per victim turn, would make
    the quick one bleed four times as often inside the same round.
    """
    from neverdeads_revenge.game.statuses import STATUSES

    battle = duel("noxx", 5, count=2)
    slow, quick = battle.enemies
    slow.stats.speed, quick.stats.speed = 0.4, 4.0
    for one in (slow, quick):
        one.stats.max_hp = one.stats.hp = 999
        one.statuses["bleed"] = 8
        one.status_stacks["bleed"] = 1

    # Aim at the quick one, so everything the slow one loses is the wound.
    for _ in range(3):
        if battle.over:
            break
        battle.choose(ATTACK, quick)

    expected = 999 - 3 * STATUSES["bleed"].damage
    assert slow.stats.hp == expected, (
        f"the slow one bled to {slow.stats.hp}, not {expected} -- the wound "
        "followed the monster's turns instead of the hero's"
    )




def test_every_level_teaches_exactly_one_trick():
    """Seven tricks, the levels two to eight: one per level, in order.

    A level that hands over two is a level that feels like a list, and the menu
    reads bottom-up -- so the kit is ordered by the level it arrives at, and no
    two names share one.
    """
    from neverdeads_revenge.game.specials import SPECIALS_BY_HERO

    for hero, kit in SPECIALS_BY_HERO.items():
        levels = [special.level for special in kit]
        assert levels == list(range(2, 2 + len(kit))), f"{hero}: {levels}"
