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

from neverdeads_revenge.core.direction import chebyshev

from .actions import (
    Action,
    inflict,
    perform_action,
    resolve_enemy_attack,
    resolve_player_attack,
    tick_statuses,
    ultimate_refusal,
)
from .actors import Actor
from .combat import AttackOutcome
from .specials import (
    ATRITAS,
    BETWEEN_BLOWS,
    LEFT_HAND,
    OPEN_VEIN,
    SPECIALS,
    VOID,
    Special,
    special_by_key,
)
from .state import GameState, LogKind

__all__ = [
    "ATTACK",
    "DEFEND",
    "FLEE",
    "ITEM",
    "SPECIAL",
    "STAGE",
    "VERBS",
    "Battle",
    "Guarded",
    "Special",
    "Over",
    "Said",
    "Struck",
    "encounter_around",
    "open_fight",
]

#: How many monsters one fight holds. The stage draws three in a row, and a
#: fourth wants a second row -- which is a wider glass, and M3's business.
STAGE = 3

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
    #: A word about *how* the blow was struck, for whoever is doing the showing:
    #: the arena paints a different flash for a dagger than for the void. A name
    #: and not a colour -- the rules have no business knowing what green is.
    flair: str = ""


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


def open_fight(state: GameState, trigger: Actor | None = None) -> Battle | None:
    """The fight the floor handed over, ready to play -- or ``None`` if none is.

    Cleared as it is taken, because a fight that could be asked for twice would
    be two fights. The app calls this the moment it notices ``state.encounter``;
    a test calls it to play a turn of contact without building a screen.
    """
    trigger = trigger if trigger is not None else state.encounter
    if trigger is None or not trigger.stats.alive:
        return None
    if state.encounter is trigger:
        state.encounter = None
    return Battle(state, encounter_around(state, trigger))


#: What the dagger adds to a stab it makes sure of. Small, because the crit is
#: already the point: this is the difference between a knife and a knife that was
#: aimed.
LEFT_HAND_BONUS = 3

#: How far from the hero the room reaches. A fight takes whoever is standing in
#: the same room, and "the same room" is a distance rather than a graph of walls:
#: two squares is close enough to join in, and a monster across the floor is not.
ROOM = 2


def encounter_around(
    state: GameState, trigger: Actor, limit: int = STAGE
) -> list[Actor]:
    """The monsters that join the fight the floor handed over.

    The one the hero met first, then whoever is standing near enough to be in the
    same room -- within :data:`ROOM` squares of *the hero*, because the room is
    where he is and not where the monster he bumped into happens to be standing.
    A monster that watches its neighbour cut apart two feet away and does nothing
    is a monster nobody believes in.
    """
    group = [trigger]
    for other in state.enemies:
        if other is trigger or not other.stats.alive:
            continue
        if chebyshev(other.position, state.player.position) <= ROOM:
            group.append(other)
            if len(group) >= limit:
                break
    return group


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
        self.over = False
        self.won = False
        self.escaped = False
        #: Whether the round is standing still, waiting on the hero. The one
        #: piece of bookkeeping that makes a *round* out of everybody's turns:
        #: the hero's command is the command of his place in it, and the round
        #: does not hand him a second turn for free.
        self._hero_up = False
        #: Which of the hero's tricks this *fight* has already spent. The void is
        #: not in here: it is priced by the floor, and the floor's own flag says so.
        self._used: set[str] = set()
        #: BETWEEN BLOWS: until the end of this round, nothing finds the hero.
        self._unseen = False

    # -- what the hero is offered -------------------------------------------
    def commands(self) -> list[str]:
        """The five verbs. None of them is ever withheld.

        A verb that says why it will not work teaches the rule; a verb that is
        missing from the menu teaches nothing, and leaves the player wondering
        whether they misremembered the game or the game forgot them.
        """
        return list(VERBS)

    def specials(self) -> list[Special]:
        """The hero's five tricks, in the order a fight offers them."""
        return list(SPECIALS)

    def special_ready(self, special: Special | None = None) -> bool:
        """Whether the dark would answer -- this one, or any of them.

        Asked by the menu, which dims what cannot be spent rather than letting
        the player spend a turn finding out. The gate itself is the dungeon's.
        """
        if special is not None:
            return self.special_available(special)
        return any(self.special_available(one) for one in SPECIALS)

    def special_available(self, special: Special) -> bool:
        """Whether this one can still be asked for, right now.

        The void is the dungeon's ask and is priced by the dungeon: the level the
        dark answers at, and the once-a-floor flag the floor refills. The other
        four are the fight's, and are spent one by one inside it.

        Their level is capped by the level the dark answers at, which is the one
        place a test can lower: `--testrun` runs make the dark speak at level one,
        and a run the dark talks through does not keep four of the hero's tricks
        secret. In an ordinary run nothing changes -- the void arrives at seven
        and the other four are all in hand by six -- so the cap only ever opens
        what was going to open anyway, earlier.
        """
        if special.uses_floor:
            return ultimate_refusal(self.state) is None
        if special.key in self._used:
            return False
        gate = min(special.level, self.state.ultimate_level)
        return self.state.level >= gate

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

    def choose(
        self,
        command: str,
        target: Actor | None = None,
        *,
        special: str | None = None,
    ) -> list[Event]:
        """Take the hero's verb, and let the round run on from it.

        If nobody has asked the hero yet -- a fight that was opened without
        :meth:`begin` -- the round is entered first, so that his command is the
        command of his place in it. Otherwise a caller could give the hero a free
        action bolted onto the front of a round he is already standing in.
        """
        events: list[Event] = []
        if self.over:
            return events
        if not self._hero_up:
            self._advance(events)
        if self.over:
            return events
        self._hero_up = False
        #: Which of the hero's tricks this *fight* has already spent. The void is
        #: not in here: it is priced by the floor, and the floor's own flag says so.
        self._used: set[str] = set()
        #: BETWEEN BLOWS: until the end of this round, nothing finds the hero.
        self._unseen = False
        if self._hero_acts(command, target, events, special):
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
                self._hero_up = True
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
                if self._round:
                    # A round that was *played* has ended; the first one is being
                    # built, and nothing has happened yet to run out.
                    self._lapse()
                self._round = self._order()
                self._taken = 0
                self._guarded = False
            actor = self._round[self._taken]
            self._taken += 1
            if actor.stats.alive:
                return actor

    def _lapse(self) -> None:
        """A round has gone by: the counters that run out by the turn run out.

        The dungeon ticks these in ``advance_world`` after its own enemy phase,
        which is exactly this moment -- the end of a round -- so a borrowed face
        or a salt circle covers one round's worth of answers here too. Without
        this a shrouding raised by a kill would last the whole fight, and the
        amulet that sells it would be selling a different, much longer, promise.
        """
        if self.state.shrouded:
            self.state.shrouded -= 1
        if self.state.salt_ward:
            self.state.salt_ward -= 1
        self._unseen = False
        # And the wounds run, for everybody: a poison hurt on the victim's own
        # turn on the map, and a round is the arena's turn. Without this a bleed
        # would be a sentence the fight never read out.
        for actor in [self.hero, *self.enemies]:
            if actor.stats.alive:
                tick_statuses(self.state, actor)

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
        self,
        command: str,
        target: Actor | None,
        events: list[Event],
        special: str | None = None,
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
            chosen = special_by_key(special) if special else self._first_ready()
            if chosen is None or not self.special_available(chosen):
                self.state.say(self._special_refusal(chosen), LogKind.PLAIN)
                self._splice(before, events)
                return False
            self._run_special(chosen, target, events)
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

    # -- the hero's five tricks ---------------------------------------------
    def _first_ready(self) -> Special | None:
        """The first of the five that can be spent, for a caller with no opinion."""
        for special in SPECIALS:
            if self.special_available(special):
                return special
        return None

    def _special_refusal(self, special: Special | None) -> str:
        """Why the dark will not do this one, in the dungeon's own words.

        The void's refusal *is* the dungeon's -- the level the dark answers at,
        and the floor it has already had -- because it is the same ask priced the
        same way. The others are the fight's, and say so.
        """
        if special is None:
            return "The dark has nothing left to spend here."
        if special.uses_floor:
            return ultimate_refusal(self.state) or "The dark has already had this floor."
        if special.key in self._used:
            return f"{special.name} has already been spent in this fight."
        if self.state.level < special.level:
            return f"Not yet. {special.name} arrives at level {special.level}."
        return "The dark is quiet."

    def _run_special(self, special: Special, target: Actor | None, events: list[Event]) -> None:
        """Spend one of the five, through the same blow as everything else.

        Every one of them ends in `resolve_player_attack`, because that is where
        a blow in this game is resolved: a special that swung with its own dice
        would disagree with the dungeon about what a curse or a gift is worth.
        """
        run = {
            LEFT_HAND: self._special_left_hand,
            ATRITAS: self._special_atritas,
            OPEN_VEIN: self._special_open_vein,
            BETWEEN_BLOWS: self._special_between_blows,
            VOID: self._special_the_void,
        }[special.key]
        run(target, events)
        if not special.uses_floor:
            self._used.add(special.key)

    def _blow(
        self,
        enemy: Actor,
        events: list[Event],
        *,
        flair: str = "",
        force_crit: bool = False,
        bonus: int = 0,
    ) -> AttackOutcome:
        """One hero's blow, said and shown, with the trick's own word on it."""
        before = len(self.state.log)
        outcome = resolve_player_attack(
            self.state, enemy, force_crit=force_crit, bonus=bonus
        )
        self._splice(before, events)
        events.append(Struck(self.hero, enemy, outcome, flair=flair))
        return outcome

    def _special_left_hand(self, target: Actor | None, events: list[Event]) -> None:
        """The dagger: the stab it makes sure of, and it is a little deeper."""
        enemy = self._pick(target)
        if enemy is not None:
            self._blow(enemy, events, flair=LEFT_HAND, force_crit=True, bonus=LEFT_HAND_BONUS)

    def _special_atritas(self, target: Actor | None, events: list[Event]) -> None:
        """The shadow leaves, and strikes twice while its owner stands still."""
        enemy = self._pick(target)
        if enemy is None:
            return
        before = len(self.state.log)
        self.state.say("Your shadow peels off and goes for him.", LogKind.SYSTEM)
        self._splice(before, events)
        for _ in range(2):
            if not enemy.stats.alive:
                break
            self._blow(enemy, events, flair=ATRITAS)

    def _special_open_vein(self, target: Actor | None, events: list[Event]) -> None:
        """A cut that will not close: small, and it keeps costing him."""
        enemy = self._pick(target)
        if enemy is None:
            return
        self._blow(enemy, events, flair=OPEN_VEIN)
        if enemy.stats.alive:
            before = len(self.state.log)
            inflict(self.state, enemy, ("bleed",))
            self._splice(before, events)

    def _special_between_blows(self, target: Actor | None, events: list[Event]) -> None:
        """He is not where they swing: nothing finds him this round, and the cut
        still lands."""
        enemy = self._pick(target)
        if enemy is not None:
            self._blow(enemy, events, flair=BETWEEN_BLOWS)
        before = len(self.state.log)
        self.state.say("You are already somewhere else.", LogKind.GOOD)
        self._splice(before, events)
        self._unseen = True

    def _special_the_void(self, target: Actor | None, events: list[Event]) -> None:
        """The dungeon's own ask, in the room: the dark answers, and everything
        in front of him takes it at once."""
        self.state.ultimate_available = False
        before = len(self.state.log)
        self.state.say("The dark answers.", LogKind.SYSTEM)
        self._splice(before, events)
        for enemy in self.living_enemies():
            if not self.hero.stats.alive:
                break
            self._blow(enemy, events, flair=VOID)

    def _pick(self, target: Actor | None) -> Actor | None:
        """The one being hit: the chosen one, or whoever is still standing."""
        if target is not None and target.stats.alive:
            return target
        living = self.living_enemies()
        return living[0] if living else None

    def _enemy_acts(self, attacker: Actor, events: list[Event]) -> None:
        """One monster's turn: it swings at the hero.

        Aggressive or cautious, there is no *distance* in a room to hang back
        into. The cautious label is a rule about closing -- a skeleton holds its
        ground on the floor until the hero comes to it -- and that rule still
        lives where closing happens. Inventing a second reading of it for the
        arena would be two opinions about one word.
        """
        if self._unseen:
            # BETWEEN BLOWS: the swing goes through the place he was standing.
            before = len(self.state.log)
            self.state.say(
                f"The {attacker.name} strikes at where you were.", LogKind.PLAIN
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
