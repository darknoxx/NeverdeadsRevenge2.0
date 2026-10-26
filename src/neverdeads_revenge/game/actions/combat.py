"""One part of the turn: combat."""

from __future__ import annotations

from neverdeads_revenge.core.direction import (
    direction_towards,
)
from ..actors import (
    Actor,
)
from ..combat import AttackOutcome, attack
from ..state import GameState, LogKind


from .core import (
    ENEMY_BITE,
    LAST_BREATH_EVASION,
    MIRROR_REFLECTION,
)
from .life import (
    _enemy_takes_damage,
    _inflicts_of,
    _on_death,
    _player_takes_damage,
    _remove_corpse,
    _thorns_of,
    _weapon_rule_bonus,
    inflict,
)


#: What an aspect does when its blow lands. A table, not another branch in the
#: attack: a new aspect is one entry here and one entry in ``game/affixes.py``.
ENEMY_AFFIX_RULES = {
    "fire_kissed": lambda state, attacker, target: inflict(
        state, target, ("burn",)
    ),
    "frostbound": lambda state, attacker, target: inflict(
        state, target, ("chill",)
    ),
}

#: And what an aspect does when the *hero's* blade carries it. The depthless
#: already opens a wound; darkness-touched makes that wound one deeper.
WEAPON_AFFIX_RULES = {
    "fire_kissed": lambda state, target, player: inflict(
        state, target, ("burn",), source=player
    ),
    "frostbound": lambda state, target, player: inflict(
        state, target, ("chill",), source=player
    ),
    "darkness_touched": lambda state, target, player: inflict(
        state, target, ("bleed",), stacks=1, source=player
    ),
}


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
        for affix in state.player.weapon_affixes:
            rule = WEAPON_AFFIX_RULES.get(affix)
            if rule is not None:
                rule(state, target, state.player)
        if outcome.crit and state.bleed_on_crit:
            # BLEEDING EDGE. A lucky blow opens a wound as deep as the bloodline
            # is: one stack, two, three, five -- the ceiling the wounds have. It used
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
    if target.thorns or target.ring_thorns:
        # THE BRIAR: what it grows, you take -- straight, because a thorn is not
        # a blow and armour has nothing to do with it. The ring's thorn is a
        # single bite: the first cut breaks it, so a player can spend it down.
        back = state.player.stats.reflect(target.thorns + target.ring_thorns)
        if back:
            state.say(
                f"The {target.name} gives {back} of it back.", LogKind.BAD
            )
            if state.player.hp <= 0:
                state.die("The briar had the last of it.")
        target.ring_thorns = 0

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
        for affix in attacker.affixes:
            rule = ENEMY_AFFIX_RULES.get(affix)
            if rule is not None:
                rule(state, attacker, player)
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


