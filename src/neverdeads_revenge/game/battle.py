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
    STACK_LIMIT,
    Action,
    _advance_atritas,
    inflict,
    perform_action,
    resolve_enemy_attack,
    resolve_player_attack,
    tick_statuses,
    ultimate_refusal,
)
from .actors import Actor
from .combat import AttackOutcome
from .statuses import status_by_key
from .specials import (
    AVALANCHE,
    CHORD,
    EMBER_FIST,
    GUT_PUNCH,
    HAYMAKER,
    HEADBUTT,
    JAB,
    RED_MIST,
    ROUNDHOUSE,
    DEVOURING_DARKNESS,
    FLEETING_SHADOW,
    PAINT_THE_WALLS_RED,
    LONG_WINTER,
    BELLS_THROW,
    BETWEEN_BLOWS,
    ECHOING_CUT,
    FIRST_NOTE,
    HOARFROST,
    LEFT_HAND,
    OPEN_VEIN,
    ORB_OF_PTAMERA,
    OVERTURE,
    QUAKE,
    RIME,
    SILENCE,
    SNOW_BLIND,
    STILLNESS,
    TRUE_NOTE,
    Special,
    learned_at,
    special_by_key,
    specials_for,
)
from .state import GameState, LogKind

__all__ = [
    "ATTACK",
    "FLEE",
    "ITEM",
    "SPECIAL",
    "STAGE",
    "VERBS",
    "Battle",
    "Flourish",
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
FLEE = "flee"
VERBS: tuple[str, ...] = (ATTACK, SPECIAL, ITEM, FLEE)


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
class Flourish:
    """Something a trick did that was not a blow: an aura, a wall, a disappearance.

    The five are not all swings. One raises the armour, one sets the frost, one
    takes the hero out of the room -- and a screen that only ever heard about
    blows would have nothing to show for them. This carries the *word* and
    nothing else, the same way :class:`Struck` does.
    """

    actor: Actor
    flair: str


@dataclass(frozen=True, slots=True)
class ShadowStruck:
    """Atritas landed on somebody: the arena paints the shadow over them.

    The shadow is not in the room's queue -- he is the *void's* creature and acts
    on the round's own beat -- so a screen that only ever heard about ``Struck``
    would have a shadow standing about doing nothing. This is the word it needs:
    who he went for, and whether that was the end of them.
    """

    actor: Actor
    killed: bool = False


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
Event = Said | Struck | ShadowStruck | Flourish | Guarded | Over


def open_fight(state: GameState, trigger: Actor | None = None) -> Battle | None:
    """The fight the floor handed over, ready to play -- or ``None`` if none is.

    Cleared as it is taken, because a fight that could be asked for twice would
    be two fights. The app calls this the moment it notices ``state.encounter``;
    a test calls it to play a turn of contact without building a screen.
    """
    trigger = trigger if trigger is not None else state.encounter
    if trigger is None:
        return None
    if not trigger.stats.alive:
        # Owed by a corpse, and a corpse owes nothing. A death clears its own
        # encounter (see `_on_death`); this is the other door, so that a fight
        # nobody can ever have cannot be *asked for* again and again either.
        if state.encounter is trigger:
            state.encounter = None
        return None
    if state.encounter is trigger:
        state.encounter = None
    return Battle(state, encounter_around(state, trigger))


#: What the hammer multiplies a blow by, what the stillness adds to the armour,
#: and what the true note adds to every blow after it. Three numbers in one place
#: because they are the whole balance of two kits, and they should be readable at
#: a glance rather than hunted for.
AVALANCHE_SCALE = 1.8
STILLNESS_ARMOUR = 2
TRUE_NOTE_DAMAGE = 3

#: What a plain swing is worth, against everything else a turn can buy.
#:
#: The tricks are priced in kill points, and a price is only meaningful against
#: what the *free* option does: if swinging the sword is as good as THE OPEN VEIN,
#: then the vein is not a choice, it is a way of spending points for nothing. So
#: the baseline comes down an inch and the tricks get their room -- not far enough
#: to make the sword feel like a mistake, which would be its own kind of wrong:
#: the verbs are all meant to be worth a turn, and the attack is still the one
#: that costs nothing and never runs out.
PLAIN_SWING = 0.85

#: What an area trick does to *each* one of them, against what a single-target
#: trick does to the one. The crowd is the payment: three at sixty percent is
#: more than one at a hundred, and none of these should ever be the right answer
#: against a single monster -- which is the choice they are for.
QUAKE_SCALE = 0.7
OVERTURE_SCALE = 0.6
WINTER_SCALE = 0.5
SILENCE_SCALE = 0.5
#: And the one heavy note, for the price of a full purse, on one target.
CHORD_SCALE = 1.6

# -- Inferno: the weight of a fist -----------------------------------------
#: The cheapest thing in the game by a whole point, and light: a jab is a plain
#: swing with two more on the end of it, which is what makes it worth pressing
#: twice rather than saving for something bigger.
JAB_BONUS = 2
#: The body blow: a little more than a swing, and the wound that comes with it.
GUT_PUNCH_SCALE = 1.1
#: The burning hand: a little more again, and the fire is the reason to spend.
EMBER_FIST_SCALE = 1.2
#: The hardest single blow in the game, and the only one that is *priced in
#: blood*: an eighth of what he has, taken whichever way the swing goes.
HEADBUTT_SCALE = 1.7
HEADBUTT_BLOOD = 0.125
#: RED MIST: he starts at a swing and a fifth and ends up near three swings, so
#: the trick is worth using when he is *losing* and a waste when he is not --
#: which is the only shape a rage can be that is not simply a better attack.
RED_MIST_SCALE = 1.2
RED_MIST_RAGE = 1.6
#: The spin, priced like the other area tricks: seventy percent of a blow to
#: everything, which is worse than the haymaker on one and much better on three.
ROUNDHOUSE_SCALE = 0.7
#: The haymaker: a full extra blow on top of a blow, and the biggest number in
#: the game. It is what the whole hero is: no rider, no wound, no second chance.
HAYMAKER_SCALE = 2.0
#: The orb of Ptamera is *loaded* and not promised: it hunts the throat without
#: ever being certain of it, which is the one thing that tells it apart from the
#: knife -- and the knife is the one that always crits.
ORB_CRIT = 0.5
#: Devouring Darkness: the share of what it bites that he keeps.
SIPHON = 0.5
#: Friends Like These: the shadow brings a wound with it, and the wound is deep.
#: ''It'' and not only ''longer'': two a turn for three turns is the vein's own
#: cut, and a trick that cost a whole turn and a whole fight to hand out the same
#: wound would be a trick nobody spends twice.
DEEP_BLEED = "maul"

#: How far from the hero the room reaches. A fight takes whoever is standing in
#: the same room, and "the same room" is a distance rather than a graph of walls:
#: this many squares is close enough to join in, and a monster across the floor
#: is not. Three rather than two, because the floors hold more monsters now, and
#: a room that took only the ones touching the hero still made a crowd of one:
#: the stage holds three, so three is the reach that fills it.
ROOM = 3


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
    if state.debt:
        # THE DEBT. It died, and dying paid nothing: the thing it owed walks into
        # the next room of this floor wearing it. Read here, where a room is
        # made, because that is the only moment a fight has a company to buff.
        for enemy in group:
            enemy.stats.max_hp = round(enemy.stats.max_hp * 1.25)
            enemy.stats.hp = enemy.stats.max_hp
            low, high = enemy.stats.damage
            enemy.stats.damage = (low + 2 * state.debt, high + 2 * state.debt)
        state.say(
            "The debt is collected: what comes next is wearing it.",
            LogKind.BAD,
        )
        state.debt = 0
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
        #: The blade a reaver took, held here until the room is done with it.
        self._held_weapon = None
        for enemy in self.enemies:
            if enemy.behaviour == "reaver" and "weapon" in self.hero.equipment:
                # THE REAVER. The free swing is not the weapon; this is. Held
                # and given back when the fight ends -- win, lose or run -- so
                # the fight is a fight without a blade and not a robbery.
                self._held_weapon = self.hero.equipment.pop("weapon")
            elif enemy.behaviour == "notary":
                # THE NOTARY bills the floor: its health is what has already
                # been killed on it. Read when the room opens, because that is
                # when the bill is handed over.
                bill = max(8, state.floor_kills * 4)
                enemy.stats.max_hp = bill
                enemy.stats.hp = bill
        #: Whether the hero has his feet set, which lasts one round.
        self._guarded = False
        #: Armour lent by a trick for the length of the fight, and taken back
        #: when the room is done. Kept as a number to subtract rather than added
        #: to the hero's own stat: a stat that is never given back is not a
        #: trick, it is an upgrade the player did not pay for.
        self._round_armour = 0
        #: When each combatant is next up, in the same kind of units the
        #: dungeon's own queue uses: every turn costs ``1 / speed``, so a quick
        #: hero's turns come round sooner and he simply gets more of them. A
        #: *round* would hand the slow hero the same number of turns as the quick
        #: one, which is the one thing speed in this game is not allowed to mean.
        self._pace: dict[int, float] = {}
        #: Who has taken a turn in the round being resolved, and in what order.
        #: The queue is a set of paces, and paces do not read out loud: this is
        #: what the arena's order strip counts down.
        self._turns: list[Actor] = []
        self.over = False
        self.won = False
        self.escaped = False
        #: The first landing blow of the fight is a fact about the *fight*, not
        #: about each monster: THE FIRST BLOW says "of a fight" and paid seven
        #: once per target, so a room of three paid it three times.
        state.first_blow_spent = False
        #: Whether the round is standing still, waiting on the hero. The one
        #: piece of bookkeeping that makes a *round* out of everybody's turns:
        #: the hero's command is the command of his place in it, and the round
        #: does not hand him a second turn for free.
        self._hero_up = False
        #: Whether the hero has taken a turn yet. The dungeon's counters -- a salt
        #: circle, a borrowed face -- were raised *before* the fight and cover its
        #: first turn, so the lapse waits until he has taken one; what the fight
        #: raises itself ("this round") lapses at his next turn, which is where the
        #: dungeon's own tail ticks them too.
        self._settled = False
        #: BETWEEN BLOWS: until the end of this round, nothing finds the hero.
        self._unseen = False
        #: THE HOARFROST: until the end of this round, whoever lands a blow on him
        #: takes the cold home with them.
        self._frost = False
        #: And the floor stops taking turns while the fight is open: the room is
        #: what answers a turn spent in it. See ``GameState.in_fight``, and
        #: ``_close_the_fight`` for the other end of it.
        state.in_fight = True
        if state.ravaging:
            # THE RAVAGING FIRE. Everything that reaches him is already burning
            # when it gets there -- applied here, where a fight is *built*,
            # because that is what the promise is: not the monsters standing on
            # the floor when he lit it, but every one of them that ever comes at
            # him while it burns.
            for enemy in self.enemies:
                inflict(state, enemy, ("burn",), source=state.player)

    # -- what the hero is offered -------------------------------------------
    def commands(self) -> list[str]:
        """The five verbs. None of them is ever withheld.

        A verb that says why it will not work teaches the rule; a verb that is
        missing from the menu teaches nothing, and leaves the player wondering
        whether they misremembered the game or the game forgot them.
        """
        return list(VERBS)

    def specials(self) -> list[Special]:
        """The hero's own five, in the order a fight offers them.

        Per hero and not per game: the tricks follow whoever is standing there,
        because Yeti's glacier is not Noxx's shadow and a menu of somebody else's
        moves is a menu with nothing in it.
        """
        return list(specials_for(self.state.hero.key))

    def learned(self) -> list[Special]:
        """The tricks the hero has *learned*: which is what the menu shows.

        Not the same question as :meth:`special_available`, which also asks the
        purse. A trick he knows but cannot afford belongs on the menu -- dimmed,
        with its price beside it -- because the price is the decision, and a
        decision nobody can see is not one. A trick he has not learned yet is not
        on the menu at all: a list of names a player cannot use is a list of
        spoilers.
        """
        return [one for one in self.specials() if self.has_learned(one)]

    def has_learned(self, special: Special) -> bool:
        """Whether the level has taught him this one. Nothing to do with money."""
        return self.state.level >= learned_at(special, self.state.ultimate_level)

    def special_ready(self, special: Special | None = None) -> bool:
        """Whether the dark would answer -- this one, or any of them.

        Asked by the menu, which dims what cannot be spent rather than letting
        the player spend a turn finding out. The gate itself is the dungeon's.
        """
        if special is not None:
            return self.special_available(special)
        return any(self.special_available(one) for one in self.specials())

    def special_available(self, special: Special) -> bool:
        """Whether this one can be spent, right now.

        Two questions, and both of them are the player's: has the level *taught*
        it, and is it *affordable* out of the kill points he has left. There is
        no third -- no once-a-fight tally, no floor the dark has already had. One
        purse for the whole kit, every trick priced against it, so the only thing
        that ever stops a trick is its price, and the price is the choice.

        The level the dark answers at is still the *gate* on the ultimate (see
        `learned_at`), which is the one place a test can lower it: `--testrun`
        runs make the dark speak at level one, and a run the dark talks through
        does not keep the hero's tricks secret.
        """
        return self.has_learned(special) and self.state.kill_points >= special.cost

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
        if self._held_weapon is not None:
            events.append(
                Said(
                    "The reaver takes your blade out of your hand. It gives it "
                    "back when the room is done.",
                    LogKind.BAD,
                )
            )
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
        # The round about to be played, from its first turn to its last: a fight
        # that opens with a monster acting has to say so *first*, because that is
        # the order the blows are about to arrive in.
        self._turns = []
        if self.over:
            return events
        if not self._hero_up:
            self._advance(events)
        if self.over:
            return events
        self._hero_up = False
        self._turns.append(self.hero)
        # And the clock. A fight used to be *free*: no turn, no time, no score --
        # which made killing score-positive and the speed bonus a lie, because
        # ``KILL_SCORE`` is calibrated against "a fight costs fifty to ninety
        # points" and it cost nothing at all. One hero command is one turn here,
        # exactly as one step is one turn on the floor.
        self.state.turn += 1
        self.state.total_turns += 1
        #: BETWEEN BLOWS: until the end of this round, nothing finds the hero.
        self._unseen = False
        #: THE HOARFROST: until the end of this round, whoever lands a blow on him
        #: takes the cold home with them.
        self._frost = False
        if self._hero_acts(command, target, events, special):
            self._advance(events)
        return events

    # -- the round ----------------------------------------------------------
    def _advance(self, events: list[Event]) -> None:
        """Let the queue run until the hero is up, or until it is decided.

        Everything that runs out *by the turn* runs out here, once per hero turn
        -- the statuses, the borrowed face, the salt circle, the guard -- which is
        exactly where the dungeon ticks them, one player turn at a time.
        """
        while True:
            if self._decide(events):
                return
            actor = self._next()
            if actor is self.hero:
                if self._settled:
                    self._lapse(events)
                    # And what the wounds did, at the end of them. A monster that
                    # *bled to death* at the start of this turn is the last one
                    # dead -- and the fight has to be decided here, or the player
                    # is left standing in a room with nothing in it, swinging at
                    # nothing, twice, before the fight admits it is over. This
                    # was the whole of "the fight does not end straight away,
                    # sometimes": it was everything to do with the statuses.
                    if self._decide(events):
                        return
                self._settled = True
                self._hero_up = True
                # And the purse fills, one point a turn of his own. Which makes
                # the cheap tricks a rhythm and the dear ones a plan -- and makes
                # a quick hero richer in them, on top of getting more turns.
                if not self._hushed():
                    # THE HUSH: while it lives the dark does not pay. A hero is
                    # his tricks, and this takes them away without touching his
                    # health.
                    self.state.kill_points = min(
                        self.state.kill_points_max, self.state.kill_points + 1
                    )
                return
            self._turns.append(actor)
            self._enemy_acts(actor, events)

    @property
    def drinks_refused(self) -> bool:
        """Whether a quiet has the hero's mouth closed.

        The rule as a question rather than as a refusal: a caller that has to
        *ask* -- the bot does, before it picks the bottle -- must be able to get
        the answer without spending a turn to be told no.
        """
        return any(
            one.behaviour == "quiet" and one.stats.alive for one in self.enemies
        )

    def _hushed_drink(self) -> bool:
        """Whether a quiet has the hero's mouth closed. Says so, and takes nothing."""
        quiet = next(
            (
                one
                for one in self.enemies
                if one.behaviour == "quiet" and one.stats.alive
            ),
            None,
        )
        if quiet is None:
            return False
        before = len(self.state.log)
        self.state.say(
            f"The {quiet.name} has your voice. The bottle stays corked.",
            LogKind.BAD,
        )
        self._splice(before, [])
        return True

    def _hushed(self) -> bool:
        """Whether a hush is standing: no kill point is paid while it is."""
        return any(
            one.stats.alive and one.behaviour == "hush" for one in self.enemies
        )

    def _next(self) -> Actor:
        """Whose turn it is: whoever's own pace is up.

        The dungeon answers this with a queue that divides its interval by speed,
        which is what makes a quick hero act more often than a slow one. The arena
        answers it the same way, with the same number -- `Actor.speed` is the same
        property, statuses folded in -- or Noxx's whole identity (1.5 against
        Yeti's 0.75) would buy him nothing but going first.
        """
        living = [one for one in [self.hero, *self.enemies] if one.stats.alive]
        for one in living:
            # First time in the queue, a combatant waits its own speed's worth --
            # so the quickest opens the fight, and the slowest watches him do it.
            self._pace.setdefault(id(one), 1.0 / max(0.1, one.speed))
        actor = min(living, key=lambda one: self._pace[id(one)])
        self._spend(actor)
        return actor

    def _spend(self, actor: Actor) -> None:
        """Charge an actor for the turn it is taking: its own speed's worth."""
        self._pace[id(actor)] = self._pace.get(id(actor), 0.0) + 1.0 / max(
            0.1, actor.speed
        )

    def _lapse(self, events: list[Event]) -> None:
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
        self._frost = False
        self._guarded = False
        # And the wounds run, for everybody: a poison hurt on the victim's own
        # turn on the map, and a round is the arena's turn. Without this a bleed
        # would be a sentence the fight never read out.
        for actor in [self.hero, *self.enemies]:
            if not actor.stats.alive:
                continue
            # What is *going* to run, taken before it runs: the tick spends the
            # wound down as it reads it, and a status on its last turn would be
            # gone by the time anything could say it had bitten. The screen needs
            # to be told, or the only sign of a bleed would be a line of text.
            biting = [
                key
                for key in actor.statuses
                if (status := status_by_key(key)) is not None and status.damage
            ]
            before = len(self.state.log)
            tick_statuses(self.state, actor)
            # And the fight *says* it: "the ghoul is bleeding. 2." was being
            # written into the run's log and never reaching the arena's, so a
            # wound cost the monster health in a fight where nobody ever
            # mentioned it.
            self._splice(before, events)
            for key in biting:
                # One flourish per wound, on the one it is happening *to* -- which
                # for a status is anybody in the room, not the hero.
                events.append(Flourish(actor, key))

        # And the void's own creature, who is not in this queue and never was:
        # on the floor he goes from prey to prey, and a room is only a smaller
        # floor. One strike each round -- a fight is five to nine rounds against
        # the map's forty turns, so the floor's cadence would have him swing at
        # nothing at all.
        struck = _advance_atritas(self.state, swing_every=1)
        if struck is not None:
            events.append(
                ShadowStruck(struck, killed=not struck.stats.alive)
            )

        self._the_judge_reads(events)
        self._the_eater_eats(events)

    def _the_judge_reads(self, events: list[Event]) -> None:
        """THE JUDGE reads the hero's curses out loud, and each one costs a point.

        It never swings; this is the whole of what it does, and it is the only
        monster that makes a fat collection of curses -- the fame build -- into a
        liability. Capped at three, because thirteen curses at a point a round is
        not a judgement, it is an execution.
        """
        judge = next(
            (
                one
                for one in self.enemies
                if one.behaviour == "judge" and one.stats.alive
            ),
            None,
        )
        if judge is None or not self.state.curses:
            return
        words = min(3, len(self.state.curses))
        before = len(self.state.log)
        self.state.say(
            f"The {judge.name} reads your curses aloud. {words}.",
            LogKind.DAMAGE,
        )
        self.hero.stats.hp = max(0, self.hero.stats.hp - words)
        self.state.hits.append(self.hero.position)
        self._splice(before, events)

    def _the_eater_eats(self, events: list[Event]) -> None:
        """THE EATER takes a wound off one of its own and grows on it.

        One stack a round, off somebody who is not itself: a status build in its
        room starves, and the room has to decide whether the eater or the wound
        is the problem. Four health a stack, which is what makes a deep bleed
        worth eating.
        """
        for eater in [
            one
            for one in self.enemies
            if one.behaviour == "eater" and one.stats.alive
        ]:
            prey = next(
                (
                    one
                    for one in self.enemies
                    if one is not eater
                    and one.stats.alive
                    and one.statuses
                ),
                None,
            )
            if prey is None:
                continue
            key = sorted(prey.statuses)[0]
            depth = max(1, prey.status_stacks.get(key, 1))
            if depth > 1:
                prey.status_stacks[key] = depth - 1
            else:
                del prey.statuses[key]
                prey.status_stacks.pop(key, None)
            healed = eater.stats.heal(4 * depth)
            tail = f" and puts {healed} back" if healed else ""
            before = len(self.state.log)
            self.state.say(
                f"The {eater.name} eats the {key} out of the {prey.name}{tail}.",
                LogKind.BAD,
            )
            self._splice(before, events)

    def turns(self) -> list[Actor]:
        """Who took a turn in the round just resolved, in the order they took it.

        The hero first and then the room: this is the round the arena is about to
        *play*, which is what the order strip at the bottom counts down.
        """
        return list(self._turns)

    def upcoming(self, count: int = 3) -> list[Actor]:
        """Who is up next, and after them, and after them -- without spending it.

        Simulated and not saved: the queue is a set of paces that every turn
        *spends*, and this reads them forward and gives them back. Two numbers
        decide it -- who is up, which is the lowest pace, and what a turn costs
        them, which is their own speed's worth -- and they are the same two the
        fight itself uses. A strip drawn any other way would be a decoration that
        lied about the fight it is standing in, and the whole reason to show a
        player the order is that they can plan with it.
        """
        pace = dict(self._pace)
        living = [one for one in [self.hero, *self.enemies] if one.stats.alive]
        for one in living:
            pace.setdefault(id(one), 1.0 / max(0.1, one.speed))
        # The turn *in flight* comes first. While the hero is up, the queue has
        # already charged him for the turn he has not taken yet -- that is how
        # `_advance` finds him -- so the paces describe what comes after it and
        # the turn itself would be missing from the strip. Which is exactly the
        # jump a player sees otherwise: the hero's turn drops off the front when
        # he swings and slides back in when the room settles.
        ahead: list[Actor] = []
        if self._hero_up and self.hero.stats.alive:
            ahead.append(self.hero)
        while len(ahead) < max(0, count):
            if not living:
                break
            who = min(living, key=lambda one: pace.get(id(one), 0.0))
            ahead.append(who)
            pace[id(who)] = pace.get(id(who), 0.0) + 1.0 / max(0.1, who.speed)
        return ahead[: max(0, count)]

    def _order(self) -> list[Actor]:
        """Who is up next, and after them, and after them.

        Not a round: the arena has none. This is the order the queue *will*
        produce, which is what the fight's flourishes are read against -- and what
        a test can ask about without playing the turns out.
        """
        living = [one for one in [self.hero, *self.enemies] if one.stats.alive]
        return sorted(living, key=lambda one: self._pace.get(id(one), 0.0))

    def _decide(self, events: list[Event]) -> bool:
        """Whether the fight is over, saying so once. True means stop."""
        if self.over:
            return True
        if not self.hero.stats.alive:
            self.over = True
            self._close_the_fight()
            events.append(Over(won=False))
            return True
        if not self.living_enemies():
            self.over = True
            self.won = True
            self._close_the_fight()
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
            outcome = resolve_player_attack(
                self.state, enemy, damage_scale=PLAIN_SWING, wield=True
            )
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
            if self._hushed_drink():
                return False
            result = perform_action(self.state, Action.QUAFF)
            self._splice(before, events)
            return result.consumed_turn

        if command == FLEE:
            self._flee(events)
            return False

        return False

    # -- the hero's five tricks ---------------------------------------------
    def _first_ready(self) -> Special | None:
        """The first of the five that can be spent, for a caller with no opinion."""
        for special in self.specials():
            if self.special_available(special):
                return special
        return None

    def _special_refusal(self, special: Special | None) -> str:
        """Why the dark will not do this one, in the dungeon's own words.

        Two ways to be turned down, and they are different sentences: a trick the
        level has not taught yet is a *distance*, and a trick he cannot afford is
        a *wait*. The player can act on either, but only if the fight says which.
        """
        if special is None:
            return "The dark has nothing left to spend here."
        if not self.has_learned(special):
            gate = learned_at(special, self.state.ultimate_level)
            return f"Not yet. {special.name} arrives at level {gate}."
        if self.state.kill_points < special.cost:
            return (
                f"{special.name} costs {special.cost} kill points. "
                f"You have {self.state.kill_points}."
            )
        return "The dark is quiet."

    def _run_special(self, special: Special, target: Actor | None, events: list[Event]) -> None:
        """Spend one of the five, through the same blow as everything else.

        Every one of them ends in `resolve_player_attack`, because that is where
        a blow in this game is resolved: a special that swung with its own dice
        would disagree with the dungeon about what a curse or a gift is worth.
        """
        run = {
            LEFT_HAND: self._special_left_hand,
            ORB_OF_PTAMERA: self._special_orb_of_ptamera,
            FLEETING_SHADOW: self._special_fleeting_shadow,
            DEVOURING_DARKNESS: self._special_devouring_darkness,
            PAINT_THE_WALLS_RED: self._special_paint_the_walls_red,
            OPEN_VEIN: self._special_open_vein,
            SNOW_BLIND: self._special_snow_blind,
            QUAKE: self._special_quake,
            LONG_WINTER: self._special_long_winter,
            OVERTURE: self._special_overture,
            CHORD: self._special_ringing_chord,
            SILENCE: self._special_silence_after,
            BETWEEN_BLOWS: self._special_between_blows,
            AVALANCHE: self._special_avalanche,
            RIME: self._special_rime,
            HOARFROST: self._special_hoarfrost,
            STILLNESS: self._special_stillness,
            FIRST_NOTE: self._special_first_note,
            BELLS_THROW: self._special_bells_throw,
            TRUE_NOTE: self._special_true_note,
            ECHOING_CUT: self._special_echoing_cut,
            JAB: self._special_jab,
            GUT_PUNCH: self._special_gut_punch,
            EMBER_FIST: self._special_ember_fist,
            HEADBUTT: self._special_headbutt,
            RED_MIST: self._special_red_mist,
            HAYMAKER: self._special_haymaker,
            ROUNDHOUSE: self._special_roundhouse,
        }[special.key]
        run(target, events)
        # Paid on the way out, and only if it went off: a trick the fight refused
        # never got here, and a refusal that cost money would be a punishment for
        # asking a question.
        if special.cost:
            self.state.kill_points = max(0, self.state.kill_points - special.cost)

    def _blow(
        self,
        enemy: Actor,
        events: list[Event],
        *,
        flair: str = "",
        force_crit: bool = False,
        crit_bonus: float = 0.0,
        bonus: int = 0,
        damage_scale: float = 1.0,
    ) -> AttackOutcome:
        """One hero's blow, said and shown, with the trick's own word on it."""
        before = len(self.state.log)
        outcome = resolve_player_attack(
            self.state,
            enemy,
            force_crit=force_crit,
            crit_bonus=crit_bonus,
            bonus=bonus,
            damage_scale=damage_scale,
            # A trick is not the weapon: what the sword does it does when it is
            # swung, and a spell that carried the sword's wound as well would make
            # every trick a delivery service for the thing in his hand.
            wield=False,
        )
        self._splice(before, events)
        events.append(Struck(self.hero, enemy, outcome, flair=flair))
        return outcome

    def _special_left_hand(self, target: Actor | None, events: list[Event]) -> None:
        """The dagger, and what it leaves in: a plain cut, and a poison.

        It used to make sure of its stab -- a forced crit and a flat bonus -- and
        that was the wrong promise for the cheapest trick in the kit. A small
        certain hit is a small certain hit; poison is not a bigger blow at all,
        it is a reason to open with this one and a thing that keeps working while
        the purse fills.
        """
        enemy = self._pick(target)
        if enemy is None:
            return
        outcome = self._blow(enemy, events, flair=LEFT_HAND)
        # A wound needs a wound *to be in*: a dagger that missed cannot leave
        # poison in anybody, for the same reason a sword that missed cannot
        # leave a cut. The weapon's own effects have always been gated on the
        # hit -- the *tricks* were not, which is the inconsistency this closes.
        if outcome.hit and enemy.stats.alive:
            before = len(self.state.log)
            inflict(self.state, enemy, ("poison",), source=self.hero)
            self._splice(before, events)

    def _special_orb_of_ptamera(self, target: Actor | None, events: list[Event]) -> None:
        """The orb: a dark thing thrown instead of carried, and loaded for the throat.

        The only trick in the game that reaches into the *odds* rather than the
        numbers: it is not a promised crit, it is a blow that hunts one, which is
        what makes it the knife's opposite and not its bigger brother.
        """
        enemy = self._pick(target)
        if enemy is None:
            return
        before = len(self.state.log)
        self.state.say("The orb leaves your hand and goes for him.", LogKind.SYSTEM)
        self._splice(before, events)
        self._blow(enemy, events, flair=ORB_OF_PTAMERA, crit_bonus=ORB_CRIT)

    def _special_fleeting_shadow(self, target: Actor | None, events: list[Event]) -> None:
        """Out -- and not the way a run is out.

        Fleeing is the floor noticing: everything standing gets a swing at the
        hero's back, which is the whole price of turning around. This is nobody
        noticing. He is not in the room before anything in it moves, and nothing
        in it gets to answer for that.
        """
        before = len(self.state.log)
        self.state.say("You are somewhere else before they move.", LogKind.GOOD)
        self._splice(before, events)
        events.append(Flourish(self.hero, FLEETING_SHADOW))
        self.over = True
        self.escaped = True
        self.won = False
        # Every way out of a fight hands the floor its turns back, this one too:
        # without it the dungeon stayed frozen behind a fight that had ended.
        self._close_the_fight()
        events.append(Over(won=False, escaped=True))

    def _special_devouring_darkness(self, target: Actor | None, events: list[Event]) -> None:
        """It eats him, and he keeps what it ate.

        Half of what the bite took, and never nothing: a mouthful of a mouthful
        is still a mouthful, and a steal that rounded down to zero would be a
        sentence the fight did not mean.
        """
        enemy = self._pick(target)
        if enemy is None:
            return
        outcome = self._blow(enemy, events, flair=DEVOURING_DARKNESS)
        if not outcome.hit:
            return
        kept = max(1, round(outcome.damage * SIPHON))
        # `stats.heal` and not the draught path: FAMINE is worded as "half of what
        # every draught is worth", and this is not a draught. What the dark bites
        # out of a monster is not something a curse about bottles can reach.
        gained = self.hero.stats.heal(kept)
        before = len(self.state.log)
        if gained:
            self.state.say(f"You keep {gained} of it.", LogKind.GOOD)
        else:
            self.state.say("There is nothing left of you to give it back to.", LogKind.PLAIN)
        self._splice(before, events)
        events.append(Flourish(self.hero, DEVOURING_DARKNESS))

    def _special_paint_the_walls_red(self, target: Actor | None, events: list[Event]) -> None:
        """Atritas comes, and he does not come alone.

        On *every* one of them, and three wounds deep: the vein's own cut is a
        single stack, and this is the deepest a wound goes -- four a turn for
        four turns, times three. A room of three opened at once is a room that is
        over before the floor runs dry.
        """
        before = len(self.state.log)
        self.state.say("Atritas comes, and he does not come alone.", LogKind.SYSTEM)
        self._splice(before, events)
        events.append(Flourish(self.hero, PAINT_THE_WALLS_RED))
        for enemy in self.living_enemies():
            before = len(self.state.log)
            self.state.say(f"Something in the {enemy.name} opens.", LogKind.GOOD)
            inflict(
                self.state,
                enemy,
                (DEEP_BLEED,),
                stacks=STACK_LIMIT,
                source=self.hero,
            )
            self._splice(before, events)

    def _special_open_vein(self, target: Actor | None, events: list[Event]) -> None:
        """A cut that will not close: small, and it keeps costing him."""
        enemy = self._pick(target)
        if enemy is None:
            return
        outcome = self._blow(enemy, events, flair=OPEN_VEIN)
        if outcome.hit and enemy.stats.alive:
            before = len(self.state.log)
            # Two stacks and not one: the vein is the *cut that will not close*,
            # and a blade that opens it for the same single wound every other
            # blade leaves was the cheapest sentence in Noxx's kit.
            inflict(self.state, enemy, ("bleed",), stacks=2, source=self.hero)
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

    def _special_snow_blind(self, target: Actor | None, events: list[Event]) -> None:
        """A cut, and it loses its place: the snow takes its eyes for a moment.

        The bell's throw in Yeti's hands -- the same shove back down the queue and
        no bell to do it with. What a mountain has instead of a note.
        """
        enemy = self._pick(target)
        if enemy is None:
            return
        before = len(self.state.log)
        self.state.say("The snow takes the light out of the room.", LogKind.SYSTEM)
        self._splice(before, events)
        outcome = self._blow(enemy, events, flair=SNOW_BLIND)
        if outcome.hit and enemy.stats.alive:
            self._throw_back(enemy)

    def _special_quake(self, target: Actor | None, events: list[Event]) -> None:
        """The floor answers: everything standing takes it, at seventy percent.

        An area trick and priced like one. Against a single monster it is a
        *worse* blow than the avalanche for twice the points, which is the whole
        of the choice: the crowd is what pays for it.
        """
        before = len(self.state.log)
        self.state.say("He puts the mountain into the floor.", LogKind.SYSTEM)
        self._splice(before, events)
        for enemy in self.living_enemies():
            if not self.hero.stats.alive:
                break
            self._blow(enemy, events, flair=QUAKE, damage_scale=QUAKE_SCALE)

    def _special_long_winter(self, target: Actor | None, events: list[Event]) -> None:
        """The cold comes in and stays: a cut on each of them, and the chill with it.

        The rime's own wound, handed out to the room: slow legs for everyone, and
        a little damage while it settles.
        """
        before = len(self.state.log)
        self.state.say("The cold comes in and does not leave.", LogKind.SYSTEM)
        self._splice(before, events)
        for enemy in self.living_enemies():
            if not self.hero.stats.alive:
                break
            outcome = self._blow(
                enemy, events, flair=LONG_WINTER, damage_scale=WINTER_SCALE
            )
            if outcome.hit and enemy.stats.alive:
                before = len(self.state.log)
                inflict(self.state, enemy, ("chill",), source=self.hero)
                self._splice(before, events)

    def _special_overture(self, target: Actor | None, events: list[Event]) -> None:
        """The first bar is for everyone in the room: a note on all of them."""
        before = len(self.state.log)
        self.state.say("He strikes the first bar, and the room hears it.", LogKind.SYSTEM)
        self._splice(before, events)
        for enemy in self.living_enemies():
            if not self.hero.stats.alive:
                break
            self._blow(enemy, events, flair=OVERTURE, damage_scale=OVERTURE_SCALE)

    def _special_ringing_chord(self, target: Actor | None, events: list[Event]) -> None:
        """Three notes at once, and the last of them is the floor: a heavy blow,
        and what it lands on is thrown off its feet."""
        enemy = self._pick(target)
        if enemy is None:
            return
        before = len(self.state.log)
        self.state.say(
            "Three notes at once, and the last of them is the floor.", LogKind.SYSTEM
        )
        self._splice(before, events)
        outcome = self._blow(enemy, events, flair=CHORD, damage_scale=CHORD_SCALE)
        if outcome.hit and enemy.stats.alive:
            self._throw_back(enemy)

    def _special_silence_after(self, target: Actor | None, events: list[Event]) -> None:
        """He stops playing: every one of them loses its place, and takes a little.

        Not damage -- *order*. The room is put back to the far end of the queue,
        which is worth more than a blow when there are three of them and one of him.
        """
        before = len(self.state.log)
        self.state.say("He stops, and the room has lost its place.", LogKind.SYSTEM)
        self._splice(before, events)
        for enemy in self.living_enemies():
            if not self.hero.stats.alive:
                break
            outcome = self._blow(enemy, events, flair=SILENCE, damage_scale=SILENCE_SCALE)
            if outcome.hit and enemy.stats.alive:
                self._throw_back(enemy)


    def _special_avalanche(self, target: Actor | None, events: list[Event]) -> None:
        """The hammer, with the mountain behind it: slow, and it lands hard."""
        enemy = self._pick(target)
        if enemy is not None:
            self._blow(enemy, events, flair=AVALANCHE, damage_scale=AVALANCHE_SCALE)

    def _special_rime(self, target: Actor | None, events: list[Event]) -> None:
        """A shallow cut, and the cold gets into the legs: it acts later now."""
        enemy = self._pick(target)
        if enemy is None:
            return
        outcome = self._blow(enemy, events, flair=RIME)
        if outcome.hit and enemy.stats.alive:
            before = len(self.state.log)
            inflict(self.state, enemy, ("chill",), source=self.hero)
            self._splice(before, events)

    def _special_hoarfrost(self, target: Actor | None, events: list[Event]) -> None:
        """He does not swing: this round, the cold answers for him."""
        before = len(self.state.log)
        self.state.say("You let the cold do the answering.", LogKind.GOOD)
        self._splice(before, events)
        self._frost = True

    def _special_stillness(self, target: Actor | None, events: list[Event]) -> None:
        """He sets his feet: half of everything that lands, and the ice under it."""
        self._guarded = True
        self.state.player.stats.armor += STILLNESS_ARMOUR
        self._round_armour += STILLNESS_ARMOUR
        before = len(self.state.log)
        self.state.say("You set your feet, and the ice does not care.", LogKind.GOOD)
        self._splice(before, events)
        events.append(Flourish(self.hero, STILLNESS))


    def _special_first_note(self, target: Actor | None, events: list[Event]) -> None:
        """One cut, and the note of it carries to whatever is behind him."""
        enemy = self._pick(target)
        if enemy is None:
            return
        outcome = self._blow(enemy, events, flair=FIRST_NOTE)
        others = [one for one in self.living_enemies() if one is not enemy]
        if outcome.hit and others:
            # The note carries *because* it was struck. Miss, and there is no
            # note to carry.
            self._blow(others[0], events, flair=FIRST_NOTE, damage_scale=0.6)

    def _throw_back(self, enemy: Actor) -> None:
        """Send what was struck to the back of the queue.

        It is not removed from the fight, only put behind everyone still to come:
        its own pace is set past the furthest one, so the next turn it takes is
        after theirs. Being thrown *back* and not *out* is the whole of the bell's
        promise -- the dungeon's version does not remove anything either, it only
        makes it walk back.
        """
        for one in [self.hero, *self.enemies]:
            self._pace.setdefault(id(one), 1.0 / max(0.1, one.speed))
        self._pace[id(enemy)] = max(self._pace.values()) + 0.001

    def _special_bells_throw(self, target: Actor | None, events: list[Event]) -> None:
        """The ring of it throws what it lands on to the back of the round."""
        enemy = self._pick(target)
        if enemy is None:
            return
        outcome = self._blow(enemy, events, flair=BELLS_THROW)
        if outcome.hit and enemy.stats.alive:
            self._throw_back(enemy)
            before = len(self.state.log)
            self.state.say("The ring of it throws him back on his heels.", LogKind.GOOD)
            self._splice(before, events)

    def _special_true_note(self, target: Actor | None, events: list[Event]) -> None:
        """He finds the note the sword is for, and keeps it: every blow after."""
        # Its own field: ``damage_bonus`` is REVENGE's, and a kill rewrites it
        # (``apply_revenge`` sets rather than adds). The note was being erased by
        # the next monster that died.
        self.state.player.note_bonus += TRUE_NOTE_DAMAGE
        before = len(self.state.log)
        self.state.say("You find the note the sword is for.", LogKind.GOOD)
        self._splice(before, events)
        events.append(Flourish(self.hero, TRUE_NOTE))

    def _special_echoing_cut(self, target: Actor | None, events: list[Event]) -> None:
        """The cut lands once and is heard three times."""
        enemy = self._pick(target)
        if enemy is None:
            return
        self._blow(enemy, events, flair=ECHOING_CUT)
        for other in self.living_enemies():
            if other is not enemy:
                self._blow(other, events, flair=ECHOING_CUT, damage_scale=0.5)

    # -- Inferno: the weight of a fist -------------------------------------
    def _special_jab(self, target: Actor | None, events: list[Event]) -> None:
        """The cheapest thing in the game: a light hand with two more behind it.

        A plain swing and a little, which is exactly the point -- a trick this
        cheap is a trick you press twice rather than save for, and a hero with no
        armour and the smallest body in the roster needs one of those.
        """
        enemy = self._pick(target)
        if enemy is not None:
            self._blow(
                enemy,
                events,
                flair=JAB,
                damage_scale=PLAIN_SWING,
                bonus=JAB_BONUS,
            )

    def _special_gut_punch(self, target: Actor | None, events: list[Event]) -> None:
        """A body blow: more than a swing, and something inside gives way."""
        enemy = self._pick(target)
        if enemy is None:
            return
        before = len(self.state.log)
        self.state.say("He puts his hand in where the ribs stop.", LogKind.SYSTEM)
        self._splice(before, events)
        outcome = self._blow(
            enemy, events, flair=GUT_PUNCH, damage_scale=GUT_PUNCH_SCALE
        )
        if outcome.hit and enemy.stats.alive:
            before = len(self.state.log)
            inflict(self.state, enemy, ("bleed",), source=self.hero)
            self._splice(before, events)

    def _special_ember_fist(self, target: Actor | None, events: list[Event]) -> None:
        """The burning hand: a heavy blow, and the fire it leaves is why.

        The one rider in his kit, and his own element: everything he does is
        damage, and this is the damage that keeps being dealt after the turn is
        over.
        """
        enemy = self._pick(target)
        if enemy is None:
            return
        before = len(self.state.log)
        self.state.say("His hand comes up already burning.", LogKind.SYSTEM)
        self._splice(before, events)
        outcome = self._blow(
            enemy, events, flair=EMBER_FIST, damage_scale=EMBER_FIST_SCALE
        )
        if outcome.hit and enemy.stats.alive:
            before = len(self.state.log)
            inflict(self.state, enemy, ("burn",), source=self.hero)
            self._splice(before, events)

    def _special_headbutt(self, target: Actor | None, events: list[Event]) -> None:
        """The hardest thing he has, and it is paid for in his own blood."""
        enemy = self._pick(target)
        if enemy is None:
            return
        before = len(self.state.log)
        self.state.say("He puts his own brow into it.", LogKind.SYSTEM)
        self._splice(before, events)
        self._blow(enemy, events, flair=HEADBUTT, damage_scale=HEADBUTT_SCALE)
        self._in_his_blood(
            max(1, round(self.state.player.stats.max_hp * HEADBUTT_BLOOD)), events
        )

    def _special_red_mist(self, target: Actor | None, events: list[Event]) -> None:
        """The red comes down: a blow that grows with what he has already lost.

        At full health it is barely a swing and at the edge of dying it is close
        to three of them, which is the only shape a rage can have that is not
        simply a better attack: it has to be worth *losing* for.
        """
        enemy = self._pick(target)
        if enemy is None:
            return
        player = self.state.player
        missing = 1.0 - (player.stats.hp / max(1, player.stats.max_hp))
        before = len(self.state.log)
        self.state.say("The red comes down over everything.", LogKind.SYSTEM)
        self._splice(before, events)
        self._blow(
            enemy,
            events,
            flair=RED_MIST,
            damage_scale=RED_MIST_SCALE + RED_MIST_RAGE * missing,
        )

    def _special_haymaker(self, target: Actor | None, events: list[Event]) -> None:
        """The whole floor goes into it: the heaviest single blow in the game.

        No rider, no wound and no second chance -- two blows' worth in one, which
        is what he is for and the reason the price is what it is.
        """
        enemy = self._pick(target)
        if enemy is not None:
            self._blow(enemy, events, flair=HAYMAKER, damage_scale=HAYMAKER_SCALE)

    def _special_roundhouse(self, target: Actor | None, events: list[Event]) -> None:
        """He turns once: everything standing takes it, at seventy percent.

        Priced like the other two area tricks and for the same reason -- worse
        than the haymaker against one monster and much better against three.
        """
        before = len(self.state.log)
        self.state.say("He turns once, and everything is in the way.", LogKind.SYSTEM)
        self._splice(before, events)
        for enemy in self.living_enemies():
            if not self.hero.stats.alive:
                break
            self._blow(
                enemy, events, flair=ROUNDHOUSE, damage_scale=ROUNDHOUSE_SCALE
            )


    def _in_his_blood(self, amount: int, events: list[Event]) -> None:
        """The price of a wild trick: his own health, and it can be all of it.

        A cost that cannot finish him is not a cost, which is the rule the tithe
        is already written under -- and for a hero whose whole kit is damage on
        a small body, blood is the only currency the fight has not already spent.
        """
        player = self.state.player
        before = len(self.state.log)
        player.stats.hp = max(0, player.stats.hp - amount)
        if player.stats.hp <= 0:
            self.state.die("He puts the last of it into it, and it takes him.")
        else:
            self.state.say(f"It costs him {amount} of his own blood.", LogKind.BAD)
        self._splice(before, events)


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
        if attacker.behaviour in ("unbroken", "judge"):
            # These two never swing: one is a trade and one is a sentence.
            return
        # And it leaves when there is nothing left to take: with an empty purse
        # it can never set ``stolen``, so the old rule kept it in the room until
        # one of the two died -- a purse with nothing in it, fought to the death.
        if (
            attacker.behaviour == "thief"
            and (attacker.stolen or not self.state.gold)
            and attacker.stats.hp * 2 < attacker.stats.max_hp
        ):
            # THE PICKER leaves when it has something to leave with, and it does
            # not wait to be killed for it. The coins are gone; the room is
            # quieter.
            self.enemies.remove(attacker)
            attacker.alive = False
            self.state.say(
                f"The {attacker.name} is gone, and so is what it took.",
                LogKind.BAD,
            )
            return
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
        if self._frost and outcome is not None and outcome.hit and not outcome.killed:
            # THE HOARFROST: the cold comes off him onto whatever touched him.
            inflict(self.state, attacker, ("chill",), source=self.hero)
            self.state.say(
                f"The cold comes off him onto the {attacker.name}.", LogKind.GOOD
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
        self._close_the_fight()
        events.append(Over(won=False, escaped=self.escaped))

    def _close_the_fight(self) -> None:
        """Hand the floor its turns back, now that the room has stopped asking.

        Every way out of a fight comes through here: a win, a death, and a run
        for the dark. The other end of it is the flag going up in ``__init__``,
        and a fight that went out without coming back through here would leave a
        floor that never moves again.
        """
        if self._held_weapon is not None:
            # The blade comes back. A reaver that kept it would be a monster that
            # deletes a find, and this game does not do that.
            self.hero.equipment["weapon"] = self._held_weapon
            self._held_weapon = None
        if self._round_armour:
            # A fight that ends mid-round still gives the borrowed armour back.
            self.state.player.stats.armor -= self._round_armour
            self._round_armour = 0
        self.state.in_fight = False

    # -- plumbing -----------------------------------------------------------
    def _splice(self, before: int, events: list[Event]) -> None:
        """Hand on everything the rules wrote into the log, in order."""
        for entry in self.state.log[before:]:
            events.append(Said(text=entry.text, kind=entry.kind))
