"""One part of the turn: life."""

from __future__ import annotations

from neverdeads_revenge.core.direction import (
    Pos,
)
from neverdeads_revenge.world.items import make_coin
from ..actors import (
    NOTARY_BILL,
    Actor,
    ActorKind,
)
from ..combat import apply_revenge
from ..curses import TOUCH_CURSES, CURSES
from ..gifts import gift_by_key
from ..levels import kill_points_for
from ..specials import learned_at, specials_for
from ..statuses import status_by_key
from ..levels import apply_gain, gains_between, level_for
from ..state import GameState, LogKind


from .core import (
    COIN_SCALE,
    COUNTS_FAVOUR_EVERY,
    COWARD_EDGE,
    EMBER_HEAL,
    FIRST_BLOW,
    KINDLY_PRICE,
    LEDGER_CAP,
    STACK_LIMIT,
)


def tick_statuses(state: GameState, actor: Actor) -> None:
    """Run whatever a blow left behind, at the start of the actor's own turn.

    On the floor this is the victim's turn, so a poison means different things to
    different monsters: eight turns is a long time for a ghoul and not very long
    at all for something quick. In the arena the whole room runs on the hero's
    turn instead -- ``Battle._lapse`` calls this for everybody once per round --
    which is what makes a status build a speed build.

    The decrement comes first so that the last turn still hurts -- a status that
    expires before it bites is a status that lied about its length.
    """
    if not actor.statuses:
        return

    for key in list(actor.statuses):
        status = status_by_key(key)
        if status is None:
            del actor.statuses[key]
            actor.status_stacks.pop(key, None)
            continue

        # Read before the decrement: the last tick of a wound is worth as many
        # stacks as the wound *had*, and popping the stacks first made a
        # three-stack bleed deal six, six, then two.
        stacks = max(1, actor.status_stacks.get(key, 1))
        actor.statuses[key] -= 1
        if actor.statuses[key] <= 0:
            del actor.statuses[key]
            actor.status_stacks.pop(key, None)

        if not status.damage:
            continue

        # The depth is the damage: one stack is what the status says it is, and
        # three of them is that three times. It is the only thing a stack means,
        # which is what makes the number on the badge and the number in the log
        # the same number.
        dealt = max(1, round(status.damage * stacks * actor.status_scale))
        actor.stats.hp = max(0, actor.stats.hp - dealt)
        state.hits.append(actor.position)
        if actor.is_player:
            state.say(f"You are {status.name}. {dealt}.", LogKind.DAMAGE)
        else:
            state.say(
                f"The {actor.name} is {status.name}. {dealt}.", LogKind.GOOD
            )

        if actor.stats.hp <= 0:
            if actor.is_player:
                state.die(f"The {status.name} finishes you.")
            else:
                state.say(f"The {actor.name} dies of it.", LogKind.GOOD)
                # A kill is a kill, however it was finished: the coins, the
                # level and the REVENGE all still belong to the player.
                _on_death(state, actor)
                _remove_corpse(state, actor)
            return


def inflict(
    state: GameState,
    target: Actor,
    keys: tuple[str, ...],
    *,
    turns_bonus: int = 0,
    stacks: int | None = None,
    source: Actor | None = None,
) -> None:
    """Leave something running on whoever was just hit.

    Refreshed, and -- for the two wounds -- *deepened*, to three at most. A
    second cut on a bleeding thing makes the bleeding last its own turns again
    and bleed one stack harder, which is the shape a fast cheap blade wants: it
    builds a wound rather than a damage multiplier, and three is the ceiling
    that keeps it one.

    ``stacks`` is for the rules that are not a second blow: the bloodline that
    says how deep a crit's wound is, and the trick that opens a vein for two.
    It *adds* to whatever is already open, up to the ceiling -- a cut on a cut is
    a deeper cut, and setting the depth instead meant that opening a vein on a
    monster that was already bleeding twice did nothing at all.

    ``source`` is who caused it, and it exists for one rule: the amulets that
    deepen a *particular* wound. They work on what the hero leaves in somebody
    else -- a monster's own self-bleed and a curse's price are not the hero's
    doing, and neither is a wound he takes himself.
    """
    if not keys or not target.stats.alive:
        return

    for key in keys:
        status = status_by_key(key)
        if status is None:
            continue
        fresh = key not in target.statuses
        target.statuses[key] = max(
            target.statuses.get(key, 0), status.turns + turns_bonus
        )
        deepens = (
            1
            if source is not None
            and source.is_player
            and target is not source
            and state.status_depth_bonus(key)
            else 0
        )
        if stacks is not None:
            depth = target.status_stacks.get(key, 0) + stacks
        elif status.stackable:
            depth = target.status_stacks.get(key, 0) + 1
        else:
            # A wound that does not take a second cut keeps the depth it has: a
            # second dose of the same poison is not a deeper one, and the amulet
            # below is the only thing that makes it deeper.
            depth = max(1, target.status_stacks.get(key, 1))
        target.status_stacks[key] = max(1, min(STACK_LIMIT, depth + deepens))
        if not fresh:
            continue
        if target.is_player:
            state.say(f"You are {status.name}.", LogKind.BAD)
        else:
            state.say(f"The {target.name} is {status.name}.", LogKind.GOOD)


def _weapon_rule_bonus(state: GameState, first: bool) -> int:
    """Flat damage the blade's own rule adds, read at the swing.

    Three blades are worth something the numbers cannot say: THE FIRST BLOW is
    worth seven *once* -- the first landing blow of the fight, the same flag the
    patient knife and the grave ward read -- THE COWARD'S EDGE is worth four
    while the hero is above half his blood, and THE REAPER'S LEDGER is worth one
    a kill *this floor*. A blade with no rule adds nothing, and so does a fist.
    """
    weapon = state.player.equipment.get("weapon")
    if weapon is None:
        return 0
    if weapon.rule == "first_blow":
        return FIRST_BLOW if first else 0
    if weapon.rule == "coward":
        return COWARD_EDGE if state.player.hp * 2 > state.player.max_hp else 0
    if weapon.rule == "ledger":
        return min(LEDGER_CAP, state.floor_kills)
    return 0


def pay_the_kindly_one(state: GameState) -> bool:
    """Pay its price, and let it go. ``False`` when the purse cannot.

    The enemy *leaves*: no kill, no coin, no kill point. It got what it came for,
    which is the whole of what refusing was protecting.
    """
    enemy = state.encounter
    if enemy is None or enemy.behaviour != "kindly":
        return False
    if state.gold < KINDLY_PRICE:
        return False
    state.gold -= KINDLY_PRICE
    enemy.alive = False
    if enemy in state.enemies:
        state.enemies.remove(enemy)
    state.encounter = None
    state.say(
        f"You give it {KINDLY_PRICE} gold, and it is not there any more.",
        LogKind.BAD,
    )
    return True


def _thorns_of(actor: Actor) -> int:
    """What the wearer gives back to whatever lands a blow on them.

    Read off the coat, at the moment it matters, for the same reason the blade's
    statuses are read at the moment of the swing: a coat swapped mid-floor has to
    start working on the next blow rather than the next run.
    """
    if not actor.is_player:
        return 0
    coat = actor.equipment.get("armour")
    return coat.thorns if coat is not None else 0


def _inflicts_of(actor: Actor) -> tuple[str, ...]:
    """What this actor's blows leave behind.

    For the player that is the blade in hand, read at the moment of the swing: a
    weapon swapped mid-floor has to start working on the next blow, not the next
    run. A monster carries it on its template, because a monster does not change
    weapons.
    """
    if not actor.is_player:
        return actor.inflicts
    return actor.weapon_inflicts


def _remove_corpse(state: GameState, enemy: Actor) -> None:
    enemy.alive = False
    state.enemies.remove(enemy)
    state.turn_queue.remove(enemy)


def _one_death_answers(state: GameState, enemy: Actor) -> None:
    """The three monsters whose *death* is their move.

    A death is usually the end of a monster's rules. For three of them it is the
    beginning of somebody else's: the twin's grief, the debt's collection, and
    the notary's bill (which grows with every kill on the floor, this one
    included).
    """
    if enemy.behaviour == "twin":
        # The one left stops grieving: full health and twice the anger. Killing
        # the pair in one order is a different fight from the other.
        mate = next(
            (
                one
                for one in state.enemies
                if one is not enemy
                and one.behaviour == "twin"
                and one.stats.alive
            ),
            None,
        )
        if mate is not None:
            mate.stats.hp = mate.stats.max_hp
            low, high = mate.stats.damage
            mate.stats.damage = (low * 2, high * 2)
            state.say(
                f"The {mate.name} stops grieving, and comes for you.",
                LogKind.BAD,
            )

    if enemy.behaviour == "debt":
        # Dying does not cancel it. The next room on this floor collects.
        state.debt += 1
        state.say("The debt is not paid. It is passed on.", LogKind.BAD)

    # THE NOTARY grows on every kill on its floor, and this is one of them.
    notary = next(
        (
            one
            for one in state.enemies
            if one is not enemy
            and one.behaviour == "notary"
            and one.stats.alive
        ),
        None,
    )
    if notary is not None:
        fed = notary.stats.heal(NOTARY_BILL)
        if fed:
            state.say(f"The {notary.name} writes it down. {fed}.", LogKind.BAD)


def _kill_message(state: GameState, enemy: Actor, outcome) -> None:
    """Report a blow that killed, and everything a kill is worth."""
    state.say(
        f"You {outcome.verb_second_person} the {enemy.name} for {outcome.damage}!",
        LogKind.CRIT if outcome.crit else LogKind.COMBAT,
    )
    _on_death(state, enemy)


def _on_death(state: GameState, enemy: Actor) -> None:
    """Everything that happens because something died, however it died.

    Its own function because a monster can die with the player's name on it in
    two ways: a blow, and the mirror. The mirror used to skip straight to the
    corpse, so a kill it finished counted for *nothing* -- no coin, no REVENGE,
    no level and no ember -- which made an amulet quietly cost the player a
    handful of things it had never mentioned.
    """
    # The two answers to one question, made to agree here: every death comes
    # through this door, and a monster left ``alive`` with no health in it is a
    # monster the map still draws, still walks around, and still raises an
    # encounter for -- and the arena refuses that fight, because it asks the
    # *health*. The player presses into a corpse and nothing happens.
    enemy.alive = False
    if state.encounter is enemy:
        # And nothing is owed any more. A monster that died before its fight was
        # opened leaves a floor that would otherwise owe a battle to a corpse:
        # the door into the arena asks the *health* and refuses, so the run sits
        # in a room it can never enter, with the enemy phase standing still for
        # it, for the rest of the floor.
        state.encounter = None
    state.kills += 1
    state.floor_kills += 1
    if enemy.kind is ActorKind.ENEMY and enemy.key and enemy.key not in state.defeated:
        # THE ALMANAC's rule, kept where every death passes: the first kill of a
        # monster is the moment it is *known*. What the page says is the book's
        # business; that there is one is the dungeon's.
        state.defeated.append(enemy.key)
    state.deaths.append(enemy.position)
    # THE CARRION TONGUE reads this long after the blood has been cleared: a
    # square where something died is a square that feeds, for the whole floor.
    state.death_squares.add(enemy.position)
    _drop_coins(state, enemy)
    if enemy.behaviour == "hunter":
        _hunter_spoils(state, enemy)
    _one_death_answers(state, enemy)
    _learn(state)

    # The blade's own reckoning, after the kill is counted: a debt paid, and a
    # fire that does not stop with the thing it started on.
    weapon = state.player.equipment.get("weapon")
    rule = weapon.rule if weapon is not None else ""
    if rule == "debtor" and state.gold:
        state.gold = max(0, state.gold - 1)
        state.say("The debtor takes a coin.", LogKind.BAD)
    elif rule == "spread_burn":
        # Only what the hero can see: the state's enemy list is the whole floor,
        # and the fire used to jump to something on the other side of the map.
        others = [
            one
            for one in state.enemies
            if one is not enemy
            and one.stats.alive
            and state.dungeon_map.is_visible(one.position)
        ]
        if others:
            victim = state.rng.pick(others)
            inflict(state, victim, ("burn",), source=state.player)
            state.say(f"The fire takes the {victim.name}.", LogKind.GOOD)

    # THE TITHE. The one price that argues with the score, which now pays for
    # killing: it can finish the hero, and a price that cannot is not a price.
    cost = state.kill_cost
    if cost:
        state.player.stats.hp = max(0, state.player.stats.hp - cost)
        if state.player.hp <= 0:
            state.die("The tithe takes the last of you.")
            return
        state.say(f"The tithe takes {cost}.", LogKind.DAMAGE)

    player = state.player

    heal = (EMBER_HEAL if state.has_passive("ember") else 0) + state.kill_heal
    if heal:
        healed = player.stats.heal(heal)
        if healed:
            state.say(f"The kill feeds you: {healed} back.", LogKind.GOOD)

    if state.has_wild("counts_favour") and state.kills % COUNTS_FAVOUR_EVERY == 0:
        player.stats.hp = player.stats.max_hp
        state.say(
            f"The count is satisfied at {state.kills}. You are whole again.",
            LogKind.GOOD,
        )

    if state.has_passive("borrowed_face"):
        # One turn of nobody being able to land on you. The world counts it down,
        # and the monsters that answer this very kill are the ones it covers.
        state.shrouded = 1

    before = state.revenge_stacks
    gain = 1 + (1 if state.has_passive("long_hunger") else 0)
    if state.has_draught("short_crown"):
        # THE SHORT CROWN. Twice the charge for the floor and no longer: it is
        # the one bottle that turns a floor into a fight worth picking.
        gain *= 2
    state.revenge_stacks = apply_revenge(player, before + gain)
    if state.revenge_stacks > before:
        # Say what it actually granted, and say it by its own name: the tide,
        # the fortress and the blade are three grants wearing one word. Note the
        # `title` on the trait -- "REVENGE" still names the system, this names
        # the grant.
        state.say(
            f"{player.trait.title} {state.revenge_stacks}: "
            f"{player.trait.describe(state.revenge_stacks)}.",
            LogKind.GOOD,
        )


def _learn(state: GameState) -> None:
    """Fold whatever the last kill taught into the hero.

    Asked after every kill and almost always a no-op. The level is derived from
    the kill count rather than counted up, so this is a comparison and not a
    counter that could drift out of step with the thing it counts.
    """
    reached = level_for(state.kills)
    if reached <= state.level:
        return

    was = state.level
    gain = gains_between(state.level, reached)
    state.level = reached
    apply_gain(state.player, gain)
    state.say(f"Level {reached}: {gain.describe()}.", LogKind.GOOD)
    # And the purse: this is where kill points *come from*. A level raises the
    # ceiling and fills to it, because a level that only raised the ceiling would
    # be a level that handed the player a longer wait.
    if state.kill_points_max > kill_points_for(was):
        state.kill_points = state.kill_points_max
        state.say(f"Kill points {state.kill_points}.", LogKind.GOOD)
    # And what the level *taught*. A trick's gate is a level, so a level-up is
    # the only moment anything is ever learned -- and the announcement belongs
    # here, where it happens, and not in a menu the player might not open for
    # another floor. The line is written the same way on the map and in the
    # arena, because the arena splices the run's log into its own.
    for special in specials_for(state.hero.key):
        if was < learned_at(special, state.ultimate_level) <= reached:
            state.say(f"{special.name} learned!", LogKind.GOOD)


def _hunter_spoils(state: GameState, enemy: Actor) -> None:
    """The rule the thing that hunts leaves behind when it is finally killed.

    It is the one monster with a rule to give. Everything else drops coin and
    maybe a wound; the hunter is the floor's decision, and beating a decision
    should change what the player can do rather than just what they carry. The
    rule is drawn from the ones the run does not have yet, exactly the way a
    chest's is, so the prize is never something already in hand -- and when
    there is nothing left to hand over, the kill says so rather than inventing
    a second copy of a rule the player is already holding.

    A rule a chest on this same floor is already owing is left out of the draw
    too. The chest was stocked before the player saw either of them, and a
    hunter that spent that lid's gift would turn the chest into a second copy of
    a rule -- which is the one thing a chest's own docstring refuses to be.
    """
    promised = {
        item.gift
        for item in state.dungeon_map.items.values()
        if item.kind == "chest" and item.gift is not None
    }
    unheld = tuple(key for key in state.unheld_gifts if key not in promised)
    if not unheld:
        state.say(
            f"The {enemy.name} falls, and there is nothing left it can teach you.",
            LogKind.PLAIN,
        )
        return

    gift = gift_by_key(state.rng.pick(unheld))
    if gift is None:  # pragma: no cover - the table and its keys agree
        return
    state.gifts.add(gift.key)
    state.say(
        f"The {enemy.name} was carrying something. {gift.name}: {gift.blurb}.",
        LogKind.GOOD,
    )


def _drop_coins(state: GameState, enemy: Actor) -> None:
    """Leave what the monster was carrying where it fell.

    A pile rather than a number added straight to the purse: gold you have to
    walk over is gold you can decide to leave, and deciding is the point. It
    also puts the two clocks in the game against each other -- the score wants
    you gone quickly, the coins want you to take one more step.
    """
    low, high = enemy.gold
    if high <= 0:
        return

    # Half of what a monster used to drop, because the floors hold twice as
    # many of them: a purse's worth of coin per floor, spread over more kills.
    # The score reads the purse too, so the *coin* half of a run's score is
    # halved with it -- which is the point: more bodies is not meant to pay more.
    #
    # Not the hunter, though. There is still one hunter a floor and no more of
    # them than there ever was, so its purse is not a share of the floor's but a
    # reward of its own -- and a decision worth taking must not pay half of what
    # it paid last week.
    scale = 1.0 if enemy.behaviour == "hunter" else COIN_SCALE
    value = max(
        1, round(state.rng.between(low, high) * state.coin_factor * scale)
    )
    if enemy.stolen:
        # THE PICKER carries what it took. Kill it and the purse is whole again
        # -- its own coin *and* yours -- which is the whole of why chasing it is
        # worth the turns. Let it leave and the difference is what it cost.
        value += round(enemy.stolen * state.coin_factor)
    _scatter_coins(state, enemy.position, value)


def _scatter_coins(state: GameState, pos: Pos, value: int) -> None:
    """Put ``value`` coins on ``pos``, merging with a pile already lying there.

    Split out of :func:`_drop_coins` so THE BLOOD PRICE can pay in the same
    currency and by the same rules: two piles in one corner are one bigger pile,
    and a pile under a chest is coin the player will never see.
    """
    existing = state.dungeon_map.item_at(pos)
    if existing is not None and existing.kind == "coin":
        existing.gold += value
        return
    if existing is not None:
        return  # something else is lying there; the coins are lost to it

    state.dungeon_map.add_item(pos, make_coin(value))


def _player_takes_damage(state: GameState, enemy: Actor, outcome) -> None:
    if outcome.hit:
        # The player's own cell, so a blow you take is something you see as well
        # as read. The useful half of the flash, and the half a message log
        # cannot do: the log scrolls, and the map is where you are looking.
        state.hits.append(state.player.position)
        state.say(
            f"The {enemy.name} {outcome.verb} you for {outcome.damage}.",
            LogKind.BAD if outcome.killed else LogKind.DAMAGE,
        )
        # THE DEBT OF BLOOD. Every point a blow costs is owed back on the next
        # one the hero lands, which turns being hurt from a pure loss into a
        # loaded answer.
        if state.has_gift("blood_debt"):
            state.blood_debt += outcome.damage
        # THE BLOOD PRICE. The floor pays for what the hero bleeds, at the
        # hero's own feet -- coin you have to pick up in the middle of a fight,
        # which is the decision the gift is made of.
        if state.has_gift("blood_price"):
            _scatter_coins(
                state,
                state.player.position,
                max(1, round(outcome.damage * state.coin_factor)),
            )
    else:
        state.say(f"The {enemy.name} attacks and misses you.", LogKind.PLAIN)
    if outcome.killed:
        state.die(f"You are slain by the {enemy.name}.")
    elif outcome.hit and enemy.curse_chance:
        _maybe_cursed(state, enemy)

    # The deathwatch turns on the moment the wound lands, so it is recomputed
    # before the next thing in the queue swings.
    state.refresh_passives()


def _maybe_cursed(state: GameState, enemy: Actor) -> None:
    """A monster's touch can leave something behind.

    Every curse in the game so far has been a price the player read and agreed
    to -- the line on a chest, the catch on a pact. One that can simply happen
    to you is a different feeling, and it is the one the wraith is for: not a
    bargain but the dungeon reaching out.
    """
    if not state.rng.chance(enemy.curse_chance):
        return
    # Only something it can actually leave behind. Landing the curse the player
    # already carries reads as a bug -- and two of the four touch curses do not
    # stack, so half the time it *is* one.
    carried = {curse.key for curse in state.curses}
    available = [key for key in TOUCH_CURSES if key not in carried]
    if not available:
        state.say(
            f"The {enemy.name}'s touch goes through you and finds nothing "
            f"left to take.",
            LogKind.BAD,
        )
        return
    state.say(
        f"The {enemy.name}'s touch goes through you, and something stays.",
        LogKind.BAD,
    )
    state.add_curse(CURSES[state.rng.pick(available)])


def _enemy_takes_damage(state: GameState, enemy: Actor, outcome) -> None:
    state.hits.append(enemy.position)
    if outcome.killed:
        _kill_message(state, enemy, outcome)
        return
    state.say(
        f"You {outcome.verb_second_person} the {enemy.name} for {outcome.damage}.",
        LogKind.CRIT if outcome.crit else LogKind.COMBAT,
    )
    if outcome.capped:
        state.say("The silence swallows the rest of it.", LogKind.PLAIN)


