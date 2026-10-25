"""Run state: everything one attempt at the dungeon consists of.

:class:`GameState` owns the map, the actors, the turn queue and the message log.
It is pure data plus queries -- no Textual, no I/O -- which is what lets the
whole game be simulated in a unit test.

A "run" is one life: pick a hero, descend until you die, see the summary.
Permanent progress between runs lives in :mod:`neverdeads_revenge.persistence`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from neverdeads_revenge.core.direction import Direction, Pos, chebyshev
from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.core.turn_queue import TurnQueue
from neverdeads_revenge.world.fov import compute_fov_full
from neverdeads_revenge.world.generator import (
    GeneratedFloor,
    enemy_count,
    generate_floor,
)
from neverdeads_revenge.world.items import ITEMS, make_item
from neverdeads_revenge.world.map import DungeonMap, GroundItem
from neverdeads_revenge.world.modifiers import Modifiers
from neverdeads_revenge.world.tiles import Tile

from .affixes import enemy_affixes
from .actors import (
    ENEMIES,
    Actor,
    ActorKind,
    Hero,
    make_enemy,
    make_hero,
    make_npc,
    pick_enemy_template,
    scale_template,
)
from .combat import apply_revenge
from .levels import (
    SACRIFICED_KILL_POINTS,
    kill_points_for,
    kills_to_next,
)
from .curses import CURSES, Curse
from .difficulty import (
    ATRITAS_VIEW,
    EMBERHEART_PER_STACK,
    BASE_PACK_SLOTS,
    BELL_RING_PER_STACK,
    FORTRESS_VIEW,
    HOARFROST_PER_STACK,
    ULTIMATE_LEVEL,
    potency,
)
from .gifts import GIFTS
from .lore import PAGE_COUNT
from .npcs import NPCS
from .shop import META_UPGRADES, Loadout
from .text import the as _the

__all__ = [
    "LogEntry",
    "LogKind",
    "RunState",
    "GameState",
    "VIEW_RADIUS",
    "ESCAPE_BONUS",
    "KILL_SCORE",
    "FAME_PER_CHEST",
    "TURN_BUDGET_PER_FLOOR",
    "SPEED_BONUS_PER_TURN",
    "CLEANSE_COST",
]

VIEW_RADIUS = 9
"""How far the player can see, in cells."""

#: The health at which THE LAST BREATH turns on: at or below it, the hero's blows
#: land twice and the enemies' find them harder to reach.
#:
#: Three, because it has to be a state a fight can put you in and get you out
#: of -- not a number you aim for. It lives here rather than beside the other
#: gift constants because the *state* asks the question (``GameState.cornered``)
#: and ``game/actions.py`` imports this module, not the other way round.
LAST_BREATH_HP = 3

ESCAPE_BONUS = 5000
"""Score awarded for leaving the dungeon alive instead of dying in it."""

#: Turns a floor is "allowed" before speed stops paying.
#:
#: Measured, not chosen: across 144 bot runs the median floor cost 63 turns and
#: the quickest cost 34, so a budget of 80 leaves most runs scoring something
#: while still going to zero for a slow one. A budget nobody beats is
#: decoration; one everybody beats is noise.
TURN_BUDGET_PER_FLOOR = 80

#: Points a kill is worth, before depth scaling.
#:
#: Deliberately *less than a fight costs in time*. A fight is five to nine
#: player turns -- an approach and the blows; the enemy's own turns cost the
#: player nothing -- and a turn is worth ten points under budget, so a fight
#: costs fifty to ninety. Thirty keeps killing score-*negative*: the score goes
#: on rewarding leaving early and the purse goes on rewarding the fight, and the
#: decision between them stays a decision.
#:
#: A kill worth more than it costs in time turns the game into a floor-sweeper
#: and the speed bonus into a rounding error.
KILL_SCORE = 30

#: What one promise of fame is worth, added to the score multiplier.
#:
#: Added rather than multiplied. A fifth each sounds small, but multiplied it
#: runs away: the top of the board stops being about the run at all.
#:
#: There is no ceiling, and there does not need to be one: a chest is only ever
#: placed for a curse the player has *not* already paid, so the curses themselves
#: are the ceiling. Taking every one of the thirteen is 3.6x on a run that is not
#: going to finish, and a spring can free a curse for another promise, at forty
#: coin and a detour.
FAME_PER_CHEST = 0.20

#: Points per turn saved against that budget.
#:
#: Ten makes the difference between a brisk run and a median one worth roughly a
#: sixth of the total, which is enough to play for and not enough to drown out
#: killing things and getting out alive.
SPEED_BONUS_PER_TURN = 10

#: What the spring charges to take one curse off.
#:
#: A flat price, and deliberately a real one: coin is the only thing in the game
#: that outlives the run, so spending it on the run in progress is a genuine
#: trade rather than a formality. Placeholder, like every other price.
CLEANSE_COST = 40


class LogKind(Enum):
    """Message categories, so the UI can colour them without parsing text."""

    PLAIN = "plain"
    COMBAT = "combat"
    CRIT = "crit"
    DAMAGE = "damage"
    GOOD = "good"
    BAD = "bad"
    SYSTEM = "system"
    #: Coins. Their own kind because they are their own thing in this game --
    #: the one resource that outlives the run -- so the log can colour the
    #: meta-currency apart from loot, and the sound can be a coin rather than a
    #: potion.
    COIN = "coin"


@dataclass(frozen=True, slots=True)
class LogEntry:
    """One line in the message log."""

    text: str
    kind: LogKind = LogKind.PLAIN
    turn: int = 0


class RunState(Enum):
    """Where the run currently stands."""

    PLAYING = "playing"
    DEAD = "dead"
    ESCAPED = "escaped"


@dataclass(slots=True)
class GameState:
    """A run in progress."""

    hero: Hero
    rng: Rng
    seed: int
    depth: int = 1
    dungeon_map: DungeonMap = field(default_factory=lambda: DungeonMap(width=1, height=1))
    player: Actor = None  # type: ignore[assignment]
    enemies: list[Actor] = field(default_factory=list)
    #: Whoever is standing about on this floor. Kept apart from ``enemies``
    #: rather than flagged inside it, because almost everything that walks the
    #: floor asks about enemies and none of it should have to ask twice.
    npcs: list[Actor] = field(default_factory=list)
    turn_queue: TurnQueue = field(default_factory=TurnQueue)
    log: list[LogEntry] = field(default_factory=list)
    turn: int = 0
    total_turns: int = 0
    run_state: RunState = RunState.PLAYING
    kills: int = 0
    #: Kills *on this floor*, which is what THE REAPER'S LEDGER counts. The run's
    #: count never comes back down; this one is emptied every descent, because a
    #: ledger is a page and a page is a floor.
    floor_kills: int = 0
    #: The monsters this run has killed, by template key, in the order they
    #: first died. The dungeon's own record: it does not know what a page is,
    #: and it is the Almanac that decides what a first kill writes down.
    defeated: list[str] = field(default_factory=list)
    #: The blades this run has taken up, by item key, in the order they were
    #: first held. The Armory's record, and deliberately narrower than "seen":
    #: a blade lying on the floor is not one the hero knows.
    found_weapons: list[str] = field(default_factory=list)
    #: Coats this run has put on, for the Wardrobe's page. The same shape as
    #: ``found_weapons``: the book is written from the run, and the run only
    #: remembers what it met so the screen can tell what is new.
    found_armours: list[str] = field(default_factory=list)
    #: Whether the weapon's *first blow* rule has been paid this fight. A fact
    #: about the fight and not about each monster, which is what the blade says.
    first_blow_spent: bool = False
    #: What the run has taught the hero so far. Derived from ``kills`` by
    #: :func:`~neverdeads_revenge.game.levels.level_for`; kept as a field only so
    #: the moment it changes can be noticed and written into the log.
    level: int = 1
    #: Kill points: the purse every trick is paid from, and how much of it is
    #: left. Persistent, like the hero's health and for the same reason -- a
    #: purse that filled itself between fights would make every fight the same
    #: fight, and this one is supposed to be about what you can afford *now*.
    kill_points: int = 0
    revenge_stacks: int = 0
    floors_cleared: int = 0
    #: Draughts carried, not drunk. Survives a descent: it is the run's health
    #: reserve, and a floor that stripped it would make every descent a fresh
    #: start rather than a cost.
    inventory: list[GroundItem] = field(default_factory=list)
    #: What chests have taken. Run-long: there is no cure, so a curse is a
    #: decision made once and lived with.
    curses: list[Curse] = field(default_factory=list)
    #: Coins picked up this run. Banked when the run ends and spent in the shop,
    #: which is why it is kept apart from the score: one is a record of the run,
    #: the other is what the run was worth to you afterwards.
    gold: int = 0
    #: The page numbers still to be found, from the book's point of view.
    #:
    #: Handed in when the run starts and drawn down as pages turn up, so a page
    #: never appears twice -- not on two floors of one run and not in two runs
    #: either. It is the *book* that decides, and the book is the only thing
    #: that outlives the run.
    missing_pages: set[int] = field(default_factory=set)
    #: What this run has found, in the order it found them. The app folds these
    #: into the book the moment they are picked up, and this is how it knows
    #: there is something to fold.
    found_pages: list[int] = field(default_factory=list)
    #: Promises of fame taken at chests. Each one is a curse paid for a bigger
    #: score rather than for the loot behind the lid, and each one raises what
    #: the whole run is worth. Kept as a count rather than as a multiplier so the
    #: summary can say how many promises it was.
    fame: int = 0
    #: Cells a blow landed on since the player's last action, for the map to
    #: flash. A UI-facing field like ``log``, and here for the same reason: the
    #: domain knows where a blow landed and the map is the only thing that can
    #: draw it. Cleared at the start of every action, which is what makes the
    #: flash last exactly one action and need no timer to end.
    hits: list[Pos] = field(default_factory=list)
    #: Where things died since the player's last action, for the screen to throw
    #: its pixels at. Same shape as ``hits`` and the same life: filled by the
    #: domain, which is the only place that knows where a corpse stopped moving,
    #: and cleared at the start of every action. A position taken from *before*
    #: the action is a bullet that lands one square from its target, because the
    #: thing that died may well have walked on before it did.
    deaths: list[Pos] = field(default_factory=list)

    # -- the void ------------------------------------------------------------
    #
    # Each hero's ultimate, once a floor, from the level the dark starts
    # answering. The flag is shared: one ask a floor, whichever shape it takes.
    #: Whether this floor's ultimate can still be asked for. Refilled by
    #: :meth:`build_floor`, spent by the cast, and carried through the save so
    #: an old save cannot lie its way into a second ask.
    ultimate_available: bool = True    #: The level the ultimates start answering at. `--testrun` runs turn it to 2.
    ultimate_level: int = ULTIMATE_LEVEL    #: The shadow itself, while it walks. Not in ``enemies`` -- nothing aims at
    #: it, nothing counts it as a monster, and nothing in the turn queue acts
    #: for it. It is driven alongside the scheduler in :func:`advance_world`
    #: and unsummoned by its own clock, which is why it does not live in the
    #: queue that speed owns.
    atritas: Actor | None = None
    #: Turns left before Atritas sinks back into the dark.
    atritas_turns_left: int = 0
    #: THE SIGHT. While Atritas walks, the whole floor is shown -- every wall,
    #: every corner, whether or not the hero has been there. It is *drawn*
    #: open, not *known* open: nothing here makes a monster act (that is
    #: ``visible``), and it is deliberately not written into ``explored``,
    #: because the dark showing you something is not the same as you having
    #: seen it. When the shadow leaves, the walls close back over what the
    #: hero never actually walked.
    void_sight: bool = False

    # -- the arena -----------------------------------------------------------
    #
    # A fight is owed. The floor hands one over where it used to resolve a blow
    # itself: walking into something, or something reaching the hero. Nothing
    # about the fight lives here -- no rounds, no order, no pair of fighters --
    # because the arena has its own module for that. This is only the sentence
    # "the next thing that happens is a battle", and the whole reason it lives
    # on the state rather than in a return value is that the *monsters* raise it
    # too, from deep inside :func:`advance_world`, where there is nobody to
    # return it to.
    #: The monster the floor handed over, or ``None``. Cleared by whoever opens
    #: the arena; the domain is finished with it the moment it is set.
    encounter: Actor | None = None

    def raise_encounter(self, actor: Actor) -> None:
        """Hand a fight to whoever is drawing the floor. The first one wins.

        First wins because two monsters arriving at the hero in the same breath
        are one fight: the second is standing right next to the first, and the
        arena takes whoever is beside the monster it was handed anyway.
        """
        if self.encounter is None:
            self.encounter = actor

    #: Whether a fight is *open* over this state -- owed and not yet opened, or
    #: running in the arena. The floor stands still while one is, and not only
    #: for the reason the encounter check below gives: a turn spent in a room is
    #: answered *by the room*, and the dungeon's own answer to the same turn is a
    #: second one. Which is not a theory. A mouthful drunk in the arena ran
    #: ``advance_world``, the floor's monsters took their turn in the middle of
    #: the fight, and one of them -- with no business moving while the hero was
    #: in a room -- walked up and was handed over as a *fresh* encounter. The
    #: fight then killed it, and the floor was left owing a fight to a corpse: a
    #: run that stood still for as long as it had left.
    in_fight: bool = False
    #: Whether the floor is on fire: Inferno's own gift to a floor, and the one
    #: thing in the game that *takes* from the hero rather than giving. It never
    #: runs out and it never has a shape on the map -- what it does is make every
    #: fight on this floor start with everything in it already burning, and hold
    #: his purse at three points for as long as it lasts.
    ravaging: bool = False
    #: How many debts are owed on this floor: one monster's death is paid by the
    #: next room. Read where a room is made, and cleared when it pays.
    debt: int = 0
    #: Whether an ultimate has been given into this run. One shared price: the
    #: purse holds five points for the rest of it, and the shop cannot buy them
    #: back. See :data:`levels.SACRIFICED_KILL_POINTS`.
    sacrificed: bool = False
    #: Yeti's bastion, while it stands. Same shape of life as the shadow: not
    #: an enemy, not in the queue, kept by its own clock -- and the one thing
    #: on the floor every monster would rather bite than the hero.
    fortress: Actor | None = None    #: Turns left before the fortress melts.
    fortress_turns_left: int = 0
    #: Sight taken away by an ultimate still running, in tiles.
    sight_penalty: int = 0
    #: How many things the pack holds. Base plus whatever the shop sold, so a
    #: run that bought slots carries them for its whole life.
    pack_capacity: int = BASE_PACK_SLOTS
    # -- the bloodlines ------------------------------------------------------
    #
    # Bought once, folded into the run at its start, and only for the hero they
    # belong to. Numbers rather than a lookup, for the same reason the wilds
    # are: nothing in the hot path should have to ask the save file what an
    # upgrade does.
    #: Noxx: turns a crit's wound lasts *longer* by this much.
    bleed_on_crit: int = 0
    #: Yeti: chance that whoever lands a blow on him freezes.
    freeze_chance: float = 0.0
    #: Walkyrion: chance that a landing blow throws its target.
    pushback_chance: float = 0.0
    #: And how often one of the hero's blows sets what it landed on alight. The
    #: third of the shop's bloodlines, and the one that is a *wound* rather than
    #: a shove: a burn is three a turn for two, which is the kindled breath's
    #: rule on a coin instead of in a bottle.
    ember_chance: float = 0.0
    #: The strange draughts drunk on this floor, by key. A set rather than a
    #: single slot because nothing stops a player drinking two, and every one
    #: of them is emptied by :meth:`build_floor` -- a rule carried down the
    #: stairs would be a rule the next floor never agreed to.
    floor_draughts: set[str] = field(default_factory=set)
    #: Where things have died on this floor, for THE CARRION TONGUE. A floor
    #: long memory rather than the per-action ``deaths`` list: the tongue feeds
    #: on a square long after the blood that marked it has been cleared.
    death_squares: set[Pos] = field(default_factory=set)

    # -- what the shop sent with you ----------------------------------------
    #
    # Bought before the run and carried into it. Kept as plain numbers rather
    # than as a reference to the purchase, so nothing in the hot path has to ask
    # the save file what a wild offer does.
    #: Extra sight on top of the base radius, from the lantern upgrade.
    sight_bonus: int = 0
    #: How much further a draught goes, from the cellar upgrade: a fraction, and
    #: multiplied into :attr:`heal_scale` where the curses and amulets meet.
    heal_bonus: float = 0.0
    #: Extra kill points the purse holds, from the Focus upgrade. Added to the
    #: level's ceiling, and *not* to the sacrificed one: a hero who has given
    #: himself to a floor's ask does not get to buy his tricks back.
    kill_points_bonus: int = 0
    #: What a dropped coin is multiplied by: the pact and greed both touch it.
    coin_multiplier: float = 1.0
    #: What every monster's health is multiplied by. Greed's catch.
    enemy_hp_multiplier: float = 1.0
    #: Killing blows left before one of them lands. Second wind.
    extra_lives: int = 0
    #: Player turns during which nothing can land a blow on you. The borrowed
    #: face, set to one by a kill and counted down by the world.
    shrouded: int = 0
    #: Whether the grave ward is still unspent on this floor. Armed when the
    #: floor is built, spent by the first blow that reaches you.
    ward_ready: bool = False
    #: MOMENTUM: consecutive steps taken in one direction, and which direction
    #: that was. The walk loads it, the next blow spends it, and a WAIT clears
    #: it (deliberately only a WAIT: quaffing or opening a lid spends that
    #: floor's turns without giving the walk away). Per floor, like revenge --
    #: a charge carried down the stairs would be a charge for a fight that has
    #: not happened yet.
    momentum: int = 0
    momentum_direction: Direction | None = None
    #: THE DEBT OF BLOOD: what the hero has been made to bleed since the last
    #: blow they landed. Owed back on it, then forgotten.
    blood_debt: int = 0
    #: THE SALT CIRCLE: the turn of untouchability the circle draws when a fight
    #: opens. One blow is refused while it holds.
    salt_ward: int = 0
    #: THE HUNGRY ROAD: the squares the hero has left glass on, oldest first,
    #: and what it will cost whatever follows them onto one. On the run rather
    #: than the map because it is a rule about the player, and ``world/`` has no
    #: business knowing what a gift does.
    trail: dict[Pos, int] = field(default_factory=dict)
    #: THE KINDNESS OF STRANGERS: the people who have already given.
    helped: set[Pos] = field(default_factory=set)
    #: Which wild offers are in force this run, by key.
    #:
    #: The two that multiply -- greed and the pact -- are numbers rather than
    #: flags, because two of them have to stack. Everything else is a rule that
    #: is either on or off, and a set says that once instead of six booleans.
    wilds: set[str] = field(default_factory=set)
    #: Which gifts the dungeon has handed over, by key. Run-long like the wilds,
    #: and for the same reason: a rule that lapsed every floor would be a number.
    gifts: set[str] = field(default_factory=set)
    #: Whether the borrowed hour is still unspent on this floor. Set when a floor
    #: is built, spent by a rewind.
    rewind_ready: bool = False
    #: The run as it was before the player's last action, held only while a
    #: borrowed hour is in hand. Deliberately not saved: a run put down and
    #: picked up again has simply lost the hour, which is the price of putting it
    #: down.
    snapshot: dict | None = None

    # -- curses -------------------------------------------------------------
    def add_curse(self, curse: Curse) -> None:
        """Take on ``curse``, for good.

        The stat changes are folded into the player's ``curse_modifiers`` here
        rather than derived on every read, because the effective stats are asked
        for constantly -- every attack, every turn of the queue -- and a list of
        curses walked each time is a cost paid in the hot path for a value that
        changes at most twice a run.

        Wither is the exception: it is not a modifier but a subtraction, taken
        once, from the health the hero will never get back.
        """
        self.curses.append(curse)
        player = self.player
        player.curse_modifiers = player.curse_modifiers + curse.modifiers

        if curse.wither:
            lost = max(1, round(player.max_hp * curse.wither))
            player.stats.max_hp = max(1, player.stats.max_hp - lost)
            player.stats.hp = min(player.stats.hp, player.stats.max_hp)
            # Written down, because the fraction is of the maximum at this
            # moment and recomputing it later would give a different number.
            self.curses[-1] = replace(curse, wither_taken=lost)

        self.say(f"{curse.name}: {curse.price}.", LogKind.BAD)

    def remove_curse(self, curse: Curse) -> None:
        """Lift a curse, and give back exactly what it took.

        Exactly, because "a quarter of your health" is a quarter of whatever the
        maximum was the moment it landed. Recomputed later it is a quarter of a
        different number, and a spring that hands back the wrong amount is a
        spring nobody trusts twice.
        """
        if curse not in self.curses:
            return
        self.curses.remove(curse)

        player = self.player
        # Rebuilt rather than subtracted. Floats do not subtract back to where
        # they started, and a residue of 0.0000001 on the speed would be
        # invisible right up until it was not.
        player.curse_modifiers = Modifiers()
        for remaining in self.curses:
            player.curse_modifiers = player.curse_modifiers + remaining.modifiers

        if curse.wither_taken:
            player.stats.max_hp += curse.wither_taken
            player.stats.hp = min(
                player.stats.max_hp, player.stats.hp + curse.wither_taken
            )

    @property
    def unpaid_curses(self) -> tuple[str, ...]:
        """Every curse the player is not already carrying, by key.

        A chest whose price you have already paid is not a bargain, it is a lie:
        the dialog reads the price out and nothing further happens. Duplicates
        were reachable and common -- fifteen chests over a run, drawn from
        thirteen curses -- and they were worse than a lie, because some of the
        thirteen stack when repeated and the rest do not, so the same second
        curse could be a sentence or a no-op depending on which one it was.

        Handed to the floor generator, which knows nothing about curses beyond
        their names, and used by the wraith's touch for the same reason. An
        empty tuple is a floor with no chests, which the generator already knows
        how to draw.
        """
        carried = {curse.key for curse in self.curses}
        return tuple(key for key in CURSES if key not in carried)

    @property
    def sight_radius(self) -> int:
        """How far the player can see, after anything that narrows it.

        The tightest curse wins rather than the last one applied: two things
        closing the dark in should not open it back up.
        """
        radius = VIEW_RADIUS + self.sight_bonus - self.sight_penalty
        for curse in self.curses:
            if curse.sight is not None:
                radius = min(radius, curse.sight)
        return max(1, radius)

    @property
    def bleed_every(self) -> int:
        """Steps between losing a point of blood, or 0 for none."""
        return min(
            (curse.bleed_every for curse in self.curses if curse.bleed_every),
            default=0,
        )

    @property
    def kill_cost(self) -> int:
        """Health every kill takes, from the curses. Zero for most runs.

        The one price that argues with the score, which now pays for killing:
        a run with the tithe has to decide whether the points are worth the
        blood, and that is the decision the curse exists to create.
        """
        return sum(curse.kill_cost for curse in self.curses)

    @property
    def extra_enemies(self) -> int:
        """How many monsters the curses add to every floor."""
        return sum(curse.extra_enemies for curse in self.curses)

    @property
    def step_cost_every(self) -> int:
        """Every how many steps the curses take one away, or 0 for none.

        The tightest curse wins, like the sight: two things slowing the same
        clock should not add up to a hero who cannot move.
        """
        return min(
            (
                curse.step_cost_every
                for curse in self.curses
                if curse.step_cost_every
            ),
            default=0,
        )

    @property
    def damage_spread(self) -> float:
        """How much wider the player's damage roll swings.

        Multiplied, unlike the others: a fever is a *shape* of uncertainty, and
        two of them should be twice as uncertain rather than merely present.
        """
        spread = 1.0
        for curse in self.curses:
            spread *= curse.damage_spread
        return spread

    @property
    def follows(self) -> int:
        """How many survivors follow the player down.

        The largest rather than the sum: two curses that each drag things along
        would be a swarm, and a swarm is not a price.
        """
        return max((curse.follows for curse in self.curses), default=0)

    @property
    def kills_to_level(self) -> int:
        """How many more kills buy the next level. Asked by both panels."""
        return kills_to_next(self.kills)

    @property
    def kill_points_max(self) -> int:
        """How big the purse is at this level: the ceiling the pool fills to.

        And while a floor is *burning*, three. That is Inferno's price, written
        where the purse is measured rather than where it is spent, so that the
        bar, the list of tricks and the arithmetic all read the same small
        number -- a cap any of the three could disagree about is not a cap.
        """
        if self.sacrificed:
            # The one price every ultimate shares: five points, whatever the level
            # and whatever the shop sold. The ask is paid in tricks.
            return SACRIFICED_KILL_POINTS
        return kill_points_for(self.level) + self.kill_points_bonus

    @property
    def heal_scale(self) -> float:
        """What a draught is worth, as a fraction of what it says on the tin.

        Curses take their share and the amulets add to it, and the two are meant
        to be able to meet: FAMINE halves a draught and the marrow makes it half
        again as much, which is the whole reason the marrow is worded that way.

        The mirror of hunger quotes the same figure from the shop's side of the
        counter: its pitch says a draught heals half again as much, and its
        price is set for that promise, so this is where the promise is kept.
        """
        scale = 1.0
        for curse in self.curses:
            scale *= curse.heal_scale
        if self.has_passive("marrow"):
            scale *= 1.5
        if self.has_wild("mirror_of_hunger"):
            scale *= 1.5
        # And the cellar, which is the shop's side of the same promise: a bottle
        # bought from a merchant who has kept it longer.
        scale *= 1.0 + self.heal_bonus
        return scale

    @property
    def cornered(self) -> bool:
        """THE LAST BREATH: the hero is down to the last few points.

        A question the *state* answers rather than one each rule re-derives, so
        the double blow and the harder-to-hit half can never disagree about
        where the line is.
        """
        return self.player is not None and self.player.stats.hp <= LAST_BREATH_HP

    # -- amulets ------------------------------------------------------------
    @property
    def amulet(self) -> str | None:
        """The ability the worn amulet grants, or ``None``.

        One slot, so one ability. A second amulet would be a second rule to hold
        in your head at the same time, and the three slots already ask for two.
        """
        worn = self.player.equipment.get("amulet")
        return worn.amulet if worn is not None else None

    def status_depth_bonus(self, key: str) -> int:
        """How much deeper the worn amulet makes one wound, in stacks.

        One for the four amulets that are each about a single status, none for
        everything else -- and the cap is the wound's own, applied where the
        stack is written.
        """
        from .amulets import amulet_by_key

        passive = amulet_by_key(self.amulet)
        return 1 if passive is not None and passive.status == key else 0

    def has_passive(self, key: str) -> bool:
        """Whether the worn amulet is this one."""
        return self.amulet == key

    # -- what the dungeon gave back -----------------------------------------
    def has_gift(self, key: str) -> bool:
        """Whether the dungeon has handed this gift over."""
        return key in self.gifts

    def has_draught(self, key: str) -> bool:
        """Whether a strange draught is working on this floor."""
        return key in self.floor_draughts

    def corpse_blocks(self, pos: Pos) -> bool:
        """Whether THE GALLOWS ROAD holds a monster out of ``pos``.

        One place, read by everything that moves a monster, so the rule cannot
        be half-applied: the hunter's own path search and the ordinary greedy
        step both ask here. The hero is never asked -- the dead are on their
        side, and the tongue eats what the road walls off.
        """
        return self.has_draught("gallows_road") and pos in self.death_squares

    @property
    def unheld_gifts(self) -> tuple[str, ...]:
        """Every gift this run has not been given, by key.

        Handed to the floor generator the way the unpaid curses are, so a chest
        can only ever offer something the player does not already have. Two of
        the same rule is not twice the rule, it is a lid that lied.
        """
        return tuple(key for key in GIFTS if key not in self.gifts)

    # -- what a wild offer did to the run -----------------------------------
    def has_wild(self, key: str) -> bool:
        """Whether this wild offer is in force."""
        return key in self.wilds

    @property
    def draughts_forbidden(self) -> bool:
        """Whether drinking has been taken away. The hollow tooth."""
        return self.has_wild("hollow_tooth")

    @property
    def kill_heal(self) -> int:
        """Health a kill puts back from the run's bargains.

        The last ember is an amulet and is asked separately; this is the one a
        wild offer pays, and the two are added rather than compared because a
        player who bought both bought both.
        """
        return 3 if self.has_wild("hollow_tooth") else 0

    @property
    def toll_per_floor(self) -> int:
        """What the dark charges for the next floor down. The pilgrim's toll."""
        return 5 if self.has_wild("pilgrims_toll") else 0

    @property
    def score_multiplier(self) -> float:
        """What the run is worth on the board.

        Two things move it and both are a wager against the other currency: the
        nameless run halves it and pays in coin, and a promise of fame raises it
        and pays in nothing at all -- the fame *is* the score, and the score is
        the board.
        """
        return (1.0 + self.fame_bonus) * (
            0.5 if self.has_wild("nameless_run") else 1.0
        )

    @property
    def coin_factor(self) -> float:
        """What a dropped coin is multiplied by, from every source.

        The wilds set ``coin_multiplier``; the coin hand multiplies it on top.
        Kept apart so a wild can be re-applied or replaced without having to know
        what the amulet is doing.
        """
        factor = self.coin_multiplier
        if self.has_passive("coin_hand"):
            factor *= 1.25
        for curse in self.curses:
            factor *= curse.coin_scale
        return factor

    def refresh_passives(self) -> None:
        """Recompute the two amulets whose effect depends on the moment.

        Written on every call rather than only when something changed, for the
        same reason REVENGE is: a bonus that is written rather than nudged cannot
        leave a residue behind when its condition stops being true.
        """
        player = self.player
        player.passive_armor = 0
        player.passive_damage = 0

        amulet = self.amulet
        if amulet == "deathwatch" and player.hp * 3 <= player.max_hp:
            player.passive_armor += 3
        if amulet == "patience":
            # Four at turn forty, which is about the point a careful floor stops
            # being careful and starts being a fight. The score wants you gone
            # quickly and this amulet wants you to stay; that argument is the
            # whole reason it exists.
            player.passive_damage += min(4, self.turn // 10)

    # -- logging ------------------------------------------------------------
    def say(self, text: str, kind: LogKind = LogKind.PLAIN) -> None:
        """Append a message to the log."""
        self.log.append(LogEntry(text=text, kind=kind, turn=self.turn))

    # -- queries ------------------------------------------------------------
    @property
    def over(self) -> bool:
        return self.run_state is not RunState.PLAYING

    @property
    def living_enemies(self) -> list[Actor]:
        return [enemy for enemy in self.enemies if enemy.alive]

    def actor_at(self, pos: Pos) -> Actor | None:
        """Anything standing on ``pos``, if anything is.

        Includes the people, because they are in the way and the map has to draw
        them. Anything that wants a *monster* wants :meth:`enemy_beside_player`
        or :attr:`living_enemies` instead.
        """
        if self.player.alive and self.player.position == pos:
            return self.player
        for enemy in self.enemies:
            if enemy.alive and enemy.position == pos:
                return enemy
        for npc in self.npcs:
            if npc.position == pos:
                return npc
        if self.atritas is not None and self.atritas.position == pos:
            # The shadow stands in the way the way a shadow does: solid to its
            # summoner, and a bump against it is a word, not a fight.
            return self.atritas
        if self.fortress is not None and self.fortress.position == pos:
            # A wall of ice is a wall.
            return self.fortress
        return None

    def standing(self) -> dict[Pos, Actor]:
        """Who is where, in one pass, for a painter that asks about every square.

        ``actor_at`` answers the same question for one square, and the overworld
        asks it for every square in view -- two thousand of them a frame. One
        pass over the actors is a map; two thousand passes are two thousand times
        the monsters, which is exactly what a busy floor used to cost.

        The precedence is ``actor_at``'s, and written the other way round so the
        highest claim lands last: the hero, then the living enemies, the people,
        the shadow, the fortress.
        """
        standing: dict[Pos, Actor] = {}
        if self.fortress is not None:
            standing[self.fortress.position] = self.fortress
        if self.atritas is not None:
            standing[self.atritas.position] = self.atritas
        for npc in self.npcs:
            standing[npc.position] = npc
        for enemy in self.enemies:
            if enemy.alive:
                standing[enemy.position] = enemy
        if self.player.alive:
            standing[self.player.position] = self.player
        return standing

    @property
    def lure(self) -> Actor | None:
        """What the monsters would rather bite than the hero, if anything.

        THE FROZEN FORTRESS and nothing else. It is read by the enemy turn
        rather than written into every monster, so the one place that decides
        where a floor's teeth point stays one place.
        """
        if self.fortress is not None and self.fortress.alive:
            return self.fortress
        return None

    def npc_beside_player(self) -> Actor | None:
        """Somebody standing next to the player, if anybody is."""
        from neverdeads_revenge.core.direction import DIRECTIONS

        for direction in DIRECTIONS:
            found = self.actor_at(direction.step(self.player.position))
            if found is not None and found.kind is ActorKind.NPC:
                return found
        return None

    def enemy_beside_player(self) -> Actor | None:
        """An adjacent living *monster*, if there is one.

        Asked of ``enemies`` rather than of ``actor_at``, because a person
        standing next to the player is not something to swing at -- and this is
        what the bot and the revenge path use to decide whether there is a fight
        on.
        """
        for enemy in self.living_enemies:
            if chebyshev(enemy.position, self.player.position) <= 1:
                return enemy
        return None

    # -- perception ---------------------------------------------------------
    def refresh_vision(self) -> None:
        """Recompute what the player can see. Call after every move."""
        self.dungeon_map.clear_visibility()
        visible, explored = compute_fov_full(
            self.player.position,
            self.sight_radius,
            self.dungeon_map.is_opaque,
            self.dungeon_map.in_bounds,
        )
        if self.fortress is not None:
            # THE FROZEN FORTRESS watches on the hero's behalf. Three paces
            # around the wall stay visible even after the cold has taken his
            # eyes, so the thing he built is never lost behind what it cost.
            self._widen_vision(visible, explored, self.fortress.position, FORTRESS_VIEW)
        if self.atritas is not None:
            # And the shadow sees its own work. It blinks from prey to prey,
            # and wherever it lands it looks: three paces, so the summoner can
            # watch the thing he is bleeding for.
            self._widen_vision(visible, explored, self.atritas.position, ATRITAS_VIEW)
        self.dungeon_map.visible = visible
        self.dungeon_map.explored |= explored

    def _widen_vision(
        self,
        visible: set[Pos],
        explored: set[Pos],
        centre: Pos,
        radius: int,
    ) -> None:
        """Open a square of floor around ``centre`` in both sight sets.

        Its own function because the fortress and the shadow ask the same
        thing of the map, and the copy that would drift is the one written
        twice.
        """
        cx, cy = centre
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                pos = (cx + dx, cy + dy)
                if self.dungeon_map.in_bounds(pos):
                    visible.add(pos)
                    explored.add(pos)

    # -- floors -------------------------------------------------------------
    def build_floor(self, depth: int) -> GeneratedFloor:
        """Generate the next floor and move everyone onto it."""
        # Captured before the floor is replaced, because these are the ones that
        # follow: the survivors of the floor being left behind.
        following = (
            [enemy for enemy in self.enemies if enemy.alive][: self.follows]
            if self.follows
            else []
        )
        self.depth = depth
        # The ledger is a page and a page is a floor: a new floor starts it empty,
        # wherever the floor was begun from.
        self.floor_kills = 0
        # What the player is already carrying goes into the floor's own dice.
        # A chest that hands out a third coat is a chest nobody opens twice, and
        # the floor is the only place that can decide not to.
        floor = generate_floor(
            self.rng,
            depth=depth,
            curse_keys=self.unpaid_curses,
            filled_slots=tuple(self.player.equipment) if self.player else (),
            npc_keys=tuple(NPCS),
            gift_keys=self.unheld_gifts,
            page_keys=tuple(sorted(self.missing_pages)),
            # COMPANY. Passed as a budget rather than applied afterwards so the
            # generator can still refuse: a floor with nowhere to put them hands
            # back the floor it has, which is better than monsters in the walls.
            enemy_budget=enemy_count(depth) + self.extra_enemies,
        )
        self.dungeon_map = floor.map

        if self.player is None:
            self.player = make_hero(self.hero, floor.player_start)
        else:
            self.player.position = floor.player_start
            # ``steps`` is deliberately not reset here. It is a run total, like
            # ``total_turns``. It used to reset per floor, which made the
            # summary's "Cells walked" report only the last floor while reading
            # like a run total -- and the old score, which counted steps, was
            # quietly counting only that one floor too.

        # The aspects roll on their own dice: the floor's monsters are drawn
        # exactly as they always were, and only the name changes when the dark
        # has been at one.
        marks = Rng(self.seed * 1009 + depth * 97)

        def one(pos):
            template = pick_enemy_template(self.rng, depth)
            affixes = (
                enemy_affixes(marks, depth)
                if template.behaviour == "aggressive"
                else ()
            )
            return make_enemy(template, pos, affixes=affixes)

        self.enemies = [one(pos) for pos in floor.spawn_points]
        if floor.hunter is not None:
            # Scaled by hand, because it is not drawn from the table: the
            # potency curve lives in ``pick_enemy_template``, and a hunter that
            # skipped it would be a floor-one monster on floor nine.
            self.enemies.append(
                make_enemy(scale_template(ENEMIES["hunter"], depth), floor.hunter)
            )
            # Said out loud, in the colour the game uses for things that are
            # happening *to* the player. Everything else on a floor can be met
            # by walking into it; this one is already on its way, and a threat
            # nobody was told about is not a decision, it is an ambush.
            self.say(
                "Something on this floor already knows where you are. "
                "It is not waiting.",
                LogKind.BAD,
            )
        self.toughen_enemies()
        self.npcs = [make_npc(NPCS[key], pos) for pos, key in floor.npcs]
        if following:
            # THE CRAWL. They arrive at this floor's own free ground rather than
            # at their old coordinates, because the old coordinates belong to a
            # floor that no longer exists.
            # *Free* is the word that was missing: the spawn points already hold
            # this floor's own monsters, so the ones that followed shared a tile
            # with a stranger.
            taken = {
                self.player.position,
                floor.stairs_down,
                *floor.springs,
                *(pos for pos, _key in floor.npcs),
                *(enemy.position for enemy in self.enemies),
            }
            free = [
                pos
                for pos in self.dungeon_map.walkable_positions()
                if pos not in taken
            ]
            for enemy in following:
                if not free:
                    break
                enemy.position = free.pop(self.rng.below(len(free)))
                enemy.struck = False
                self.enemies.append(enemy)
            if following:
                self.say(
                    f"{len(following)} of them came down with you.",
                    LogKind.BAD,
                )

        self.turn_queue = TurnQueue([self.player, *self.enemies])
        self.refresh_vision()
        # The per-floor clock restarts; total_turns keeps counting so the run
        # summary reports the whole run, not the room the hero died in.
        self.turn = 0

        # Revenge is a per-floor reward, so it lapses on the way down. Setting it
        # to zero clears whichever bonus this hero collects, without the caller
        # needing to know which that is.
        self.revenge_stacks = 0
        apply_revenge(self.player, 0)
        # And the note a blade's trick found: "every blow after" is about this
        # room, like the revenge it used to be mistaken for.
        self.player.note_bonus = 0
        self.first_blow_spent = False

        # The rest of the per-floor bookkeeping. Momentum is a charge built up on
        # this floor and spent on it; the debt is owed for wounds taken here; the
        # circle and the glass are both about this floor's ground; and a person
        # who has already given does not give again on the next one.
        self.momentum = 0
        self.momentum_direction = None
        self.blood_debt = 0
        # THE DEBT is owed for this floor's wounds: it would buff a fight the
        # dead were never in if it crossed the stairs.
        self.debt = 0
        self.salt_ward = 0
        self.trail.clear()
        self.helped.clear()
        # THE VOID. One give per floor: a new floor is a new dark asking, and
        # whatever the last one sent stays with the floor it was asked on.
        self.atritas = None
        self.atritas_turns_left = 0
        self.void_sight = False
        self.ravaging = False
        self.fortress = None
        self.fortress_turns_left = 0
        self.sight_penalty = 0
        self.ultimate_available = True
        # The floor's own weather, and its own memory of the dead. Both are the
        # floor's: neither the strange draughts nor the carrion tongue's
        # feeding crosses the stairs.
        self.floor_draughts.clear()
        self.death_squares.clear()

        self.arm_amulets()

        # THE BORROWED HOUR. One per floor, and the floor is where it comes
        # back: an hour that refilled on a timer would be a resource, and this
        # is meant to be a single held breath.
        self.rewind_ready = self.has_gift("borrowed_hour")
        self.snapshot = None

        # THE KIND DARK. One curse lifted on the way down, which is the exact
        # answer to the price a chest charged -- a bargain with a refund in it.
        # Skipped on floor one, where there is nothing to give back.
        if self.depth > 1 and self.has_gift("kind_dark") and self.curses:
            lifted = self.rng.pick(self.curses)
            self.remove_curse(lifted)
            self.say(
                f"The dark gives one back: {lifted.name} is gone.",
                LogKind.GOOD,
            )

        self.say(f"You descend to floor {depth}.", LogKind.SYSTEM)
        if floor.is_final:
            self.say("A rift tears the dark open, and beyond it: air.", LogKind.GOOD)
        if self.enemies:
            self.say(f"{len(self.enemies)} shapes move in the dark.", LogKind.PLAIN)
        return floor

    def arm_amulets(self) -> None:
        """Whatever the worn amulet does at the start of a floor.

        Called from ``build_floor`` and again from :func:`start_run`, because the
        first floor is built before the shop's parcel is opened. Without the
        second call an amulet bought or found for this run would sit out the floor
        it was bought for -- the same trap the wild offers fell into.

        Every step has to survive being run twice on the same floor, which is why
        the rune heart is guarded by depth and the rest are plain assignments.
        """
        self.player.stored_armor = 0
        self.shrouded = 0
        for enemy in self.enemies:
            enemy.struck = False

        if self.depth > 1 and self.has_passive("rune_heart"):
            # Only on the way down. Paying out on floor one as well would make
            # "every floor you descend" one floor more than it says.
            self.player.stats.max_hp += 1
            self.player.stats.hp += 1

        if self.has_passive("wayfarer") and self.exit_pos is not None:
            # Dimly, the way anywhere else you have walked past is drawn. The map
            # already knows how to show a place you have been and cannot see; this
            # only tells it that you have been there.
            self.dungeon_map.explored.add(self.exit_pos)

        self.ward_ready = self.has_passive("grave_ward")
        self.refresh_passives()

    @property
    def exit_pos(self) -> Pos | None:
        """Where the way onward is, or ``None`` on a floor that has none.

        Deliberately optional. The old version fell back to the player's own
        position, which quietly turned ``on_stairs`` into "always true" on any
        floor without a staircase -- and the final floor is exactly that floor.
        """
        for tile in (Tile.STAIRS_DOWN, Tile.RIFT):
            found = self.dungeon_map.find_tile(tile)
            if found:
                return found[0]
        return None

    @property
    def on_exit(self) -> bool:
        """Standing on whatever takes you onward, stairs or rift alike."""
        return self.exit_pos is not None and self.player.position == self.exit_pos

    @property
    def spring_pos(self) -> Pos | None:
        """Where the cleansing spring is, if this floor has one."""
        found = self.dungeon_map.find_tile(Tile.SPRING)
        return found[0] if found else None

    @property
    def at_the_spring(self) -> bool:
        """Standing in the spring, which is the only way to use it."""
        return self.dungeon_map.tile_at(self.player.position) is Tile.SPRING

    @property
    def cleanse_cost(self) -> int:
        """What one curse costs to wash off, right now."""
        return CLEANSE_COST

    @property
    def at_the_rift(self) -> bool:
        """Standing on the rift, which ends the run rather than descends."""
        return self.dungeon_map.tile_at(self.player.position) is Tile.RIFT

    @property
    def stairs(self) -> Pos | None:
        """Where the stairs down are, if this floor has any."""
        found = self.dungeon_map.find_tile(Tile.STAIRS_DOWN)
        return found[0] if found else None

    @property
    def on_stairs(self) -> bool:
        return self.stairs is not None and self.player.position == self.stairs

    def toughen_enemies(self) -> None:
        """Apply the enemy-health multiplier to whatever is on this floor.

        Called from ``build_floor``, and again from :func:`start_run` after the
        wild offers land -- greed is bought for a run that has already had its
        first floor built, and a bargain that skips floor one is a bargain that
        is quietly mis-sold.
        """
        if self.enemy_hp_multiplier == 1.0:
            return
        for enemy in self.enemies:
            enemy.stats.max_hp = max(
                1, round(enemy.stats.max_hp * self.enemy_hp_multiplier)
            )
            enemy.stats.hp = enemy.stats.max_hp

    # -- endings ------------------------------------------------------------
    def die(self, cause: str) -> bool:
        """Kill the hero, unless something bought keeps them alive.

        Returns whether the hero actually died. One place rather than at every
        way a run can end, because bleeding out is a death like any other and a
        bargain that only worked against monsters would be a bargain with a
        footnote.
        """
        if self.extra_lives > 0:
            self.extra_lives -= 1
            self.player.stats.hp = 1
            self.player.alive = True
            self.say(
                "Something hauls you back from the edge. Not this time.",
                LogKind.GOOD,
            )
            return False

        self.player.alive = False
        self.run_state = RunState.DEAD
        self.say(cause, LogKind.BAD)
        return True

    def escape(self) -> None:
        """Step through the rift and out of the dungeon.

        The one ending that is not a death, and the answer to the question the
        prologue asks. Kept here beside ``build_floor`` so both endings of a run
        are set in one file.
        """
        self.run_state = RunState.ESCAPED
        self.say("You step into the rift. The emptiness lets you go.", LogKind.GOOD)

    # -- scoring ------------------------------------------------------------
    @property
    def base_score(self) -> int:
        """Depth, before speed and before getting out.

        Killing things pays in coin rather than in points. The score is about
        how far and how fast; the purse is about what you can afford next time,
        and running them together made every fight worth points whether or not
        it was worth fighting.
        """
        return self.floors_cleared * 250

    @property
    def kill_score(self) -> int:
        """Points for what the run killed.

        Scaled by depth the way a coin is, so a deep floor is worth the risk.
        Derived from the kill count and the depth rather than accumulated, so
        the summary can be checked by hand and nothing can drift -- which is the
        same reason the level is derived from the kills.
        """
        return round(self.kills * KILL_SCORE * potency(self.depth))

    @property
    def fame_bonus(self) -> float:
        """What the promises add to the score multiplier. Zero for most runs."""
        return self.fame * FAME_PER_CHEST

    @property
    def speed_bonus(self) -> int:
        """Points for getting through the floors quickly.

        A budget rather than a penalty. Going over it scores nothing here instead
        of going negative, so a slow run is worth less, not worth less than
        nothing -- a screen with a minus sign on it reads as a punishment rather
        than a comparison.

        Scaled by the floors actually cleared, so standing still on floor one
        cannot bank a bonus for the turns it did not spend descending.
        """
        budget = TURN_BUDGET_PER_FLOOR * self.floors_cleared
        return max(0, budget - self.total_turns) * SPEED_BONUS_PER_TURN

    @property
    def score(self) -> int:
        """The run's score, for the summary screen.

        Time is in here and walking is not: steps measure how much of the floor
        you saw, and a run should be rewarded for leaving sooner rather than for
        wandering further. The escape bonus is larger than any plausible death
        score at the same depth, so a screen full of numbers can never rank an
        escape below a run that died on floor ten one step from the rift.
        """
        escape = ESCAPE_BONUS if self.run_state is RunState.ESCAPED else 0
        total = self.base_score + self.speed_bonus + self.kill_score + escape
        return round(total * self.score_multiplier)


def start_run(
    hero: Hero,
    seed: int,
    loadout: Loadout | None = None,
    upgrades: dict[str, int] | None = None,
    pages: tuple[int, ...] | None = None,
    ultimate_level: int | None = None,
) -> GameState:
    """Begin a fresh run with ``hero``.

    Args:
        hero: The chosen character.
        seed: The run seed. The same seed always yields the same dungeon.
        loadout: What the shop sold for this run.
        upgrades: Permanent meta upgrades, as ``{key: stacks}``. Kept as a
            shorthand for callers that have no loadout; ``loadout.upgrades``
            wins when both are given.
        pages: The chronicle pages still to be found, from the book. Left out,
            every page is still out there -- which is right for a new book and
            for every test that is not about the collection.
    """
    loadout = loadout or Loadout()
    state = GameState(hero=hero, rng=Rng(seed), seed=seed)
    state.kill_points = kill_points_for(state.level)
    if ultimate_level is not None:
        state.ultimate_level = ultimate_level
    state.missing_pages = (
        set(pages) if pages is not None else set(range(1, PAGE_COUNT + 1))
    )

    # The hero is made first, so the shop's parcel lands on a hero; the floor
    # is built second, so its dice roll knowing what the hero carries. The
    # ordering used to be backwards: the pact's curse never touched floor one
    # (COMPANY rented its shapes that floor), and a floor-one chest would
    # offer the very curse the pact had just charged for.
    state.player = make_hero(hero, (0, 0))  # placed on the floor built below

    permanent = loadout.upgrades or (upgrades or {})
    _apply_upgrades(state, permanent)
    _apply_pending(state, loadout.pending)
    _apply_wilds(state, loadout.wilds)
    state.build_floor(1)
    return state


def _apply_upgrades(state: GameState, upgrades: dict[str, int]) -> None:
    """Fold permanent upgrades into the hero's starting stats.

    Every upgrade is a delta, including the negative one the blood bargain
    sells, which is why this is a sum and not a set of special cases.
    """
    player = state.player
    for key, stacks in upgrades.items():
        upgrade = META_UPGRADES.get(key)
        if upgrade is None or stacks <= 0:
            continue
        if upgrade.max_hp:
            player.stats.max_hp = max(1, player.stats.max_hp + upgrade.max_hp * stacks)
        if upgrade.speed:
            player.stats.speed += upgrade.speed * stacks
        if upgrade.sight:
            state.sight_bonus += upgrade.sight * stacks
        if upgrade.pack_slots:
            state.pack_capacity += upgrade.pack_slots * stacks
        if upgrade.heal:
            state.heal_bonus += upgrade.heal * stacks
        if upgrade.kp:
            state.kill_points_bonus += upgrade.kp * stacks
        if upgrade.damage:
            player.stats.damage = (
                player.stats.damage[0] + upgrade.damage * stacks,
                player.stats.damage[1] + upgrade.damage * stacks,
            )
        if upgrade.crit:
            player.stats.crit_chance += upgrade.crit * stacks
        if upgrade.hero:
            # A bloodline only works for its own hero. Checked here rather than
            # in the shop, because the shop stands before the hero is chosen.
            if upgrade.hero != state.hero.key:
                continue
            if upgrade.key == "bleeding_edge":
                state.bleed_on_crit = stacks
            elif upgrade.key == "hoarfrost":
                state.freeze_chance = HOARFROST_PER_STACK * stacks
            elif upgrade.key == "bell_ring":
                state.pushback_chance = BELL_RING_PER_STACK * stacks
            elif upgrade.key == "emberheart":
                state.ember_chance = EMBERHEART_PER_STACK * stacks

    # A run starts whole. Bought health you do not have is not bought health,
    # and the blood bargain's whole point is that the missing part is gone.
    player.stats.hp = player.stats.max_hp


def _receive(state: GameState, template) -> None:
    """Put an item where it belongs: what has no slot in the pack, the rest worn.

    The test is the *slot* and not the kind: a strange draught is not a draught
    and has no slot either, and the old test dropped the blind box's bottles into
    ``equipment[None]``, where nothing could ever find them again.
    """
    item = make_item(template)
    if template.slot is None:
        state.inventory.append(item)
        return

    previous = state.player.equipment.get(template.slot)
    state.player.equipment[template.slot] = item
    # Finding it is knowing it: the armory and the wardrobe keep the page for a
    # piece that was bought, not only for one that was picked up off the floor.
    if template.slot == "weapon" and item.item_id not in state.found_weapons:
        state.found_weapons.append(item.item_id)
    if template.slot == "armour" and item.item_id not in state.found_armours:
        state.found_armours.append(item.item_id)
    if previous is not None:
        # Two things for one slot: the last one bought is worn, the one it
        # replaced goes into the pack. Before the first floor there is no ground
        # to set it down on, and a purchase that vanished would be a purchase
        # the shop should not have sold.
        state.inventory.append(previous)
        state.say(f"The {previous.name} goes into the pack.", LogKind.SYSTEM)


def _apply_pending(state: GameState, keys) -> None:
    """Open the shop's parcel: everything bought for this run."""
    for key in keys:
        template = ITEMS.get(key)
        if template is None:
            continue
        _receive(state, template)
        state.say(
            f"You start with {_the(template.name)}.",
            LogKind.SYSTEM,
        )


def _apply_wilds(state: GameState, keys) -> None:
    """Apply the bargains. Each one is its own small rule, on purpose.

    A table of effects would be shorter and would also be a table of lambdas,
    which is not shorter to read. Each one does something the others do not.
    """
    for key in keys:
        state.wilds.add(key)

        if key == "blind_box":
            # Deliberately the *whole* table, not the floor's own: the box is
            # the wildcard that can pay out something from the deep. Chest-only
            # pieces carry a default weight of 1.0, and they add up to 27 of the
            # table's 89.3 -- so **three boxes in ten** hold a strong-tier piece,
            # not the one in five this comment used to claim. That is why it
            # costs near what the wager's good face does. Change this to a
            # floor-weighted roll and the box becomes a mop; note it if you tune
            # it.
            template = state.rng.choice_weighted(
                [(t, t.weight) for t in ITEMS.values()]
            )
            _receive(state, template)
            state.say(f"The blind box holds a {template.name}.", LogKind.GOOD)
        elif key == "pact":
            state.coin_multiplier *= 1.5
            state.add_curse(state.rng.pick(list(CURSES.values())))
            state.say("The pact settles over you, and will not lift.", LogKind.BAD)
        elif key == "greed":
            state.coin_multiplier *= 2.0
            state.enemy_hp_multiplier *= 1.2
            state.say("You want all of it, and the dark can tell.", LogKind.BAD)
        elif key == "grave_goods":
            _receive(state, ITEMS["grave"])
            state.say("Grave iron, cold and heavier than it looks.", LogKind.SYSTEM)
        elif key == "second_wind":
            state.extra_lives += 1
            state.say("Something down here is keeping count of your deaths.", LogKind.SYSTEM)
        elif key == "wager":
            # A coin, and it is not a metaphor. Half the runs it is the best
            # blade in the game and half the runs it is a curse, and the player
            # who buys it has decided they do not mind which.
            strong_blades = [
                t.key
                for t in ITEMS.values()
                if t.chest_only and t.kind == "weapon"
            ]
            if state.rng.chance(0.5):
                blade = ITEMS[state.rng.pick(strong_blades)]
                _receive(state, blade)
                state.say(
                    f"The coin comes up clean. {blade.name} is in your hands.",
                    LogKind.GOOD,
                )
            else:
                state.add_curse(state.rng.pick(list(CURSES.values())))
                state.say("The coin comes up dark.", LogKind.BAD)
        elif key == "hollow_tooth":
            state.say(
                "Your teeth are gone and nothing will stay down. "
                "Everything you kill feeds you instead.",
                LogKind.SYSTEM,
            )
        elif key == "pilgrims_toll":
            state.coin_multiplier *= 1.5
            state.say("Every floor down will be paid for.", LogKind.BAD)
        elif key == "counts_favour":
            state.say("Something is counting your kills. It has a number in mind.", LogKind.SYSTEM)
        elif key == "mirror_of_hunger":
            state.say("Something will drink whenever you do.", LogKind.BAD)
        elif key == "nameless_run":
            state.coin_multiplier *= 2.0
            state.say(
                "Your name is not on this run, and the coin does not care.",
                LogKind.SYSTEM,
            )
