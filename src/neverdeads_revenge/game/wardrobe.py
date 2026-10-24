"""The Wardrobe's half of the Almanac: every coat, once it has been worn.

The same shape as :mod:`game.armory`, and for the same reason: the numbers are
read off the item table when the screen asks for them -- so a coat that is tuned
moves its page with it -- and what is written here by hand is what a table cannot
hold: what the thing *is*, and what the house says about it.

Two rules of the book, the armory's own:

* **A page is earned by wearing the coat.** Seeing it on the floor and walking
  past does not write it down. Picking a coat up puts it on (there is no
  comparison dialog, and what you took off stays on the floor), so "taken up" and
  "worn" are the same act in this house.
* **Alphabetical by the name without its article.** Half of them are called "the
  something"; a catalogue filed under T is a catalogue nobody can use.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..world.items import ITEMS
from .shop import describe_item

__all__ = ["Armour", "ARMOURS", "armour", "stat_lines"]


@dataclass(frozen=True, slots=True)
class Armour:
    """One page: the coat's name, what it is, and the house's paragraph."""

    key: str
    name: str
    #: What the coat is for, in the wardrobe's own voice.
    what: str
    #: The house's paragraph on it -- the same voice as the bestiary's pages.
    lore: str

    @property
    def glyph(self) -> str:
        """The map's mark for something worn, which every coat shares."""
        return "["

    @property
    def picture(self) -> str:
        """The painted coat, by the item key the sheets are named for."""
        return f"sprites/items/{self.key}.png"


#: ``key -> (name, what it is, the paragraph)``.
_PAGES: dict[str, tuple[str, str, str]] = {
    "thorn_coat": (
        "the thorn coat",
        "One point of armour and a bad idea to touch: two damage back to whatever lands a blow.",
        "The Lord of Plants is a name in a book now, and this is what he left in the "
        "wardrobe: a coat of briars that has not noticed it was cut. It keeps the edge "
        "off, and it makes touching you a decision the other side regrets.",
    ),
    "hide": (
        "the thin hide",
        "One point of armour, and the cheapest way to get it.",
        "The first answer the house gives to a blade, and the least it can do. Something "
        "else's skin, cured badly, still warm in the wrong weather. It turns one point of "
        "steel and no more; the rest is yours to carry.",
    ),
    "shroud": (
        "the grey shroud",
        "One point of evasion: harder to hit, not harder to hurt.",
        "The dust came in through the weave and never left, which is why it is grey and why "
        "it is hard to look at. Nothing about it stops a blow. It only makes the blow "
        "arrive somewhere you are not.",
    ),
    "step": (
        "the swift step",
        "One point of evasion and a fifth more turns -- the coat for a guest who intends "
        "not to be there.",
        "Cut for a guest who had already decided not to be there when the sword came down: "
        "short at the hem, long at the stride, no weight to speak of. You will not feel "
        "safer. You will be faster, which in this house is the same thing, most nights.",
    ),
    "rune_plate": (
        "the rune plate",
        "Two points of armour: the best a floor ever leaves lying about.",
        "Somebody wore it before the letters stopped meaning anything, and the letters have "
        "not forgiven them. Two points of steel and a line of script down the ribs that "
        "nobody reads aloud. It is the best thing the floor leaves lying about, and it does "
        "not lie about often.",
    ),
    "warden": (
        "warden plate",
        "Three points of armour and no speed to speak of -- the house's own guard, chest only.",
        "The house's own guard, still standing where the post used to be. Three points of "
        "plate and no speed left in it at all -- armour for somebody whose job was to be in "
        "the way. The chest it comes from is the only room that still respects it.",
    ),
    "shade": (
        "shade cloak",
        "Three points of evasion, chest only: the coat that makes the swing arrive late.",
        "Not a colour: an absence of being aimed at. It is cut from the part of the dark a "
        "torch does not reach, and it does not make you invisible -- it makes the swing "
        "arrive late, and late is enough. Three points of not being hit, and no help at all "
        "when something does land.",
    ),
    "ashfall": (
        "the ashfall cloak",
        "Armour one, evasion two, and three damage back: the ash of the plain, chest only.",
        "It is made of what the plain is covered in, and the plain has not finished with it. "
        "Hard to hit, unpleasant to touch: whatever grabs you comes away with the grey in "
        "its hands and a few thorns it did not ask for. A chest's answer to a floor full of "
        "things that want to hold you.",
    ),
    "deep_plate": (
        "the deep plate",
        "Four points of armour, the most anything offers, paid for with a tenth of your "
        "speed.",
        "Four points of armour, which is everything the house owns, and it is paid for in "
        "speed -- the coat has decided for you that you are going to be hit. A guest in "
        "this is not dodging; a guest in this is a door. The deep floors are where it is "
        "found, which is where doors are needed.",
    ),
    "burial": (
        "the burial shroud",
        "Two of armour, two of evasion, and a hem that drags: the best coat in the house, "
        "chest only.",
        "The best coat in the house, and it was made for somebody who was not going to need "
        "it. Two points of steel, two of luck, and a hem that drags: whoever prepared this "
        "body expected the walk to be short. It is the last thing a chest can give you, and "
        "it is the first thing a guest should be afraid of wanting.",
    ),
}

#: The pages, alphabetical by the name without its leading "the".
ARMOURS: tuple[Armour, ...] = tuple(
    sorted(
        (
            Armour(key=key, name=name, what=what, lore=lore)
            for key, (name, what, lore) in _PAGES.items()
        ),
        key=lambda page: page.name.removeprefix("the "),
    )
)

#: And by key, for the one question that is asked by key.
_BY_KEY: dict[str, Armour] = {page.key: page for page in ARMOURS}


def armour(key: str) -> Armour | None:
    """The page for a coat, or ``None`` if the wardrobe has no such coat."""
    return _BY_KEY.get(key)


def stat_lines(page: Armour) -> tuple[str, str]:
    """What the coat does, and where it comes from -- both read off the table.

    The first line is the game's own sentence about it (the same one the pickup
    card and the character sheet print), so a page cannot disagree with the thing
    on the hero's back.
    """
    template = ITEMS[page.key]
    if template.chest_only:
        where = (
            "chest only   deeper chests favour it"
            if template.weight_growth > 1.0
            else "chest only   any depth"
        )
    else:
        where = f"weight {template.weight:g}   the floor"
    return (describe_item(template), where)
