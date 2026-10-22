"""The Armory's half of the Almanac: every blade, once it has been taken up.

The same shape as :mod:`game.bestiary`, and for the same reason: the numbers are
read off the item table when the screen asks for them -- so a blade that is tuned
moves its page with it -- and what is written here by hand is what a table cannot
hold: what the thing *is*, and what the house says about it.

Two rules of the book:

* **A page is earned by taking the blade up.** Finding it on the floor and
  walking past it does not write it down; the house does not count what you
  merely saw.
* **Alphabetical by the name without its article.** The blades are called "the
  ash kiss", "the blood price" and so on, and a catalogue sorted under T is a
  catalogue nobody can use. `grave iron` is the one that had no article to lose.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..world.items import ITEMS
from .shop import describe_item

__all__ = ["Weapon", "WEAPONS", "weapon", "stat_lines"]


@dataclass(frozen=True, slots=True)
class Weapon:
    """One page: the blade's name, what it is, and the house's paragraph."""

    key: str
    name: str
    #: What the blade is for, in the armory's own voice.
    what: str
    #: The house's paragraph on it -- the same voice as the bestiary's pages.
    lore: str

    @property
    def glyph(self) -> str:
        """The map's mark for a blade, which every blade shares."""
        return ")"

    @property
    def picture(self) -> str:
        """The painted blade, by the item key the sheets are named for."""
        return f"sprites/weapons/{self.key}.png"


#: ``key -> (name, what it is, the paragraph)``.
_PAGES: dict[str, tuple[str, str, str]] = {
    "kiss": (
        "the ash kiss",
        "The only blade in the game that can start a chain: a kill by fire lights the next monster, and that kill lights the next.",
        "A blade that carries fire and passes it on. The fire always hated solitude and craves a companion — one spark, two corpses. Like a flame searching for its lover.",
    ),
    "blood_price": (
        "the blood price",
        "Six damage, which is the top of the armory, for two a turn on yourself — three turns a cut, stacking. A short fight is free. A long one is a coin toss with your own blood.",
        "The strongest cheap steel in the house, and it takes its cut from the hand that holds it: every landed blow opens a wound on you as well. It is a blade for a guest who has decided the fight is shorter than the bleeding.",
    ),
    "coward": (
        "the coward's edge",
        "A blade that stops working exactly when a fight gets dangerous. Take it if you intend to win without being hit; leave it if you do not.",
        "What a weird axe this is. Its grimace begs you to leave this place, to find peace and not venture further, not letting the ridicule of others stop it — but maybe there is wisdom in his cowardice? Afterall: the house rewards guests who have not been hurt yet.",
    ),
    "debtor": (
        "the debtor",
        "Four damage for one coin a corpse. In a run that fights forty times, that is the price of a coat.",
        "A good blade with countless debt instruments attached. Every kill costs a coin, taken at once, whether or not the guest meant to pay.",
    ),
    "depthless": (
        "the depthless",
        "The wound build's endgame: three damage a turn from the wounds alone, and more every time the cut deepens.",
        "The blade with no reflection. It opens two wounds at once — one that bleeds fast and one that rots slow — and the thing it cuts never quite knows which is worse.",
    ),
    "first_blow": (
        "the first blow",
        "Seven damage, once a fight, and nothing after. The opening of a fight is where it lives — and the blade knows what a blow is: a trick does not carry it.",
        "A hammer and a timed one at that. A victor does not care for anything beside his first place and might get dull afterwards, because the house has always believed that a fight is decided by who speaks first.",
    ),
    "frostbite": (
        "the frostbite",
        "Do both at once, for one point of damage more than a bare knife. \\",
        "A claymore stuck in winter evermore: it opens and it slows. It is the cheapest way to make a fast thing slow and a slow thing dead.",
    ),
    "gambler": (
        "the gambler",
        "The most damage on the floor and the worst aim: a fifth more of the hero's blows crit, and two in ten fewer land at all. For a hero who can afford to miss.",
        "A short dagger but still somehow balanced wrong - On purpose, so that every swing is a coin. It hits like a debt collector and misses like a rumour; the house finds this funny.",
    ),
    "grave": (
        "grave iron",
        "The heaviest number a blade adds, and the heaviest price in turns. Yeti swings it like it was made for him.",
        "An old Zweihänder that was buried with its house. It hits like a falling wall and moves like one. Whatever it kills stays killed; whatever it misses has time to leave.",
    ),
    "bite": (
        "the grey bite",
        "The first real step up, and the first small gamble.",
        "A piece of cutlery that has a silvery shine to it. It bites a little harder than it should, the way a table does when you walk into it in the dark.",
    ),
    "sorrow": (
        "the heavy sorrow",
        "Damage bought with turns. On a slow hero it is nearly free; on Noxx it is a real trade.",
        "A heavy axe with a sorrowful visage on its blade. It is slow because it is heavy, and heavy because it was made to fell a men in one blow. Guests who carry it stop running from things.",
    ),
    "hummingbird": (
        "the hummingbird",
        "Half again Yeti's turns and a fifth more Noxx's, each of which opens a cut. The status build's first blade.",
        "Not a blade at all, but a foil which guard is a beautiful image of a pigmy bird, made for a hand that would rather move than hit. It opens a small wound on every pass and is gone before the answer.",
    ),
    "argument": (
        "the last argument",
        "Five damage and a point of armour into the bargain — the only blade that is also a coat.",
        "A slab of an axe, wild and relentless as the tribes to the south/east. The house issues it to guests who have run out of things to say.",
    ),
    "hunger": (
        "the long hunger",
        "The crit blade before the crit blades: a tenth more often, and heavier when it does. On Noxx — who already crits a quarter of the time — it is the first blade that feels like a build.",
        "A rapier with a grotesque mouth on its guard. It has been left in the same drawer for a long time, and has learned to wait. It does not hit harder; it hits better, and only sometimes. The house calls that luck. The house is lying.",
    ),
    "marksman": (
        "the marksman's",
        "A fifth more hit chance. Against a wraith or a hush — anything that dodges — it is worth more than the damage.",
        "A thin blade with a long history of not missing. The house keeps it for guests who cannot afford to swing twice.",
    ),
    "needle": (
        "the needle",
        "Armour 2 is the ooze, the skeleton and most of the guards; against them the needle is a +4 blade that never says so.",
        "Long, thin, and made for the gap in the plate. It ignores two points of armour — the house's own answer to the house's own guards.",
    ),
    "numbing": (
        "the numb",
        "The most brutal slow in the game, and the shortest. Land it on the turn that matters.",
        "A hammer of the deep cold, but not as heavy as it looks. Its bitter coldness makes a man's body brittle and slow — the same bargain as the winter's tooth, but told in a brutal fashion.",
    ),
    "patient": (
        "the patient",
        "No damage of its own at all — twelve points over twelve turns, slowly, which is more than a bare swing and less than a heavy one. It is a wager on the fight lasting. Against a crowd it is nothing.",
        "A blade that does almost nothing. It leaves an abhorrent taint that runs through your body, slowly, which is the longest promise in the house. Draw it only when the fight is a siege.",
    ),
    "pyre": (
        "the pyre",
        "The two clocks: three a turn for two turns, then one a turn for eight. The most front-loaded blade on the floor.",
        "A blade with emitting poisonous fumes of a life long past. It sets what it touches burning — fire for the fight you are in, and rot for the one after it.",
    ),
    "ledger": (
        "the reaper's ledger",
        "A blade that wants the floor after the floor: at +5 it is the best blade in the house, and at the door it is a letter opener. Clear the room, then descend with it.",
        "The bookkeeper's blade. Grotesque to even call them bookkeepers... It grows on the floor's deaths: On an empty floor it is the heaviest thing in the house; at the door it is but a letter opener.",
    ),
    "edge": (
        "the runed edge",
        "The plain best: four damage and a tenth more crits, with no rule to learn.",
        "The first thing in the chest that is not cutlery. Beautiful, but the marks on its blade are not letters and not decoration; they are a bill, and the edge collects it.",
    ),
    "tooth": (
        "the rusted tooth",
        "The first blade, and the yardstick for every other. Nothing about it is a decision.",
        "The first knife in the drawer, and the one every guest is given. It was sharp when the house was young. It is not sharp now, and the house has never replaced it — a guest who complains about the cutlery has already been judged.",
    ),
    "rot": (
        "the slow rot",
        "The long wound: eight turns of one. It is for a fight you intend to leave before it ends — and it is the best thing in the game against a room you are walking away from.",
        "The primitive looking axe, covered in a moss that the gardners tried so hard to yeet out. What it leaves behind is not a cut but a season: slow agony, the way rot works when nobody is looking.",
    ),
    "wound": (
        "the thin wound",
        "The cheapest way to make every blow worth two: the cut keeps paying after the swing.",
        "A kitchen carving knife, a jagged blade, thin as a rumour. It does not kill; it opens, and the house is very good at letting a small wound do its work over the next few turns.",
    ),
    "thunder": (
        "the thunderclap",
        "The only blade that is fast, hard-hitting and slows what it hits. Nothing else in the armory does three things.",
        "Made from something that fell in the west and did not break. Cold steel. It is fast, it is loud, and what it touches is late for the rest of the fight, for it seems it accelerates that hand that is wielding it",
    ),
    "winter": (
        "the winter's tooth",
        "Speed taken away, not health: a third of the victim's turns, for four turns. Against a fast monster it is worth more than any damage number.",
        "Ground from the ice under the palace floor. It does not bleed you; it makes you late. Everything you do comes a third slower while it is in you, and the house has all the time there is.",
    ),
}

#: The pages, alphabetical by the name without its leading "the".
WEAPONS: tuple[Weapon, ...] = tuple(
    sorted(
        (
            Weapon(key=key, name=name, what=what, lore=lore)
            for key, (name, what, lore) in _PAGES.items()
        ),
        key=lambda page: page.name.removeprefix("the "),
    )
)

#: And by key, for the one question that is asked by key.
_BY_KEY: dict[str, Weapon] = {page.key: page for page in WEAPONS}


def weapon(key: str) -> Weapon | None:
    """The page for a blade, or ``None`` if the armory has no such blade."""
    return _BY_KEY.get(key)


def stat_lines(page: Weapon) -> tuple[str, str]:
    """What the blade does, and where it comes from -- both read off the table.

    The first line is the game's own sentence about the blade (the same one the
    shop card and the character sheet print), so a page cannot disagree with the
    thing in the player's hand. The second is the drop: the floor's weight, or
    the fact that only a chest has ever held it.
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
