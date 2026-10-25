"""Feats: the things a run can prove after it is over.

A feat is not a score and not a purchase. It is a sentence the game can say
about what happened, kept forever, and it is checked when the run is written
down rather than while it is played -- a card that appeared mid-fight would be
the game interrupting the fight to congratulate itself.

The list is deliberately small. A feat that every run earns is a participation
line; a feat that needs a *particular* run is a thing a player can aim at.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Feat", "FEATS", "FEAT_BY_KEY", "earned", "award"]


@dataclass(frozen=True, slots=True)
class Feat:
    key: str
    name: str
    blurb: str


FEATS: tuple[Feat, ...] = (
    Feat(
        "first_blood",
        "FIRST BLOOD",
        "Finish a run and put a name on the board.",
    ),
    Feat(
        "escaped",
        "OUT OF THE DARK",
        "Leave through the rift on floor ten.",
    ),
    Feat(
        "door_opened",
        "THE TENTH DOOR",
        "Set foot in the endless mode.",
    ),
    Feat(
        "second_ring",
        "THE SECOND RING",
        "Push through a door into the next ten floors.",
    ),
    Feat(
        "keeper",
        "THE KEEPER",
        "Kill a warden.",
    ),
    Feat(
        "banked",
        "BANKED",
        "Take a Tenth Door run out through the door.",
    ),
    Feat(
        "deep_twenty",
        "TWENTY DOWN",
        "Reach floor twenty in the Tenth Door.",
    ),
    Feat(
        "daily",
        "THE DAY'S DOOR",
        "Answer a daily door.",
    ),
    Feat(
        "bestiary_ten",
        "TEN PAGES",
        "Write ten bestiary pages.",
    ),
    Feat(
        "golden",
        "GOLDEN",
        "Hold a thousand coin in the permanent purse.",
    ),
)

FEAT_BY_KEY: dict[str, Feat] = {feat.key: feat for feat in FEATS}


def earned(state, progress) -> list[str]:
    """The feats this finished run has proved, in table order."""
    found: list[str] = []
    if progress.runs_started >= 1:
        found.append("first_blood")
    if progress.runs_won >= 1:
        found.append("escaped")
    if state.tenth_door:
        found.append("door_opened")
    if state.door_ring >= 2:
        found.append("second_ring")
    if state.wardens_slain >= 1:
        found.append("keeper")
    if state.banked:
        found.append("banked")
    if state.tenth_door and state.depth >= 20:
        found.append("deep_twenty")
    if state.daily:
        found.append("daily")
    if len(progress.bestiary) >= 10:
        found.append("bestiary_ten")
    if progress.gold >= 1000:
        found.append("golden")
    return found


def award(progress, state) -> list[str]:
    """Write the newly proved feats onto the meta. Returns the new keys."""
    new = [key for key in earned(state, progress) if key not in progress.feats]
    if new:
        progress.feats.extend(new)
        progress.feats.sort()
    return new
