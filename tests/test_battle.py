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
    Flourish,
    Guarded,
    Over,
    Said,
    Struck,
    encounter_around,
    open_fight,
)
from neverdeads_revenge.game.specials import (
    ATRITAS,
    AVALANCHE,
    BELLS_THROW,
    BETWEEN_BLOWS,
    ECHOING_CUT,
    FIRST_NOTE,
    HOARFROST,
    LEFT_HAND,
    OPEN_VEIN,
    RIME,
    SHATTERED_BELL,
    SPECIALS,
    STILLNESS,
    TRUE_NOTE,
    VOID,
    FORTRESS,
    special_by_key,
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


def test_the_void_answers_once_and_everything_takes_it():
    """The hero's ask, in the arena: one blow on everybody, one per floor.

    The price is the dungeon's own -- ``ultimate_available`` is spent here the
    way ``f`` spends it on the map -- which is what keeps a floor from being
    asked twice for the same favour.
    """
    state = run(ultimate_level=1)
    enemies = take(state, 3)
    battle = Battle(state, enemies)
    battle.begin()

    events = battle.choose(SPECIAL, special=VOID)

    hit = [blow for blow in strikes(events) if blow.actor is state.player]
    assert [blow.target for blow in hit] == enemies, "the ask missed somebody"
    assert not state.ultimate_available, "the dark was not spent"
    assert {blow.flair for blow in hit} == {VOID}, "the blows wear no word"

    again = battle.choose(SPECIAL, special=VOID)
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

    events = battle.choose(SPECIAL, special=LEFT_HAND)

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


# -- the five tricks (M3) -----------------------------------------------------
def levelled(level: int, count: int = 2, ultimate_level: int = 7):
    """A fight at a chosen level, with the dark answering where it really does.

    The void's gate is the dungeon's own -- the level the dark answers at -- so a
    test about *levels* has to leave that gate where the game leaves it, or every
    level would come with the void attached.
    """
    state = start_run(HEROES["noxx"], 1, ultimate_level=ultimate_level)
    state.level = level
    return Battle(state, take(state, count))


def test_the_left_hand_is_a_stab_it_makes_sure_of():
    """The dagger: a crit it does not have to roll for, and deeper than usual."""
    battle = levelled(2)
    enemy = battle.enemies[0]
    enemy.stats.hp = 999

    events = battle.choose(SPECIAL, enemy, special=LEFT_HAND)

    blow = [one for one in strikes(events) if one.actor is battle.hero][0]
    assert blow.outcome.crit, "the left hand did not make sure of it"
    assert blow.flair == LEFT_HAND
    assert not battle.special_available(special_by_key(LEFT_HAND)), (
        "the knife was spent and can be spent again"
    )


def test_the_shadow_strikes_twice():
    """ATRITAS goes on its own, and lands two blows while the hero stands still."""
    battle = levelled(4)
    enemy = battle.enemies[0]
    enemy.stats.hp = 999

    events = battle.choose(SPECIAL, enemy, special=ATRITAS)

    hit = [one for one in strikes(events) if one.flair == ATRITAS]
    assert len(hit) == 2, f"the shadow struck {len(hit)} times"


def test_the_open_vein_keeps_costing_him():
    """A wound that will not close: the status is left, and a round makes it bite."""
    battle = levelled(5)
    enemy = battle.enemies[0]
    enemy.stats.hp = 999

    battle.choose(SPECIAL, enemy, special=OPEN_VEIN)
    assert "bleed" in enemy.statuses, "the vein was opened and nothing ran"

    hp = enemy.stats.hp
    battle.choose(DEFEND)  # a round goes by: the wound does its work
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

    events = battle.choose(DEFEND)  # a round goes by: the wound does its work

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

    assert names_at(2) == [LEFT_HAND]
    assert names_at(4) == [LEFT_HAND, ATRITAS]
    assert names_at(5) == [LEFT_HAND, ATRITAS, OPEN_VEIN]
    assert names_at(6) == [LEFT_HAND, ATRITAS, OPEN_VEIN, BETWEEN_BLOWS]
    assert names_at(7) == [one.key for one in SPECIALS], "the void never arrived"


def test_only_the_void_costs_the_floor():
    """Four of them are the fight's to spend; the fifth is the floor's.

    A new fight has the four back, because a trick learned is a trick to use --
    and the void is still gone, because that is the ask the dungeon prices.
    """
    state = run(ultimate_level=7)
    state.level = 7
    first = Battle(state, take(state, 2))
    first.choose(SPECIAL, first.enemies[0], special=LEFT_HAND)
    first.choose(SPECIAL, first.enemies[0], special=VOID)

    second = Battle(state, take(state, 2))
    assert second.special_available(special_by_key(LEFT_HAND)), "the knife did not come back"
    assert not second.special_available(special_by_key(VOID)), "the void came back"


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

    ordinary = levelled(1, ultimate_level=7)
    assert [
        special.key
        for special in SPECIALS
        if ordinary.special_available(special)
    ] == [], "an ordinary run at level one started with tricks"


# -- Yeti and Walkyrion (M3) --------------------------------------------------
def duel(hero: str, level: int = 7, count: int = 2):
    """A fight as another hero, at a level where the whole kit is in hand."""
    state = start_run(HEROES[hero], 1, ultimate_level=7)
    state.level = level
    return Battle(state, take(state, count))


def test_each_hero_has_their_own_five():
    """The tricks follow whoever is standing there: Yeti's glacier is not Noxx's
    shadow, and a menu of somebody else's moves is a menu with nothing in it."""
    for hero, first in (
        ("noxx", LEFT_HAND),
        ("yeti", AVALANCHE),
        ("walkyrion", FIRST_NOTE),
    ):
        kit = duel(hero).specials()
        assert len(kit) == 5, f"{hero} has {len(kit)} tricks"
        assert kit[0].key == first and kit[-1].uses_floor, (
            f"{hero}'s kit is in the wrong order or has no ultimate"
        )


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


def test_the_fortress_doubles_the_ice_and_costs_the_floor():
    """His own ultimate: the wall with twice his blood in it, priced by the floor."""
    battle = duel("yeti", 1)
    battle.state.level = 7
    armor = battle.hero.stats.armor

    battle.choose(SPECIAL, battle.enemies[0], special=FORTRESS)

    assert battle.hero.stats.armor >= armor * 2, "the wall was made of paper"
    assert not battle.state.ultimate_available, "the floor was not spent"


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
    before = battle.hero.damage_bonus

    battle.choose(SPECIAL, battle.enemies[0], special=TRUE_NOTE)

    assert battle.hero.damage_bonus > before, "the note was found and lost again"


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


def test_the_shattered_bell_takes_everyone_and_the_floor():
    battle = duel("walkyrion", 1, count=3)
    battle.state.level = 7
    for enemy in battle.enemies:
        enemy.stats.hp = 999
    battle.hero.stats.accuracy = 99
    for enemy in battle.enemies:
        enemy.stats.evasion = 0

    events = battle.choose(SPECIAL, battle.enemies[0], special=SHATTERED_BELL)

    hit = [one for one in strikes(events) if one.actor is battle.hero]
    assert len(hit) == 3, "the note did not go round"
    assert not battle.state.ultimate_available, "the floor was not spent"
