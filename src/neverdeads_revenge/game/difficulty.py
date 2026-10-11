"""How the dungeon gets harder as you go down.

Two independent dials, deliberately kept apart:

``potency``
    How hard each individual monster hits. Scales health and damage together, so
    a tougher monster is not a sponge, it is a real threat.

``weight_growth``
    Which monsters show up at all. A floor of only buffed ghouls is the same
    fight ten times; a floor that gradually fills with faster, evasier wraiths
    changes what the player has to do about it.

Both curves are pure functions of depth and hold no state, so the balance of the
whole game can be checked by calling them rather than by playing fifty runs.

Floor 1 is the baseline by construction: ``potency(1) == 1.0`` and every growth
exponent is ``depth - 1``, so the templates in :mod:`actors` describe floor 1
exactly as written. That matters for more than tidiness -- it means the numbers
in ``actors.py`` are the numbers a new player meets, and every test that builds
an enemy from a bare template is still testing floor 1.
"""

from __future__ import annotations

__all__ = [
    "POTENCY_PER_FLOOR",
    "MAX_POTENCY",
    "MAX_ENEMY_SPEED",
    "SPEED_HORIZON",
    "GAP_CLOSED_BY_THEN",
    "potency",
    "enemy_speed",
    "weight_at_depth",
]

#: Fraction added to health and damage per floor descended.
#:
#: Lower than it has ever been, and that is the point. The wall is the *ground*
#: now, not the slope: floor one is a real fight (see the templates in actors.py)
#: and the run climbs a gentle curve on top of it. A steep curve over a soft
#: floor made the early game a formality and the late game a cliff; a shallow
#: curve over a hard floor makes every floor of the run tense, which is what a
#: run should be.
#:
#: Measured, not chosen: see the escape rates in the README.
#:
#: Raised from 0.14 on the experimental branch, because a human plays this a
#: great deal better than the bot does and reported reaching the end almost
#: every time. The bot is the *floor* -- if it is still escaping sometimes at
#: this slope, a person is still fine.
#:
#: Raised again from 0.18, on the report that a run with good equipment gets
#: *easier* as it goes. That is a slope problem as much as a ceiling one: the
#: hero levels on every floor, so the dungeon has to be climbing at least as
#: fast just to stand still. The two dials are kept in step by a test, which
#: insists the ceiling is reached exactly on the last floor and not before.
POTENCY_PER_FLOOR = 0.225

#: Ceiling on potency. Without it a floor-40 monster would be unplayable and any
#: formula mistake would silently become exponential. Just over two and a half
#: times floor 1 is enough once floor 1 is already dangerous, and the hero's own
#: levels are what the rest of the growth is for.
#:
#: Raised again on the experimental branch, from 2.6 to 3.0, and for a
#: *different* reason than the last time. The report was that a run with good
#: equipment gets easier as it goes -- which is what a ceiling does: once a floor
#: is at 2.6x, every floor after it is at 2.6x, and the hero keeps levelling.
#: Raising the ceiling moves where that flattening starts without touching floor
#: one, which is the floor a new player actually meets.
MAX_POTENCY = 3.0

#: No monster may act this fast.
#:
#: Noxx's base speed is 1.50. This is the one hard constraint in the whole
#: balance: the hero must stay strictly faster than everything in the dungeon.
#: His crit chance and his REVENGE speed stacking both pay off because he gets
#: more actions than anything else -- a single monster that outruns him turns
#: every other stat into decoration. The gap is deliberately narrow (0.05), so
#: a deep-floor wraith is genuinely faster than a floor-1 wraith without ever
#: being faster than the player.
MAX_ENEMY_SPEED = 1.45

#: The floor the speed curve is aimed at: the deepest one there is. Kept equal to
#: :data:`~world.generator.ESCAPE_DEPTH` by a test rather than by an import, so
#: this module stays arithmetic and touches nothing.
SPEED_HORIZON = 10

#: How much of the gap between a monster's speed and the ceiling the dungeon
#: closes by :data:`SPEED_HORIZON`.
#:
#: Not all of it, and that is the point. Speed used to be scaled by potency and
#: then clamped, which meant every kind of monster had reached the ceiling by
#: floor five: a ghoul, a skeleton and a wraith all acted exactly as often, and
#: the variety the three of them exist to provide was gone. The fast ones had
#: nowhere to go, so scaling them did nothing but flatten them.
#:
#: Closing most of the gap instead keeps them in the same order at every depth
#: while still making a deep floor quicker than a shallow one -- and it keeps the
#: last sliver of the gap, which belongs to the hero.
GAP_CLOSED_BY_THEN = 0.9


def potency(depth: int) -> float:
    """How much harder every monster on ``depth`` hits, relative to floor 1.

    Returns exactly ``1.0`` at depth 1 and never exceeds :data:`MAX_POTENCY`.
    """
    if depth < 1:
        return 1.0
    return min(1.0 + POTENCY_PER_FLOOR * (depth - 1), MAX_POTENCY)


def enemy_speed(base: float, depth: int) -> float:
    """How fast a monster of speed ``base`` acts on ``depth``.

    Monotone in depth, never at or past :data:`MAX_ENEMY_SPEED`, and strictly
    order-preserving: if one kind of monster is faster than another on floor 1 it
    is faster on floor 10 too, and by a smaller margin rather than by none. That
    is what a floor of mixed monsters is *for*.
    """
    if depth <= 1:
        return base
    progress = min((depth - 1) / (SPEED_HORIZON - 1), 1.0) * GAP_CLOSED_BY_THEN
    return base + (MAX_ENEMY_SPEED - base) * progress


def weight_at_depth(base: float, growth: float, depth: int) -> float:
    """Spawn weight of one monster kind on ``depth``.

    ``growth`` is the factor applied per floor: ``1.0`` keeps a monster as
    common as it was on floor 1 forever, ``1.14`` makes it fourteen percent more
    likely on each floor down. Only relative weights matter, so two monsters
    both growing at ``1.05`` is the same mix as neither growing.
    """
    if depth < 1:
        return base
    return base * growth ** (depth - 1)