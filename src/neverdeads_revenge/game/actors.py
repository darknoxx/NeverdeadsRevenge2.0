"""Actors: the player, the monsters, and the numbers that make them tick.

An :class:`Actor` is pure state plus a couple of queries. It holds no reference
to the map and imports nothing from the UI, so the whole simulation stays
testable without a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from neverdeads_revenge.core.direction import Pos
from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.world.map import GroundItem
from neverdeads_revenge.world.modifiers import Modifiers

from .difficulty import enemy_speed, potency, weight_at_depth
from .npcs import NPC_COLOR, NPC_GLYPH, Npc
from .statuses import status_by_key

__all__ = [
    "Stats",
    "ActorKind",
    "Actor",
    "Trait",
    "REVENGE_MAX_STACKS",
    "REVENGE_PER_STACK",
    "Hero",
    "NOXX",
    "YETI",
    "WALKYRION",
    "HEROES",
    "EnemyTemplate",
    "ENEMIES",
    "make_hero",
    "make_atritas",
    "make_fortress",
    "make_enemy",
    "make_npc",
    "scale_template",
    "pick_enemy_template",
]


@dataclass(slots=True)
class Stats:
    """The numbers combat cares about.

    ``speed`` is the odd one out: it is not a combat stat at all but the
    interval divisor in the turn queue, which is what makes a fast hero act more
    often.
    """

    max_hp: int = 10
    hp: int = 10
    speed: float = 1.0
    damage: tuple[int, int] = (2, 4)
    crit_chance: float = 0.05
    crit_multiplier: float = 1.5
    accuracy: int = 0
    evasion: int = 0
    armor: int = 0

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def average_damage(self) -> float:
        low, high = self.damage
        return (low + high) / 2

    def heal(self, amount: int) -> int:
        """Restore health, never above the maximum. Returns the amount healed."""
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - before

    def reflect(self, amount: int) -> int:
        """Take ``amount`` straight, ignoring armour.

        For the mirror. A reflection is not a blow, so the armour that turns a
        blow aside has nothing to do with it -- and an amulet that says two and
        delivers one against anything armoured is an amulet that lied.
        """
        amount = max(0, amount)
        self.hp = max(0, self.hp - amount)
        return amount

    def hurt(self, amount: int, bonus_armor: int = 0) -> int:
        """Apply ``amount`` after armour. Returns damage actually taken.

        ``bonus_armor`` is the defender's temporary armour, which lives on the
        :class:`Actor` rather than here: this object is copied from a template
        and never sees a kill, so it has no business knowing about REVENGE.
        """
        amount = max(0, amount - self.armor - bonus_armor)
        self.hp = max(0, self.hp - amount)
        return amount


class ActorKind(Enum):
    """What an actor is, which decides how it is drawn and how it behaves."""

    HERO = "hero"
    ENEMY = "enemy"
    #: Somebody who is neither. Not in the turn queue, not attackable, and in
    #: the way -- walking into one is a conversation, not a fight.
    NPC = "npc"
    #: The dark beside Noxx. Not an enemy and not a person: nothing aims at it,
    #: nothing counts it on a floor, and it has no turn in the queue. It acts
    #: alongside the scheduler and answers only to its own clock.
    ATRITAS = "atritas"
    #: Yeti's bastion: a wall of ice that everything hostile would rather bite
    #: than the hero. Solid, temporary, and it has hit points of its own --
    #: half of what the builder had when it went up.
    FORTRESS = "fortress"


#: What REVENGE grants a hero, and how much of it.
#:
#: The mechanic is the game's own name and is the same for everyone; what it
#: grants is not. Handing speed to a slow hero is handing his worst stat the
#: biggest relative boost, which is exactly backwards.
class Trait(Enum):
    """What one stack of REVENGE grants, and what to call it in the UI."""

    SPEED = "speed"
    ARMOUR = "armour"
    DAMAGE = "damage"

    @property
    def per_stack(self) -> float:
        return REVENGE_PER_STACK[self]

    @property
    def label(self) -> str:
        return self.value

    @property
    def title(self) -> str:
        """What the grant *is called* for the hero it belongs to.

        One mechanic shared by three heroes was played three ways, and "REVENGE"
        told each of them nothing: Noxx's tide and Yeti's fortress and
        Walkyrion's blade are different things to play around, so each of them
        calls its own. The word `REVENGE` still names the *system* -- the score,
        the amulets that touch it -- but a panel a player reads from says the
        name.
        """
        return REVENGE_TITLES[self]

    @property
    def cap(self) -> int:
        return REVENGE_MAX_STACKS[self]

    def describe(self, stacks: int) -> str:
        """A short phrase for a message log or a status line."""
        amount = self.per_stack * stacks
        if self is Trait.SPEED:
            return f"+{amount:.1f} speed"
        return f"+{int(amount)} {self.value}"


#: What each grant is called by the hero who uses it: BLACK TIDE for Noxx,
#: FROZEN FORTRESS for Yeti, AURAL BLADE for Walkyrion.
REVENGE_TITLES: dict["Trait", str] = {
    Trait.SPEED: "BLACK TIDE",
    Trait.ARMOUR: "FROZEN FORTRESS",
    Trait.DAMAGE: "AURAL BLADE",
}


#: How much a single stack of REVENGE grants, per trait.
#:
#: Speed is the calibrated one -- 0.3 was tuned against the whole existing game
#: and left alone. The other two are chosen to be worth roughly the same: five
#: stacks of speed doubles Noxx's actions, so five stacks of armour should change
#: a deep-floor hit by about half, and five stacks of damage should cut a
#: skeleton's health in roughly half the blows.
REVENGE_PER_STACK: dict[Trait, float] = {
    Trait.SPEED: 0.3,
    Trait.ARMOUR: 1.0,
    Trait.DAMAGE: 2.0,
}

#: How many stacks each trait takes before it stops paying.
#:
#: Deliberately not one number for all three. ``+0.3 speed`` and ``+1 armour``
#: are not the same amount of game -- armour is a flat subtraction, so a point of
#: it is worth more the more of it you already have -- and a shared cap either
#: strangles one trait or lets another run away with the run. Each cap is set at
#: roughly the point the trait has doubled its own hero's speciality: Noxx's
#: actions, Yeti's armour, Walkyrion's damage.
REVENGE_MAX_STACKS: dict[Trait, int] = {
    Trait.SPEED: 5,
    Trait.ARMOUR: 3,
    Trait.DAMAGE: 4,
}


@dataclass(slots=True)
class Actor:
    """Something that occupies a cell and can act."""

    name: str
    kind: ActorKind
    stats: Stats
    position: Pos
    #: A fallback for an actor built without an identity. Heroes and monsters get
    #: theirs from their template, so this is never the player -- it used to
    #: default to ``@``, which read as "the hero" long after the hero stopped
    #: being an ``@``.
    glyph: str = "?"
    color: str = "white"
    is_player: bool = False
    alive: bool = True
    #: Coins this actor leaves behind when it dies. Copied from the template so
    #: the kill does not have to go looking for which monster it was.
    gold: tuple[int, int] = (0, 0)
    #: Chance per landed blow that this actor's touch leaves a curse behind.
    curse_chance: float = 0.0
    #: Statuses this actor's blows leave running, by key. Copied from the
    #: template for a monster; the player's is read off the blade in hand.
    inflicts: tuple[str, ...] = ()
    #: Which NPC this is, by key. ``None`` for everything that is not a person.
    npc: str | None = None
    #: Cells entered since the run started. A run total, like ``total_turns``,
    #: and a statistic rather than a score input: the score rewards time, and
    #: walking further is the opposite of that.
    steps: int = 0
    #: Temporary additive bonuses granted by REVENGE. Kept on the actor rather
    #: than folded into ``stats`` so that lapsing is one assignment and cannot
    #: leave a residue behind on a template.
    speed_bonus: float = 0.0
    armor_bonus: int = 0
    damage_bonus: int = 0
    #: What this actor is wearing, by slot. Only the player ever fills it, but
    #: it lives here because that is where the effective stats are computed and
    #: a bonus that cannot go stale is worth a dict on every monster.
    equipment: dict[str, GroundItem] = field(default_factory=dict)
    #: Stat changes from curses. Kept apart from the equipment so the character
    #: sheet can say which is which -- "you are wearing this" and "this was done
    #: to you" are different sentences.
    curse_modifiers: Modifiers = Modifiers()
    #: What a blow left running on this actor, by key, with the turns left on
    #: each. Empty for almost everything: only something a weapon or a monster
    #: inflicted lives here, and it empties itself as it runs out.
    statuses: dict[str, int] = field(default_factory=dict)
    #: Which of the three REVENGE grants this actor collects. Copied from the
    #: hero so the game layer never has to look the hero up mid-fight.
    trait: Trait = Trait.SPEED
    #: How this actor wants to fight. Copied from the template so the AI does not
    #: have to carry the template around.
    behaviour: str = "aggressive"
    #: Armour an amulet grants only under a condition -- the deathwatch, which
    #: only counts while the wearer is nearly gone. Recomputed by the game, not
    #: derived here: the condition is a rule, and rules live in ``game/``.
    passive_armor: int = 0
    #: Armour an amulet banked earlier -- what the second mouth does with a
    #: draught that had nothing left to heal. Cleared when the floor changes,
    #: because armour stored against one floor's monsters should not follow you
    #: down to the next.
    stored_armor: int = 0
    #: Damage an amulet grants only under a condition. Recomputed like
    #: ``passive_armor``.
    passive_damage: int = 0
    #: Whether the player has already landed a blow on this actor. The patient
    #: knife only makes the *first* one a crit, so something has to remember.
    struck: bool = False

    # -- combat -------------------------------------------------------------
    #
    # Everything below sums three layers: the base ``Stats`` the actor was built
    # with, the temporary bonuses REVENGE grants, and what it is wearing. Keeping
    # the sum in one place is why combat never has to ask what a stat "really" is.
    @property
    def hp(self) -> int:
        return self.stats.hp

    @property
    def max_hp(self) -> int:
        return self.stats.max_hp

    @property
    def modifiers(self) -> Modifiers:
        """Everything worn and everything owed, summed. Derived, so it cannot
        go stale."""
        total = self.curse_modifiers
        for item in self.equipment.values():
            total = total + item.modifiers
        return total

    @property
    def speed(self) -> float:
        """Effective speed.

        This is what the turn queue divides by, so a bonus granted by a kill
        immediately makes the holder act more often.
        """
        base = self.stats.speed + self.speed_bonus + self.modifiers.speed
        factor = 1.0
        for key in self.statuses:
            status = status_by_key(key)
            if status is not None:
                factor *= status.speed_factor
        return base * factor

    @property
    def armor(self) -> int:
        """Armour from every source, for display and for combat."""
        return (
            self.stats.armor
            + self.armor_bonus
            + self.modifiers.armor
            + self.passive_armor
            + self.stored_armor
        )

    @property
    def evasion(self) -> int:
        return self.stats.evasion + self.modifiers.evasion

    @property
    def accuracy(self) -> int:
        return self.stats.accuracy + self.modifiers.accuracy

    @property
    def crit_chance(self) -> float:
        return self.stats.crit_chance + self.modifiers.crit_chance

    @property
    def crit_multiplier(self) -> float:
        return self.stats.crit_multiplier + self.modifiers.crit_multiplier

    @property
    def damage_range(self) -> tuple[int, int]:
        """The damage roll before the dice, bonuses included."""
        low, high = self.stats.damage
        bonus = self.damage_bonus + self.modifiers.damage + self.passive_damage
        return (low + bonus, high + bonus)

    def damage_roll(self, rng, spread: float = 1.0) -> int:
        """A damage value in this actor's range, plus every flat bonus.

        Flat, not a multiplier: the bonus is added once to the roll, so it reads
        on screen as the same number every hit and a player can count it.

        ``spread`` widens the range around its own middle, which is what THE
        FEVER does -- not less damage, less *predictable* damage. Widening
        around the middle rather than raising the top is the whole point: a
        curse that made the hero stronger on average would not be a curse.
        """
        low, high = self.damage_range
        if spread != 1.0:
            middle = (low + high) / 2
            low = max(1, round(middle - (middle - low) * spread))
            high = round(middle + (high - middle) * spread)
        return rng.between(low, high)

    def hurt(self, amount: int) -> int:
        """Take a hit, after everything this actor has on.

        The armour is passed down to ``Stats`` rather than subtracted here so
        there is exactly one place that knows what armour does. What is passed is
        ``armor`` minus the base, so a new source of armour cannot be added to the
        property and forgotten here -- which is the bug this line exists to not
        have.
        """
        return self.stats.hurt(amount, self.armor - self.stats.armor)

    def __repr__(self) -> str:
        return f"Actor({self.name!r}, hp={self.hp}/{self.max_hp}, at={self.position})"


# -- heroes ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Hero:
    """A playable character definition."""

    key: str
    name: str
    title: str
    blurb: str
    glyph: str
    color: str
    stats: Stats
    #: What REVENGE grants this hero for every kill. See :class:`Trait`.
    trait: Trait = Trait.SPEED
    #: Permanent modifiers applied when the run starts, keyed by meta upgrade.
    unlocked: bool = True

    @property
    def average_damage(self) -> float:
        return self.stats.average_damage


#: Noxx -- high speed, high crit, low durability. Hits and runs.
#:
#: ``N`` rather than the usual ``@``: this hero has a name, and the map is where
#: the player spends the whole run looking at him. Purple is his own -- the
#: wraith is plain magenta and the elixir is bright magenta, so no two things on
#: the map share both a glyph and a colour.
NOXX = Hero(
    key="noxx",
    name="Noxx",
    title="the swift one",
    blurb=(
        "Quick hands, quicker feet. Noxx wins fights he should lose: strike, "
        "vanish, come back before they can swing. Fragile, but every opening "
        "is lethal."
    ),
    glyph="N",
    # A hex rather than the name "purple": named colours get snapped to the
    # terminal's nearest palette entry, and "purple" lands on the same magenta
    # the wraith already uses. Hex renders exactly and stays his own.
    color="#a855f7",
    stats=Stats(
        max_hp=26,
        hp=26,
        speed=1.5,
        damage=(4, 6),
        crit_chance=0.25,
        crit_multiplier=2.2,
        accuracy=1,
        # Five, not four. Evasion is worth 10 points of enemy hit chance each,
        # and the hit chance floor is 30%: at 5 a ghoul is down to 35%, at 6 it
        # would be 25% and clamped, so the sixth point is partly paid for and
        # not received. Five is the last value that fully counts.
        evasion=5,
        armor=1,
    ),
    # REVENGE makes him faster still, which is the same joke his whole kit tells:
    # the fight is over before it started.
    trait=Trait.SPEED,
)

#: Yeti -- the opposite answer to the same question. Where Noxx avoids the blow,
#: Yeti absorbs it: armour is a flat subtraction, so it eats the small hits that
#: early floors are made of, and it is the only hero who can stand in a corridor
#: and let three things hit him.
#:
#: His speed is below everything that matters and below the average of the
#: dungeon, deliberately. He does not get to choose the fight, and a player who
#: picks him is trading tempo for the right to never be the one who dies first.
#: Damage is what makes that survivable: the sweep said raising his health
#: changed nothing while raising his damage moved his escape rate threefold,
#: because a slow hero does not lose by being fragile, he loses by needing four
#: turns to kill something that hits him every one of them.
YETI = Hero(
    key="yeti",
    name="Yeti",
    title="the unmoved",
    blurb=(
        "Slow as a glacier and about as easy to move. Yeti does not dodge and "
        "does not rush; everything that reaches him has to get through the "
        "armour first, and most things do not."
    ),
    glyph="Y",
    color="#7fd4ff",
    stats=Stats(
        max_hp=52,
        hp=52,
        speed=0.75,
        # Damage is what makes a slow hero work, and the sweep keeps saying so.
        # Raising his health changed nothing (54 hp measured the same as 46).
        # Raising his damage from 9-13 to 12-17 took his escape rate from 0% to
        # 4% against the floor-10 wall, and his armour is the proof of the same
        # rule from the other side: three more points of it took him to 33%,
        # because armour is a flat subtraction and the monsters now scale.
        damage=(12, 17),
        crit_chance=0.05,
        crit_multiplier=1.5,
        accuracy=1,
        evasion=0,
        armor=3,
    ),
    # Every kill hardens him. This is the one the roster was missing: REVENGE
    # used to hand a *slow* hero a speed bonus, which meant the hero built to
    # absorb hits was the one who most wanted to stop taking them, and the trait
    # worked hardest on the hero whose identity least wanted it.
    trait=Trait.ARMOUR,
)

#: Walkyrion -- the middle road, taken on purpose. Fast enough to leave a fight
#: he does not want, armoured enough to survive the one he misjudged, and with no
#: single glaring hole for a deep floor to find.
#:
#: Every hero needs one number they are bad at or they are not a choice. His is
#: that none of his numbers is the best, so nothing he does wins the run by
#: itself.
WALKYRION = Hero(
    key="walkyrion",
    name="Walkyrion",
    title="the even blade",
    blurb=(
        "No weakness worth naming and no trick worth relying on. Walkyrion "
        "strikes on time, takes the hit he has to, and is still standing when "
        "the screaming stops."
    ),
    glyph="W",
    color="#ffb000",
    stats=Stats(
        # Every number here sits between Noxx's and Yeti's, which is the whole
        # point, and the accuracy of 2 is the one thing that is nobody else's.
        # "Balanced" measured as the worst hero in the game until that edge
        # existed: a middle of two specialists is below both of them unless it
        # gets a small speciality of its own, and never missing is a quiet one.
        max_hp=36,
        hp=36,
        speed=1.15,
        damage=(6, 9),
        crit_chance=0.20,
        crit_multiplier=1.8,
        accuracy=2,
        evasion=2,
        armor=2,
    ),
    # Every kill sharpens him. He is the hero with the least to gain from
    # becoming more of one thing, so he becomes more dangerous instead -- which
    # is what "balanced" should compound into rather than turning him into a
    # slightly worse version of whoever he is standing next to.
    trait=Trait.DAMAGE,
)

#: Registry. Later heroes drop in here and the select screen picks them up for
#: free -- that is the whole reason heroes are data and not a hardcoded branch.
#:
#: Heroes take the capital of their name and monsters stay lowercase, so a letter
#: on the map tells you which side of the fight it is on before you have read the
#: legend. The wraith had the ``W`` until Walkyrion needed it.
HEROES: dict[str, Hero] = {hero.key: hero for hero in (NOXX, YETI, WALKYRION)}


def make_hero(hero: Hero, position: Pos) -> Actor:
    """Create a fresh actor from a hero definition."""
    return Actor(
        name=hero.name,
        kind=ActorKind.HERO,
        # Copy the stats: templates are shared and must never be mutated.
        # replace(), not vars() -- Stats uses __slots__, so it has no __dict__.
        stats=replace(hero.stats),
        position=position,
        glyph=hero.glyph,
        color=hero.color,
        is_player=True,
        trait=hero.trait,
    )


# -- enemies ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EnemyTemplate:
    """A monster definition, plus how it wants to fight."""

    key: str
    name: str
    glyph: str
    color: str
    stats: Stats
    #: How this monster moves. Only ``"cautious"`` is read, by the movement code
    #: in :mod:`game.actions`: it hangs back until the player closes. Everything
    #: else -- including the default -- walks straight at them.
    #:
    #: It used to say "see game.ai", which never existed, and the wraith carried
    #: ``"hunter"``, which nothing has ever read. A label that names a behaviour
    #: no code implements is worse than no label: it reads as a monster doing
    #: something clever when it is doing the same thing as a ghoul.
    behaviour: str = "aggressive"
    #: Coins this monster leaves behind, before depth scaling. A range rather
    #: than a number so a kill is worth something different each time, which is
    #: what makes a floor feel like it paid out unevenly.
    gold: tuple[int, int] = (2, 4)
    #: Chance per landed blow that this monster's touch leaves a curse behind.
    #: Zero for everything that is not the wraith.
    curse_chance: float = 0.0
    #: Statuses this monster's blows leave running, by key. The other way a
    #: monster can be a problem without hitting harder.
    inflicts: tuple[str, ...] = ()
    #: Relative chance of being picked when populating a floor.
    weight: float = 1.0
    #: How much ``weight`` grows per floor descended. ``1.0`` keeps the monster
    #: as common as on floor 1; higher values make it steadily more likely, and
    #: that is how the enemy *mix* shifts rather than just the enemy *numbers*.
    #: See :mod:`game.difficulty`.
    weight_growth: float = 1.0


ENEMIES: dict[str, EnemyTemplate] = {
    "ghoul": EnemyTemplate(
        key="ghoul",
        name="ghoul",
        glyph="g",
        color="green",
        behaviour="aggressive",
        # Floor one is a fight now. It used to be a formality -- the whole
        # dungeon was a formality -- and the fix is here rather than in the
        # potency curve, because the challenge should be the ground the run
        # stands on, not the slope it climbs.
        stats=Stats(max_hp=15, hp=15, speed=0.7, damage=(4, 6), evasion=0, armor=0),
        gold=(3, 6),
        weight=4.0,
    ),
    "bone": EnemyTemplate(
        key="bone",
        name="skeleton",
        glyph="s",
        color="grey70",
        behaviour="cautious",
        stats=Stats(max_hp=22, hp=22, speed=1.0, damage=(5, 8), accuracy=1, armor=1),
        gold=(6, 11),
        weight=3.0,
    ),
    "wraith": EnemyTemplate(
        key="wraith",
        name="wraith",
        glyph="w",
        color="magenta",
        stats=Stats(max_hp=11, hp=11, speed=1.3, damage=(4, 7), evasion=3),
        gold=(5, 9),
        # One blow in twenty. Rare enough that a run can pass without it, often
        # enough that a wraith is something you would rather not be touched by --
        # which is the whole point of the only monster here that is already
        # fast, evasive and hard to out-trade.
        curse_chance=0.05,
        weight=1.5,
        # The only monster that gets more common as you descend. It is fast and
        # evasive, which is exactly the thing that makes a floor feel unfair if
        # the player cannot simply out-trade it -- so the deeper floors are
        # floors where out-trading is no longer the whole answer. Raised from
        # 1.14 with the rest of the wall: a slow hero's problem is the number of
        # things hitting him, and this is the dial that changes it.
        weight_growth=1.25,
    ),
    "ooze": EnemyTemplate(
        key="ooze",
        name="ooze",
        glyph="o",
        color="cyan",
        # The wall. More health than anything else in the game and almost no
        # damage: it will not kill a careful player and it will not die to one
        # either. What it does is *cost* -- turns, which are the score, and the
        # potions that would have carried the hero through the next floor.
        # Every other monster asks a question; this one is a bill.
        stats=Stats(max_hp=45, hp=45, speed=0.5, damage=(2, 4), armor=2),
        gold=(9, 15),
        weight=1.2,
        # Grows more common with depth, like the wraith: a slow floor that is
        # merely long is a floor that is merely long on floor two, and a real
        # problem by floor eight, when the turns it eats are the turns the run
        # needed.
        weight_growth=1.18,
    ),
    "viper": EnemyTemplate(
        key="viper",
        name="viper",
        glyph="v",
        color="bright_green",
        # The other end of the same idea: almost no health, quick, and it leaves
        # poison behind. Killing it is easy and killing it *second* is the
        # mistake -- the eight turns of poison outlive the viper by a long way,
        # and that is the fight it is trying to pick.
        stats=Stats(max_hp=12, hp=12, speed=1.2, damage=(3, 5), evasion=1),
        gold=(5, 9),
        inflicts=("poison",),
        weight=1.5,
        weight_growth=1.10,
    ),
    "mound": EnemyTemplate(
        key="mound",
        name="mound",
        glyph="m",
        color="blue",
        # Tanky in the other direction: not a wall, a *weight*. It hits hard
        # enough to be worth avoiding and has enough health that avoiding it is
        # often the right answer, which is the decision the floor was missing.
        # Cautious, so it does not chase -- it waits in the room it was put in.
        behaviour="cautious",
        stats=Stats(max_hp=34, hp=34, speed=0.6, damage=(6, 9), accuracy=1, armor=1),
        gold=(10, 16),
        weight=1.0,
        weight_growth=1.20,
    ),
    "hunter": EnemyTemplate(
        key="hunter",
        # Not "the hunter": every line that names a monster already says "The
        # {name}", so the article here would be read out as "The the hunter
        # strikes you". Every other monster is one lowercase word for the same
        # reason, and it also keeps the legend row inside the sidebar.
        name="hunter",
        glyph="X",
        # Its own red. ``bright_red`` is the draughts', and a monster that is
        # the same colour as a potion is a monster the eye reads as loot.
        color="#ff5555",
        # The only thing down here that comes *looking*. Everything else waits
        # to be walked into or drifts at the player once it can see them; this
        # one knows where they are from the moment the floor is built and walks
        # there, however far away that is.
        #
        # It is a decision rather than a wall: it can be outrun (speed 1.4
        # against Noxx's 1.50, which is the one constraint in the whole balance)
        # and it can be left behind on the stairs. Killing it is worth a great
        # deal -- more health than anything else on the floor, a heavy purse,
        # and the only monster in the dungeon with a *rule* to leave behind --
        # and is still not the answer a floor is asking for.
        behaviour="hunter",
        stats=Stats(
            max_hp=80, hp=80, speed=1.4, damage=(7, 11), accuracy=2, armor=2
        ),
        gold=(60, 90),
        # Never rolled: the floor spawns it deliberately, or not at all. See
        # ``world/generator.py``.
        weight=0.0,
    ),
}


def make_enemy(template: EnemyTemplate, position: Pos) -> Actor:
    """Create a fresh actor from an enemy template."""
    return Actor(
        name=template.name,
        kind=ActorKind.ENEMY,
        # Copy for the same reason as make_hero: templates outlive every actor.
        stats=replace(template.stats),
        position=position,
        glyph=template.glyph,
        color=template.color,
        behaviour=template.behaviour,
        gold=template.gold,
        curse_chance=template.curse_chance,
        inflicts=template.inflicts,
    )


def make_fortress(position: Pos, health: int) -> Actor:
    """Raise Yeti's wall of ice.

    ``health`` is twice what Yeti had when he built it -- the wall is not a
    second Yeti, it is a thicker one, and a bastion that broke as fast as its
    builder bleeds would never earn the sight it takes.
    """
    return Actor(
        name="the frozen fortress",
        kind=ActorKind.FORTRESS,
        # Hit points only, and none of Yeti's armour: the promise was half his
        # *blood* in a wall of ice, not half his kit. An armoured wall would
        # soak the very bites it exists to take.
        stats=replace(
            HEROES["yeti"].stats,
            hp=health,
            max_hp=health,
            armor=0,
            evasion=0,
        ),
        position=position,
        # Black, not ice-blue: the fortress puts the whole floor on white, and
        # the one glyph that has to be found at a glance should not be the one
        # that washes out in its own weather.
        glyph="F",
        color="#0b0f12",
        behaviour="fortress",
        gold=(0, 0),
        curse_chance=0.0,
    )


def make_atritas(position: Pos, level: int, depth: int) -> Actor:
    """Set the dark on its feet beside Noxx.

    The damage is the summoner's yardstick, not a whisper: this is the part of
    the void the promise names enormous, so it scales with the depth the way
    everything that hits does, and a little with the level the void was given
    into at. One tile, one shape, one dark letter.
    """
    low = 18 + 3 * depth + level
    return Actor(
        name="atritas",
        kind=ActorKind.ATRITAS,
        # Health is irrelevant: nothing may strike the shadow. One rather than
        # zero, because an actor at zero health is a corpse by convention.
        stats=replace(HEROES["noxx"].stats, hp=1, max_hp=1, damage=(low, low + 6)),
        position=position,
        glyph="A",
        color="#12716f",
        behaviour="atritas",
        gold=(0, 0),
        curse_chance=0.0,
    )


def make_npc(npc: Npc, position: Pos) -> Actor:
    """Create a fresh actor from an NPC definition.

    One hit point and no attacks, because nothing here is a fight. They are not
    in the turn queue and never will be, so the stats are only what the character
    sheet would say about them, which is nothing.
    """
    return Actor(
        name=npc.name,
        kind=ActorKind.NPC,
        stats=Stats(max_hp=1, hp=1),
        position=position,
        glyph=NPC_GLYPH,
        color=NPC_COLOR,
        npc=npc.key,
    )


def scale_template(template: EnemyTemplate, depth: int) -> EnemyTemplate:
    """Return ``template`` as it appears on ``depth``.

    Health and damage scale with :func:`~game.difficulty.potency`; speed closes
    most of the gap to :data:`~game.difficulty.MAX_ENEMY_SPEED` by
    :func:`~game.difficulty.enemy_speed`, so a deep-floor wraith is genuinely
    faster than a floor-1 wraith while nothing in the dungeon ever acts more
    often than the hero does -- and, unlike a plain clamp, a fast monster stays
    faster than a slow one all the way down. Armour, evasion and
    accuracy stay put: they are small integers, and doubling an armour value
    would subtract more from every hit than doubling damage adds.

    At ``depth == 1`` the template comes back unchanged, which is what lets
    ``ENEMIES`` double as the floor-1 reference.
    """
    factor = potency(depth)
    if factor == 1.0:
        return template

    low, high = template.stats.damage
    stats = replace(
        template.stats,
        max_hp=round(template.stats.max_hp * factor),
        hp=round(template.stats.max_hp * factor),
        damage=(
            max(1, round(low * factor)),
            max(1, round(high * factor)),
        ),
        # Closing the gap rather than clamping: a clamp gave every monster the
        # same speed by floor five, which is the opposite of what a floor with
        # three kinds of monster on it is for.
        speed=enemy_speed(template.stats.speed, depth),
    )
    # The purse scales with the same factor as the damage: a deep floor pays
    # better, which is the whole reason to keep going down rather than farm the
    # first three.
    low, high = template.gold
    gold = (max(1, round(low * factor)), max(1, round(high * factor)))
    return replace(template, stats=stats, gold=gold)


def pick_enemy_template(rng: Rng, depth: int = 1) -> EnemyTemplate:
    """Choose an enemy for a floor at ``depth``, honouring spawn weights.

    Both the weights (via ``weight_growth``) and the returned stats are depth
    dependent, so this is the only place a floor's population is decided.
    """
    weights = [
        (t, weight_at_depth(t.weight, t.weight_growth, depth))
        for t in ENEMIES.values()
        # A weight of zero is "never rolled". The hunter is placed by the floor
        # rather than drawn from the table, and leaving it in with a zero would
        # be a trap for whatever ``choice_weighted`` does with one.
        if t.weight > 0
    ]
    return scale_template(rng.choice_weighted(weights), depth)
