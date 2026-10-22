"""Player actions and the AI that answers them.

Everything the player can do goes through :func:`perform_action`, and everything
a monster does goes through :func:`take_turn`. Both mutate :class:`GameState` and
return nothing; the messages they emit are what the UI renders. Keeping the
decision-making here and the drawing in ``ui/`` means a test can play ten turns of
the game without a terminal.
"""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import fields

from dataclasses import dataclass
from enum import Enum

from neverdeads_revenge.core.direction import (
    DIRECTIONS,
    Direction,
    Pos,
    chebyshev,
    direction_towards,
)
from neverdeads_revenge.world.items import ITEMS, make_coin, make_item
from neverdeads_revenge.world.map import GroundItem
from neverdeads_revenge.world.tiles import Tile

from .actors import (
    Actor,
    ActorKind,
    make_atritas,
    make_enemy,
    make_fortress,
    pick_enemy_template,
)
from .combat import apply_revenge, attack
from .curses import TOUCH_CURSES, CURSES, curse_by_key
from .draughts import draught_by_key
from .difficulty import (
    ATRITAS_HUNT_RADIUS,
    ATRITAS_KILL_HEAL,
    ATRITAS_RADIUS,
    ATRITAS_SWING_EVERY,
    ATRITAS_TURNS,
    BELL_RADIUS,
    FORTRESS_TURNS,
)
from .gifts import gift_by_key
from .lore import numeral
from .levels import kill_points_for
from .specials import learned_at, specials_for
from .statuses import status_by_key
from .levels import apply_gain, gains_between, level_for
from .npcs import npc_by_key
from .state import GameState, LogKind, RunState

__all__ = [
    "Action",
    "ActionResult",
    "perform_action",
    "take_turn",
    "advance_world",
    "descend",
    "drink",
    "drop",
    "MAX_ENEMY_ACTIONS_PER_PLAYER_TURN",
    # The two blows, by name: the arena resolves the same ones the dungeon does.
    "resolve_player_attack",
    "resolve_enemy_attack",
    "ultimate_refusal",
    # The two the arena needs to run a special: what a wound leaves running, and
    # the beat on which it runs. Both were private until a fight had to read them.
    "inflict",
    "tick_statuses",
]


#: What the last ember puts back on a kill.
EMBER_HEAL = 2

#: What the mirror gives back to whatever struck you. Straight, not through
#: armour -- see :meth:`~neverdeads_revenge.game.actors.Stats.reflect`.
MIRROR_REFLECTION = 2

#: Every how many kills the count's favour heals you whole.
COUNTS_FAVOUR_EVERY = 13

#: What the second mouth can hold on the first floor, plus one for every floor
#: below it.
#:
#: armour is a flat subtraction, so what the cap is worth depends entirely on
#: what is hitting you, and what hits you scales with the depth. The cap moves
#: with the depth the same way the monsters do, or the amulet is a floor-N
#: trinket wearing a strong-tier price.
SECOND_MOUTH_BASE = 3


def second_mouth_cap(depth: int) -> int:
    """The most armour the second mouth will hold on ``depth``."""
    return SECOND_MOUTH_BASE + max(0, depth)


class Action(Enum):
    """Everything the player can do."""

    MOVE_NORTH = "north"
    MOVE_SOUTH = "south"
    MOVE_EAST = "east"
    MOVE_WEST = "west"
    MOVE_NE = "ne"
    MOVE_NW = "nw"
    MOVE_SE = "se"
    MOVE_SW = "sw"
    WAIT = "wait"
    #: Do whatever is under the player: take it, or take the stairs. This is the
    #: verb a key is bound to. The two specific actions below stay because they
    #: are meaningful on their own -- ``>`` is the classic "go down" and does not
    #: need to guess, and a test that wants to pick something up should not have
    #: to arrange a floor first.
    INTERACT = "interact"
    PICK_UP = "pickup"
    DESCEND = "descend"
    #: Open the chest underfoot. Never bound to a key: it only happens after the
    #: player has been shown the price and said yes, so the dialog is the only
    #: thing that issues it.
    OPEN_CHEST = "open_chest"
    #: Pay the price and leave the reward: a curse bought for a bigger score
    #: rather than for the thing behind the lid. Never bound to a key, like
    #: OPEN_CHEST, because it is a third answer to the same question.
    TAKE_FAME = "take_fame"
    #: Take back the last thing that happened. Only possible with THE BORROWED
    #: HOUR, and the only verb in the game that may be used after the run is
    #: over -- undoing a death is the whole of what it is for.
    REWIND = "rewind"
    #: Wash a curse off in the spring. Like OPEN_CHEST, never bound to a key:
    #: it only happens after the player has been shown the price and said yes.
    CLEANSE = "cleanse"
    QUAFF = "quaff"
    INVENTORY = "inventory"
    #: The hero's ultimate. Once a floor, from a level, and different for every
    #: hero: Noxx calls his friends, Yeti builds the Frozen Fortress,
    #: Walkyrion shatters the golden bell. Bound to `f`, because an ultimate is
    #: not a navigation verb and deserved a key of its own.
    ULTIMATE = "ultimate"

    @property
    def direction(self) -> Direction:
        """The movement direction, or ``NONE`` for non-movement actions."""
        return _ACTION_DIRECTIONS.get(self, Direction.NONE)


_ACTION_DIRECTIONS: dict[Action, Direction] = {
    Action.MOVE_NORTH: Direction.NORTH,
    Action.MOVE_SOUTH: Direction.SOUTH,
    Action.MOVE_EAST: Direction.EAST,
    Action.MOVE_WEST: Direction.WEST,
    Action.MOVE_NE: Direction.NORTH_EAST,
    Action.MOVE_NW: Direction.NORTH_WEST,
    Action.MOVE_SE: Direction.SOUTH_EAST,
    Action.MOVE_SW: Direction.SOUTH_WEST,
}


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Outcome of a player action."""

    consumed_turn: bool
    acted: bool
    died: bool = False
    escaped: bool = False
    #: Set when the player has to decide something before the action can happen.
    #:
    #: The domain never draws a dialog. It says one is needed, and the UI asks --
    #: which is what keeps the whole decision tree testable without a terminal.
    prompt: str | None = None
    #: Which dialog the prompt belongs to. The domain never draws one; it says
    #: one is needed and which question it is asking. Three kinds now -- a chest,
    #: a spring, somebody talking -- and a fourth would want an enum.
    prompt_kind: str = "chest"
    #: Set when the prompt is somebody talking, so the dialog can title itself.
    speaker: str = ""
    #: Set when the game *refused* something the player asked for -- a full pack,
    #: a bottle that is not there. The log says why in words; the front end says
    #: it in the one language an eye on the map does not read, and beeps.
    denied: bool = False


# -- helpers ---------------------------------------------------------------


def _the(name: str) -> str:
    """``the`` before a name that needs one, and not before one that has it.

    Half the equipment is called "the something" -- every amulet is, and the
    strongest blades are -- and "You start with the the patient knife" is the
    sort of thing that makes a whole screen look unfinished.
    """
    return name if name.startswith("the ") else f"the {name}"


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

    ``stacks`` is for the two rules that are not a second blow: the bloodline
    that says how deep a crit's wound is, and the trick that says *three*. It
    sets the depth rather than adding to it, because "how deep" is the sentence
    those two are written in.

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
            depth = stacks
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


#: What a blade's *rule* is worth, at the moment it is read. They live here and
#: not in the item table because they are rules and not numbers: the table says
#: which rule a blade carries, and these say what it does.
FIRST_BLOW = 7
COWARD_EDGE = 4
LEDGER_CAP = 5


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


#: What THE KINDLY ONE asks for. Small on purpose: it is not a toll, it is a hand
#: held out, and refusing is the expensive answer.
KINDLY_PRICE = 8


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
        fed = notary.stats.heal(4)
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


#: What a kill leaves behind, against what the monster says it was worth. See
#: :func:`_drop_coins`: the floors hold more monsters now, and this is the other
#: half of that trade, so that a floor still pays a floor.
COIN_SCALE = 0.5


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


# -- player actions --------------------------------------------------------


def _outcome(state: GameState, consumed_turn: bool, acted: bool) -> ActionResult:
    """Wrap a result, reading the ending off the state rather than assuming it.

    Worth the two lines: ``died=state.over`` was true after an escape too, and
    the game over screen would have announced a death to a player who had just
    won.
    """
    return ActionResult(
        consumed_turn=consumed_turn,
        acted=acted,
        died=state.run_state is RunState.DEAD,
        escaped=state.run_state is RunState.ESCAPED,
    )


def perform_action(state: GameState, action: Action) -> ActionResult:
    """Apply a player action, then let the world answer.

    Returns whether the action consumed a turn, so the UI knows whether to run
    enemy turns.
    """
    # The borrowed hour is allowed while the run is over, and it is the only
    # thing that is. Everything else has stopped being possible, because there
    # is nobody left to do it.
    if state.over and action is not Action.REWIND:
        return _outcome(state, consumed_turn=False, acted=False)

    state.refresh_passives()
    # Everything struck from here on is this action's. Cleared here rather than
    # by the screen, so the flash cannot outlive the turn it belongs to.
    state.hits.clear()
    state.deaths.clear()

    if action is Action.REWIND:
        return _rewind(state)

    # The run as it is, taken before anything happens, so the hour has somewhere
    # to go back to. Only while one is in hand: a deep copy of a floor is not
    # free, and most runs never take one.
    if state.rewind_ready:
        state.snapshot = _snapshot(state)

    # THE SALT CIRCLE counts waits *in a row*, so anything that is not a wait
    # breaks the run of them. This is the one place every action passes through,
    # which is why it is here and not in the wait itself.
    if action is not Action.WAIT:
        state.waits_in_a_row = 0

    match action:
        case Action.INTERACT:
            return _interact(state)
        case Action.PICK_UP:
            return _pick_up(state)
        case Action.OPEN_CHEST:
            return _open_chest(state)
        case Action.TAKE_FAME:
            return _take_fame(state)
        case Action.CLEANSE:
            return _cleanse(state)
        case Action.ULTIMATE:
            return _ultimate(state)
        case Action.QUAFF:
            return _quaff(state)
        case Action.INVENTORY:
            return _inventory(state)
        case Action.DESCEND:
            return _try_descend(state)
        case _:
            pass

    if action is Action.WAIT:
        state.say("You wait.", LogKind.PLAIN)
        # Waiting breaks the line as surely as turning does: a charge that
        # survived standing still would be a charge with no rule behind it.
        state.momentum = 0
        state.momentum_direction = None
        _hold_the_circle(state)
        acted, spent = True, True
    else:
        acted, spent = _try_move(state, action.direction)

    if state.over:
        return _outcome(state, consumed_turn=spent, acted=acted)

    # Only a real action advances the clock. Bumping a wall must not tick the
    # turn counter, or the displayed turn number drifts away from the world --
    # and a step taken for free must not either, which is why the two are not
    # the same flag.
    if spent:
        state.turn += 1
        state.total_turns += 1
        advance_world(state)
    state.refresh_vision()
    return _outcome(state, consumed_turn=spent, acted=acted)


def _hold_the_circle(state: GameState) -> None:
    """THE SALT CIRCLE. Waiting is the one thing a floor cannot answer.

    Three waits in a row close it, and the turn it closes is untouchable -- the
    same one-turn window the borrowed face buys, bought instead with the thing a
    run is scored in. The third wait is what raises it, and the counter resets so
    the next circle costs three more.
    """
    if not state.has_gift("salt_circle"):
        return
    state.waits_in_a_row += 1
    if state.waits_in_a_row < SALT_CIRCLE_WAITS:
        return
    state.waits_in_a_row = 0
    state.salt_ward = 1
    state.say("You close the circle. Nothing will reach you.", LogKind.GOOD)


def _try_move(state: GameState, direction: Direction) -> tuple[bool, bool]:
    """Move or attack in ``direction``.

    Returns ``(acted, spent)``: whether anything happened, and whether the world
    gets to answer it. They are the same thing for every move but one -- THE STEP
    BEHIND takes a step for free -- and the distinction has to exist before that
    gift can: a step that reported "nothing happened" would leave the player
    standing still on screen.
    """
    target = direction.step(state.player.position)
    if not state.dungeon_map.in_bounds(target):
        return False, False

    blocker = state.actor_at(target)
    if blocker is not None:
        if blocker.is_player:  # cannot happen, but be explicit
            return False, False
        if blocker.kind is ActorKind.NPC:
            # Solid, and not a fight. Saying so beats refusing to move in
            # silence: the player pressed a direction and something has to
            # happen, even if the something is "no, and here is why".
            state.say(f"{blocker.name} is in the way. Press enter to speak.", LogKind.PLAIN)
            return False, False
        if blocker.kind is ActorKind.ATRITAS:
            # The shadow is standing right where you were about to walk. It
            # asks nothing of your blade, and charging a turn for bumping
            # your own dark would be the void taxing its summoner.
            state.say("It is yours. It moves with you, not against you.", LogKind.PLAIN)
            return False, False
        if blocker.kind is ActorKind.FORTRESS:
            # A wall of your own ice. It is not a fight, and it is not a door.
            state.say("The ice is yours. It is not going anywhere.", LogKind.PLAIN)
            return False, False
        # Everything that is not a fight has been ruled out by now, so this is
        # one: the floor *hands the monster over* rather than resolving a blow,
        # and the arena does the swinging. The world does not get to answer --
        # the fight is the answer -- so no turn is spent here.
        state.raise_encounter(blocker)
        return True, False

    # THE LONG REACH. A direction with something hostile one square beyond an
    # empty square is a blow rather than a step -- and the empty square is the
    # whole rule: the reach is a reach, not a bow, so stone stops it. Which
    # makes the gift about corridors and doorways rather than about shooting.
    #
    # It costs nothing: the player already spends a turn on the blow, and making
    # them walk into the monster first would make the reach a decoration.
    if state.has_gift("long_reach") and state.dungeon_map.is_walkable(target):
        beyond = direction.step(target)
        if state.dungeon_map.in_bounds(beyond):
            far = state.actor_at(beyond)
            if far is not None and far.kind is ActorKind.ENEMY and far.alive:
                state.raise_encounter(far)
                return True, False

    # THE HESITATION. Every so many turns the hero does not take the step, and
    # the turn is spent anyway -- a price paid in *time*, which is half the
    # score.
    #
    # Cadenced on the turn count rather than on the step count, and that is not
    # a detail: a stumble does not advance ``player.steps``, so a cadence taken
    # from it would fire on the same number forever and the hero would never
    # move again. The turn counter is the one clock a stumble does advance.
    every = state.step_cost_every
    if every and (state.total_turns + 1) % every == 0:
        state.say("You hesitate, and the moment is gone.", LogKind.PLAIN)
        return True, True

    if not state.dungeon_map.is_walkable(target):
        # THE HOLLOW ROAD. Anything in bounds that nobody is standing on can be
        # walked into at a price -- including the void, which is *drawn* as wall,
        # so that what the player can see is what they can cross. A gift that
        # only worked on the tiles the map calls wall would be a gift that
        # visibly refused at every room's edge.
        if state.has_gift("hollow_road"):
            return _through_stone(state, target, direction)
        return False, False

    origin = state.player.position
    state.player.position = target
    state.player.steps += 1
    _after_step(state, origin, direction)
    _bleed(state)
    _knit(state)
    if state.has_draught("carrion_tongue") and target in state.death_squares:
        # THE CARRION TONGUE. A square where something died feeds the hero who
        # walks over it -- once: the floor remembers the dead, not the meal.
        state.death_squares.discard(target)
        healed = state.player.stats.heal(1)
        if healed:
            state.say("The tongue finds what the floor left. One back.", LogKind.GOOD)

    # THE STEP BEHIND. Every fifth step costs no time at all, which is the one
    # gift that touches the *score* -- turns are the score -- and therefore the
    # exact answer to a floor that is going badly.
    if state.has_gift("step_behind") and state.player.steps % STEP_BEHIND_EVERY == 0:
        state.say("The step costs you nothing.", LogKind.GOOD)
        return True, False

    return True, True


def _after_step(state: GameState, origin: Pos, direction: Direction) -> None:
    """Everything a step does that is not the step itself.

    Two gifts read the step and only the step: MOMENTUM loads on it, and THE
    HUNGRY ROAD writes on the ground it left behind. Both live here rather than
    being spelled out at the two places a step can land -- floor and stone --
    because a rule written twice is a rule that drifts.
    """
    if state.has_gift("momentum"):
        if state.momentum_direction is direction:
            state.momentum = min(state.momentum + 1, MOMENTUM_MAX)
        else:
            # A new line. The step that starts it is the first charge, so the
            # rule reads as "walk straight and it builds" rather than "walk
            # straight twice before anything happens".
            state.momentum = 1
            state.momentum_direction = direction
    _lay_trail(state, origin)


def _lay_trail(state: GameState, origin: Pos) -> None:
    """THE HUNGRY ROAD. Leave glass on the square the step began on.

    A trail rather than a minefield: only the last few squares hold, so what is
    behind the hero reads as a path they walked and not as a floor they salted.
    The length is the whole difference between a rule and a chore.
    """
    if not state.has_gift("hungry_road"):
        return
    trail = state.trail
    # Re-stamped rather than duplicated, so stepping back over your own line
    # moves it to the head of the trail instead of leaving a second entry.
    trail.pop(origin, None)
    trail[origin] = HUNGRY_ROAD_DAMAGE
    while len(trail) > HUNGRY_ROAD_TRAIL:
        trail.pop(next(iter(trail)))


def _spring_the_trail(state: GameState, actor: Actor) -> None:
    """Whatever walks onto the hero's glass pays for it.

    Only enemies: it is the hero's own rule, and a floor that cut the person who
    laid it would be a floor you could not retreat across.
    """
    if not state.trail:
        return
    damage = state.trail.pop(actor.position, None)
    if damage is None:
        return

    dealt = actor.stats.hurt(damage)
    state.hits.append(actor.position)
    state.say(f"The glass bites the {actor.name}. {dealt}.", LogKind.GOOD)
    if not actor.stats.alive:
        state.say(f"The {actor.name} comes apart on it.", LogKind.GOOD)
        _on_death(state, actor)
        _remove_corpse(state, actor)
        return
    inflict(state, actor, ("bleed",))


def _through_stone(
    state: GameState, target: Pos, direction: Direction
) -> tuple[bool, bool]:
    """Take a step into something solid, and pay for it.

    It can kill, like the bleed can, and for the same reason: a gift that cannot
    finish you has no floor, and the whole point of the hollow road is that it
    makes the wall a *decision*.
    """
    origin = state.player.position
    state.player.position = target
    state.player.steps += 1
    _after_step(state, origin, direction)
    state.player.stats.hp = max(0, state.player.stats.hp - HOLLOW_ROAD_COST)
    state.say(
        f"You push through the stone. {HOLLOW_ROAD_COST} of you stays in it.",
        LogKind.DAMAGE,
    )
    if state.player.hp <= 0:
        state.die("The stone takes the rest of you.")
        return True, True
    _bleed(state)
    _knit(state)
    return True, True


def _knit(state: GameState) -> None:
    """THE SLOW KNITTING. Walking, and only walking, closes a little.

    Called from the two places a step can land -- ordinary floor and stone --
    because a gift that only worked on one of them would be a gift with a
    footnote.
    """
    if not state.has_gift("slow_knitting"):
        return
    if state.player.steps % SLOW_KNITTING_EVERY:
        return
    if state.player.stats.heal(1):
        state.say("Something closes over. One back.", LogKind.GOOD)


def _bleed(state: GameState) -> None:
    """Lose a point of blood every so many steps, if cursed to.

    Cadenced on the run's step count rather than a counter of its own, so the
    drip is even across floors and a descent does not reset it.

    It can kill. A curse the player chose should be able to finish them, or it
    is not a price -- and the message says plainly what happened.
    """
    every = state.bleed_every
    if not every or state.player.steps % every:
        return
    if not state.player.alive:
        return

    state.player.stats.hp = max(0, state.player.stats.hp - 1)
    if state.player.hp <= 0:
        state.die("You bleed out between one step and the next.")
        return
    state.say("You are bleeding.", LogKind.DAMAGE)


def resolve_player_attack(
    state: GameState,
    target: Actor,
    *,
    force_crit: bool = False,
    crit_bonus: float = 0.0,
    bonus: int = 0,
    damage_scale: float = 1.0,
    wield: bool = True,
) -> AttackOutcome:
    """The hero's blow, with everything the dark has loaded into it.

    Public because the arena resolves the same blow the dungeon does: a fight
    that swung with its own dice would be a second opinion about what a gift or
    a curse is worth, and the player would be right to trust neither. Returns
    the outcome -- the arena says the number and shakes the frame with it, and
    cannot read either off the log without parsing its own prose.
    """
    # The patient knife only makes the *first* blow count double, so something
    # has to remember whether there has been one. The flag is cleared on every
    # descent, with the monsters it belonged to.
    first = not target.struck
    # The blade's own rule, though, is about the *fight* and not about the
    # monster: THE FIRST BLOW says "of a fight", and a room of three used to pay
    # its seven three times. A swing that misses spends nothing -- the flag is
    # set on a blow that lands.
    opening = not state.first_blow_spent
    # Only on a swing *with* the blade: a trick is not the weapon, and a trick
    # that inherited THE FIRST BLOW's seven was the sword casting the spell.
    bonus_flat = bonus + (_weapon_rule_bonus(state, opening) if wield else 0)
    # Three gifts load the blow itself. The charge and the debt are read here and
    # spent below, and only on a *landing* blow -- a swing that missed was not
    # the blow either of them was waiting for, which is the rule the patient
    # knife reads too.
    bonus = 0
    if state.has_gift("momentum"):
        bonus += state.momentum
    if state.has_gift("blood_debt"):
        bonus += state.blood_debt
    cornered = state.has_gift("last_breath") and state.cornered
    outcome = attack(
        state.player,
        target,
        state.rng,
        # The knife's own rule, and the arena's: a special asks for the crit it
        # paid for, and both of them are the same crit.
        force_crit=force_crit or (first and state.has_passive("patient_knife")),
        crit_bonus=crit_bonus,
        damage_scale=(2.0 if cornered else 1.0) * damage_scale,
        spread=state.damage_spread,
        bonus=bonus + bonus_flat,
    )

    if not outcome.hit:
        # A swing that missed was not a blow, so it does not spend the knife.
        # The grave ward is worded the same way and is read the same way -- only
        # a landing blow spends it -- and the two amulets disagreeing about what
        # "the first blow" means was a bug, not a rule.
        state.say(f"You swing at the {target.name} and miss.", LogKind.PLAIN)
        return outcome

    target.struck = True

    if state.has_gift("momentum"):
        state.momentum = 0
        state.momentum_direction = None
    if state.has_gift("blood_debt") and state.blood_debt:
        state.say(f"The debt comes due: {state.blood_debt} more.", LogKind.GOOD)
        state.blood_debt = 0

    if outcome.crit and state.has_passive("patient_knife") and first:
        state.say("It has been waiting for this one.", LogKind.GOOD)

    target.awake = True
    _enemy_takes_damage(state, target, outcome)
    if target.reflect_share:
        # THE UNBROKEN: half of every landed blow, straight back and through the
        # armour. It never swings; this is the whole of the exchange.
        back = max(1, round(outcome.damage * target.reflect_share))
        given = state.player.stats.reflect(back)
        if given:
            state.say(
                f"The {target.name} gives {given} of it back.", LogKind.BAD
            )
            if state.player.hp <= 0:
                state.die("What did not break gave it all back.")
                return outcome
    if state.has_draught("thin_veil"):
        # The veil was a promise about *looking*. The moment a blow lands, the
        # floor has seen where the hero is, and the bottle's work is done.
        state.floor_draughts.discard("thin_veil")
        state.say("The veil tears, and the floor finds you.", LogKind.BAD)
    if not outcome.killed and wield:
        # The blade's own statuses, plus the two gifts that add one. Built here
        # rather than on the weapon because a gift is a *rule about the player*,
        # not a property of the thing in their hand -- and the wound only opens
        # on the first blow, which is the same "first" the patient knife reads.
        #
        # And only on a swing *with the blade*: what the weapon does is a fact
        # about the weapon, and a trick is not the weapon. THE LEFT HAND carries
        # its own poison and the vein its own cut; a sword that bled on every
        # spell as well would be a sword that made the spells a delivery service.
        opening: tuple[str, ...] = _inflicts_of(state.player)
        if state.has_gift("ash_mark") or state.has_draught("kindled_breath"):
            # THE KINDLED BREATH is the ash mark in a bottle: every blow sets
            # it burning, for as long as the floor lasts.
            opening += ("burn",)
        if first and state.has_gift("open_wound"):
            opening += ("bleed",)
        inflict(state, target, opening, source=state.player)
        if outcome.crit and state.bleed_on_crit:
            # BLEEDING EDGE. A lucky blow opens a wound as deep as the bloodline
            # is: one stack, two, three -- the ceiling the wounds have. It used
            # to make the wound *last* longer, which was the same ladder told in
            # the other currency; the depth is the one a player can see, because
            # it is the number on the badge.
            inflict(
                state,
                target,
                ("bleed",),
                stacks=state.bleed_on_crit,
                source=state.player,
            )
        if state.pushback_chance and state.rng.chance(state.pushback_chance):
            # RING OF THE BELL. Walkyrion's blows throw what they land on --
            # the same shove the dead weight amulet buys, on a coin.
            _knock_back(state, target)
        if state.ember_chance and state.rng.chance(state.ember_chance):
            # EMBERHEART. Inferno's blows leave what they landed on alight --
            # the fire the kindled breath buys, on a coin rather than in a
            # bottle. A *blow* and not a trick, which is the rule the other two
            # bloodlines keep: what the hero swings is the weapon, and his
            # specials carry their own fire already.
            inflict(state, target, ("burn",))
    if wield and outcome.hit:
        state.first_blow_spent = True
        weapon = state.player.equipment.get("weapon")
        if weapon is not None and weapon.self_inflicts:
            # THE BLOOD PRICE: the blow costs the hand that swings it, on every
            # blow it *lands* -- the killing one included. It used to sit inside
            # "and it did not kill", which meant the blade was free exactly when
            # it mattered most.
            inflict(state, state.player, weapon.self_inflicts)
    if outcome.killed:
        _remove_corpse(state, target)
        return outcome
    if target.thorns:
        # THE BRIAR: what it grows, you take -- straight, because a thorn is not
        # a blow and armour has nothing to do with it.
        back = state.player.stats.reflect(target.thorns)
        if back:
            state.say(
                f"The {target.name} gives {back} of it back.", LogKind.BAD
            )
            if state.player.hp <= 0:
                state.die("The briar had the last of it.")

    if state.has_passive("dead_weight"):
        _knock_back(state, target)
    return outcome


def _knock_back(state: GameState, target: Actor) -> None:
    """Throw ``target`` one square further away, if there is anywhere to go.

    The one amulet that trades a stat for a rule, and the rule has to be worth the
    trade. It is not free damage -- it is a turn the monster spends walking back,
    which is the thing a slow hero needs more than anything.
    """
    away = direction_towards(state.player.position, target.position)
    landing = away.step(target.position)
    if not state.dungeon_map.is_walkable(landing):
        return
    if state.actor_at(landing) is not None:
        return
    target.position = landing
    state.say(f"The weight of it throws the {target.name} back.", LogKind.GOOD)


def _interact(state: GameState) -> ActionResult:
    """Do the one useful thing where the player is standing.

    Items are taken before the exit is used, and the order is the whole design:
    the generator never puts loot on the stairs, but if it ever did, walking onto
    the staircase and leaving the floor without the potion would be the game
    silently throwing something away on the player's behalf. Taking it first
    means ``enter`` is always safe to press.

    Costs no turn. Picking something up and going downstairs are not things the
    monsters should get to answer.
    """
    if state.dungeon_map.item_at(state.player.position) is not None:
        item = state.dungeon_map.item_at(state.player.position)
        assert item is not None
        if item.kind == "chest":
            # Not a refusal and not an action: the player has been asked to
            # decide, and the domain does not decide for them.
            return ActionResult(consumed_turn=False, acted=False, prompt=chest_prompt(item))
        return _pick_up(state)

    if state.at_the_spring:
        return _spring(state)

    if state.on_exit:
        return _try_descend(state)

    # After the exit, deliberately: standing on the stairs and next to somebody
    # should take you downstairs. The stairs are a decision the player has
    # already made by walking onto them.
    beside = state.npc_beside_player()
    if beside is not None:
        return _talk(state, beside)

    state.say("There is nothing here.", LogKind.PLAIN)
    return ActionResult(consumed_turn=False, acted=False)


def chest_prompt(chest: GroundItem) -> str:
    """What the dialog says about a chest: the price, and nothing else.

    The reward stays hidden until the lid is up. Showing both would turn daring
    into arithmetic -- and the player is meant to be weighing a cost against a
    hope, not comparing two numbers.
    """
    curse = curse_by_key(chest.curse)
    if curse is None:
        return "Whatever is inside is not free."
    return f"The price: {curse.price}."


def _talk(state: GameState, npc: Actor) -> ActionResult:
    """Somebody has something to say.

    One line per meeting, picked at random, because hearing the same sentence
    twice from the same person is the moment a person becomes furniture.
    """
    template = npc_by_key(npc.npc)
    if template is None:
        return ActionResult(consumed_turn=False, acted=False)

    # THE KINDNESS OF STRANGERS. The only thing down here that is not trying to
    # kill you gives you something, once: a person who handed out a draught every
    # time they were spoken to would be a well with a face on it.
    if state.has_gift("kindness") and npc.position not in state.helped:
        state.helped.add(npc.position)
        state.inventory.append(make_item(ITEMS["potion"]))
        state.say(
            f"{template.name} presses something into your hand. It is still warm.",
            LogKind.GOOD,
        )

    return ActionResult(
        consumed_turn=False,
        acted=False,
        prompt=state.rng.pick(template.lines),
        prompt_kind="npc",
        speaker=template.name,
    )


def spring_prompt(state: GameState) -> str:
    """What the spring says before it costs anything.

    Which curse comes off is the water's decision, not the player's, so the
    dialog says so -- and when there is only one curse there is nothing random
    about it, so it names it.
    """
    if len(state.curses) == 1:
        return (
            f"The water will take {state.curses[0].name} off you, "
            f"for {state.cleanse_cost} coins."
        )
    return (
        "The water will take one of your curses, whichever it chooses, "
        f"for {state.cleanse_cost} coins."
    )


def _spring(state: GameState) -> ActionResult:
    """Standing in the spring. Ask before it costs anything.

    Three answers and all three are said plainly: nothing to wash off, not
    enough coin, or the question. The middle one is stated rather than offered
    and then refused, because a dialog that ends in "you cannot afford this" is
    a dialog that wasted the player's time.
    """
    if not state.curses:
        state.say(
            "The water is clear and cold. There is nothing on you to wash off.",
            LogKind.PLAIN,
        )
        return ActionResult(consumed_turn=False, acted=False)

    if state.gold < state.cleanse_cost:
        state.say(
            f"The water would take a curse off you, for {state.cleanse_cost} "
            f"coins, and you have {state.gold}.",
            LogKind.PLAIN,
        )
        return ActionResult(consumed_turn=False, acted=False)

    return ActionResult(
        consumed_turn=False,
        acted=False,
        prompt=spring_prompt(state),
        prompt_kind="spring",
    )


def _cleanse(state: GameState) -> ActionResult:
    """Wash one curse off, chosen by the water.

    Only ever reached from the dialog, so there is no key that spends forty
    coins by accident. Costs no turn: being clean should not be something the
    monsters get to answer.
    """
    if not state.at_the_spring or not state.curses:
        return ActionResult(consumed_turn=False, acted=False)
    if state.gold < state.cleanse_cost:
        return ActionResult(consumed_turn=False, acted=False)

    curse = state.rng.pick(state.curses)
    state.gold -= state.cleanse_cost
    state.remove_curse(curse)

    # Spent. One wash per spring, so a curse becomes a decision about which
    # spring to spend rather than a standing offer you can walk back to -- and
    # the tile goes back to plain floor, which is what the map should show and
    # what makes ``enter`` on it say "there is nothing here" like anywhere else.
    state.dungeon_map.set_tile(state.player.position, Tile.FLOOR)

    state.say(
        f"The water closes over {curse.name} and takes it with it.",
        LogKind.GOOD,
    )
    state.say("The spring is spent, and the water goes still.", LogKind.PLAIN)
    return ActionResult(consumed_turn=False, acted=False)


def _the_lid_bites(state: GameState, chest) -> bool:
    """Whether that was a chest at all -- THE LID, and the fight starts now.

    A mimic is not a price, it is an encounter: the player asked for a reward and
    the reward had teeth. So it takes no curse, hands over no contents, and
    leaves nothing to read -- the lid is lifted and the thing is already in the
    room. The front end reads ``state.encounter`` the moment the answer is given,
    which is what makes the arena open on the same keypress that lifted it.
    """
    if not getattr(chest, "mimic", False):
        return False

    from .actors import ENEMIES, make_enemy, scale_template

    lid = make_enemy(scale_template(ENEMIES["lid"], state.depth), state.player.position)
    state.enemies.append(lid)
    # In the queue as well as in the room: a lid that is not in the queue can
    # never take a turn, so fleeing the ambush left it standing there forever.
    state.turn_queue.add(lid)
    state.encounter = lid
    state.say("The lid is a jaw, and it has been patient.", LogKind.BAD)
    return True


def _open_chest(state: GameState) -> ActionResult:
    """Prise open the chest underfoot: the reward, and the bill.

    Only ever reached from the dialog, so there is no key that opens a chest by
    accident -- walking onto one and pressing enter asks first.
    """
    chest = state.dungeon_map.item_at(state.player.position)
    if chest is None or chest.kind != "chest":
        return ActionResult(consumed_turn=False, acted=False)

    state.dungeon_map.remove_item(state.player.position)
    if _the_lid_bites(state, chest):
        # No curse and no contents: what was under the lid was the lid.
        return ActionResult(consumed_turn=False, acted=False)

    state.say("The lid gives, and something in the dark takes note.", LogKind.SYSTEM)

    curse = curse_by_key(chest.curse)
    if curse is not None and any(c.key == curse.key for c in state.curses):
        # Already paid. Only reachable when a wraith's touch landed this same
        # curse between the floor being drawn and this lid being lifted, which
        # is why the generator's guarantee is not enough on its own. The reward
        # is still handed over: a chest that refused would be a piece of loot
        # the player can see and never have.
        state.say(
            "You have paid this price already. The lid takes no more.",
            LogKind.PLAIN,
        )
    elif curse is not None:
        state.add_curse(curse)

    if chest.gift is not None:
        state.gifts.add(chest.gift)
        gift = gift_by_key(chest.gift)
        if gift is not None:
            state.say(f"{gift.name}: {gift.blurb}.", LogKind.GOOD)
    elif chest.contents is not None:
        _equip(state, chest.contents)

    # A turn, like a draught, and for the same reason: this is the moment the
    # bargain lands. It was free, which made the riskiest thing in the game --
    # a permanent curse, read and agreed to -- the only one a monster had no
    # answer to.
    state.turn += 1
    state.total_turns += 1
    advance_world(state)
    state.refresh_vision()
    return _outcome(state, consumed_turn=True, acted=True)


def _snapshot(state: GameState) -> dict:
    """The run as it is, deeply, for the borrowed hour to give back.

    A copy of every field rather than a reference to the state: the point is to
    put the run back the way it *was*, and a reference to something mutable is a
    record of where it went rather than of where it started.

    One memo across every field, which is not a detail: the turn queue holds
    the very same objects the ``player`` and ``enemies`` fields hold, and
    separate ``deepcopy`` calls would hand the snapshot a queue full of
    strangers the restored ``player`` has never met -- a phantom who keeps
    taking turns, never visibly moves, and cannot be removed when it dies. The
    save code warns of the same trap in its own docstring and solves it the
    same way.
    """
    memo: dict = {}
    return {
        f.name: copy.deepcopy(getattr(state, f.name), memo)
        for f in fields(state)
        if f.name != "snapshot"
    }


def _restore(state: GameState, snapshot: dict) -> None:
    """Put the run back, in place.

    In place because everything that holds a run holds *this* object -- the
    screen, the save, the tests -- and handing back a different one would mean
    every caller had to notice.

    One memo per restore, for the same reason the snapshot takes one: the queue
    and the actors have to come back as each other's, not as near misses that
    happen to share every attribute.
    """
    memo: dict = {}
    for name, value in snapshot.items():
        setattr(state, name, copy.deepcopy(value, memo))


def _rewind(state: GameState) -> ActionResult:
    """Take back the last thing that happened.

    The one verb that works after the run is over, because undoing a death is
    the whole of what the gift is for: the hour is borrowed against the mistake
    there is no other way to unmake.

    It costs no turn -- there is nothing left to give back but the action itself
    -- and it is spent whether or not the action it undoes was a good one.
    """
    if not state.rewind_ready or state.snapshot is None:
        return ActionResult(consumed_turn=False, acted=False)

    _restore(state, state.snapshot)
    # Set *after* the restore, which would otherwise put the old flags back.
    state.rewind_ready = False
    state.snapshot = None
    state.say(
        "The hour is given back. What you did, you did not do.",
        LogKind.GOOD,
    )
    return _outcome(state, consumed_turn=False, acted=True)


def ultimate_refusal(state: GameState) -> str | None:
    """Why the dark will not answer, or ``None`` when it will.

    The two gates in one place, because the arena offers the same ask the
    dungeon does: a level the hero has not reached and a floor the dark has
    already had are refusals in a fight exactly as they are on the map, and the
    words for them should not have to be written twice to stay the same words.
    """
    if state.level < state.ultimate_level:
        return f"Not yet. The dark answers at level {state.ultimate_level}."
    if not state.ultimate_available:
        return "The dark has already had this floor. It does not ask twice."
    return None


def _ultimate(state: GameState) -> ActionResult:
    """The hero's own ask, once a floor, from the level the dark answers at.

    One gate for all three, then one shape each. Kept as a dispatcher rather
    than three verbs so the key, the gate, the once-a-floor rule and the
    sidebar's promise have exactly one place to be true.
    """
    refusal = ultimate_refusal(state)
    if refusal is not None:
        state.say(refusal, LogKind.PLAIN)
        return ActionResult(consumed_turn=False, acted=False)

    builders = {
        "noxx": _summon_void,
        "yeti": _build_fortress,
        "walkyrion": _shatter_bell,
        "inferno": _ravaging_fire,
    }
    build = builders.get(state.hero.key)
    if build is None:
        # A hero the dark has nothing for. The key does nothing at all, and
        # says nothing: an unanswerable offer is worse than silence.
        return ActionResult(consumed_turn=False, acted=False)
    return build(state)


def _summon_void(state: GameState) -> ActionResult:
    """Noxx gives into the void. Once a floor, from a level, and his alone.

    What the promise pays with, in order: a shadow with a name, the whole
    floor laid open, and a drop of the summoner's own blood on every second
    beat of the shadow's stay -- never the last drop. And what the shadow
    kills feeds the summoner back one heart each: the price is what makes the
    group worth wading into, and the feeding is what makes it a trade rather
    than a tax.
    """
    spot = _ultimate_spot(state)
    if spot is None:
        # Nowhere for the dark to stand is a corner case a cast cannot live
        # through: rather than spend the ask and smother the shadow, refuse.
        state.say("The dark has nowhere to stand here.", LogKind.PLAIN)
        return ActionResult(consumed_turn=False, acted=False)

    state.ultimate_available = False
    state.atritas = make_atritas(spot, state.level, state.depth)
    state.atritas_turns_left = ATRITAS_TURNS

    # THE SIGHT. The whole floor, through the walls -- and only for as long as
    # the shadow walks. Written as a flag rather than into ``explored``: the
    # dark showing Noxx everything it owns is not the same as Noxx having been
    # there, and a floor he leaves with the shadow's eyes should close back
    # over what he never saw for himself.
    state.void_sight = True
    state.say("You call on your friends, and they come.", LogKind.BAD)
    state.say("Atritas rises from your dark and looks around.", LogKind.SYSTEM)
    state.say(
        "Every wall is glass -- for as long as he walks.",
        LogKind.GOOD,
    )
    return _spend_the_turn(state)


def _build_fortress(state: GameState) -> ActionResult:
    """Yeti raises the Frozen Fortress: a wall of ice with twice his blood in
    it, which everything on the floor would rather bite than him.

    The wall is the whole of it. The sight it used to cost was a second price
    only one hero paid; the ask is paid out of the purse now, like every other.
    """
    spot = _ultimate_spot(state)
    if spot is None:
        state.say("There is no room here to raise a wall.", LogKind.PLAIN)
        return ActionResult(consumed_turn=False, acted=False)

    state.ultimate_available = False
    # Twice what Yeti has: the wall only soaks, and a wall that breaks before
    # the floor has spent its teeth is a wall that never got to be one.
    health = max(1, state.player.stats.hp * 2)
    state.fortress = make_fortress(spot, health)
    state.fortress_turns_left = FORTRESS_TURNS

    state.say("You build the Frozen Fortress.", LogKind.GOOD)
    state.say(
        "The cold rises to your waist, and everything that was hunting you "
        "turns its head.",
        LogKind.SYSTEM,
    )
    return _spend_the_turn(state)


def _shatter_bell(state: GameState) -> ActionResult:
    """Walkyrion drives his blade into the floor and rings the golden bell.

    Three paces of ground answer: the walls come down -- plain floor, not
    rubble, because the promise was a clearing and rubble is a fence -- and
    everything hostile standing there is thrown off its feet and cut. Not the
    heaviest blow in the game; the shadow holds that record. This one is a
    room, not a duel.
    """
    hero = state.player
    here = hero.position
    broken = 0
    struck: list[str] = []

    for x in range(here[0] - BELL_RADIUS, here[0] + BELL_RADIUS + 1):
        for y in range(here[1] - BELL_RADIUS, here[1] + BELL_RADIUS + 1):
            pos = (x, y)
            if chebyshev(here, pos) > BELL_RADIUS:
                continue
            if not state.dungeon_map.in_bounds(pos):
                continue
            if state.dungeon_map.tile_at(pos) is Tile.WALL:
                if _is_outer_wall(state, pos):
                    # The map's own edge stays: a wall that fell there would
                    # open the dungeon onto nothing.
                    continue
                state.dungeon_map.set_tile(pos, Tile.FLOOR)
                broken += 1

    state.ultimate_available = False
    state.say("You shatter the golden bell.", LogKind.GOOD)
    state.say("The note goes down through the floor.", LogKind.SYSTEM)

    for enemy in list(state.living_enemies):
        if chebyshev(here, enemy.position) > BELL_RADIUS:
            continue
        roll = enemy.stats.hurt(hero.damage_roll(state.rng))
        state.hits.append(enemy.position)
        struck.append(f"{enemy.name} ({roll})")
        if not enemy.stats.alive:
            state.say(f"The {enemy.name} comes apart on the note.", LogKind.COMBAT)
            _on_death(state, enemy)
            _remove_corpse(state, enemy)
            continue
        # Off its feet: two paces away from the hero, or as far as the room
        # allows. The wall it lands against is its own problem.
        _knock_back(state, enemy)
        _knock_back(state, enemy)

    if broken:
        state.say(f"{broken} walls come down around you.", LogKind.GOOD)
    if struck:
        state.say("The note finds: " + ", ".join(struck) + ".", LogKind.COMBAT)
    elif not broken:
        state.say("The note finds nothing to break.", LogKind.PLAIN)
    return _spend_the_turn(state)


def _ravaging_fire(state: GameState) -> ActionResult:
    """Inferno sets the floor alight with everything he has left.

    The only ask in the game that *takes* rather than gives. There is nothing to
    walk to and nothing to hit: the floor itself burns, and for as long as it
    does, two things are true of it.

    Every fight on it starts with everything in it already on fire -- not the
    monsters standing there *now*, which would make this a bomb, but every one
    of them that ever reaches him, which is what a fire on a floor actually is.

    The three-point purse it used to cost is gone with the other three prices:
    the ask is paid in the same five points every hero pays now, and this one
    keeps its fire -- the floor burns because that is what he *bought*.
    """
    state.ravaging = True
    state.ultimate_available = False
    state.say("You put everything you have into the floor.", LogKind.SYSTEM)
    state.say("It catches, and it keeps catching.", LogKind.GOOD)
    return _spend_the_turn(state)


def _spend_the_turn(state: GameState) -> ActionResult:
    """The tail every ultimate shares: the price, the beat, the answering world.

    The price is the same for all four, and it is the only one they have now:
    the purse holds five points for the rest of the run. It used to be four
    different prices -- a slow bleed, a narrowed sight, a burning floor that
    bankrupted one hero in particular -- which meant four rules to learn and one
    hero paying in a currency the others never touched.

    Paid *here* and not over the turns that follow: a cap the hero has to walk
    around while holding more would be a cap that never bit.
    """
    state.sacrificed = True
    state.kill_points = min(state.kill_points, state.kill_points_max)
    state.turn += 1
    state.total_turns += 1
    advance_world(state)
    state.refresh_vision()
    return _outcome(state, consumed_turn=True, acted=True)


def _is_outer_wall(state: GameState, pos: Pos) -> bool:
    """Whether ``pos`` is on the dungeon's own edge, which nothing may break."""
    x, y = pos
    return (
        x <= 0
        or y <= 0
        or x >= state.dungeon_map.width - 1
        or y >= state.dungeon_map.height - 1
    )


def _ultimate_spot(state: GameState) -> Pos | None:
    """Where a summoned thing stands when it arrives.

    Beside the hero first -- the promise is a thing that happens *next to
    you*, and both asks read better the closer they land. If everything
    adjacent is taken (an enemy in the way, a wall), one pace further, and so
    on out; a summon that refused because the hero stood in a doorway would be
    a summon the dungeon could veto.
    """
    for distance in (1, 2, 3, 4):
        for direction in DIRECTIONS:
            x, y = state.player.position
            steps = 0
            pos = (x, y)
            while steps < distance:
                pos = direction.step(pos)
                steps += 1
            if not state.dungeon_map.in_bounds(pos):
                continue
            if not state.dungeon_map.is_walkable(pos):
                continue
            if state.actor_at(pos) is not None:
                continue
            return pos
    return None


def _advance_atritas(
    state: GameState, swing_every: int = ATRITAS_SWING_EVERY
) -> Actor | None:
    """One beat of the shadow's life. Called from ``advance_world``, which is
    why it is in turns and not in seconds: the monsters it kills live in turns,
    and a shadow on a different clock from its prey would be a shadow nothing
    could ever reach.

    Every swing aims at what stands close to Noxx -- the promise was that it
    attacks *around* him. The price of the ask is not here any more: it is the
    purse, paid once when the ultimate is used, and it is the same for all four.

    ``swing_every`` is the cadence, and the arena passes one: a fight is five to
    nine rounds while the stay is forty turns, so the floor's every-sixth beat
    would have the shadow stand in the room and swing at nothing. Returns the
    monster he went for, or ``None`` when this beat was not a swing -- the arena
    paints that, and the floor has nothing to paint.
    """
    atritas = state.atritas
    if atritas is None or state.over:
        return

    hero = state.player
    age = ATRITAS_TURNS - state.atritas_turns_left

    # THE ASSISTANCE.
    struck: Actor | None = None
    if swing_every <= 1 or age % swing_every == 3:
        target = _shadow_prey(state, atritas)
        if target is not None:
            # THE BLINK. The dark does not walk to its prey -- it is simply
            # found there, one free square beside it, so the summoner sees
            # the shadow arrive where it strikes and never wonders whether
            # it worked.
            _place_beside(state, atritas, target)
            struck = target
            outcome = attack(atritas, target, state.rng, spread=state.damage_spread)
            if outcome.hit:
                state.hits.append(target.position)
                if outcome.killed:
                    state.say(
                        f"Atritas tears the {target.name} apart for "
                        f"{outcome.damage}!",
                        LogKind.CRIT if outcome.crit else LogKind.COMBAT,
                    )
                    _on_death(state, target)
                    _remove_corpse(state, target)
                    # The feeding. Every kill the shadow makes hands the
                    # summoner one heart back, which is what makes wading
                    # into a group a trade instead of a tax.
                    healed = state.player.stats.heal(ATRITAS_KILL_HEAL)
                    if healed:
                        state.say("The dark gives one back.", LogKind.GOOD)
                else:
                    state.say(
                        f"Atritas wounds the {target.name} for {outcome.damage}.",
                        LogKind.CRIT if outcome.crit else LogKind.COMBAT,
                    )
            else:
                state.say(
                    f"Atritas swings at the {target.name} and misses.",
                    LogKind.PLAIN,
                )
        else:
            # No prey by Noxx: the shadow keeps to his side.
            if chebyshev(atritas.position, hero.position) > 2:
                step = direction_towards(atritas.position, hero.position)
                landing = step.step(atritas.position)
                if state.dungeon_map.is_walkable(landing) and state.actor_at(landing) is None:
                    atritas.position = landing

    state.atritas_turns_left -= 1
    if state.atritas_turns_left <= 0:
        state.atritas = None
        state.void_sight = False
        state.say(
            "Atritas sinks back into your dark. The walls close over "
            "everything you never saw.",
            LogKind.SYSTEM,
        )
    return struck


def _advance_fortress(state: GameState) -> None:
    """One beat of the fortress's stay. The wall is not a fighter -- it does
    nothing but stand there and be worth biting -- so this is only the clock
    and, at the end, the thaw."""
    fortress = state.fortress
    if fortress is None or state.over:
        return
    if not fortress.alive:
        # Broken by teeth rather than by time. The enemies' blows set
        # ``alive`` false; the message belongs to whoever landed the last one,
        # which is the enemy turn, so this only cleans up.
        _melt_fortress(state)
        return
    state.fortress_turns_left -= 1
    if state.fortress_turns_left <= 0:
        _melt_fortress(state)
        state.say(
            "The Frozen Fortress thaws to slush, and the cold lets go of "
            "your eyes.",
            LogKind.SYSTEM,
        )


def _melt_fortress(state: GameState) -> None:
    state.fortress = None
    state.fortress_turns_left = 0
    state.sight_penalty = 0


def _shadow_prey(state: GameState, atritas: Actor) -> Actor | None:
    """What the shadow goes for next.

    First anything within its hunt radius of where it *stands* -- seek and
    destroy, prey to prey, across the floor. Failing that, anything within the
    guard radius of its summoner, so it never abandons the hero it belongs to
    just because the room it left had nothing in it.
    """
    prey = _nearest_enemy(state, atritas.position, ATRITAS_HUNT_RADIUS)
    if prey is not None:
        return prey
    return _nearest_enemy(state, state.player.position, ATRITAS_RADIUS)


def _nearest_enemy(state: GameState, centre: Pos, radius: int) -> Actor | None:
    best: Actor | None = None
    best_distance = radius + 1
    for enemy in state.living_enemies:
        distance = chebyshev(centre, enemy.position)
        if distance <= radius and distance < best_distance:
            best = enemy
            best_distance = distance
    return best


def _place_beside(state: GameState, atritas: Actor, target: Actor) -> None:
    """Put the shadow on a free square beside its prey, before it strikes.

    Beside, never on: the prey's own square is occupied, and so is every
    square an actor holds. If the prey is packed in on all eight sides the
    shadow stays where it is and strikes through anyway -- the blink is for
    seeing, and seeing can fail without breaking the swing.
    """
    options = []
    for direction in DIRECTIONS:
        landing = direction.step(target.position)
        if landing == state.player.position:
            continue
        if not state.dungeon_map.is_walkable(landing):
            continue
        if state.actor_at(landing) is not None:
            continue
        options.append(landing)
    if not options:
        return
    # The square closest to the summoner, so the shadow keeps to his side of
    # its prey when there is a choice.
    atritas.position = min(
        options, key=lambda pos: chebyshev(pos, state.player.position)
    )


def _take_fame(state: GameState) -> ActionResult:
    """Take the curse, and the promise with it.

    The third answer to a chest, and the only one that trades *now* for *later*:
    the price is paid and the thing inside is *lost* -- the chest goes with it --
    and what the player gets instead is a bigger number at the end of the run.
    The score is the board and the board is the only fame there is, which is the
    joke.

    There is no ceiling on it and there does not need to be one -- a chest is
    only ever placed for a curse the player has not already paid, so the
    thirteen curses are the ceiling. Taking all thirteen is nearly a death
    sentence, and that is the shape the wager should have.
    """
    chest = state.dungeon_map.item_at(state.player.position)
    if chest is None or chest.kind != "chest":
        return ActionResult(consumed_turn=False, acted=False)

    state.dungeon_map.remove_item(state.player.position)
    if _the_lid_bites(state, chest):
        # The wager opens the lid too, and the lid does not care what was
        # wagered: the same jaw, and no curse, because there was never a price.
        return ActionResult(consumed_turn=False, acted=False)

    curse = curse_by_key(chest.curse)
    new_price = curse is not None and not any(
        c.key == curse.key for c in state.curses
    )
    if new_price:
        state.add_curse(curse)
    else:
        # A price the wraith already charged is not fame in the bank: the
        # wager pays out for courage, and this player is not paying. The
        # old version read +1 fame on the shared multiplier either way.
        state.say(
            "The price was already paid, elsewhere. This wager pays nothing.",
            LogKind.PLAIN,
        )

    if new_price:
        state.fame += 1
        state.say(
            "You take the curse and leave the blade where it lies. "
            "The dark will remember your name.",
            LogKind.GOOD,
        )
        state.say(
            f"FAME {state.fame}: this run is worth "
            f"{state.score_multiplier:.2f}x.",
            LogKind.GOOD,
        )

    # A turn, like opening it. The bargain lands either way.
    state.turn += 1
    state.total_turns += 1
    advance_world(state)
    state.refresh_vision()
    return _outcome(state, consumed_turn=True, acted=True)


def _pick_up(state: GameState) -> ActionResult:
    item = state.dungeon_map.item_at(state.player.position)
    if item is None:
        state.say("There is nothing here to take.", LogKind.PLAIN)
        return ActionResult(consumed_turn=False, acted=False)

    if item.kind == "chest":
        # It is furniture, not loot. Without this the whole chest -- contents
        # and all -- went into the pack, and the curse went with it unread.
        state.say("It is not going anywhere. It has to be opened.", LogKind.PLAIN)
        return ActionResult(consumed_turn=False, acted=False)

    if (
        item.slot is None
        and item.kind not in ("coin", "page")
        and len(state.inventory) >= state.pack_capacity
    ):
        # A full pack is a full pack: the thing stays where it lies, and the
        # shop is where the room comes from. Checked before the item is taken
        # off the floor, so a refusal does not eat it.
        state.say(
            f"The pack is full: {state.pack_capacity} slots, and the shop "
            f"sells more.",
            LogKind.PLAIN,
        )
        # Refused, and said so out loud: the item did not move, and a player
        # looking at the map rather than the log needs to hear that.
        return ActionResult(consumed_turn=False, acted=False, denied=True)

    state.dungeon_map.remove_item(state.player.position)

    if item.kind == "page":
        # Off the floor and into the book. Free, like everything else that is
        # picked up, and drawn down from what is still missing so the same page
        # cannot turn up twice.
        state.found_pages.append(item.page)
        state.missing_pages.discard(item.page)
        state.say(
            f"A torn page: {numeral(item.page)} of the chronicle.",
            LogKind.GOOD,
        )
        return ActionResult(consumed_turn=False, acted=False)

    if item.kind == "coin":
        state.gold += item.gold
        state.say(f"You pocket {item.gold} coins.", LogKind.COIN)
        return ActionResult(consumed_turn=False, acted=False)

    if item.slot:
        _equip(state, item)
    else:
        state.inventory.append(item)
        state.say(f"You pick up {_the(item.name)}.", LogKind.GOOD)
    return ActionResult(consumed_turn=False, acted=False)


def _set_down(state: GameState, item: GroundItem) -> bool:
    """Lay ``item`` on a free tile beside the player. Returns whether it fitted.

    Beside, not under. An item beneath your feet is one you pick up again the
    next time you press enter, which turns swapping equipment into a loop that
    never lets ``enter`` reach the stairs -- and it is also the square the
    player has to stand on to leave. Swapping stays reversible, it just costs a
    step: walk onto what you set down and take it back.
    """
    for direction in DIRECTIONS:
        pos = direction.step(state.player.position)
        if not state.dungeon_map.is_walkable(pos):
            continue
        if state.actor_at(pos) is not None:
            continue
        if state.dungeon_map.item_at(pos) is not None:
            continue
        state.dungeon_map.add_item(pos, item)
        return True
    return False


def _equip(state: GameState, item: GroundItem) -> None:
    """Wear ``item``, setting whatever it replaces down beside the player.

    Setting down rather than discarding is what makes trying something on free:
    what you took off is still on the floor, so nothing a player finds can be
    lost by picking it up. That is the only reason auto-equipping is safe --
    there is no comparison dialog, so there has to be an undo.
    """
    player = state.player
    previous = player.equipment.get(item.slot)
    player.equipment[item.slot] = item

    changes = ", ".join(item.modifiers.describe())
    detail = f" ({changes})" if changes else ""

    if previous is None:
        state.say(f"You take up {_the(item.name)}{detail}.", LogKind.GOOD)
        return

    if _set_down(state, previous):
        state.say(
            f"You take up {_the(item.name)}{detail} and set down "
            f"{_the(previous.name)}.",
            LogKind.GOOD,
        )
        return

    # Boxed in on every side. Rare, and the item is not thrown away for it.
    state.dungeon_map.add_item(player.position, previous)
    state.say(
        f"You take up {_the(item.name)}{detail}; {_the(previous.name)} falls at "
        f"your feet.",
        LogKind.GOOD,
    )


def _inventory(state: GameState) -> ActionResult:
    """Report what is being carried. Costs nothing -- it is only a look."""
    if not state.inventory:
        state.say("You carry nothing.", LogKind.PLAIN)
        return ActionResult(consumed_turn=False, acted=False)

    counts: dict[str, int] = {}
    for item in state.inventory:
        counts[item.name] = counts.get(item.name, 0) + 1
    carried = ", ".join(f"{count}x {name}" for name, count in sorted(counts.items()))
    state.say(f"You carry {carried}.", LogKind.PLAIN)
    return ActionResult(consumed_turn=False, acted=False)


def _quaff(state: GameState) -> ActionResult:
    """Drink the cheapest draught that covers the wound.

    Picking the smallest one that still heals in full is the choice a careful
    player would make anyway: drinking the elixir at 24/26 health throws away
    sixteen points of it. Handing that decision to the player is a real decision,
    but it is also one a new player gets wrong once and then never again, so the
    game makes the obvious play and charges a turn for it.
    """
    if state.draughts_forbidden:
        state.say(
            "Your mouth is closed to it. Nothing you drink stays down.",
            LogKind.BAD,
        )
        return ActionResult(consumed_turn=False, acted=False)

    if not state.inventory:
        state.say("You have nothing to drink.", LogKind.PLAIN)
        return ActionResult(consumed_turn=False, acted=False)

    player = state.player
    missing = player.max_hp - player.stats.hp
    if missing <= 0:
        state.say("You are unhurt.", LogKind.PLAIN)
        return ActionResult(consumed_turn=False, acted=False)

    # Spend the smallest draught that does the job without overflowing; if none
    # can, spend the smallest one anyway and accept the spill. Either way the
    # good draught is saved for a wound that needs it.
    #
    # Only the ones that *heal*: the strange draughts are drunk from the pack by
    # name, and a mouthful that mends nothing would have been swallowed here
    # whenever the wounds were small.
    healing = [item for item in state.inventory if item.heal > 0]
    if not healing:
        state.say("Nothing in the pack heals.", LogKind.PLAIN)
        return ActionResult(consumed_turn=False, acted=False)

    affordable = [item for item in healing if item.heal <= missing]
    item = (
        max(affordable, key=lambda i: i.heal)
        if affordable
        else min(healing, key=lambda i: i.heal)
    )

    _swallow(state, item)
    _after_a_draught(state)
    return _outcome(state, consumed_turn=True, acted=True)


def _swallow(state: GameState, item) -> int:
    """One bottle, out of the pack and down: what it mends, and what spills.

    The whole of a draught that heals, in one place, because there are two ways
    to drink one -- the quick key and the pack's own list -- and the second used
    to skip the second mouth, the mirror and the turn.
    """
    player = state.player
    state.inventory.remove(item)
    amount = max(1, round(item.heal * state.heal_scale))
    healed = player.stats.heal(amount)
    state.say(f"You drink the {item.name} and recover {healed}.", LogKind.GOOD)
    if amount < item.heal:
        state.say(
            "It should have been more. The curse takes its share.",
            LogKind.BAD,
        )
    elif healed < amount:
        spare = amount - healed
        if state.has_passive("second_mouth"):
            # Armour for this floor only. Carrying it down would make one drink
            # on floor two worth something on floor nine.
            cap = second_mouth_cap(state.depth)
            kept = min(cap, player.stored_armor + spare) - player.stored_armor
            player.stored_armor += kept
            if kept:
                state.say(
                    f"The second mouth keeps what spills: {kept} armour.",
                    LogKind.GOOD,
                )
        else:
            state.say(
                f"Its power spills past the wound; {spare} is lost.",
                LogKind.PLAIN,
            )
    return healed


def _after_a_draught(state: GameState) -> None:
    """What answers a swallowed bottle, and the turn it costs.

    Drinking takes a turn, so it is not a free action in the middle of a fight
    and monsters get their answer -- the *floor's* answer, which is the right one
    when the floor is where the drinking happened. In the arena the answer is the
    room's own queue and the turn is the arena's to spend, so the dungeon's clock
    is left alone: ticking it here as well counted one mouthful twice in the run's
    own turn count, and ran the floor's phase in the middle of a fight.
    """
    if state.has_wild("mirror_of_hunger"):
        _wake_something(state)

    if state.has_gift("nothing_wasted"):
        _shatter(state)

    if not state.in_fight:
        state.turn += 1
        state.total_turns += 1
        advance_world(state)
        state.refresh_vision()


def _shatter(state: GameState) -> None:
    """NOTHING WASTED. The empty glass goes into whatever is beside you.

    Only the enemies standing next to the drink: it is a small rule about where
    you choose to be thirsty, not a second weapon.
    """
    for direction in DIRECTIONS:
        enemy = state.actor_at(direction.step(state.player.position))
        if enemy is None or enemy.kind is not ActorKind.ENEMY or not enemy.alive:
            continue
        dealt = enemy.stats.hurt(NOTHING_WASTED_DAMAGE)
        state.hits.append(enemy.position)
        state.say(f"The glass goes into the {enemy.name}. {dealt}.", LogKind.GOOD)
        if not enemy.stats.alive:
            state.say(f"The {enemy.name} comes apart on it.", LogKind.GOOD)
            _on_death(state, enemy)
            _remove_corpse(state, enemy)


def _wake_something(state: GameState) -> None:
    """Put a monster beside the player, if there is anywhere to put one.

    The mirror of hunger. It does not appear on the far side of the floor and
    walk over -- it is already there, and it was waiting for you to be thirsty.
    """
    spots = [
        direction.step(state.player.position)
        for direction in DIRECTIONS
    ]
    free = [
        pos
        for pos in spots
        if state.dungeon_map.is_walkable(pos) and state.actor_at(pos) is None
    ]
    if not free:
        return

    enemy = make_enemy(
        pick_enemy_template(state.rng, state.depth), state.rng.pick(free)
    )
    state.enemies.append(enemy)
    state.turn_queue.add(enemy)
    state.say("Something drinks with you, and it was already here.", LogKind.BAD)


def _try_descend(state: GameState) -> ActionResult:
    if not state.on_exit:
        # On the last floor there are no stairs at all, and "no stairs here"
        # next to a glowing rift would read as a bug.
        if state.dungeon_map.find_tile(Tile.RIFT):
            state.say("There is nothing here to take you out.", LogKind.PLAIN)
        else:
            state.say("There are no stairs here.", LogKind.PLAIN)
        return ActionResult(consumed_turn=False, acted=False)

    if state.at_the_rift:
        state.escape()
        return _outcome(state, consumed_turn=False, acted=False)

    state.floors_cleared += 1
    state.build_floor(state.depth + 1)
    # A floor is a new purse. The points do not trickle back between fights --
    # that is what makes spending them a decision -- but walking into a floor
    # empty-handed and staying empty-handed is not a decision, it is a corner.
    state.kill_points = state.kill_points_max

    if state.toll_per_floor:
        # After the descent, so it reads as the price of the floor rather than
        # as something that happened on the last one. It can empty the purse but
        # not go below it: a debt the run cannot pay is not a toll.
        paid = min(state.toll_per_floor, state.gold)
        state.gold -= paid
        state.say(f"The dark takes its toll: {paid} coins.", LogKind.BAD)

    return _outcome(state, consumed_turn=False, acted=False)


#: How far a blow reaches with THE LONG REACH, in squares. Two, because one is
#: already every blow -- and the number is written down here rather than inlined
#: so the gift's blurb and the rule cannot drift apart.
LONG_REACH = 2

#: Every how many steps THE STEP BEHIND gives away.
STEP_BEHIND_EVERY = 5

#: Every how many steps THE SLOW KNITTING closes one point of.
#:
#: Twenty rather than five. It is not a heal, it is a floor you can afford to
#: walk: a hundred steps of it is five health, which is a potion, and the price
#: is the turns -- the same currency the score is in. A gift that healed faster
#: than that would make the draughts pointless and the run patient instead of
#: careful.
SLOW_KNITTING_EVERY = 20

#: What THE HOLLOW ROAD charges for a square of stone.
HOLLOW_ROAD_COST = 2

#: The ceiling on MOMENTUM: how many straight steps it can hold, and therefore
#: how much a blow can carry. Five, because a run down a corridor is about that
#: long before a doorway makes it a decision again.
MOMENTUM_MAX = 5

#: How many waits in a row close THE SALT CIRCLE.
SALT_CIRCLE_WAITS = 3

#: What THE LAST BREATH is worth to the enemy's aim: two points of evasion,
#: which is twenty points off their hit chance, while the hero is cornered.
LAST_BREATH_EVASION = 2

#: What a square of THE HUNGRY ROAD costs whatever walks onto it, and how many
#: squares of it a hero leaves behind at once.
#:
#: A trail rather than a minefield: the length is what makes it read as a path
#: walked rather than a floor salted, and it is also what keeps the rule from
#: turning a whole room into a trap the player set once and forgot.
HUNGRY_ROAD_DAMAGE = 5
HUNGRY_ROAD_TRAIL = 10

#: How much longer a crit's wound bleeds per BLEEDING EDGE stack, in the
#: victim's turns.
#: How deep a wound can be cut: the ceiling a second blade, a bloodline or a
#: trick with the word "three" in it can reach. Three is a wound that is a
#: problem without being a sentence.
STACK_LIMIT = 3

#: What NOTHING WASTED puts into everything beside the drinker.
NOTHING_WASTED_DAMAGE = 4

#: Public wrapper so the UI can trigger a descent without importing internals.
def descend(state: GameState) -> ActionResult:
    """Try to go down a level from wherever the player stands."""
    return _try_descend(state)


#: Public wrappers for the pack: the two things a player can do with a thing
#: they are carrying, by name, from the pack screen. The screen picks; the
#: engine decides what the pick means.
def drink(state: GameState, item_id: str) -> str:
    """Drink one named draught out of the pack. Returns the line to show.

    Healing draughts mend; the strange ones lay a rule on the floor. Either
    way the bottle is gone, and either way it is the *player's* choice which
    one -- `q` still drinks the cheapest that covers the wound, because that
    decision is the one nobody wants to make twice.
    """
    item = next((i for i in state.inventory if i.item_id == item_id), None)
    if item is None:
        return "There is none of that in the pack."
    if state.draughts_forbidden:
        return "Your mouth is closed to it. Nothing you drink stays down."

    template = ITEMS.get(item.item_id)

    if template is not None and template.draught:
        state.inventory.remove(item)
        draught = draught_by_key(template.draught)
        state.floor_draughts.add(template.draught)
        _after_a_draught(state)
        if draught is not None:
            state.say(
                f"You drink {_the(item.name)}. {draught.blurb.capitalize()} -- "
                f"until you leave this floor.",
                LogKind.GOOD,
            )
            return f"{draught.name}: {draught.blurb}."
        return f"You drink the {item.name}."

    healed = _swallow(state, item)
    _after_a_draught(state)
    return f"You drink {_the(item.name)} and recover {healed}."


def drop(state: GameState, item_id: str) -> str:
    """Set one named thing out of the pack onto the floor beside the hero.

    Beside, not underfoot: an item beneath the player is one they pick up again
    the next time they press enter, which is a loop, not a discard.
    """
    item = next((i for i in state.inventory if i.item_id == item_id), None)
    if item is None:
        return "There is none of that in the pack."
    if not _set_down(state, item):
        return "There is nowhere to put it down."
    state.inventory.remove(item)
    state.say(f"You set down {_the(item.name)}.", LogKind.PLAIN)
    return f"You set down {_the(item.name)}."


# -- enemy turns -----------------------------------------------------------


def take_turn(state: GameState, actor: Actor) -> bool:
    """Let one enemy act. Returns whether it actually spent a turn."""
    if not actor.alive or state.over:
        return False
    if state.has_draught("thin_veil"):
        # THE THIN VEIL. Nothing looks at the hero until the hero strikes: the
        # same gate as being unseen, and it drops the moment a blow lands.
        return False
    if actor.behaviour != "hunter" and not state.dungeon_map.is_visible(
        actor.position
    ):
        # Only act when the player can see you; keeps the game fair. The hunter
        # is the exception and the whole of what it is: it knows where the
        # player is from the moment the floor is built, so "fair" for it would
        # be a monster that stands still in the dark.
        return False

    player = state.player
    if actor.behaviour == "idle" and not actor.awake:
        # THE IDLE sleeps until it is hit or somebody stands beside it. It does
        # not spend a turn while it sleeps; a sleeper that walked would be a
        # monster you cannot leave.
        if chebyshev(actor.position, player.position) <= 1:
            actor.awake = True
            state.say(f"The {actor.name} wakes.", LogKind.BAD)
        else:
            return False
    # THE FROZEN FORTRESS. While the wall stands, it is what everything on
    # the floor wants: the lure is read once, here, so no monster has its own
    # opinion about it. The hunter is included -- a wall of ice that the one
    # monster that always knows where you are ignores would be a wall with a
    # hole in it.
    lure = state.lure
    target = lure.position if lure is not None else player.position
    distance = chebyshev(actor.position, target)

    if distance <= 1:
        if lure is not None:
            _resolve_attack_on_fortress(state, actor, lure)
        else:
            # It reached the hero: that is a fight, and the arena is where the
            # hero gets to answer it. Nothing is rolled here any more -- the
            # whole of what a monster's arrival means is that the two of them
            # are about to be in a room together.
            state.raise_encounter(actor)
        return True

    if _move_towards_player(state, actor, player, distance, towards=target):
        # THE HUNGRY ROAD: the step it just took may have been onto the hero's
        # glass, which is the whole point of leaving it.
        _spring_the_trail(state, actor)
        return True
    return False


def _resolve_attack_on_fortress(state: GameState, attacker: Actor, fortress: Actor) -> None:
    """A monster bites the ice.

    A plain attack, with none of the rules that guard the *hero* -- the salt
    circle, the grave ward and the last breath are promises about the player,
    and a wall is not a person. What the fortress has instead is hit points,
    and when they run out the wall is gone.
    """
    outcome = attack(attacker, fortress, state.rng)
    if not outcome.hit:
        state.say(
            f"The {attacker.name} scrapes at the ice and finds no purchase.",
            LogKind.PLAIN,
        )
        return
    state.hits.append(fortress.position)
    if not fortress.stats.alive:
        fortress.alive = False
        state.say(
            f"The {attacker.name} breaks the Frozen Fortress apart.",
            LogKind.BAD,
        )
        return
    state.say(
        f"The {attacker.name} strikes the ice for {outcome.damage}.",
        LogKind.PLAIN,
    )


#: What a monster's blow is worth, against what it says on the tin.
#:
#: The floors were built for the *map's* combat, where a fight was one step and
#: a blow: eleven monsters a floor at a few percent of the hero each, and a
#: staircase to be reached with most of him left. The arena made a fight a fight,
#: which is the whole point of it -- and every blow in one costs the hero real
#: health, so the same eleven monsters now cost him several times what the floor's
#: potions and levels were ever priced to cover. Measured: a floor-one fight took
#: about a fifth of him, so a run died on floor one with two kills to its name,
#: shop or no shop. At sixty percent a fight costs a tenth, a floor costs a
#: floor's worth, and the tricks have to make up the rest -- which is the game
#: this was supposed to be.
ENEMY_BITE = 0.75


def resolve_enemy_attack(
    state: GameState, attacker: Actor, player: Actor, *, guard: bool = False
) -> AttackOutcome | None:
    """One monster's blow, with everything the floor has loaded into it.

    Public for the same reason the hero's is: the arena and the dungeon resolve
    the same blow. ``guard`` is the arena's own verb -- the hero set his feet --
    and it is half a blow, the same half the grave ward takes, folded in before
    the ward because setting your feet is not wearing an amulet. Returns ``None``
    when nothing was resolved at all -- a circle, a borrowed face -- because a
    fight that called that a miss would report a blow that was never thrown.
    """
    if state.salt_ward:
        # THE SALT CIRCLE. The whole of what it buys: this one turn, nothing
        # lands. Checked before anything else, because a circle that let a blow
        # through would be a circle that did not hold.
        state.say(
            f"The {attacker.name} strikes at the circle and cannot find you.",
            LogKind.PLAIN,
        )
        return None

    if state.shrouded and state.has_passive("borrowed_face"):
        state.say(
            f"The {attacker.name} strikes at where you were, and finds nothing.",
            LogKind.PLAIN,
        )
        return None

    warded = state.ward_ready and state.has_passive("grave_ward")
    # THE LAST BREATH, the defensive half: a cornered hero is harder to land on,
    # worth two points of evasion for this one swing and only while the rule is
    # on.
    evasion = (
        LAST_BREATH_EVASION
        if state.has_gift("last_breath") and state.cornered
        else 0
    )
    outcome = attack(
        attacker,
        player,
        state.rng,
        damage_scale=(
            ENEMY_BITE * (0.5 if warded else 1.0) * (0.5 if guard else 1.0)
        ),
        evasion_bonus=evasion,
    )

    _player_takes_damage(state, attacker, outcome)
    if outcome.hit and not outcome.killed:
        inflict(state, player, attacker.inflicts)
        if attacker.self_inflicts:
            # THE ALREADY-DYING: the blow opens a wound on the thing that threw
            # it. A monster that is a race against itself, and the race is the
            # whole of the fight.
            inflict(state, attacker, attacker.self_inflicts)
        if attacker.behaviour == "thief" and state.gold:
            # THE PICKER: it wants the purse, not the blood. A *share* of what it
            # is carrying a blow -- so the theft grows with the floor the way its
            # purse does, and a hero who trades blows with it for a whole fight
            # has paid for a potion by the time it is done. It remembers every
            # coin: that is what it leaves with, and what it drops if it dies.
            low, high = attacker.gold
            taken = min(
                state.gold,
                state.rng.between(max(2, low // 8), max(3, high // 5)),
            )
            state.gold -= taken
            attacker.stolen += taken
            state.say(
                f"The {attacker.name} takes {taken} gold and steps away.",
                LogKind.BAD,
            )
        thorns = _thorns_of(player)
        if thorns:
            back = attacker.stats.reflect(thorns)
            if back:
                state.hits.append(attacker.position)
                state.say(
                    f"Whatever is growing on you gives {back} of it back.",
                    LogKind.GOOD,
                )
            if not attacker.stats.alive:
                state.say(
                    f"The {attacker.name} comes apart on you.", LogKind.GOOD
                )
                _on_death(state, attacker)
                _remove_corpse(state, attacker)

    if warded and outcome.hit:
        # Spent by a blow that landed, not by a swing. "The first blow of each
        # floor" is what the amulet says, and a swing that missed was not one.
        state.ward_ready = False
        state.say("The ward takes half of it, and is spent.", LogKind.GOOD)

    if (
        outcome.hit
        and state.freeze_chance
        and state.player.alive
        and state.rng.chance(state.freeze_chance)
    ):
        # HOARFROST. Whoever lands a blow on Yeti takes the cold home with
        # them: the chill the status table already knows, on a coin.
        inflict(state, attacker, ("chill",))
        state.say(f"The cold comes off you onto the {attacker.name}.", LogKind.GOOD)

    if outcome.hit and state.has_passive("mirror") and attacker.stats.alive:
        # Whatever struck you wears it. Two points is small against a deep-floor
        # monster and is not meant to be the answer -- it is meant to make a
        # crowd of small things into a decision.
        #
        # ``alive`` and not merely hit: the thorns above may have killed it
        # already, and a corpse that dies a second time is a second corpse -- one
        # that pays its kill twice and then raises on the way out of the list.
        back = attacker.stats.reflect(MIRROR_REFLECTION)
        if back:
            state.hits.append(attacker.position)
            state.say(f"The mirror gives {back} of it back.", LogKind.GOOD)
        if not attacker.stats.alive:
            state.say(f"The {attacker.name} comes apart on its own blow.", LogKind.GOOD)
            # Its death is the player's doing -- the mirror is worn, not found --
            # so it pays out like any other kill.
            _on_death(state, attacker)
            _remove_corpse(state, attacker)
    return outcome


def _move_towards_player(
    state: GameState, actor: Actor, player: Actor, distance: int, towards: Pos | None = None
) -> bool:
    """Step one cell closer, or drift if there is no way through.

    Candidate steps are tried in preference order, straight ahead first, so
    monsters close in rather than jitter. Sideways options let them slide around
    a blocked approach instead of pressing uselessly into a wall.

    ``towards`` is where the step is aimed -- the hero by default, and the
    Frozen Fortress while it stands. Passing it in rather than reading
    ``state.lure`` here keeps the targeting decision in one place (the enemy
    turn), and keeps this a function about stepping.
    """
    goal = towards if towards is not None else player.position
    if actor.behaviour == "hunter":
        # The hunter takes the first step of the *shortest path*, not the
        # straightest line. A greedy step is what everything else uses, and for
        # a monster that only ever fights in the room it was placed in that is
        # plenty -- but a greedy stepper walks into the first wall between it
        # and the player and stays there, which is a hunter that looks broken
        # rather than dangerous.
        target = _hunter_step(state, actor, player, goal)
        if target is None:
            return False
        actor.position = target
        return True

    forward = direction_towards(actor.position, goal)

    if actor.behaviour == "cautious" and distance > 5:
        # Keep their distance until the player comes to them.
        options = [forward.rotate(2), forward.rotate(-2)]
    else:
        options = [forward]
        if distance <= 6:
            options = [forward, forward.rotate(1), forward.rotate(-1)]

    for direction in dict.fromkeys(options):  # de-duplicate, keep order
        target = direction.step(actor.position)
        if not state.dungeon_map.is_walkable(target):
            continue
        if state.corpse_blocks(target):
            # THE GALLOWS ROAD. The floor's dead are walls to everything that
            # hunts: the hero walks over them (and eats them, with the tongue),
            # the monsters cannot follow.
            continue
        if state.actor_at(target) is not None:
            continue
        if chebyshev(target, goal) >= distance:
            continue
        actor.position = target
        return True
    return False


def _hunter_step(
    state: GameState, actor: Actor, player: Actor, goal_pos: Pos | None = None
) -> Pos | None:
    """The first cell of the shortest walkable path from ``actor`` to its goal.

    Breadth-first over the floor, which is about fifteen hundred cells on the
    largest map and runs once per hunter turn. The path is rebuilt every turn
    rather than stored: the player moves, the floor does not change, and a
    cached path that outlives the thing it was planned around is how a monster
    ends up walking confidently into a wall. ``goal_pos`` overrides the hero
    when something else on the floor is the thing worth walking to -- the
    Frozen Fortress, for the one monster whose pathing is not greedy.
    """
    start, goal = actor.position, goal_pos if goal_pos is not None else player.position
    came_from: dict[Pos, Pos | None] = {start: None}
    queue = deque([start])

    while queue:
        here = queue.popleft()
        if here == goal:
            break
        for direction in DIRECTIONS:
            step = direction.step(here)
            if step in came_from:
                continue
            if step != goal and not state.dungeon_map.is_walkable(step):
                continue
            if step != goal and state.corpse_blocks(step):
                # THE GALLOWS ROAD holds the hunter too: the dead are walls to
                # everything that hunts, and the hunter's path is not an
                # exception it gets to keep.
                continue
            if step != goal and state.actor_at(step) is not None:
                continue
            came_from[step] = here
            queue.append(step)

    if goal not in came_from:
        return None

    # Walk the path back to the cell just after the start.
    here = goal
    while came_from.get(here) is not None and came_from[here] != start:
        here = came_from[here]
    return None if here == start else here


#: Safety net so a pathological queue can never hang the game loop.
MAX_ENEMY_ACTIONS_PER_PLAYER_TURN = 64


def advance_world(state: GameState) -> None:
    """Run the scheduler until it is the player's turn again.

    This is where the speed stat actually pays off: Noxx acts, then one or two
    monsters get an action in before the queue hands control back. A speed-0.7
    ghoul only gets to move about every second player turn.
    """
    if state.in_fight:
        # A fight is open: the room is the answer to a turn spent in it, and the
        # floor outside it has no business moving. Nor do the counters tick --
        # the arena ticks the same ones at its own round boundary, and two clocks
        # on one ward is a ward that lasts half as long as it says.
        return
    state.refresh_passives()
    for _ in range(MAX_ENEMY_ACTIONS_PER_PLAYER_TURN):
        if state.over or state.encounter is not None:
            # A fight is owed. The floor stands still until it has happened --
            # the monsters in it are the ones the hero is about to meet, and the
            # ones outside it have no business moving while he is in a room.
            break
        actor = state.turn_queue.pop()
        if actor is None:
            break
        if actor.is_player:
            # The player's own statuses run on the player's own turn, like
            # everybody else's.
            tick_statuses(state, actor)
            break
        if actor.alive:
            tick_statuses(state, actor)
            if actor.alive and not state.over:
                take_turn(state, actor)

    # Counted down here rather than once per turn, so the borrowed face covers
    # exactly the monsters that answer the kill and not the ones after them.
    #
    # Not counted down when the floor stopped to hand a fight over: the turn
    # those counters cover has not happened yet -- it is about to, in the arena
    # -- and a ward that lapsed on the way in would be a ward that guarded
    # nothing. The arena ticks them at its own round boundary instead.
    if state.encounter is None:
        if state.shrouded:
            state.shrouded -= 1
        if state.salt_ward:
            state.salt_ward -= 1

    # The shadow's beat sits after the monsters': the dark works while and
    # over the dungeon's own answering turn, and every fresh player turn is
    # one tick of its stay.
    _advance_atritas(state)
    _advance_fortress(state)
