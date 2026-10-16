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
from neverdeads_revenge.game.battle import (  # noqa: E402
    ATTACK,
    ITEM,
    SPECIAL,
    open_fight,
)
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


def _room_for_loot(state) -> bool:
    """Whether the pack will take one more thing.

    The game's own capacity, and not the bot's preference: the two are different
    numbers, and asking for a pickup the pack refuses spends *no turn*. So a bot
    that believed its own limit pressed the same key at the same elixir until
    the idle rule ended the run -- which was two thirds of a batch: twenty-four
    runs out of thirty-six, all of them reported as depth and none of them
    measuring anything.
    """
    return len(state.inventory) < min(CARRY_LIMIT, state.pack_capacity)


def _pickable(state, item) -> bool:
    """Whether the *game* will take this thing off the floor.

    Three cases and not one, because the game has three: a coin and a torn page
    are always pocketed, a blade or a coat or an amulet goes into its own slot
    and never touches the pack at all, and everything else needs a free slot in
    a pack with as many slots as the shop sold.

    The bot's own rule was one case -- "is there room?" -- and a stricter rule
    than the game's is a run spent doing nothing: a weapon underfoot with a full
    pack is one the bot walked onto, was told there was no room for, walked off,
    and wanted again from the next square. Two squares, north and south, for
    fifteen hundred turns, which is what a capped run was.
    """
    if item.kind in ("coin", "page") or item.slot is not None:
        return True
    return _room_for_loot(state)

#: What a turn is worth before the bot decides it is stuck and gives up.
#: How long one fight may run before the bot gives up on it.
FIGHT_CAP = 200
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
    fights: int = 0
    tricks: int = 0
    #: The run did not end, it *stopped*: the bot had nothing it could do. Worth
    #: separating from a death, because a stall is the tool's fault and a death is
    #: the game's, and the report used to call both of them dying.
    stuck: bool = False
    #: And the same for the safety net: a run that ran out of turns did not die
    #: either, and its depth is where the clock stopped rather than where the
    #: floor did. Rare -- but a cap that fires silently is a number nobody can
    #: tell from a measurement.
    capped: bool = False

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


def fight_out(state, fight, spend: bool = False) -> int:
    """Play one fight the way the bot plays everything: competently, no ideas.

    Swing; drink when the wound is bad; and -- only if the caller asked for it --
    spend kill points on the *dearest* thing he can afford, which is what a player
    who wants the big numbers does. Off by default: the bot is the floor of what a
    player is, and the floor does not use its tricks.

    This used to be the floor's own business: a monster was fought by walking into
    it, and the dungeon resolved the blow. The arena resolves them now, so a run
    bot that walked on with an encounter pending was measuring a game where
    nothing could be killed -- which is exactly what it reported, for a while:
    every hero, floor one, no kills.
    """
    spent = 0
    fight.begin()
    guard = 0
    while not fight.over and guard < FIGHT_CAP:
        guard += 1
        living = fight.living_enemies()
        if not living:
            break
        hurt = state.player.hp / state.player.max_hp < DRINK_BELOW
        if hurt and any(item.heal for item in state.inventory):
            fight.choose(ITEM)
            continue
        chosen = None
        if spend:
            affordable = [one for one in fight.learned() if fight.special_available(one)]
            if affordable:
                chosen = max(affordable, key=lambda one: one.cost)
        if chosen is None:
            fight.choose(ATTACK, living[0])
        else:
            fight.choose(SPECIAL, living[0], special=chosen.key)
            spent += 1
    return spent


def play(
    seed: int,
    hero: str = "noxx",
    loadout: Loadout | None = None,
    fame: bool = False,
    tricks: bool = False,
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
        elif standing_on is not None and not on_chest and _pickable(state, standing_on):
            # Only when there is room for it. A full pack refuses the pickup and
            # the *turn is not spent*, so a bot that asked anyway stood on the
            # same coin pressing the same key until the idle rule ended the run
            # -- which is what "died on floor one with two kills" was, for every
            # hero, in every loadout, for as long as this file has been measuring
            # a game with an arena in it. The check was the bot's own limit of
            # three, against a pack that holds two: the same stall, from the
            # other side, for as long as the shop has sold pack room.
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
        if state.encounter is not None:
            # The floor handed a fight over and the arena is where blows happen.
            fight = open_fight(state)
            if fight is not None:
                run.fights += 1
                run.tricks += fight_out(state, fight, spend=tricks)
        idle = 0 if state.total_turns != before_turns else idle + 1
        if idle > MAX_IDLE_TURNS:
            run.stuck = True
            break

    run.capped = not state.over and state.total_turns >= TURN_CAP
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

    if _room_for_loot(state):
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

    # The exit is *always* on the list. It used to be the fallback for when there
    # was nothing else to want, which meant one unreachable coin -- behind a
    # monster, across a gap -- starved the whole run: the bot asked for a step to
    # the loot, got none, and waited out the turn cap standing still. Which is
    # what every "runs die on floor one with two kills" number in this file was
    # actually measuring.
    if state.exit_pos is not None:
        targets.append(state.exit_pos)

    # A goal with somebody standing on it is only walkable-at if that somebody is
    # a monster: a monster's square is a fight and a fight is progress, but an
    # NPC's square refuses the move and spends no turn, so the path to it is a
    # path to a wall. That was the last of the stalls: a coin under an NPC, and a
    # bot pressing the same key at it until the idle rule ended the run.
    living = {id(enemy) for enemy in state.living_enemies}
    targets = [
        pos
        for pos in targets
        if state.actor_at(pos) is None or id(state.actor_at(pos)) in living
    ]

    step = _bfs_step(state, targets)
    if step is not None:
        return _towards(state, step)

    # And if even the stairs cannot be walked to, the way there is *through*
    # something: go at the nearest monster that can be reached, and let the arena
    # settle it. A player does this without thinking about it.
    reachable = [
        enemy
        for enemy in state.living_enemies
        if _bfs_step(state, [enemy.position]) is not None
    ]
    if reachable:
        nearest = min(
            reachable,
            key=lambda enemy: max(
                abs(enemy.position[0] - state.player.position[0]),
                abs(enemy.position[1] - state.player.position[1]),
            ),
        )
        return _towards(state, nearest.position)
    return Action.WAIT


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

    @property
    def capped(self) -> int:
        """How many runs ran out of clock before the game ended them."""
        return sum(run.capped for run in self.runs)

    @property
    def stuck(self) -> int:
        """How many runs *stopped* rather than died.

        On the line and not in a footnote: a stall is the tool's fault and a
        death is the game's, and every number in this file is a claim about the
        game. A batch where a third of the runs gave up is not a measurement of
        anything, and it has to say so where it is read.
        """
        return sum(run.stuck for run in self.runs)

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
            f"washed {sum(r.cleansed for r in self.runs):3}  "
            f"stuck {self.stuck:3}  "
            f"capped {self.capped:3}"
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
    tricks: bool = False,
) -> list[Run]:
    """Play ``seeds`` runs a hero and report them."""
    runs: list[Run] = []
    for hero in heroes:
        hero_runs = [
            play(seed, hero, loadout, fame=fame, tricks=tricks) for seed in range(seeds)
        ]
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
    parser.add_argument(
        "--tricks",
        action="store_true",
        help="spend kill points on the dearest trick he can afford",
    )
    args = parser.parse_args(argv)

    heroes = args.hero or list(HEROES)
    for hero in heroes:
        if hero not in HEROES:
            parser.error(f"no hero called {hero!r}; try one of {', '.join(HEROES)}")

    loadout = FULL if args.loadout == "full" else None
    print(
        f"{args.seeds} seeds a hero, loadout: {args.loadout}"
        f"{', every chest taken for fame' if args.fame else ''}"
        f"{', spending kill points' if args.tricks else ', swinging only'}\n"
    )
    runs = batch(heroes, args.seeds, loadout, fame=args.fame, tricks=args.tricks)

    print()
    depths = Counter(run.depth for run in runs)
    print(f"escaped        {sum(r.escaped for r in runs)}/{len(runs)}")
    print(f"stuck          {sum(r.stuck for r in runs)}/{len(runs)}")
    print(f"capped         {sum(r.capped for r in runs)}/{len(runs)}")
    print(f"depth mean     {statistics.mean(r.depth for r in runs):.2f}")
    print(f"depth histogram {dict(sorted(depths.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
