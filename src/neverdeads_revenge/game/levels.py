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
    "LEVEL_COSTS",
    "kills_for_level",
    "kills_to_next",
    "MAX_LEVEL",
    "KILL_POINTS",
    "KILL_POINTS_CAP",
    "SACRIFICED_KILL_POINTS",
    "kill_points_for",
    "level_for",
    "gains_for",
    "gains_between",
    "apply_gain",
]

#: What each level costs, in kills -- level two is the first entry, and the rest
#: follow it up.
#:
#: It used to be one number: four kills a level, forever. That is a *line*, and a
#: line is the wrong shape for two reasons.
#:
#: The first is that it is invisible. A flat cost means the fifty-fifth kill of a
#: run is worth exactly what the third was, so the only thing growing is a
#: number, and what the player feels is a treadmill rather than a curve.
#:
#: The second is that the floors are not flat. Every descent makes the monsters
#: tougher and the floor longer, so a flat cost hands the hero *more* levels per
#: floor as the run goes on -- exactly when the run is supposed to be getting
#: harder. Which is what "it gets easier the longer you play" looks like from the
#: inside.
#:
#: So the cost climbs: cheap at the start (the first floor teaches three things,
#: so a new hero has a kit by the time it matters) and dearer as the run goes, so
#: the deep floors are the ones you *earn* rather than the ones you are handed.
#: Roughly: a full clear of the first five floors is level nine, where it used to
#: be eighteen -- and the ceiling is a promise no run has to reach.
LEVEL_COSTS: tuple[int, ...] = (
    3, 4, 5, 6, 7, 8, 9, 11, 12, 14,  # levels 2 to 11
    15, 17, 19, 20, 22, 24, 26, 28, 30, 32,  # 12 to 21
    34, 36, 38, 40, 43, 45, 48, 50, 53, 55,  # 22 to 31
    58, 61, 63, 66, 69, 72, 75, 78, 81, 84,  # 32 to 41
)

#: The level a run stops teaching at.
#:
#: Twenty, and that is measured: a perfect clear is every monster on all ten
#: floors, ``sum(13 + 2 * depth for depth in 1..10)`` = 240 of them, and that
#: buys level 18 on this curve. The ceiling sits just past what the dungeon can
#: pay rather than twenty-one levels past it, which was a ladder whose top half
#: no run could ever stand on.
MAX_LEVEL = 20

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
#: one fight, and the dearest trick in the game costs ten: exactly the last
#: ceiling. Past level seven the table is flat by design -- levels hand over
#: stats and tricks, not a bigger purse. See :data:`KILL_POINTS_CAP`.
KILL_POINTS: tuple[int, ...] = (
    3, 4, 5, 6, 8, 10, 12,  # levels one to seven
)

#: The purse never holds more than this, whatever the level.
#:
#: Ten is the dearest trick in the game (THE QUAKE, THE RINGING CHORD), so the
#: ceiling is "one big thing": a hero can hold the biggest trick he owns and
#: nothing else, or two smaller ones, and never a war chest. It used to grow to
#: 42 by level eighteen, which let a long fight chain four quakes -- a purse
#: that big stops being a decision and becomes a stockpile.
#:
#: The shop sells up to five more, one at a time: a permanent widening of the
#: purse, which is the only upgrade that buys *options* rather than numbers.
KILL_POINTS_CAP = 10

#: What the purse holds once a hero has given himself to an ultimate. Five: one
#: trick of the middle price and nothing else. It is the *same* price for all
#: four heroes -- a floor's ask costs the tricks you could have spent on it, not
#: a blindfold or a slow bleed, and one shared price is one rule a player can
#: learn once.
SACRIFICED_KILL_POINTS = 5


def kill_points_for(level: int) -> int:
    """How big the purse is at a level.

    Off the end of the table the purse stops growing rather than crashing: the
    last levels of a perfect clear are already beyond anything a run reaches,
    and a run that somehow got there should not find its tricks unaffordable.
    """
    return min(KILL_POINTS_CAP, KILL_POINTS[max(0, min(level, len(KILL_POINTS)) - 1)])


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


def kills_for_level(level: int) -> int:
    """The kills it takes to have *reached* ``level``: the steps added up.

    Cumulative and not the step, because that is the question a run asks -- "is
    he level five yet?" -- and because a table of steps is a table nobody can
    check by eye. Summed rather than stored, so the two can never drift.
    """
    if level <= 1:
        return 0
    return sum(LEVEL_COSTS[: min(level, MAX_LEVEL) - 1])


def level_for(kills: int) -> int:
    """The level a run with this many kills has reached.

    Derived rather than counted up, so a level can never be lost or double-paid
    by a missed call: the kill count is the truth and everything else follows
    from it. Walks the curve instead of dividing by it, because there is no one
    number to divide by any more -- each level costs more than the one before.
    """
    level = 1
    for cost in LEVEL_COSTS:
        if kills < cost:
            break
        kills -= cost
        level += 1
    return min(MAX_LEVEL, level)


def kills_to_next(kills: int) -> int:
    """How many more kills buy the next level.

    The number a player is actually owed. A level is a *budget* of kills, and
    what a run wants to know is how much of the current one is left -- so this
    is what the side panel counts and what the plate in the arena counts, and
    they ask it here so they cannot disagree. Zero at the cap, because there is
    no next level to be working toward.
    """
    level = level_for(kills)
    if level >= MAX_LEVEL:
        return 0
    return max(0, kills_for_level(level + 1) - kills)


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
