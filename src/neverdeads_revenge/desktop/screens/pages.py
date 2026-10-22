"""The first kill, written down -- and the card that says so.

Two screens can kill a monster: the arena, where a fight is played out, and the
floor, where a gift or an ultimate can finish something without a room. The rule
is one rule, so it lives in one place: *the first death of a monster writes its
page in the Almanac, once, and the player is told on a card.*

What is **not** here is the timing. The arena calls these after its playback, the
floor calls them after its step -- the book does not know what a blow looks like,
and the screen that does decides when the card is polite.
"""

from __future__ import annotations

from ...game.bestiary import entry as bestiary_entry
from ..art import exists as art_exists

__all__ = ["write_the_page", "the_page"]


def write_the_page(app, key: str) -> bool:
    """File one monster's page. Returns whether it was new.

    Writes the save at once rather than at the end of the run: a page is worth
    more than the run it was met on, and a crash should not lose what was
    learned. A front end without a book (a test harness) answers quietly instead
    of raising -- a screen would rather draw than explain itself.
    """
    progress = getattr(app, "progress", None)
    record = getattr(progress, "record_bestiary", None)
    if record is None or not record(key):
        return False
    play = getattr(app, "play", None)
    if play is not None:
        # The same sound a page of the chronicle makes: the book does not have
        # two ways of saying "you know something now".
        play("rare_item")
    save = getattr(app, "save_progress", None)
    if save is not None:
        save()
    return True


def the_page(key: str):
    """The card for a page, or ``None`` if the book has no such monster."""
    from .dialogs import InfoScreen

    entry = bestiary_entry(key)
    if entry is None:
        return None
    picture = entry.picture if art_exists(entry.picture) else None
    return InfoScreen(
        "THE ALMANAC",
        entry.name,
        f"A page has been written.\n\n{entry.rule}",
        picture=picture,
    )
