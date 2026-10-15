"""What a run teaches you.

Between the shop's permanent upgrades and the floor's own numbers there was
nothing that grew *during* a run except equipment, and equipment arrives in
jumps and is over by floor four. A run is ten floors long and the monsters get
22.5% harder on each of them; something has to keep up, and it should be the hero.
So kills teach.

A level is a small package of stats -- small enough that three or four of them
are worth about one floor of enemy scaling, which is what makes the curve feel
steady rather than spiky. Health every level, because health is the resource a
run spends and the one the player actually watches; then a rotation of damage,
armour and speed. A run that dies on floor three has had none of the rotation; a
run that reaches floor nine has had all of it a few times.

Automatic rather than a choice. A talent pick needs a screen, a screen needs a
key, and the point of this is that the player notices themselves getting stronger
without having to stop and think about it. The decisions worth stopping for are
in the shop, between runs, where they belong.

Lives in ``game/`` and knows nothing about a terminal: the whole curve is a
function of the kill count, so it can be read off rather than played for.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .actors import Actor

__all__ = [
    "Gain",
    "KILLS_PER_LEVEL",
    "MAX_LEVEL",
    "KILL_POINTS",
    "kill_points_for",
    "level_for",
    "gains_for",
    "gains_between",
    "apply_gain",
]

#: Kills that buy one level.
#:
#: Four, and the number is doing two jobs. The floors hold ``11 + depth`` monsters,
#: so a floor you clear is two or three levels -- fast enough that the reward for
#: fighting arrives while the fight still matters. And it makes the *deep* floors
#: the ones that teach fastest, which is the right way round: the run should
#: accelerate into the danger, not away from it.
KILLS_PER_LEVEL = 4

#: The level a run stops teaching at.
#:
#: Set at the ceiling rather than near it. A perfect clear is every monster on
#: all ten floors, and there are ``sum(11 + depth for depth in 1..10)`` = 165 of
#: them, which at :data:`KILLS_PER_LEVEL` is level 42. Forty-one is the last
#: level a run can be *working toward*: the last few kills of a perfect clear
#: have nothing left to teach, and they are only reachable by clearing every
#: floor completely, which no measured run has ever come close to.
#:
#: It used to be twenty, which was a wall a thorough run could feel without ever
#: being told it was there.
MAX_LEVEL = 41

#: Kill points: what the tricks are paid from, by level.
#:
#: The old economy was "each trick once a fight", which is not an economy at all
#: -- it is a checklist. Every fight you used each of yours once and there was
#: never a decision in it. Kill points are one purse for the whole kit, so the
#: question is not *have I used this one* but *is this one worth its price now*:
#: a cheap wound twice, or one big thing once, or nothing at all and wait.
#:
#: The table is the ceiling; the purse fills by one at every turn of the hero's
#: and to the brim on a level. So a level-2 hero can afford the knife twice in
#: one fight, and the void -- the dark's own ask at level seven -- costs more
#: than a level-seven hero can *hold*: it is a thing you save for, which is what
#: an ultimate should be.
KILL_POINTS: tuple[int, ...] = (
    3, 4, 5, 6, 8, 10, 12, 14, 16, 18,  # levels one to ten
    21, 24, 27, 30, 33, 36, 39, 42, 45, 48,
    51, 54, 57, 60, 63, 66, 69, 72, 75, 78,
    81, 84, 87, 90, 93, 96, 99, 102, 105, 108, 111,
)


def kill_points_for(level: int) -> int:
    """How big the purse is at a level.

    Off the end of the table the purse stops growing rather than crashing: the
    last levels of a perfect clear are already beyond anything a run reaches,
    and a run that somehow got there should not find its tricks unaffordable.
    """
    return KILL_POINTS[max(0, min(level, len(KILL_POINTS)) - 1)]


@dataclass(frozen=True, slots=True)
class Gain:
    """What one level grants."""

    max_hp: int = 0
    damage: int = 0
    armor: int = 0
    speed: float = 0.0
    crit_chance: float = 0.0

    def __add__(self, other: Gain) -> Gain:
        return Gain(
            max_hp=self.max_hp + other.max_hp,
            damage=self.damage + other.damage,
            armor=self.armor + other.armor,
            speed=self.speed + other.speed,
            crit_chance=self.crit_chance + other.crit_chance,
        )

    @property
    def is_empty(self) -> bool:
        return self == Gain()

    def describe(self) -> str:
        """The gain as a line for the message log."""
        parts: list[str] = []
        if self.max_hp:
            parts.append(f"+{self.max_hp} max health")
        if self.damage:
            parts.append(f"+{self.damage} damage")
        if self.armor:
            parts.append(f"+{self.armor} armour")
        if self.speed:
            parts.append(f"+{self.speed:.2f} speed")
        if self.crit_chance:
            parts.append(f"+{self.crit_chance:.0%} crit")
        return ", ".join(parts) if parts else "nothing worth writing down"


def level_for(kills: int) -> int:
    """The level a run with this many kills has reached.

    Derived rather than counted up, so a level can never be lost or double-paid
    by a missed call: the kill count is the truth and everything else follows
    from it.
    """
    return max(1, min(MAX_LEVEL, 1 + kills // KILLS_PER_LEVEL))


def gains_for(level: int) -> Gain:
    """What reaching ``level`` grants.

    Health every level and then a rotation, so no single stat runs away with the
    run and every hero gets something. The rotation lengths are coprime on
    purpose: if damage came every third level and armour every third as well, the
    two would always arrive together and the run would feel like a staircase.
    """
    if level < 2 or level > MAX_LEVEL:
        # Above the cap, and below the first level. Nothing is granted, so a
        # caller that asks for level twenty-one gets the same nothing it would
        # get for level one rather than a package that never reaches a hero.
        return Gain()
    gain = Gain(max_hp=2)
    if level % 3 == 0:
        gain = replace(gain, damage=1)
    if level % 4 == 0:
        gain = replace(gain, armor=1)
    if level % 5 == 0:
        gain = replace(gain, speed=0.05)
    return gain


def gains_between(before: int, after: int) -> Gain:
    """Everything the levels from ``before`` to ``after`` add up to."""
    total = Gain()
    for level in range(before + 1, after + 1):
        total = total + gains_for(level)
    return total


def apply_gain(player: Actor, gain: Gain) -> None:
    """Fold a level's package into the hero.

    Writes into the hero's own ``Stats`` rather than into a bonus field, because
    a level is not a bonus and does not lapse: it is the hero, and it survives
    every descent. The new health arrives as health you *have* -- a level that
    raised the ceiling and left you at the old number would be a level you have
    to drink your way back to.
    """
    if gain.max_hp:
        player.stats.max_hp += gain.max_hp
        player.stats.hp += gain.max_hp
    if gain.damage:
        low, high = player.stats.damage
        player.stats.damage = (low + gain.damage, high + gain.damage)
    if gain.armor:
        player.stats.armor += gain.armor
    if gain.speed:
        player.stats.speed += gain.speed
    if gain.crit_chance:
        player.stats.crit_chance += gain.crit_chance
