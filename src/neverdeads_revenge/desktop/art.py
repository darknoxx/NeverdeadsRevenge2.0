"""Where the art is, and what a screen asks for when it wants some on the frame.

The art is PNG files that travel with the game. Their *paths* used to live inside
the two Qt loaders, which meant anything that wanted to know where a sprite was
had to import Qt to ask -- and a second front end that must not have Qt cannot ask
a question like that. So the paths live here, in a module with no toolkit in it,
and that is all a front end needs from the art: the file, and a place to put it.

And a screen that wants a picture on the frame does not paint it. It says *what*
and *where* -- a ``Placed`` -- and whichever application is drawing blits it. That
is the same shape the verdict panel and the arena's floor already had, said out
loud here: the game says what a thing is, the painter says how it lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ART_ROOT",
    "PORTRAITS_DIR",
    "SPRITES_DIR",
    "STATUS_DIR",
    "TILES_DIR",
    "ITEMS_DIR",
    "WEAPONS_DIR",
    "Placed",
    "TITLE_ART",
    "exists",
    "path",
    "curse_icon",
    "gift_icon",
    "item_icon",
    "size",
    "weapon_icon",
]

#: The art that travels with the game, beside the fonts and the sounds.
ART_ROOT = Path(__file__).resolve().parent

#: The figures, and the two families that hang off them: the heroes seen from the
#: front with nothing to fight, and the wounds, one a status key.
SPRITES_DIR = ART_ROOT / "sprites"
PORTRAITS_DIR = SPRITES_DIR / "portraits"
STATUS_DIR = SPRITES_DIR / "status"
#: The blades: a picture per item key, for the card that says what was just
#: picked up and the sheet that says what is being carried.
WEAPONS_DIR = SPRITES_DIR / "weapons"
#: And everything that is not a blade: the bottles, the coats and the amulets.
ITEMS_DIR = SPRITES_DIR / "items"

#: And the stone the rooms are made of.
TILES_DIR = ART_ROOT / "tiles"

#: The game's own name, painted. It used to be the block font, which is the
#: alphabet the *dungeon* is drawn in -- a title is the one place the game is
#: allowed to look like a thing somebody made rather than a thing that grew.
TITLE_ART = "sprites/menu/title.png"


@dataclass(frozen=True)
class Placed:
    """A picture, and where on the frame it goes.

    Held as ``centre`` and ``bottom`` rather than as a rectangle, because that is
    how the game thinks about a painted figure: fitted to a *height*, centred on a
    line, standing on it. Every portrait stands the same height on the same line,
    which is the whole of what a roster row is for -- and the width follows from
    the picture's own shape, which the front end has in hand and the screen does
    not.
    """

    art: str
    centre: float
    bottom: float
    height: int
    #: Whether the painter may smooth-scale it. A figure that is drawn at a whole
    #: multiple is *not* smoothed: nearest-neighbour is what keeps a painted
    #: monster a painting and not a smear.
    smooth: bool = True


#: The picture of a blade that has not been painted yet: a frame and a question
#: mark. The screens ask for it themselves rather than letting the card open with
#: a hole in it -- a card that promises a picture and shows a blank band is a card
#: that lied.
PLACEHOLDER = "sprites/weapons/_placeholder.png"


def weapon_icon(key: str) -> str | None:
    """The picture of a blade, by the item's key; the placeholder if there is none.

    The blades are being painted one at a time, so this is a question with three
    answers: the blade's own picture, the placeholder, or nothing at all when even
    the placeholder is missing (a checkout without the art still draws the game).
    """
    painted = f"sprites/weapons/{key}.png"
    if exists(painted):
        return painted
    return PLACEHOLDER if exists(PLACEHOLDER) else None


#: The coat and the amulet are drawn one apiece for now: the picture belongs to
#: the *kind* until every coat has a face of its own. Named the way the exports
#: came, which is why the amulet's name is spelled the way it is. The curse and
#: the gift are the same deal: one drawing each, for the page that announces them.
ARMOUR_ART = "sprites/items/armor.png"
AMULET_ART = "sprites/items/amulett.png"
CURSE_ART = "sprites/items/curse.png"
GIFT_ART = "sprites/items/gift.png"


def _own_or_shared(key: str, shared: str | None) -> str | None:
    """An item's own drawing when it has one, the kind's drawing until then.

    One rule for everything in that folder, so the day a coat or a curse is
    painted on its own, dropping ``hide.png`` or ``greed.png`` beside the shared
    ones is the whole change -- no table to edit and no code to remember.
    """
    painted = f"sprites/items/{key}.png"
    if exists(painted):
        return painted
    if shared is not None and exists(shared):
        return shared
    return None


def item_icon(template) -> str | None:
    """The picture of a thing that can be picked up, by its template.

    Three answers, in order of how much the drawing belongs to the item: a blade
    has its own sheet (or the placeholder, until one is painted); a coat or an
    amulet has the kind's drawing, because those are one picture for now; and a
    bottle has its own, named for its key. ``None`` when there is nothing to
    show, which the card reads as "no picture" and not as a broken one.
    """
    if template.kind == "weapon":
        return weapon_icon(template.key)
    shared = {"armour": ARMOUR_ART, "amulet": AMULET_ART}.get(template.kind)
    return _own_or_shared(template.key, shared)


def monster_art(name: str) -> str | None:
    """The picture of a monster, by the name the game calls it.

    One rule, here, because three callers need it and they must not each spell
    the filename differently: the arena stages it, the Almanac prints it, and a
    name with a space in it ("the kindly one") is a file with an underscore. A
    name and not a key -- the pictures were painted to the names.
    """
    where = f"sprites/{name.replace(' ', '_')}.png"
    return where if exists(where) else None


def curse_icon(key: str) -> str | None:
    """The page that announces a curse: its own drawing, or the curse's."""
    return _own_or_shared(key, CURSE_ART)


def gift_icon(key: str) -> str | None:
    """And the same for a gift."""
    return _own_or_shared(key, GIFT_ART)


def path(name: str) -> Path:
    """A piece of art by its path inside the art, e.g. ``sprites/ghoul.png``."""
    return ART_ROOT / name


def exists(name: str) -> bool:
    """Whether that piece of art is really there.

    Asked by the screens that draw a letter when the sheets have nothing for a
    hero: a card that promises a figure and then shows a blank band is a card
    that lied, and the alphabet is what is underneath every picture in this game.

    Cached like :func:`size`, and for the same reason: the fight asks it on every
    frame for every figure, and the answer is a fact about a file that does not
    change while the game runs. On a desk a stat is nothing; on a mounted image
    it is a trip through a userspace daemon, and there were a dozen a frame.
    """
    address = path(name)
    known = _EXISTS.get(address)
    if known is None:
        known = address.exists()
        _EXISTS[address] = known
    return known


#: The sizes already read, by path. The answer is a fact about a file that never
#: changes under a running game, and this is asked per *frame* -- a full read of a
#: half-megabyte backdrop sixty times a second was a millisecond nobody needed.
_SIZES: dict[Path, tuple[int, int]] = {}

#: And which of them are there at all: the same fact, the same reason.
_EXISTS: dict[Path, bool] = {}


def size(name: str) -> tuple[int, int] | None:
    """How big that piece of art is in pixels, or ``None`` if it cannot be read.

    Read out of the file's own header instead of through a toolkit, because it is
    the *game* that asks: a figure's shadow is as wide as the figure is, and how
    wide a picture is is a fact about the picture. Eight bytes of PNG -- the
    signature, the chunk header, then width and height, big-endian -- and both
    front ends get the same answer without either of them being involved.

    Twenty-four bytes and a cache: the old version read the *whole file* to look
    at its first twenty-four, and it is called from the per-frame path.
    """
    address = path(name)
    known = _SIZES.get(address)
    if known is not None:
        return known
    try:
        with address.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    measured = (
        int.from_bytes(header[16:20], "big"),
        int.from_bytes(header[20:24], "big"),
    )
    _SIZES[address] = measured
    return measured
