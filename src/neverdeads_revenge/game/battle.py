"""The fight: whose turn it is, what the hero can ask for, and the blow by blow.

A battle is not a second combat system. The dungeon already knows how to resolve
a blow -- how a gift charges it, how a curse takes its share, what a wound left
behind, what a kill pays out -- and that knowledge lives in
:mod:`neverdeads_revenge.game.actions`, which this module *calls* rather than
repeats. What it adds is regie: a round order, the five verbs, and a list of
events small enough that a screen can play them back without knowing a single
rule.

That split is the point of the module. This decides; a screen moves. A fight in
an arena and a fight on the map spend the same health and the same draughts, and
cannot drift apart from each other, because there is exactly one place where a
blow is resolved.

The enemies are the actors standing on the floor, and that is deliberate. A kill
has to pay its coins, drop a corpse and open whatever the blade leaves, and all
of that already happens where the monster is. An encounter, when M2 brings it,
begins with the hero walking into one of them -- so the fight is always over
something real, and the floor is short one ghoul afterwards.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .actions import (
    Action,
    perform_action,
    resolve_enemy_attack,
    resolve_player_attack,
    ultimate_refusal,
)
from .actors import Actor
from .combat import AttackOutcome
from .state import GameState, LogKind

__all__ = [
    "ATTACK",
    "DEFEND",
    "FLEE",
    "ITEM",
    "SPECIAL",
    "VERBS",
    "Battle",
    "Guarded",
    "Over",
    "Said",
    "Struck",
]

#: The five verbs, in the order a fight offers them: the blade first, because it
#: is what a player does most, and running last, because it is what they should
#: do least.
ATTACK = "attack"
SPECIAL = "special"
ITEM = "item"
DEFEND = "defend"
FLEE = "flee"
VERBS: tuple[str, ...] = (ATTACK, SPECIAL, ITEM, DEFEND, FLEE)


@dataclass(frozen=True, slots=True)
class Said:
    """A line the fight wants said, in the log's own language.

    The words of a blow belong to the rules -- a gift that charged it, a curse
    that took its share -- so the fight does not write its own account of what
    happened. It hands on the lines the rules wrote, and a screen says them in
    the colours the dungeon log uses for the same kinds of line.
    """

    text: str
    kind: LogKind = LogKind.PLAIN


@dataclass(frozen=True, slots=True)
class Struck:
    """One blow, resolved: who swung, at whom, and how it went.

    This is the half a screen needs and cannot get from prose: whose turn it was
    to lunge, who takes the hit, whether it landed, how much, and whether that
    was the end of them.
    """

    actor: Actor
    target: Actor
    outcome: AttackOutcome


@dataclass(frozen=True, slots=True)
class Guarded:
    """The hero set his feet: everything aimed at him this round is halved."""

    name: str


@dataclass(frozen=True, slots=True)
class Over:
    """The fight is decided. ``escaped`` is leaving on your own terms."""

    won: bool
    escaped: bool = False


#: Everything a fight can say to a screen.
Event = Said | Struck | Guarded | Over


class Battle:
    """One fight, from the first round to the last event.

    Reach for :meth:`begin` once, then :meth:`choose` for every command the
    player makes, playing back the events each of them returns. The fight is
    never advanced twice for one command, and never waits on a timer of its own:
    the round stops when it is the hero's turn, which is the only moment it has
    anything to ask.
    """

    def __init__(self, state: GameState, enemies: Sequence[Actor]) -> None:
        self.state = state
        self.hero = state.player
        self.enemies = list(enemies)
        #: Whether the hero has his feet set, which lasts one round.
        self._guarded = False
        #: This round's order, and how far into it the fight has got.
        self._round: list[Actor] = []
        self._taken = 0
        #: How many rounds a cautious monster has spent circling, by actor. Keyed
        #: by identity rather than by name: two ghouls are two monsters, and one
        #: of them hanging back should not make the other one hesitate.
        self._circles: dict[int, int] = {}
        self.over = False
        self.won = False
        self.escaped = False

    # -- what the hero is offered -------------------------------------------
    def commands(self) -> list[str]:
        """The five verbs. None of them is ever withheld.

        A verb that says why it will not work teaches the rule; a verb that is
        missing from the menu teaches nothing, and leaves the player wondering
        whether they misremembered the game or the game forgot them.
        """
        return list(VERBS)

    def special_ready(self) -> bool:
        """Whether the dark would answer right now.

        Asked by the menu, which dims the verb rather than letting the player
        spend a turn finding out. The gate itself is the dungeon's, untouched.
        """
        return ultimate_refusal(self.state) is None

    def living_enemies(self) -> list[Actor]:
        """Everyone still standing, in the order they were met."""
        return [enemy for enemy in self.enemies if enemy.stats.alive]

    # -- the fight ----------------------------------------------------------
    def begin(self) -> list[Event]:
        """Start the round and walk it until the hero has to decide.

        Anything quicker than the hero acts before the first command. That is the
        whole of what speed buys, and it belongs in the first beat of the fight
        rather than in a number on a sheet.
        """
        events: list[Event] = []
        self._advance(events)
        return events

    def choose(self, command: str, target: Actor | None = None) -> list[Event]:
        """Take the hero's verb, and let the round run on from it."""
        events: list[Event] = []
        if self.over:
            return events
        if self._hero_acts(command, target, events):
            self._advance(events)
        return events

    # -- the round ----------------------------------------------------------
    def _advance(self, events: list[Event]) -> None:
        """Let the round run until the hero is up, or until it is decided."""
        while True:
            if self._decide(events):
                return
            actor = self._next()
            if actor is self.hero:
                return
            self._enemy_acts(actor, events)

    def _next(self) -> Actor:
        """The next combatant to act, rolling the round over when it runs out.

        Quickest first, and the roster order breaks a tie -- so the hero goes
        first among equals and the wraith does not. Rolling over is also where
        setting your feet stops counting: a round is one breath, and the guard
        lasts exactly that long.
        """
        while True:
            if self._taken >= len(self._round):
                self._round = self._order()
                self._taken = 0
                self._guarded = False
            actor = self._round[self._taken]
            self._taken += 1
            if actor.stats.alive:
                return actor

    def _order(self) -> list[Actor]:
        """Everyone alive, quickest first. Never empty: the fight is decided
        before this is asked, so somebody is always still standing."""
        return sorted(
            [actor for actor in [self.hero, *self.enemies] if actor.stats.alive],
            key=lambda actor: -actor.speed,
        )

    def _decide(self, events: list[Event]) -> bool:
        """Whether the fight is over, saying so once. True means stop."""
        if self.over:
            return True
        if not self.hero.stats.alive:
            self.over = True
            events.append(Over(won=False))
            return True
        if not self.living_enemies():
            self.over = True
            self.won = True
            before = len(self.state.log)
            self.state.say("The floor is quiet again.", LogKind.GOOD)
            self._splice(before, events)
            events.append(Over(won=True))
            return True
        return False

    # -- the two sides ------------------------------------------------------
    def _hero_acts(
        self, command: str, target: Actor | None, events: list[Event]
    ) -> bool:
        """Resolve the hero's verb. Returns whether it cost him the turn.

        A turn is spent by *doing*, not by trying: a swing that misses is still a
        swing, and a hero who reaches for a potion that is not there has not been
        anywhere or done anything, so the floor does not get to move.
        """
        before = len(self.state.log)
        if command == ATTACK:
            enemy = target if target is not None and target.stats.alive else None
            if enemy is None:
                return False
            outcome = resolve_player_attack(self.state, enemy)
            self._splice(before, events)
            events.append(Struck(self.hero, enemy, outcome))
            return True

        if command == SPECIAL:
            refusal = ultimate_refusal(self.state)
            if refusal is not None:
                self.state.say(refusal, LogKind.PLAIN)
                self._splice(before, events)
                return False
            self._ask_the_dark(events)
            return True

        if command == ITEM:
            # The dungeon's own mouthful: it picks the cheapest draught that
            # covers the wound, and it says what it did. A fight that healed by
            # its own arithmetic would disagree with the pack about what the
            # bottle is worth -- and the pack is where the bottle is.
            result = perform_action(self.state, Action.QUAFF)
            self._splice(before, events)
            return result.consumed_turn

        if command == DEFEND:
            self._guarded = True
            before = len(self.state.log)
            self.state.say("You set your feet and wait for it.", LogKind.PLAIN)
            self._splice(before, events)
            events.append(Guarded(self.hero.name))
            return True

        if command == FLEE:
            self._flee(events)
            return False

        return False

    def _ask_the_dark(self, events: list[Event]) -> None:
        """The hero's own ask, in the arena.

        The dungeon's three answers each put something on the *map*: a shadow
        that walks and sees through walls, a wall of ice, a bell that rings down
        through the floor. None of that fits in a room, and M3 is where each hero
        gets their arena shape. What already fits is the promise underneath all
        three -- the dark answers, and everything in front of the hero takes it
        at once -- and the price is the dungeon's own, so the ask cannot be spent
        twice in one floor by making it in the right place.
        """
        self.state.ultimate_available = False
        self.state.say("The dark answers.", LogKind.SYSTEM)
        for enemy in self.living_enemies():
            if not self.hero.stats.alive:
                break
            before = len(self.state.log)
            outcome = resolve_player_attack(self.state, enemy)
            self._splice(before, events)
            events.append(Struck(self.hero, enemy, outcome))

    def _enemy_acts(self, attacker: Actor, events: list[Event]) -> None:
        """One monster's turn.

        Aggressive things close and swing. A cautious one -- the skeleton is the
        only monster in the bestiary carrying the label -- hangs back every other
        round, which is this arena's reading of "waits until the player closes":
        in a room there is nowhere to hang back *to*, so holding its ground
        costs it a turn instead. The behaviour table says one thing and this is
        the one place that reads it.
        """
        if attacker.behaviour == "cautious":
            circles = self._circles.get(id(attacker), 0)
            self._circles[id(attacker)] = circles + 1
            if circles % 2 == 0:
                before = len(self.state.log)
                self.state.say(
                    f"The {attacker.name} circles, and does not close.", LogKind.PLAIN
                )
                self._splice(before, events)
                return
        before = len(self.state.log)
        outcome = resolve_enemy_attack(
            self.state, attacker, self.hero, guard=self._guarded
        )
        self._splice(before, events)
        if outcome is not None:
            events.append(Struck(attacker, self.hero, outcome))

    def _flee(self, events: list[Event]) -> None:
        """Turn your back: everything still standing gets one blow at it.

        No coin toss. There is nowhere in a dungeon to run *to* that the floor
        cannot follow, so the price of leaving a fight is the fight noticing --
        and a price the player can count is a decision, while a lottery is a
        shrug dressed up as one.
        """
        before = len(self.state.log)
        self.state.say("You turn your back and run for the dark.", LogKind.PLAIN)
        self._splice(before, events)
        for enemy in self.living_enemies():
            if not self.hero.stats.alive:
                break
            self._enemy_acts(enemy, events)
        self.over = True
        self.escaped = self.hero.stats.alive
        self.won = False
        events.append(Over(won=False, escaped=self.escaped))

    # -- plumbing -----------------------------------------------------------
    def _splice(self, before: int, events: list[Event]) -> None:
        """Hand on everything the rules wrote into the log, in order."""
        for entry in self.state.log[before:]:
            events.append(Said(text=entry.text, kind=entry.kind))
