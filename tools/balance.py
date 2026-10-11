#!/usr/bin/env python3
"""The measuring instrument.

Not a test. A bot that plays the way a competent but unimaginative player does
-- kills what is beside it, drinks when hurt, picks up what is worth walking to,
washes a curse off when it can afford to, and beelines for the exit otherwise --
plus a report of what happened over a batch of seeds.

Every number in the README's balance tables came out of this. It lives in the
repository rather than in somebody's scratch directory because a measurement
nobody can repeat is a claim, not a measurement:

    python3 tools/balance.py                 # 40 seeds a hero
    python3 tools/balance.py 8               # a quick look
    python3 tools/balance.py --hero yeti
    python3 tools/balance.py --loadout full  # with the shop spent

It is deliberately *not* a good player. A bot that kites, counts, and plans is a
bot that tells you what the game is like for somebody who has already mastered
it; this one is the floor, and the floor is what the difficulty dials are for.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from neverdeads_revenge.core.direction import Direction  # noqa: E402
from neverdeads_revenge.game.actions import Action, perform_action  # noqa: E402
from neverdeads_revenge.game.actors import HEROES  # noqa: E402
from neverdeads_revenge.game.shop import Loadout  # noqa: E402
from neverdeads_revenge.game.state import RunState, start_run  # noqa: E402

#: Every action that moves, and the offset it moves by.
MOVES: dict[Action, tuple[int, int]] = {
    action: action.direction.step((0, 0))
    for action in Action
    if action.direction is not Direction.NONE
}

#: Drink when the health drops below this fraction of the maximum.
DRINK_BELOW = 0.55

#: How many draughts the bot bothers to carry. Beyond this the detours cost more
#: turns than the health is worth, which is a decision a player makes by feel.
CARRY_LIMIT = 3

#: What a turn is worth before the bot decides it is stuck and gives up.
MAX_IDLE_TURNS = 80

#: The turn cap for one run. Well past any real run; a safety net, not a policy.
TURN_CAP = 1500


@dataclass(slots=True)
class Run:
    """What one run came to."""

    hero: str
    seed: int
    depth: int = 1
    kills: int = 0
    turns: int = 0
    gold: int = 0
    score: int = 0
    fame: int = 0
    level: int = 1
    curses: int = 0
    cleansed: int = 0
    escaped: bool = False

    @property
    def died(self) -> bool:
        return not self.escaped


def _towards(state, target) -> Action:
    """The one move that lands exactly on ``target``, or a wait."""
    delta = (
        target[0] - state.player.position[0],
        target[1] - state.player.position[1],
    )
    for action, offset in MOVES.items():
        if offset == delta:
            return action
    return Action.WAIT


def _bfs_step(state, goals) -> tuple[int, int] | None:
    """The first step of a shortest walkable path to any of ``goals``.

    Breadth-first rather than greedy, because a greedy bot walks into walls and
    spends the run in a corner -- and the corner is the one place the difficulty
    dials have no effect on.
    """
    goals = set(goals)
    start = state.player.position
    if start in goals:
        return None

    frontier = [start]
    came: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while frontier:
        following = []
        for pos in frontier:
            for neighbour in state.dungeon_map.neighbours8(pos):
                if neighbour in came or not state.dungeon_map.is_walkable(neighbour):
                    continue
                came[neighbour] = pos
                if neighbour in goals:
                    step = neighbour
                    while came[step] != start:
                        step = came[step]  # type: ignore[assignment]
                    return step
                if state.actor_at(neighbour) is None:
                    following.append(neighbour)
        frontier = following
    return None


def play(
    seed: int,
    hero: str = "noxx",
    loadout: Loadout | None = None,
    fame: bool = False,
) -> Run:
    """Play one run to its end and report what happened.

    ``fame`` turns the bot into a *score* player for one axis: it walks to chests
    and pays every price for the promise instead of for the blade. That is not
    the ordinary bot -- the ordinary bot is deliberately unimaginative -- but it
    is the only way to measure what the wager costs, and a wager nobody can
    measure is a guess.
    """
    state = start_run(HEROES[hero], seed=seed, loadout=loadout)
    run = Run(hero=hero, seed=seed)
    idle = 0

    while not state.over and state.total_turns < TURN_CAP:
        run.depth = max(run.depth, state.depth)
        before_turns = state.total_turns
        player = state.player

        beside = state.enemy_beside_player()
        standing_on = state.dungeon_map.item_at(player.position)
        hurt = player.hp / player.max_hp < DRINK_BELOW
        carrying = any(item.heal for item in state.inventory)
        on_chest = standing_on is not None and standing_on.kind == "chest"
        healthy = player.hp / player.max_hp > 0.7
        can_afford_a_wash = state.gold >= state.cleanse_cost

        if state.at_the_spring and state.curses and can_afford_a_wash:
            # The dialog first, then the deed: the domain never opens a spring
            # by itself, and a bot that skipped the prompt would never wash.
            perform_action(state, Action.INTERACT)
            perform_action(state, Action.CLEANSE)
            run.cleansed += 1
            continue

        if on_chest and healthy:
            action = Action.TAKE_FAME if fame else Action.OPEN_CHEST
        elif beside is not None:
            action = _towards(state, beside.position)
        elif standing_on is not None and not on_chest:
            action = Action.PICK_UP
        elif hurt and carrying:
            action = Action.QUAFF
        elif state.on_exit:
            action = Action.DESCEND
        else:
            # Deliberately *not* seeking chests even in fame mode: walking to
            # one costs turns and depth, and a measurement that mixes the
            # detour with the curse measures neither.
            action = _explore(state, can_afford_a_wash)

        perform_action(state, action)
        idle = 0 if state.total_turns != before_turns else idle + 1
        if idle > MAX_IDLE_TURNS:
            break

    run.kills = state.kills
    run.turns = state.total_turns
    run.gold = state.gold
    run.score = state.score
    run.fame = state.fame
    run.level = state.level
    run.curses = len(state.curses)
    run.escaped = state.run_state is RunState.ESCAPED
    return run


def _explore(state, can_afford_a_wash: bool, seek_chests: bool = False) -> Action:
    """Walk towards whatever is worth walking to, or towards the exit."""
    targets: list[tuple[int, int]] = []

    if seek_chests:
        targets += [
            pos
            for pos, item in state.dungeon_map.items.items()
            if item.kind == "chest"
        ]

    if state.curses and can_afford_a_wash and state.spring_pos is not None:
        targets.append(state.spring_pos)

    if len(state.inventory) < CARRY_LIMIT:
        targets += [
            pos
            for pos, item in state.dungeon_map.items.items()
            if item.slot is None and item.kind not in ("chest", "coin")
        ]

    # Only for a slot that is empty. Chasing an item whose slot is already
    # filled means chasing the one the player just set down -- an oscillation,
    # not a decision, and it stops the bot descending at all.
    targets += [
        pos
        for pos, item in state.dungeon_map.items.items()
        if item.slot is not None and item.slot not in state.player.equipment
    ]

    if not targets:
        targets = [state.exit_pos] if state.exit_pos else []

    step = _bfs_step(state, targets)
    return Action.WAIT if step is None else _towards(state, step)


#: Everything the shop sells, bought. The "fully upgraded" row of the tables.
FULL = Loadout(
    upgrades={"vigour": 3, "haste": 2, "lantern": 1},
    pending=("elixir", "bite", "hide", "patient_knife"),
)


@dataclass(slots=True)
class Report:
    """One line of the table."""

    label: str
    runs: list[Run] = field(default_factory=list)

    @property
    def escaped(self) -> float:
        return sum(run.escaped for run in self.runs) / len(self.runs)

    def __str__(self) -> str:
        """Two lines: how the runs went, and what they were worth.

        Split rather than run together because the score is now four things
        added up and multiplied, and a line of eleven numbers is a line nobody
        reads.
        """
        survival = (
            f"escaped {sum(r.escaped for r in self.runs):2}/{len(self.runs)} "
            f"({self.escaped:4.0%})  "
            f"depth mean {statistics.mean(r.depth for r in self.runs):5.2f} "
            f"max {max(r.depth for r in self.runs):2}  "
            f"level mean {statistics.mean(r.level for r in self.runs):4.1f}  "
            f"gold {statistics.mean(r.gold for r in self.runs):5.1f}  "
            f"washed {sum(r.cleansed for r in self.runs):3}"
        )
        scoring = (
            f"kills {statistics.mean(r.kills for r in self.runs):5.1f}  "
            f"turns {statistics.mean(r.turns for r in self.runs):6.1f}  "
            f"score {statistics.mean(r.score for r in self.runs):6.0f}  "
            f"best {max(r.score for r in self.runs):6}  "
            f"fame taken {sum(r.fame for r in self.runs):3}"
        )
        return f"{self.label:26} {survival}\n{'':26} {scoring}"


def batch(
    heroes,
    seeds: int,
    loadout: Loadout | None = None,
    label: str = "",
    fame: bool = False,
) -> list[Run]:
    """Play ``seeds`` runs a hero and report them."""
    runs: list[Run] = []
    for hero in heroes:
        hero_runs = [play(seed, hero, loadout, fame=fame) for seed in range(seeds)]
        runs += hero_runs
        name = f"{hero}{label}"
        print(Report(name, hero_runs))
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play the game with a bot and count.")
    parser.add_argument("seeds", nargs="?", type=int, default=40)
    parser.add_argument("--hero", action="append", help="restrict to one hero (repeatable)")
    parser.add_argument(
        "--loadout",
        choices=("none", "full"),
        default="none",
        help="what the shop has already sold the bot",
    )
    parser.add_argument(
        "--fame",
        action="store_true",
        help="pay every chest's price for the promise instead of the blade",
    )
    args = parser.parse_args(argv)

    heroes = args.hero or list(HEROES)
    for hero in heroes:
        if hero not in HEROES:
            parser.error(f"no hero called {hero!r}; try one of {', '.join(HEROES)}")

    loadout = FULL if args.loadout == "full" else None
    print(
        f"{args.seeds} seeds a hero, loadout: {args.loadout}"
        f"{', every chest taken for fame' if args.fame else ''}\n"
    )
    runs = batch(heroes, args.seeds, loadout, fame=args.fame)

    print()
    depths = Counter(run.depth for run in runs)
    print(f"escaped        {sum(r.escaped for r in runs)}/{len(runs)}")
    print(f"depth mean     {statistics.mean(r.depth for r in runs):.2f}")
    print(f"depth histogram {dict(sorted(depths.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
