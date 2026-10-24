"""One part of the turn: world."""

from __future__ import annotations

import copy
from dataclasses import fields
from neverdeads_revenge.world.items import ITEMS, make_item
from neverdeads_revenge.world.map import GroundItem
from neverdeads_revenge.world.tiles import Tile
from ..actors import (
    Actor,
)
from ..curses import curse_by_key
from ..gifts import gift_by_key
from ..npcs import npc_by_key
from ..state import GameState, LogKind


from .core import (
    ActionResult,
    _outcome,
)
from .pack import (
    _equip,
    _pick_up,
    _try_descend,
)
from .turn import (
    advance_world,
)


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

    from ..actors import ENEMIES, make_enemy, scale_template

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


