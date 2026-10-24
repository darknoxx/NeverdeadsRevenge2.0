"""One part of the turn: ultimates."""

from __future__ import annotations

from neverdeads_revenge.core.direction import (
    DIRECTIONS,
    Pos,
    chebyshev,
)
from neverdeads_revenge.world.tiles import Tile
from ..actors import (
    make_atritas,
    make_fortress,
)
from ..curses import curse_by_key
from ..difficulty import (
    ATRITAS_TURNS,
    BELL_RADIUS,
    FORTRESS_TURNS,
)
from ..state import GameState, LogKind


from .core import (
    ActionResult,
    _outcome,
)
from .combat import (
    _knock_back,
)
from .life import (
    _on_death,
    _remove_corpse,
)
from .turn import (
    advance_world,
)
from .world import (
    _the_lid_bites,
)


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


