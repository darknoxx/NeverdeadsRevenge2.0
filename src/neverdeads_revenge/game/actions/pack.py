"""One part of the turn: pack."""

from __future__ import annotations

from neverdeads_revenge.core.direction import (
    DIRECTIONS,
)
from neverdeads_revenge.world.items import ITEMS
from neverdeads_revenge.world.map import GroundItem
from neverdeads_revenge.world.tiles import Tile
from ..actors import (
    ActorKind,
    make_enemy,
    pick_enemy_template,
)
from ..draughts import draught_by_key
from ..lore import numeral
from ..state import GameState, LogKind


from .core import (
    ActionResult,
    NOTHING_WASTED_DAMAGE,
    _outcome,
    _the,
    second_mouth_cap,
)
from .life import (
    _on_death,
    _remove_corpse,
)
from .turn import (
    advance_world,
)


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
    if item.slot == "weapon" and item.item_id not in state.found_weapons:
        # THE ARMORY. A blade is *known* the moment it is in the hand, not when
        # it is lying on the floor: a catalogue of what you walked past is not a
        # catalogue of what you have.
        state.found_weapons.append(item.item_id)
    if item.slot == "armour" and item.item_id not in state.found_armours:
        # THE WARDROBE. A coat is known the moment it is on -- and taking one up
        # puts it on, so the same act that changes the numbers writes the page.
        state.found_armours.append(item.item_id)

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


def descend(state: GameState) -> ActionResult:
    """Try to go down a level from wherever the player stands."""
    return _try_descend(state)


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


