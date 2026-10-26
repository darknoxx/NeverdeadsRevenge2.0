"""The first kill and the first blade, written down -- and the cards that say so.

Two collections, one rule: *the first time the player meets a thing, its page is
written, once, and they are told.* The bestiary is met by killing, the armory by
taking a blade up; the bookkeeping is identical, so it lives here.

What is **not** here is the timing. The arena calls its half after the playback,
the floor calls its half after the step -- the book does not know what a blow
looks like, and the screen that does decides when the card is polite.
"""

from __future__ import annotations

from ...game.armory import stat_lines
from ...game.armory import weapon as armory_weapon
from ...game.bestiary import entry as bestiary_entry
from ...world.affixes import AFFIXES
from ..art import exists as art_exists

__all__ = [
    "write_the_page",
    "write_the_weapon",
    "write_the_weapon_aspect",
    "write_the_armour",
    "write_the_aspect",
    "the_aspect_card",
    "the_page",
    "the_weapon_page",
]


def _write(app, method: str, key: str) -> bool:
    """File one page in whichever book. Returns whether it was new.

    Writes the save at once rather than at the end of the run: a page is worth
    more than the run it was met on, and a crash should not lose what was
    learned. A front end without a book (a test harness) answers quietly instead
    of raising -- a screen would rather draw than explain itself.
    """
    progress = getattr(app, "progress", None)
    record = getattr(progress, method, None)
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


def write_the_page(app, key: str) -> bool:
    """File one monster's page in the Almanac."""
    return _write(app, "record_bestiary", key)


def write_the_weapon(app, key: str) -> bool:
    """File one blade's page in the Armory."""
    return _write(app, "record_weapon", key)


def write_the_armour(app, key: str) -> bool:
    """File one coat's page in the Wardrobe."""
    return _write(app, "record_armour", key)


def write_the_weapon_aspect(app, key: str, affix: str) -> bool:
    """Note one aspect on a blade's page. Returns whether it was new.

    The page is the *base* blade's -- a frostbound hummingbird is a hummingbird
    with a sentence under it, not a second sword. The note is still saved at
    once, because what the dark did to the blade is worth as much as the blade.
    """
    progress = getattr(app, "progress", None)
    record = getattr(progress, "record_weapon_aspect", None)
    if record is None or not record(key, affix):
        return False
    play = getattr(app, "play", None)
    if play is not None:
        play("rare_item")
    save = getattr(app, "save_progress", None)
    if save is not None:
        save()
    return True


def write_the_aspect(app, key: str, affix: str) -> bool:
    """Note one aspect on a monster's page. Returns whether it was new.

    The page already exists -- the monster was killed to meet it -- so this is
    the margin note rather than a second page. It still saves at once: what the
    dark did to a monster is worth as much as the monster.
    """
    progress = getattr(app, "progress", None)
    record = getattr(progress, "record_aspect", None)
    if record is None or not record(key, affix):
        return False
    play = getattr(app, "play", None)
    if play is not None:
        play("rare_item")
    save = getattr(app, "save_progress", None)
    if save is not None:
        save()
    return True


def the_aspect_card(key: str, affix: str, on_done=None):
    """The card for an aspect met for the first time, or ``None``.

    Not a page: the monster's page is already written and already being shown.
    This is the line underneath it -- the same ghoul, and the dark has been at
    it -- which is the thing the player has actually not seen before.
    """
    from .dialogs import InfoScreen

    entry = bestiary_entry(key)
    aspect = AFFIXES.get(affix)
    if entry is None or aspect is None:
        return None
    return InfoScreen(
        "THE ALMANAC",
        f"{aspect.adjective} {entry.name}",
        f"A new aspect has been written.\n\n{aspect.blurb}\n\n"
        f"It is the same {entry.name}. The dark has been at it.",
        picture=entry.picture if art_exists(entry.picture) else None,
        on_done=on_done,
    )


def the_page(key: str, on_done=None):
    """The card for a monster's page, or ``None`` if the book has no such monster.

    ``on_done`` is how the arena learns that the page has been read: a fight
    that writes a page on its last blow holds its verdict until the card closes.
    """
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
        on_done=on_done,
    )


def the_weapon_page(key: str):
    """The card for a blade's page, or ``None`` if the armory has no such blade."""
    from .dialogs import InfoScreen

    page = armory_weapon(key)
    if page is None:
        return None
    picture = page.picture if art_exists(page.picture) else None
    return InfoScreen(
        "THE ARMORY",
        page.name,
        f"A page has been written.\n\n{stat_lines(page)[0]}",
        picture=picture,
    )
