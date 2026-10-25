"""How the Tenth Door feels: one door's weather at a time.

The arena barometer measures the ordinary run. This one measures the mode that
starts at floor ten with level eighteen and the house's credit: it plays the
same ground fights and reports what the ring's rule did to them. It is not a
rule and it does not decide whether a run is winnable; it says where the ground
started costing more than the credit bought.

    python tools/door_balance.py [seed] [fights-per-floor]

The rule is the one the seed would actually put on that ring, so the report is
one run's weather rather than four unrelated averages.
"""

from __future__ import annotations

import sys
from statistics import mean, median

from arena_balance import HEROES_TO_TRY, simulate
from neverdeads_revenge.game.rings import rule_for

__all__ = ["FLOORS", "ring_for_depth", "report"]

FLOORS = (10, 15, 20, 25, 30, 35)


def ring_for_depth(depth: int) -> int:
    """The ring a floor belongs to: ten is one, fifteen is two, twenty is two."""
    return depth // 10 + (1 if depth % 10 else 0)


def report(seed: int = 3, fights: int = 2) -> None:
    print(
        f"seed {seed}: Tenth Door, credit level 18, no boons, {fights} fights a floor"
    )
    print(
        f"{'hero':11s} {'floor':5s} {'ring':4s} {'rule':16s} "
        f"{'crowd':6s} {'rounds med/mean':17s} {'health lost':11s} {'died':5s}"
    )
    for hero in HEROES_TO_TRY:
        for depth in FLOORS:
            ring = ring_for_depth(depth)
            rule = rule_for(seed, ring)
            rule_key = rule.key if rule is not None else "-"
            results = simulate(
                hero,
                depth,
                fights,
                seed,
                tenth_door=True,
                ring_rule=rule_key if rule is not None else "",
            )
            if not results:
                continue
            crowds = [crowd for crowd, _rounds, _lost in results]
            rounds = [played for _crowd, played, _lost in results]
            lost = [cost for _crowd, _rounds, cost in results]
            print(
                f"{hero:11s} {depth:<5d} {ring:<4d} {rule_key:16s} "
                f"{mean(crowds):4.1f}  {median(rounds):4.0f} / {mean(rounds):4.1f}   "
                f"{mean(lost) * 100:5.0f}%    {sum(cost >= 1.0 for cost in lost):>3d}"
            )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    seed = int(args[0]) if len(args) > 0 else 3
    fights = int(args[1]) if len(args) > 1 else 2
    report(seed, fights)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
