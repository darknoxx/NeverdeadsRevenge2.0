"""Persistent player data: what survives between runs.

Milestone 1 writes the file but does not yet fill it. The point of building it
now is that the shape is fixed: later upgrades and hero unlocks only need an
entry in :data:`META_UPGRADES`, not a change to how a run starts.

The save file lives in the XDG data directory so it follows the platform
convention rather than landing in the source tree.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .game.lore import PAGE_COUNT
from .game.shop import META_UPGRADES, MetaUpgrade

__all__ = [
    "ScoreEntry",
    "SCOREBOARD_SIZE",
    "MetaProgress",
    "MetaUpgrade",
    "META_UPGRADES",
    "data_dir",
    "save_path",
    "run_path",
    "save_run",
    "load_run",
    "clear_run",
    "load_meta",
    "save_meta",
    "grant_test_save",
    "TEST_GOLD",
]

SAVE_VERSION = 1

#: How many runs the scoreboard keeps. Capped because the file is rewritten on
#: every ending and a list that grows forever is a file that grows forever.
SCOREBOARD_SIZE = 10


@dataclass(slots=True)
class ScoreEntry:
    """One finished run, as the scoreboard keeps it."""

    name: str
    score: int
    depth: int
    hero: str
    won: bool

    @property
    def outcome(self) -> str:
        return "escaped" if self.won else "died"


@dataclass(slots=True)
class MetaProgress:
    """Everything that outlives a single run."""

    version: int = SAVE_VERSION
    #: Hero keys that have been unlocked.
    unlocked_heroes: list[str] = field(default_factory=lambda: ["noxx"])
    #: Upgrade key -> number of stacks bought.
    upgrades: dict[str, int] = field(default_factory=dict)
    #: Coins banked across every run. Spent in the shop, so it is the one number
    #: that survives death and is worth something afterwards.
    gold: int = 0
    #: The best runs, highest first.
    scores: list[ScoreEntry] = field(default_factory=list)
    #: The name used last, so the next run costs one keypress rather than five.
    last_name: str = ""
    #: Sound off. A setting rather than a session flag, because a player who
    #: turns the sound off in a library means it for the next time too.
    muted: bool = False
    #: Items bought for the next run, by key. Emptied when that run starts.
    pending: list[str] = field(default_factory=list)
    #: Wild offers bought and not yet spent. Emptied when that run starts.
    wilds: list[str] = field(default_factory=list)
    #: The two wild offers currently on the shelf. Re-rolled after every run.
    wild_stock: list[str] = field(default_factory=list)
    #: Which pages of the chronicle have been found, by number.
    #:
    #: A list rather than a set, because the save is JSON and a set is not --
    #: and kept sorted so the file reads in the order the book does. It is the
    #: one thing here that is a *collection* rather than a currency: gold buys,
    #: scores rank, and a page is simply known.
    pages: list[int] = field(default_factory=list)
    #: Lifetime run statistics.
    runs_started: int = 0
    runs_won: int = 0
    best_depth: int = 0
    best_score: int = 0
    total_kills: int = 0

    def record_page(self, number: int) -> bool:
        """File a page. Returns whether it was new.

        Returns the answer rather than assuming it, because the caller has a
        sound to make and a line to write, and neither is wanted for a page
        already in the book.
        """
        if number in self.pages:
            return False
        self.pages.append(number)
        self.pages.sort()
        return True

    def record_run(
        self,
        *,
        depth: int,
        score: int,
        kills: int,
        gold: int = 0,
        won: bool = False,
        name: str = "",
        hero: str = "",
    ) -> None:
        """Fold a finished run into the lifetime totals and the scoreboard.

        ``gold`` is added rather than kept at its best: coin is a currency, and a
        bad run that still picked up a purse is a run that moved you forward.
        The score, by contrast, is kept at its best -- a worse run does not lower
        anything.
        """
        self.runs_started += 1
        self.total_kills += kills
        self.gold += gold
        self.best_depth = max(self.best_depth, depth)
        self.best_score = max(self.best_score, score)
        if won:
            self.runs_won += 1

        if not name:
            return
        self.last_name = name
        self.scores.append(
            ScoreEntry(name=name, score=score, depth=depth, hero=hero, won=won)
        )
        self.scores.sort(key=lambda entry: entry.score, reverse=True)
        del self.scores[SCOREBOARD_SIZE:]

    def reroll_wilds(self, rng) -> None:
        """Put two new offers on the rotating shelf.

        Called after every run, which is what makes the shelf worth walking past:
        the fixed stock is always there, and the interesting things are not.
        """
        from .game.shop import roll_wild_stock

        self.wild_stock = roll_wild_stock(rng)


# -- storage ---------------------------------------------------------------


def data_dir() -> Path:
    """Return the directory the save file belongs in.

    Honours ``XDG_DATA_HOME`` and falls back to the platform default, so the
    source tree never collects save data.
    """
    override = os.environ.get("NEVERDEADS_REVENGE_HOME")
    if override:
        return Path(override).expanduser()

    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".local" / "share"
    return root / "neverdeads_revenge2"


def save_path() -> Path:
    """Full path of the save file."""
    return data_dir() / "meta.json"


def run_path() -> Path:
    """Where the run in progress is kept.

    Its own file rather than a corner of ``meta.json``: a run is forty kilobytes
    of map and a few hundred bytes of progress are not the same kind of thing,
    and one being corrupt should not take the other with it.
    """
    return data_dir() / "run.json"


def save_run(payload: dict) -> None:
    """Write the run in progress, over whatever was there before.

    One slot. There is no second one to write to, which is the whole reason
    quitting and reloading is not a thing a player can do twice.
    """
    _write_json(run_path(), payload)


def load_run() -> dict | None:
    """The saved run, or ``None`` if there is not one."""
    try:
        payload = json.loads(run_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def clear_run() -> None:
    """Throw the saved run away.

    Called the moment one is picked up again: a run that can be reloaded is a run
    that can be re-rolled, and the whole point of one slot is that it cannot.
    """
    run_path().unlink(missing_ok=True)


def load_meta(path: Path | None = None) -> MetaProgress:
    """Load saved progress, or return fresh progress if there is none.

    A corrupt or future-versioned file is not worth crashing over: a broken save
    should cost you your unlocks, not your ability to play.
    """
    target = path or save_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return MetaProgress()

    if not isinstance(raw, dict) or raw.get("version") != SAVE_VERSION:
        return MetaProgress()

    # Read field by field with defaults rather than by key. A save written by an
    # older build is missing whatever was added since, and the version check
    # above would otherwise have thrown the whole file away -- losing a player's
    # high score to add a coin counter.
    try:
        return MetaProgress(
            version=raw["version"],
            unlocked_heroes=list(raw.get("unlocked_heroes", ["noxx"])),
            upgrades=dict(raw.get("upgrades", {})),
            gold=int(raw.get("gold", 0)),
            scores=[
                ScoreEntry(
                    name=str(entry.get("name", "?")),
                    score=int(entry.get("score", 0)),
                    depth=int(entry.get("depth", 1)),
                    hero=str(entry.get("hero", "noxx")),
                    won=bool(entry.get("won", False)),
                )
                for entry in raw.get("scores", [])
                if isinstance(entry, dict)
            ],
            last_name=str(raw.get("last_name", "")),
            muted=bool(raw.get("muted", False)),
            pending=[str(key) for key in raw.get("pending", [])],
            wilds=[str(key) for key in raw.get("wilds", [])],
            wild_stock=[str(key) for key in raw.get("wild_stock", [])],
            pages=[int(number) for number in raw.get("pages", [])],
            runs_started=int(raw.get("runs_started", 0)),
            runs_won=int(raw.get("runs_won", 0)),
            best_depth=int(raw.get("best_depth", 0)),
            best_score=int(raw.get("best_score", 0)),
            total_kills=int(raw.get("total_kills", 0)),
        )
    except (KeyError, TypeError, ValueError):
        return MetaProgress()


def save_meta(progress: MetaProgress, path: Path | None = None) -> None:
    """Write progress to disk atomically."""
    _write_json(path or save_path(), asdict(progress), indent=2)


#: What ``--testrun`` puts in the purse. The shop's dearest line is in the
#: hundreds, so this is more coin than a run can spend -- which is the point of a
#: test save: not to be a large number but to stop being a constraint.
TEST_GOLD = 9999


def grant_test_save(path: Path | None = None) -> tuple[Path, Path | None]:
    """Fill the save for testing: every page of the chronicle, and a purse.

    A developer's flag, and it behaves like one. It *merges* rather than
    replaces, so the scoreboard, the heroes and the upgrades are whatever they
    were; the only thing it does to the old file is keep a copy of it. The copy
    is written once -- running the flag twice does not overwrite the original
    with the first test state -- so there is always exactly one file to go back
    to, and it is the one from before the first time you asked.

    Returns the save's path and the backup's, or ``None`` for the backup if
    there was nothing to back up.
    """
    target = path or save_path()
    progress = load_meta(target)

    backup: Path | None = None
    if target.exists():
        candidate = target.with_name(target.name + ".bak")
        if not candidate.exists():
            candidate.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
            backup = candidate

    progress.gold = TEST_GOLD
    progress.pages = list(range(1, PAGE_COUNT + 1))
    save_meta(progress, target)
    return target, backup


def _write_json(target: Path, payload, indent: int | None = None) -> None:
    """Write JSON to ``target`` atomically.

    A temporary file in the same directory, renamed over the target, so an
    interrupted save cannot leave a half-written file behind -- and so the run in
    progress cannot be lost to a terminal being closed at the wrong moment.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(payload, indent=indent)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=target.parent,
        prefix=".meta-",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle as stream:
            stream.write(payload)
        os.replace(handle.name, target)
    except BaseException:
        # Never leave the temp file behind on failure.
        Path(handle.name).unlink(missing_ok=True)
        raise
