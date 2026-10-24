"""One part of the turn: movement."""

from __future__ import annotations

from neverdeads_revenge.core.direction import (
    Direction,
    Pos,
)
from ..actors import (
    Actor,
    ActorKind,
)
from ..state import GameState, LogKind


from .core import (
    HOLLOW_ROAD_COST,
    HUNGRY_ROAD_DAMAGE,
    HUNGRY_ROAD_TRAIL,
    MOMENTUM_MAX,
    SLOW_KNITTING_EVERY,
    STEP_BEHIND_EVERY,
)
from .life import (
    _on_death,
    _remove_corpse,
    inflict,
)


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
    _collect_coin(state)
    _bleed(state)
    if state.over:
        # The bleed can finish him. Nothing after a death heals the body, and
        # the step still spent the world's turn -- the caller reads ``over``.
        return True, True
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
    _collect_coin(state)
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


def _collect_coin(state: GameState) -> None:
    """Coins underfoot go into the purse without a keypress.

    A pile is not a decision -- there is nothing to weigh and nothing to leave
    behind -- so pressing enter on one only ever did the obvious thing. Items
    and pages stay on the floor, where taking them *is* a choice.

    Called from the two places a step can land, beside the bleeding and the
    knitting, so a step through stone pockets what lies on the far side too.
    """
    item = state.dungeon_map.item_at(state.player.position)
    if item is None or item.kind != "coin":
        return
    state.dungeon_map.remove_item(state.player.position)
    state.gold += item.gold
    state.say(f"You pocket {item.gold} coins.", LogKind.COIN)


def _knit(state: GameState) -> None:
    """THE SLOW KNITTING. Walking, and only walking, closes a little.

    Called from the two places a step can land -- ordinary floor and stone --
    because a gift that only worked on one of them would be a gift with a
    footnote.
    """
    if not state.has_gift("slow_knitting"):
        return
    if state.over or not state.player.alive:
        # A gift that closes wounds is not a gift that undoes a death.
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


