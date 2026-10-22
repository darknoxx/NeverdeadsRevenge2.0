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
    "ATRITAS_PETROL",
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
    "INFERNO",
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

    def hurt(self, amount: int, bonus_armor: int = 0, pierce: int = 0) -> int:
        """Apply ``amount`` after armour. Returns damage actually taken.

        ``bonus_armor`` is the defender's temporary armour, which lives on the
        :class:`Actor` rather than here: this object is copied from a template
        and never sees a kill, so it has no business knowing about REVENGE.

        ``pierce`` is the *attacker's*: points of armour the blow goes through
        rather than around. THE NEEDLE carries it, and a coat that is ignored in
        part is the answer a ghoul's plating asks for.
        """
        # No clamp at zero on the *armour itself*: FRAIL takes two points off, and
        # for a hero who never had two the curse used to do nothing at all. Below
        # zero it is protection that is not there, and the blow lands that much
        # harder. Pierce, though, only ever takes armour *away* -- a needle that
        # went through a coat must not add damage to a hero who had none.
        protection = self.armor + bonus_armor
        if protection > 0:
            protection = max(0, protection - pierce)
        amount = max(0, amount - protection)
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
    #: Inferno's: the wild one. Damage is a flat number and he already has the
    #: most of it; what he *does* with it is swing from anywhere, so what his
    #: kills give him is the chance that the wild swing lands where it counts.
    CRIT = "crit"

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
        if self is Trait.CRIT:
            return f"+{amount:.0%} crit"
        return f"+{int(amount)} {self.value}"


#: What each grant is called by the hero who uses it: BLACK TIDE for Noxx,
#: FROZEN FORTRESS for Yeti, AURAL BLADE for Walkyrion.
REVENGE_TITLES: dict["Trait", str] = {
    Trait.SPEED: "BLACK TIDE",
    Trait.ARMOUR: "FROZEN FORTRESS",
    Trait.DAMAGE: "AURAL BLADE",
    Trait.CRIT: "WILD FIRE",
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
    #: Five points a stack, four stacks: a fifth of the wild swings find the
    #: throat by the end of a chain. Noxx's crit is a *plan* -- he sets it up and
    #: takes it -- and this is the other thing a crit can be, which is luck that
    #: arrives more often the more of a mess he has made.
    Trait.CRIT: 0.05,
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
    Trait.CRIT: 4,
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
    #: Whether this actor is still in the fight. Kept beside ``stats.hp`` and
    #: not derived from it, so the two have to be kept in step by hand -- and a
    #: dead thing that still answers ``alive`` blocks the tile it died on and
    #: raises a fight the arena refuses, which is a corpse the player presses
    #: into for nothing. Every death goes through ``_on_death``; that is where
    #: the two are made to agree.
    alive: bool = True
    #: Coins this actor leaves behind when it dies. Copied from the template so
    #: the kill does not have to go looking for which monster it was.
    gold: tuple[int, int] = (0, 0)
    #: Chance per landed blow that this actor's touch leaves a curse behind.
    curse_chance: float = 0.0
    #: Statuses this actor's blows leave running, by key. Copied from the
    #: template for a monster; the player's is read off the blade in hand.
    inflicts: tuple[str, ...] = ()
    #: Statuses this actor takes on *itself* whenever it lands a blow, and the
    #: damage it gives back to whoever lands one on it. Both are the monster's,
    #: for one monster each: the already-dying and the briar.
    self_inflicts: tuple[str, ...] = ()
    thorns: int = 0
    #: Whether it is awake. One monster sleeps until something wakes it, and a
    #: sleeper that acts is a monster you cannot walk past.
    awake: bool = True
    #: What a blow *into* it is worth, and what a wound on it is worth. One
    #: monster is the other way round -- the leech barely feels steel and comes
    #: apart at a bleed -- and the fight reads both here rather than by name.
    blow_scale: float = 1.0
    status_scale: float = 1.0
    #: The share of a landed blow it gives straight back. The unbroken does
    #: half, in blood, and never swings at all.
    reflect_share: float = 0.0
    #: What a thief has taken off the hero. The picker leaves when it has
    #: something to leave with, and this is what says it does.
    stolen: int = 0
    #: Which NPC this is, by key. ``None`` for everything that is not a person.
    npc: str | None = None
    #: A picture of its own, when its name is not the file. One actor has it:
    #: the echo wears the *front* of the hero whose run it is, because it walks
    #: towards the player rather than away.
    art: str | None = None
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
    #: Flat damage from a trick that found the note the blade is for. Its own
    #: field rather than ``damage_bonus``, which REVENGE rewrites on every kill.
    note_bonus: int = 0
    crit_bonus: float = 0.0
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
    #: How deep each of those is: one stack by default, three at most, and only
    #: for the wounds that stack. Kept beside ``statuses`` rather than inside it
    #: because a dict of ints is what a hundred lines of this game already read
    #: (the turns), and the depth is one number that two rules write.
    status_stacks: dict[str, int] = field(default_factory=dict)
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
    def weapon_inflicts(self) -> tuple[str, ...]:
        """What the blade in his hand leaves behind -- and nothing if he has none.

        Read off the equipment and not remembered, so a weapon swapped mid-floor
        shows what the *next* swing will do. The arena writes it next to ATTACK,
        which is why it lives here rather than in the rule that uses it: one
        answer, two readers.
        """
        weapon = self.equipment.get("weapon")
        return weapon.inflicts if weapon is not None else ()

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
    def pierce(self) -> int:
        """Armour this actor's blows go through: the weapon's, and nobody else's.

        Read off the blade at the moment of the swing, like every other weapon
        property: one swapped mid-floor works on the next blow.
        """
        if not self.is_player:
            return 0
        weapon = self.equipment.get("weapon")
        return weapon.modifiers.pierce if weapon is not None else 0

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
        return (
            self.stats.crit_chance
            + self.modifiers.crit_chance
            + self.crit_bonus
        )

    @property
    def crit_multiplier(self) -> float:
        return self.stats.crit_multiplier + self.modifiers.crit_multiplier

    @property
    def damage_range(self) -> tuple[int, int]:
        """The damage roll before the dice, bonuses included."""
        low, high = self.stats.damage
        bonus = (
            self.damage_bonus
            + self.note_bonus
            + self.modifiers.damage
            + self.passive_damage
        )
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

    def hurt(self, amount: int, pierce: int = 0) -> int:
        """Take a hit, after everything this actor has on.

        The armour is passed down to ``Stats`` rather than subtracted here so
        there is exactly one place that knows what armour does. What is passed is
        ``armor`` minus the base, so a new source of armour cannot be added to the
        property and forgotten here -- which is the bug this line exists to not
        have.

        ``pierce`` is the attacker's, and is passed the same way: the one place
        that knows what armour does also knows what going *through* it does.
        """
        return self.stats.hurt(amount, self.armor - self.stats.armor, pierce)

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


#: The dark's own petrol: Noxx's, and the shadow he casts. One constant because
#: they are one colour, and a hero and his shadow drifting apart in the palette
#: is exactly the kind of thing nobody notices until a screenshot.
#:
#: A hex rather than the name "teal", for the reason every hero's is a hex:
#: named colours get snapped to the terminal's nearest palette entry, and the
#: dark is not the terminal's business.
ATRITAS_PETROL = "#12716f"


#: Noxx -- high speed, high crit, low durability. Hits and runs.
#:
#: ``N`` rather than the usual ``@``: this hero has a name, and the map is where
#: the player spends the whole run looking at him.



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
    # The dark's own petrol, which is to say the same colour as the shadow he
    # casts: Atritas is Noxx's dark, and a hero and his shadow wearing two
    # colours was two characters in one coat.
    color=ATRITAS_PETROL,
    stats=Stats(
        # Thirty-four, down from forty-two -- the smallest body in the roster,
        # shared with Inferno, who is the other hero whose defence is not
        # health. The points come off *health* because that is the one dial he
        # can afford to lose: his defence is evasion and his tempo (he gets more
        # turns than anything in the dungeon), so health is what he has least
        # claim on. Measured, the eight points are a real step where the four
        # were noise, and the roster's shape survives it: he is still the
        # fastest and the hardest to land on.
        max_hp=34,
        hp=34,
        speed=1.5,
        damage=(6, 9),
        crit_chance=0.25,
        crit_multiplier=2.2,
        accuracy=1,
        # Three, down from five, and the reason is what five *measured* like: a
        # ghoul's 85% becomes 35% at five and 55% at three, so five points of
        # evasion was a 59% cut to everything that swung at him -- more defence
        # than Yeti's three armour, on the hero who also gets the most turns.
        # Three still makes him the hardest of the four to land on, which is his
        # half of the trade, without the other half being decided by one stat.
        evasion=3,
        # And *no* armour, down from one. The one point was doing nothing except
        # blurring the trade: a hero whose whole defence is not being hit should
        # not also soak, or the next question is why he does not soak more.
        # Whatever he does not dodge, he takes -- which is the sentence the
        # evasion is the other half of.
        armor=0,
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
        max_hp=66,
        hp=66,
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
        max_hp=46,
        hp=46,
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

#: Inferno -- all of the damage and none of the patience.
#:
#: The fourth answer to the same question, and the only one that is not a
#: *technique*. Noxx avoids, Yeti absorbs, Walkyrion measures; Inferno closes his
#: eyes and swings, and the numbers are built so that this works often enough to
#: be a hero: the largest flat damage in the roster, on the smallest body in it,
#: with no armour at all and barely more evasion than a ghoul. What he has is the
#: first strike, and the threat that a fight he is losing is a fight he is about
#: to win -- his REVENGE is the chance that the next wild swing is a killing one.
#:
#: Deliberately the worst *survivor* of the four and the best *closer*: a player
#: who picks him is trading the whole of the late game for the early kill, and a
#: run that reaches floor eight with him has earned it.
INFERNO = Hero(
    key="inferno",
    name="Inferno",
    title="the short fuse",
    blurb=(
        "Everything he has is in his hands and there is nothing behind them. "
        "Inferno hits harder than anything down here and can take less: the "
        "fight he wins is the one he finishes before it starts."
    ),
    glyph="I",
    # Fire, and *this* fire. The bright orange end of it is taken -- the hunter
    # is #ff5555, a draught is bright_red, and the strange draughts are #f85800
    # -- so this is the deep end: embers rather than flame, which is the colour
    # the art's own hood is anyway, and the only red in the roster that is not
    # standing next to another one.
    color="#c0202a",
    stats=Stats(
        # The smallest body in the roster by a wide margin -- eight below
        # Walkyrion's, who is nobody's idea of tough -- and the largest damage.
        # Damage is flat here and crit is barely a footnote (multiplier 1.8 on a
        # 5% chance), because "a lot of flat damage" and "a lot of crit" are two
        # different heroes and the roster already has the second one.
        max_hp=34,
        hp=34,
        speed=1.30,
        damage=(13, 18),
        crit_chance=0.05,
        crit_multiplier=1.8,
        accuracy=1,
        evasion=1,
        # One, and it is the whole of what a fire blocks: the smallest body in
        # the roster with the cheapest hide over it. Not zero -- a hero whose
        # argument is the first blow has to survive the first blow -- and not
        # more, or the trade stops being damage for durability.
        armor=1,
    ),
    # Every kill teaches the swing a little luck -- see `Trait.CRIT`.
    trait=Trait.CRIT,
)


#: Registry. Later heroes drop in here and the select screen picks them up for
#: free -- that is the whole reason heroes are data and not a hardcoded branch.
#:
#: Heroes take the capital of their name and monsters stay lowercase, so a letter
#: on the map tells you which side of the fight it is on before you have read the
#: legend. The wraith had the ``W`` until Walkyrion needed it.
HEROES: dict[str, Hero] = {
    hero.key: hero for hero in (NOXX, YETI, WALKYRION, INFERNO)
}


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
    #: How this monster behaves. ``"cautious"`` is read by the movement code in
    #: :mod:`game.actions` (it hangs back until the player closes); ``"hunter"``
    #: knows where the hero is from the first step; ``"thief"`` steals and leaves;
    #: ``"kindly"`` asks first; ``"hush"`` stops the purse; ``"echo"`` wears a
    #: hero's face; and the ten newest each read where their rule happens --
    #: idle, twin, debt, judge, leech, quiet, unbroken, eater, notary, reaver.
    #: Anything else walks straight at the hero, which is still most of them.
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
    #: Never rolled before this floor. The echo is a boss and a boss on floor one
    #: is a joke that kills you; everything else is 1.
    min_depth: int = 1
    #: Statuses this monster takes *itself* every time it lands a blow. One does:
    #: the already-dying is a wound with a body around it, and the race is the
    #: whole of it.
    self_inflicts: tuple[str, ...] = ()
    #: Damage given back to whatever lands a blow on it. One does: the briar is
    #: the answer to a hero who wins by taking more turns.
    thorns: int = 0
    #: The four that fight with a rule rather than a number; see ``Actor`` for
    #: what each of them means.
    awake: bool = True
    blow_scale: float = 1.0
    status_scale: float = 1.0
    reflect_share: float = 0.0


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
        # A hex and not "cyan", for the reason Noxx's is a hex: a terminal's
        # cyan is the *dark* one -- (0,128,128), a hair from the dark's own
        # petrol -- and the ooze is not the hero. (#00e5ff is the bright one the
        # game means, and a name is not what a terminal is told.)
        color="#00e5ff",
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
    # -- the ones that ask a question instead of hitting harder ---------------
    #
    # The names are one lowercase phrase and never "the ...": every line that
    # names a monster already says "The {name}", so an article here is read out
    # as "The the hunter strikes you". The rule is the hunter's, and it is right.
    "kindly": EnemyTemplate(
        key="kindly",
        name="kindly one",
        glyph="k",
        color="#3f5f9f",
        # It does not want a fight. It asks first -- see the encounter in the
        # screen, which is where the bargain lives. What it is when refused is
        # the worst thing the floor has, which is the price of refusing.
        #
        # Which is why it has the health it has. At twenty it died in two blows
        # and refusing cost a tenth of a hero's blood -- less than the eight gold
        # it asked for, so the bargain had no weight and the "choice" was one
        # answer with a cheaper option printed beside it. Measured at depth 2,
        # refusing cost Noxx 10 health and four turns; at thirty-six it costs 20
        # and seven, which is about a third of him and more than a potion mends.
        # The damage stays where it was: a long fight is the price, a burst is a
        # death sentence for whoever had to refuse with an empty purse.
        behaviour="kindly",
        stats=Stats(max_hp=36, hp=36, speed=0.95, damage=(6, 9), accuracy=2, armor=1),
        gold=(8, 12),
        min_depth=2,
        weight=0.9,
        weight_growth=1.10,
    ),
    "hush": EnemyTemplate(
        key="hush",
        name="hush",
        glyph="h",
        color="#8a8a8a",
        # While it lives the dark does not *pay*: the arena's one kill point a
        # turn stops coming in. There is no point a kill in this game, and the
        # old sentence promised one. It does not touch health, which is the
        # whole of what it is: a hero is his tricks. A hero is his tricks, and this takes them away without touching
        # his health -- the fight nobody has practised.
        behaviour="hush",
        stats=Stats(max_hp=14, hp=14, speed=1.15, damage=(4, 6), evasion=2),
        gold=(4, 7),
        min_depth=2,
        weight=1.2,
        weight_growth=1.15,
    ),
    "dying": EnemyTemplate(
        key="dying",
        name="already-dying",
        glyph="a",
        color="#5a1f1f",
        # A wound with a body around it: every blow it lands opens one on itself.
        # It hits hard and it is nearly gone, so the fight is a race and the race
        # is the point.
        self_inflicts=("bleed",),
        stats=Stats(max_hp=10, hp=10, speed=1.05, damage=(7, 10)),
        gold=(6, 10),
        min_depth=2,
        weight=1.1,
        weight_growth=1.10,
    ),
    "briar": EnemyTemplate(
        key="briar",
        name="briar",
        glyph="b",
        color="#6b8e23",
        # What it grows, you take: thorns is the answer to a hero who wins by
        # taking more turns, and the hummingbird's nightmare.
        thorns=2,
        stats=Stats(max_hp=26, hp=26, speed=0.65, damage=(5, 7), armor=1),
        gold=(6, 11),
        min_depth=2,
        weight=1.4,
        weight_growth=1.10,
    ),
    "picker": EnemyTemplate(
        key="picker",
        name="picker",
        glyph="p",
        color="#8f4f5f",
        # It wants the purse and not the blood, and it leaves when it has what it
        # came for. The gold it carries is what it took from somebody.
        # It is not a fight, it is a *purse*: it takes a great deal of killing and
        # it is not worth the killing, which is the choice. Plenty of health so
        # that chasing it is a decision and not a reflex, and a purse worth the
        # chase when it does go down.
        behaviour="thief",
        stats=Stats(max_hp=60, hp=60, speed=1.45, damage=(3, 5), evasion=2),
        gold=(30, 45),
        min_depth=2,
        weight=0.45,
        weight_growth=1.10,
    ),
    # -- the ten that ask about the room, not the numbers --------------------
    #
    # One lowercase letter each, and the name begins with it: the rule is what
    # lets the alphabet be the roster. None of them is a bigger monster; each is
    # a fact about the *room* that the room has not had before.
    "idle": EnemyTemplate(
        key="idle",
        name="idle",
        glyph="i",
        color="#184030",
        # It sleeps until it is hit or somebody stands beside it. A monster that
        # does not act is a monster you may walk past -- the first real "leave
        # it" on the floor.
        behaviour="idle",
        awake=False,
        stats=Stats(max_hp=18, hp=18, speed=0.88, damage=(5, 8)),
        gold=(4, 8),
        min_depth=2,
        weight=0.9,
        weight_growth=1.05,
    ),
    "twin": EnemyTemplate(
        key="twin",
        name="twin",
        glyph="t",
        color="#a040c8",
        # Kill one and the other one stops grieving: full health, twice the
        # damage. The order you kill them in is the fight.
        behaviour="twin",
        stats=Stats(max_hp=22, hp=22, speed=1.08, damage=(5, 8)),
        gold=(6, 10),
        min_depth=3,
        weight=0.7,
        weight_growth=1.10,
    ),
    "debt": EnemyTemplate(
        key="debt",
        name="debt",
        glyph="d",
        color="#40c898",
        # Dying does not cancel it: the next fight on this floor collects.
        behaviour="debt",
        stats=Stats(max_hp=20, hp=20, speed=0.98, damage=(5, 8), armor=1),
        gold=(5, 9),
        min_depth=4,
        weight=0.6,
        weight_growth=1.10,
    ),
    "judge": EnemyTemplate(
        key="judge",
        name="judge",
        glyph="j",
        color="#c078e8",
        # It does not swing. It reads your curses out loud, and every one of
        # them costs a point a round.
        behaviour="judge",
        stats=Stats(max_hp=26, hp=26, speed=0.82, damage=(1, 2), armor=1),
        gold=(8, 12),
        min_depth=5,
        weight=0.5,
        weight_growth=1.10,
    ),
    "leech": EnemyTemplate(
        key="leech",
        name="leech",
        glyph="l",
        color="#80e8b8",
        # Steel is nothing to it; a wound is everything. The one monster that
        # makes a status build the *only* answer.
        behaviour="leech",
        stats=Stats(max_hp=30, hp=30, speed=0.68, damage=(3, 5)),
        gold=(5, 9),
        blow_scale=0.25,
        status_scale=2.0,
        min_depth=4,
        weight=0.7,
        weight_growth=1.10,
    ),
    "quiet": EnemyTemplate(
        key="quiet",
        name="quiet",
        glyph="q",
        color="#6058e0",
        # The pack stays shut while it lives. It takes nothing but the answer.
        behaviour="quiet",
        stats=Stats(max_hp=16, hp=16, speed=1.32, damage=(3, 5), evasion=2),
        gold=(5, 9),
        min_depth=3,
        weight=0.6,
        weight_growth=1.10,
    ),
    "unbroken": EnemyTemplate(
        key="unbroken",
        name="unbroken",
        glyph="u",
        color="#d09870",
        # It never swings, and it gives half of every blow straight back. Killing
        # it is a trade, not a fight.
        behaviour="unbroken",
        stats=Stats(max_hp=34, hp=34, speed=0.78, damage=(1, 2)),
        gold=(6, 10),
        reflect_share=0.5,
        min_depth=2,
        weight=0.8,
        weight_growth=1.10,
    ),
    "eater": EnemyTemplate(
        key="eater",
        name="eater",
        glyph="e",
        color="#30b848",
        # It eats the wounds off its friends and grows on them. A status build
        # in its room starves.
        behaviour="eater",
        stats=Stats(max_hp=28, hp=28, speed=1.02, damage=(4, 7)),
        gold=(6, 10),
        min_depth=4,
        weight=0.7,
        weight_growth=1.10,
    ),
    "notary": EnemyTemplate(
        key="notary",
        name="notary",
        glyph="n",
        color="#b8b830",
        # Its health is the floor's kill count: it bills you for what you have
        # already done, and every further kill on the floor feeds it.
        behaviour="notary",
        stats=Stats(max_hp=16, hp=16, speed=0.92, damage=(4, 7), armor=1),
        gold=(7, 11),
        min_depth=3,
        weight=0.6,
        weight_growth=1.10,
    ),
    "reaver": EnemyTemplate(
        key="reaver",
        name="reaver",
        glyph="r",
        color="#c84088",
        # It takes the blade out of your hand for the length of the fight. The
        # free swing is still free; it is the *weapon* that is gone.
        behaviour="reaver",
        stats=Stats(max_hp=26, hp=26, speed=1.12, damage=(6, 9), armor=1),
        gold=(8, 13),
        min_depth=5,
        weight=0.5,
        weight_growth=1.10,
    ),
    "echo": EnemyTemplate(
        key="echo",
        name="one who did not come back",
        glyph="@",
        color="#4a3b6b",
        # A hero out of the chronicle, with the numbers of the run that got
        # furthest. It is *built* at spawn from a score entry; this is the frame.
        behaviour="echo",
        min_depth=6,
        stats=Stats(
            max_hp=40, hp=40, speed=1.25, damage=(8, 11), accuracy=1, armor=1, evasion=1
        ),
        gold=(20, 30),
        weight=0.35,
        weight_growth=1.0,
    ),
    "lid": EnemyTemplate(
        key="lid",
        name="lid",
        glyph="&",
        color="bright_yellow",
        # Never rolled: a chest that opens into a mouth. Weight zero and a
        # behaviour of its own, because a mimic is an event and not a monster in
        # the mix.
        behaviour="mimic",
        stats=Stats(max_hp=24, hp=24, speed=0.85, damage=(6, 9), armor=2),
        gold=(10, 16),
        min_depth=1,
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
        self_inflicts=template.self_inflicts,
        thorns=template.thorns,
        awake=template.awake,
        blow_scale=template.blow_scale,
        status_scale=template.status_scale,
        reflect_share=template.reflect_share,
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
        color=ATRITAS_PETROL,
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
        if t.weight > 0 and depth >= t.min_depth
    ]
    return scale_template(rng.choice_weighted(weights), depth)
