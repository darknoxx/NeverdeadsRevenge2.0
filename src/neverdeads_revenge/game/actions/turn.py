"""One part of the turn: turn."""

from __future__ import annotations

from collections import deque
from neverdeads_revenge.core.direction import (
    DIRECTIONS,
    Pos,
    chebyshev,
    direction_towards,
)
from ..actors import (
    Actor,
)
from ..combat import attack
from ..difficulty import (
    ATRITAS_HUNT_RADIUS,
    ATRITAS_KILL_HEAL,
    ATRITAS_RADIUS,
    ATRITAS_SWING_EVERY,
    ATRITAS_TURNS,
)
from ..state import GameState, LogKind


from .core import (
    MAX_ENEMY_ACTIONS_PER_PLAYER_TURN,
)
from .combat import (
    _resolve_attack_on_fortress,
)
from .life import (
    _on_death,
    _remove_corpse,
    tick_statuses,
)
from .movement import (
    _spring_the_trail,
)


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


