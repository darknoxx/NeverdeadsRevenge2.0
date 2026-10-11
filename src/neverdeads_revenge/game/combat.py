"""Combat resolution.

Deliberately small and legible. One function decides an attack, and it returns a
result object rather than mutating the world silently, so the caller can report
exactly what happened and tests can assert on it.

The hit chance is a flat base nudged by the accuracy/evasion difference. Noxx's
evasion 5 against a ghoul's accuracy 0 puts him at 35% -- being hard to pin down
is half of what makes him work, and the other half is that he gets to attack
more often.

Evasion is worth ten points of hit chance per point, which makes 5 the natural
ceiling for any hero: the floor is 30%, so a sixth point against a monster with
accuracy 0 is partly paid for and not received.
"""

from __future__ import annotations

from dataclasses import dataclass

from neverdeads_revenge.core.rng import Rng

from .actors import Actor, Trait
from .actors import REVENGE_MAX_STACKS as REVENGE_MAX_STACKS

__all__ = [
    "AttackOutcome",
    "BASE_HIT_CHANCE",
    "MIN_HIT_CHANCE",
    "MAX_HIT_CHANCE",
    "REVENGE_MAX_STACKS",
    "chance_against",
    "hit_chance",
    "attack",
    "apply_revenge",
]

BASE_HIT_CHANCE = 0.85
MIN_HIT_CHANCE = 0.30
MAX_HIT_CHANCE = 0.97


@dataclass(frozen=True, slots=True)
class AttackOutcome:
    """What happened when ``attacker`` swung at ``defender``."""

    hit: bool
    crit: bool
    damage: int
    killed: bool
    dodged: bool = False

    @property
    def verb(self) -> str:
        """Third person singular, for when a monster is the subject.

            f"The ghoul {outcome.verb} you for {outcome.damage}."
        """
        return _VERBS[self._outcome_key][0]

    @property
    def verb_second_person(self) -> str:
        """Second person singular, for when the player is the subject.

            f"You {outcome.verb_second_person} the ghoul for {outcome.damage}."
        """
        return _VERBS[self._outcome_key][1]

    @property
    def _outcome_key(self) -> tuple[bool, bool, bool]:
        return (self.dodged or not self.hit, self.crit, self.killed)


#: outcome key -> (third person, second person)
_VERBS: dict[tuple[bool, bool, bool], tuple[str, str]] = {
    (True, False, False): ("misses", "miss"),
    (True, True, False): ("misses", "miss"),
    (True, False, True): ("misses", "miss"),
    (True, True, True): ("misses", "miss"),
    (False, False, False): ("hits", "hit"),
    (False, True, False): ("crits", "crit"),
    (False, False, True): ("kills", "kill"),
    (False, True, True): ("obliterates", "obliterate"),
}


def chance_against(accuracy: int, evasion: int) -> float:
    """Probability that an accuracy lands on an evasion.

    Split out of :func:`hit_chance` so a screen can show a worked example
    without building two actors to ask about. Accuracy and evasion are worth ten
    points each and the result is clamped, which is a rule nobody can read off
    two bare integers -- which is why the sheet says what they come to.
    """
    chance = BASE_HIT_CHANCE + 0.1 * (accuracy - evasion)
    return max(MIN_HIT_CHANCE, min(MAX_HIT_CHANCE, chance))


def hit_chance(attacker: Actor, defender: Actor) -> float:
    """Probability that ``attacker`` lands a blow on ``defender``."""
    return chance_against(attacker.accuracy, defender.evasion)


def attack(
    attacker: Actor,
    defender: Actor,
    rng: Rng,
    *,
    force_crit: bool = False,
    damage_scale: float = 1.0,
    spread: float = 1.0,
    bonus: int = 0,
    evasion_bonus: int = 0,
) -> AttackOutcome:
    """Resolve one attack from ``attacker`` against adjacent ``defender``.

    Mutates ``defender``'s health and the ``alive`` flag when it lands a killing
    blow. The caller is responsible for cleaning up the body.

    ``force_crit``, ``damage_scale`` and ``spread`` all exist for rules that
    reach into the dice: the patient knife makes a first blow a crit, the grave
    ward takes half of one, and THE FEVER widens the roll. All three are passed
    in rather than read from the actors, because the rules behind them live in
    ``game/`` and this function deliberately knows nothing about amulets or
    curses.

    ``bonus`` is flat damage added after everything else -- MOMENTUM's charge,
    the DEBT OF BLOOD paid back -- and ``evasion_bonus`` is the defender's
    evasion for this one swing, which is how THE LAST BREATH makes a cornered
    hero harder to land on without touching their stats.
    """
    chance = chance_against(attacker.accuracy, defender.evasion + evasion_bonus)
    if not rng.chance(chance):
        return AttackOutcome(hit=False, crit=False, damage=0, killed=False, dodged=True)

    base = attacker.damage_roll(rng, spread)
    crit = force_crit or rng.chance(attacker.crit_chance)
    damage = int(round(base * attacker.crit_multiplier)) if crit else base
    if damage_scale != 1.0:
        # Never nothing. A ward that turned a blow into a no-op would be a
        # different amulet, and the message would be a lie.
        damage = max(1, int(round(damage * damage_scale)))
    if bonus:
        damage = max(1, damage + bonus)

    dealt = defender.hurt(damage)
    killed = not defender.stats.alive
    if killed:
        defender.alive = False

    return AttackOutcome(hit=True, crit=crit, damage=dealt, killed=killed)


def apply_revenge(actor: Actor, stacks: int) -> int:
    """Set ``actor``'s REVENGE to ``stacks`` and fold the grant into its bonuses.

    Returns the stack count actually held, clamped so a long chain cannot let the
    holder run away with the run. The grant follows the actor's own
    :class:`~neverdeads_revenge.game.actors.Trait`: speed for one hero, armour for
    another, raw damage for a third.

    Set rather than increment, deliberately. Gaining a stack and losing them all
    on a new floor are then the same operation, so lapsing cannot leave a residue
    behind on an actor -- and every bonus is written on every call rather than
    only the relevant one, for the same reason.
    """
    stacks = max(0, min(stacks, actor.trait.cap))
    amount = actor.trait.per_stack * stacks

    actor.speed_bonus = amount if actor.trait is Trait.SPEED else 0.0
    actor.armor_bonus = int(amount) if actor.trait is Trait.ARMOUR else 0
    actor.damage_bonus = int(amount) if actor.trait is Trait.DAMAGE else 0
    return stacks
