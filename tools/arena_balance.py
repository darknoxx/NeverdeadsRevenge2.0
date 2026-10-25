"""How a fight feels: play a lot of them and count.

The dungeon's numbers were tuned for a map where a step was a blow, and the
arena spends them differently -- one turn each, all of a monster's health in
front of you, and no walking away in the middle. This is the measurement that
says whether they still work: it plays whole fights, hero against floor, and
reports how many rounds they take and how much of the hero they cost.

    python tools/arena_balance.py [fights-per-depth]

Nothing here is a rule; it is a barometer. If a fight of one ghoul takes nine
rounds, or a floor's worth of them leaves the hero untouched, the numbers are
saying something and this is how to hear it.
"""

from __future__ import annotations

import sys
from statistics import mean, median

from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.battle import ATTACK
from neverdeads_revenge.game.state import start_run

__all__ = ["report", "simulate"]

#: Who the fights are fought with, and how deep the floors go.
HEROES_TO_TRY = ("noxx", "yeti", "walkyrion", "inferno")
DEPTHS = (1, 3, 5, 7, 9)


def _meet_something(state):
    """Put the hero next to a monster that is really on the floor.

    Not the first three in the list -- those are scattered over the whole floor
    and a fight against them is not a fight this game produces. The crowd comes
    from `encounter_around`, which is the rule the dungeon actually uses, so the
    hero is put beside one monster and the *room* decides who joins in.
    """
    from neverdeads_revenge.core.direction import Direction
    living = [enemy for enemy in state.enemies if enemy.stats.alive]
    if not living:
        return False
    enemy = state.rng.pick(living)
    for direction in Direction:
        if direction is Direction.NONE:
            continue
        spot = direction.step(enemy.position)
        if state.dungeon_map.is_walkable(spot) and state.actor_at(spot) is None:
            state.player.position = spot
            state.refresh_vision()
            # The monster it is standing beside, so the fight can be opened the
            # way the floor hands one over: the room is still `encounter_around`.
            return enemy
    return None


def simulate(
    hero: str,
    depth: int,
    fights: int,
    seed: int,
    *,
    tenth_door: bool = False,
    ring_rule: str = "",
) -> list[tuple[int, int, float]]:
    """Play the fights a run really meets: ``(crowd, rounds, health lost)``.

    The hero swings and nothing else -- no items, no tricks -- because this is
    about whether the *ground* is right and not whether a player is clever.

    ``tenth_door`` starts at ``depth`` with the house's credit and, when
    ``ring_rule`` is given, rebuilds the floor with that ring's weather. The
    floor is rebuilt rather than patched so the tool measures the same code the
    run uses.
    """
    from neverdeads_revenge.game.actions import descend
    from neverdeads_revenge.game.battle import open_fight

    state = start_run(
        HEROES[hero],
        seed,
        tenth_door=tenth_door,
        start_depth=depth if tenth_door else 1,
    )
    if tenth_door:
        if ring_rule:
            state.ring_rule = ring_rule
            state.build_floor(depth)
    else:
        for _ in range(depth - 1):
            state.player.stats.hp = state.player.max_hp
            descend(state)
    results: list[tuple[int, int, float]] = []
    for _ in range(fights):
        if state.over:
            break
        trigger = _meet_something(state)
        if trigger is None:
            break
        state.player.stats.hp = state.player.max_hp
        fight = open_fight(state, trigger)
        if fight is None:
            continue
        crowd = len(fight.enemies)
        fight.begin()
        rounds = 0
        while not fight.over and rounds < 60:
            rounds += 1
            living = fight.living_enemies()
            if not living:
                break
            fight.choose(ATTACK, living[0])
        lost = (state.player.max_hp - state.player.stats.hp) / max(
            1, state.player.max_hp
        )
        results.append((crowd, rounds, lost))
    return results


def report(fights: int) -> None:
    print(
        f"{'hero':11s} {'floor':5s} {'fights':6s} {'crowd (avg/max)':16s} "
        f"{'rounds (med/mean)':18s} {'health lost':12s} {'died':5s}"
    )
    for hero in HEROES_TO_TRY:
        for depth in DEPTHS:
            crowds: list[int] = []
            rounds: list[int] = []
            lost: list[float] = []
            died = 0
            for seed in range(1, 9):
                for crowd, played, cost in simulate(hero, depth, fights, seed):
                    crowds.append(crowd)
                    rounds.append(played)
                    lost.append(cost)
                    died += cost >= 1.0
            if not rounds:
                continue
            print(
                f"{hero:11s} {depth:<5d} {len(rounds):<6d} "
                f"{mean(crowds):4.1f} / {max(crowds):<9d} "
                f"{median(rounds):<6.0f} {mean(rounds):<11.1f} "
                f"{mean(lost) * 100:5.0f}% of health {died:>4d}"
            )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    report(int(args[0]) if args else 4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
