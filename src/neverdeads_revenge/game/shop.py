"""The shop: what coin buys between runs.

Three shelves and a rotating one.

*Supplies* are used up next run -- a draught is health, and health is the one
resource a run can never get enough of.
*Gear* is worn next run: it is permanent within the run, so it is the closest
thing to an upgrade the shop sells without being one.
*Upgrades* are permanent, bought in stacks, and the only thing here that a bad
run cannot take back.
*Wild offers* are the rotating shelf. Two at a time, re-rolled after every run,
each a bargain with a catch. They are the reason to look at the shop even when
you cannot afford the sensible things: a wild offer is never sensible.

Nothing here knows about Textual, and nothing here writes a file. The shop screen
renders what :func:`build_stock` hands it and calls :func:`buy`; the save layer
stores the result. That split is what makes the whole catalogue testable without
a terminal, which for a pile of prices and exceptions is the difference between
tuning it and guessing at it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from typing import Callable

from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.game.amulets import AMULETS, blurb_for
from neverdeads_revenge.game.difficulty import BELL_RING_PER_STACK, HOARFROST_PER_STACK
from neverdeads_revenge.game.draughts import draught_by_key
from neverdeads_revenge.game.statuses import status_by_key
from neverdeads_revenge.world.items import ITEMS, ItemTemplate

__all__ = [
    "MetaUpgrade",
    "META_UPGRADES",
    "ShopItem",
    "SUPPLIES",
    "GEAR",
    "AMULETS",
    "WildOffer",
    "WILD_OFFERS",
    "WILD_SLOTS",
    "Offer",
    "Loadout",
    "SECTIONS",
    "ShopError",
    "build_stock",
    "buy",
    "describe_item",
    "roll_wild_stock",
    "loadout_from",
]


# -- the catalogue ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MetaUpgrade:
    """A permanent, stackable change to every run from now on.

    The numbers are deltas rather than descriptions on purpose: an upgrade that
    says ``+2 max health`` and an upgrade that says ``-4 max health`` are the
    same mechanism with the sign flipped, which is what lets a wild offer sell
    you something that costs you health for good.
    """

    key: str
    name: str
    description: str
    price: int = 0
    #: Flat change per stack.
    max_hp: int = 0
    speed: float = 0.0
    sight: int = 0
    #: Pack slots bought, per stack.
    pack_slots: int = 0
    #: Flat damage per stack. The axis the shop was missing: everything it
    #: sold made the hero live longer or move faster, and nothing made them
    #: kill faster.
    damage: int = 0
    #: Crit chance per stack, as a fraction.
    crit: float = 0.0
    #: A *bloodline*: the upgrade works only for this hero, and the shop says
    #: which. ``None`` for the ones every hero carries.
    hero: str | None = None
    #: The effect line for a gift that is a *rule* rather than a number, given
    #: the stack count. A callable because a bloodline's sentence has
    #: arithmetic in it ("a wound 2 turns longer per stack") that a fixed
    #: string cannot say.
    note_for: Callable[[int], str] | None = None
    max_stacks: int = 3
    #: What each further stack adds to the price. A step rather than a
    #: multiplier: multiplying turned the fourth slot into a 560-coin luxury,
    #: and the pack is meant to be a comfort, not a monument.
    price_step: int = 0
    #: Only ever offered on the rotating shelf, never in the fixed stock.
    wild: bool = False

    def price_at(self, owned: int) -> int:
        """What the next stack costs, given how many are already held."""
        return self.price + self.price_step * owned

    def effect(self, stacks: int) -> str:
        """The effect line for ``stacks`` stacks, or an empty string."""
        parts: list[str] = []
        if self.max_hp:
            parts.append(f"{self.max_hp * stacks:+d} max health")
        if self.speed:
            parts.append(f"{self.speed * stacks:+.2f} speed")
        if self.sight:
            parts.append(f"{self.sight * stacks:+d} sight")
        if self.pack_slots:
            parts.append(f"{self.pack_slots * stacks:+d} pack slots")
        if self.damage:
            parts.append(f"{self.damage * stacks:+d} damage")
        if self.crit:
            parts.append(f"{self.crit * stacks:+.0%} crit")
        if self.note_for is not None:
            parts.append(self.note_for(stacks))
        return ", ".join(parts)


#: Registered upgrades. ``blood_deal`` lives here rather than in the wild table
#: because its effect is permanent -- the shelf it is sold from and the shape of
#: what it does are separate questions.
META_UPGRADES: dict[str, MetaUpgrade] = {
    "vigour": MetaUpgrade(
        key="vigour",
        name="Vigour",
        description="the body remembers being killed and grows back thicker",
        # Five stacks now, on a ladder that climbs: more to save for, without
        # making the same three steps cheaper. Health is linear against a
        # scaling dungeon, so it is the one axis safe to widen.
        price=140,
        price_step=60,
        max_hp=5,
        max_stacks=5,
    ),
    "haste": MetaUpgrade(
        key="haste",
        name="Haste",
        description="the feet remember the way out",
        # Three, not four: speed is *actions*, and the whole turn economy is
        # what a fourth stack would quietly solve.
        price=220,
        price_step=90,
        speed=0.12,
        max_stacks=3,
    ),
    "whetstone": MetaUpgrade(
        key="whetstone",
        name="Whetstone",
        description="the blade is kept by a hand that has done this before",
        price=140,
        damage=1,
        max_stacks=3,
    ),
    "edge": MetaUpgrade(
        key="edge",
        name="Edge",
        description="you have learned where the soft parts are",
        price=180,
        crit=0.05,
        max_stacks=3,
    ),
    "lantern": MetaUpgrade(
        key="lantern",
        name="Lantern",
        description="a light that does not go out when the run does",
        price=180,
        sight=1,
        max_stacks=1,
    ),
    "pack": MetaUpgrade(
        key="pack",
        name="Pack",
        description="another thing you can carry, and another after that",
        # 100, 150, 200, 250, 300: dearer each time, but by a step rather than
        # by a multiple. Five of them take the pack from two to seven, which is
        # still the whole allowance a run gets -- for 1000 coin rather than
        # 1400, because a comfort should be saveable-for.
        price=100,
        pack_slots=1,
        max_stacks=5,
        price_step=50,
    ),
    # -- the bloodlines -----------------------------------------------------
    #
    # One per hero, and each only works for its own: the shop stands before
    # the hero choice, so all three are always on the shelf and the picking
    # happens in the run. They are the reason to play all three.
    "bleeding_edge": MetaUpgrade(
        key="bleeding_edge",
        note_for=lambda n: f"a crit leaves a wound {2 * n} turns longer",
        name="Bleeding Edge",
        description="a wound you open with a lucky blow keeps opening",
        price=180,
        hero="noxx",
        max_stacks=3,
    ),
    "hoarfrost": MetaUpgrade(
        key="hoarfrost",
        note_for=lambda n: f"{round(HOARFROST_PER_STACK * n * 100)}% chance to freeze whoever strikes you",
        name="Hoarfrost",
        description="whoever strikes you takes the cold home",
        price=180,
        hero="yeti",
        max_stacks=3,
    ),
    "bell_ring": MetaUpgrade(
        key="bell_ring",
        note_for=lambda n: f"{round(BELL_RING_PER_STACK * n * 100)}% chance to throw what you hit",
        name="Ring of the Bell",
        description="your blows throw what they land on",
        price=180,
        hero="walkyrion",
        max_stacks=3,
    ),
    "blood_deal": MetaUpgrade(
        key="blood_deal",
        name="Blood Bargain",
        description="paid once, in the only currency that never comes back",
        price=0,  # sold through WILD_OFFERS, which carries its own price
        max_hp=-4,
        speed=0.15,
        max_stacks=2,
        wild=True,
    ),
}


@dataclass(frozen=True, slots=True)
class ShopItem:
    """Something off the fixed shelves, and what it costs."""

    key: str
    price: int

    @property
    def template(self) -> ItemTemplate:
        return ITEMS[self.key]


#: Draughts. The cheapest thing the shop sells and the one it sells most of.
#: Prices, and the shape of the grind. A run banks 50-115 coin, so the full
#: permanent set at 1040 is twelve to eighteen runs -- which is the number the
#: whole shop is tuned around. Cheap enough that every run buys something;
#: expensive enough that the wall is what you are buying your way through.
SUPPLIES: tuple[ShopItem, ...] = (
    ShopItem("potion", 30),
    ShopItem("elixir", 60),
)

#: Weapons and coats, for the next run.
GEAR: tuple[ShopItem, ...] = (
    ShopItem("tooth", 45),
    ShopItem("bite", 110),
    ShopItem("hide", 70),
    # The best thing that lies on a floor, sold rather than waited for.
    ShopItem("rune_plate", 170),
)

#: Amulets. All of them, priced by how much they change a run rather than by how
#: rare they are -- the weak ones can be found lying about, so the shop selling
#: them cheap is a convenience, and the strong ones are what the coin is for.
#:
#: The dead weight costs the most of the middle group because it is the only one
#: that takes something away, and a thing that takes something away has to be
#: worth buying anyway.
AMULETS_FOR_SALE: tuple[ShopItem, ...] = (
    ShopItem("wayfarer", 90),
    ShopItem("coin_hand", 100),
    ShopItem("ember", 110),
    ShopItem("marrow", 120),
    ShopItem("patience", 160),
    ShopItem("deathwatch", 170),
    ShopItem("second_mouth", 170),
    ShopItem("mirror", 180),
    ShopItem("grave_ward", 190),
    ShopItem("dead_weight", 190),
    ShopItem("rune_heart", 210),
    ShopItem("patient_knife", 220),
    ShopItem("long_hunger", 230),
    ShopItem("borrowed_face", 250),
)


@dataclass(frozen=True, slots=True)
class WildOffer:
    """A bargain with a catch, sold off the rotating shelf.

    ``pitch`` and ``catch`` are two sentences rather than one because the player
    has to be able to see both at once. A deal whose cost is a footnote is not a
    decision, and every offer here is meant to be one.
    """

    key: str
    name: str
    price: int
    pitch: str
    catch: str
    #: Set when the offer writes itself into the permanent upgrades instead of
    #: into the next run. The key names a :data:`META_UPGRADES` entry.
    permanent: str | None = None


WILD_OFFERS: dict[str, WildOffer] = {
    "blind_box": WildOffer(
        key="blind_box",
        name="the blind box",
        price=45,
        pitch="something from the deep, unseen",
        catch="you do not get to look first",
    ),
    "pact": WildOffer(
        key="pact",
        name="the pact",
        price=85,
        pitch="coins are worth half again as much",
        catch="you start cursed, and the dark picks",
    ),
    "greed": WildOffer(
        key="greed",
        name="greed",
        price=75,
        pitch="coins are worth double",
        catch="everything below is a fifth tougher",
    ),
    "grave_goods": WildOffer(
        key="grave_goods",
        name="grave goods",
        price=105,
        pitch="grave iron in hand from the start",
        catch="it is heavy, and it slows you down",
    ),
    "second_wind": WildOffer(
        key="second_wind",
        name="second wind",
        price=120,
        pitch="the first killing blow does not land",
        catch="once a run, and no more",
    ),
    "wager": WildOffer(
        key="wager",
        name="the wager",
        price=65,
        pitch="a coin, thrown into the dark",
        catch="one face a blade, the other a curse",
    ),
    "hollow_tooth": WildOffer(
        key="hollow_tooth",
        name="the hollow tooth",
        price=115,
        pitch="every kill feeds you three",
        catch="and no draught will ever stay down",
    ),
    "pilgrims_toll": WildOffer(
        key="pilgrims_toll",
        name="the pilgrim's toll",
        price=95,
        pitch="coins are worth half again as much",
        catch="the dark takes five for each floor",
    ),
    "counts_favour": WildOffer(
        key="counts_favour",
        name="the count's favour",
        price=125,
        pitch="every thirteenth kill heals you whole",
        catch="you do not want to know who counts",
    ),
    "mirror_of_hunger": WildOffer(
        key="mirror_of_hunger",
        name="the mirror of hunger",
        price=115,
        pitch="a draught heals half again as much",
        catch="and something drinks beside you",
    ),
    "nameless_run": WildOffer(
        key="nameless_run",
        name="the nameless run",
        price=105,
        pitch="coins are worth double",
        catch="and the score is worth half",
    ),
    "blood_deal": WildOffer(
        key="blood_deal",
        name="blood bargain",
        price=170,
        pitch="+0.15 speed, for good",
        catch="-4 max health, for good",
        permanent="blood_deal",
    ),
}

#: How many wild offers are on the shelf at once.
WILD_SLOTS = 2


#: The shelves, in the order the shop draws them.
SECTIONS: tuple[str, ...] = (
    "SUPPLIES",
    "GEAR",
    "AMULETS",
    "UPGRADES",
    "BLOODLINES",
    "WILD OFFERS",
)


class ShopError(Exception):
    """The shop refused. The message is what the player is told."""


# -- what the shelf holds ---------------------------------------------------


@dataclass(slots=True)
class Offer:
    """One row the shop can sell, priced and described."""

    key: str
    section: str
    label: str
    detail: str
    price: int
    #: What a wild offer costs you. Blank for everything else.
    catch: str = ""
    #: How many the player already has. Zero for most.
    owned: int = 0
    #: How many may be had in total. Zero for no limit.
    limit: int = 0
    #: Whether the purse covers it. Kept here so the screen does no arithmetic.
    affordable: bool = True

    @property
    def maxed(self) -> bool:
        return bool(self.limit) and self.owned >= self.limit



def describe_item(template: ItemTemplate) -> str:
    """A short line for what an item does, as the shop says it.

    An amulet's ability is a sentence rather than a list of numbers, so it comes
    from the amulet table; everything else is its modifiers, plus the two things
    that are not modifiers at all. The dead weight has both, and the sentence is
    the part worth reading.

    Statuses and thorns are said here rather than on the sheet, because this one
    function is what the sheet, the pack *and* the shop all read -- a blade that
    opens a wound and does not say so is a blade the player has to find out
    about by watching a monster lose health it was not being hit for.
    """
    if template.amulet is not None:
        return blurb_for(template.amulet)
    if template.draught is not None:
        # A strange bottle's rule, from the draught table -- the same way an
        # amulet's sentence comes from its own.
        draught = draught_by_key(template.draught)
        return draught.blurb if draught is not None else ""
    if template.heal:
        return f"heals {template.heal}"

    described = template.modifiers.describe()
    for key in template.inflicts:
        status = status_by_key(key)
        if status is not None:
            described.append(status.name)
    if template.thorns:
        described.append(f"thorns {template.thorns}")

    return ", ".join(described) if described else "does nothing in particular"


def build_stock(progress) -> list[Offer]:
    """Everything on sale right now, in shelf order.

    Takes anything with ``gold``, ``upgrades`` and ``wild_stock`` rather than a
    :class:`~neverdeads_revenge.persistence.MetaProgress`, so the shop screen can
    be handed a stand-in in a test and the save layer never has to be imported
    to price a potion.
    """
    gold = progress.gold
    offers: list[Offer] = []

    for item in SUPPLIES:
        template = item.template
        offers.append(
            Offer(
                key=item.key,
                section="SUPPLIES",
                label=template.name,
                detail=describe_item(template),
                price=item.price,
                affordable=gold >= item.price,
            )
        )

    for item in GEAR:
        template = item.template
        offers.append(
            Offer(
                key=item.key,
                section="GEAR",
                label=template.name,
                detail=describe_item(template),
                price=item.price,
                affordable=gold >= item.price,
            )
        )

    for item in AMULETS_FOR_SALE:
        template = item.template
        offers.append(
            Offer(
                key=item.key,
                section="AMULETS",
                label=template.name,
                detail=describe_item(template),
                price=item.price,
                affordable=gold >= item.price,
            )
        )

    for key, upgrade in META_UPGRADES.items():
        if upgrade.wild:
            continue
        owned = progress.upgrades.get(key, 0)
        price = upgrade.price_at(owned)
        detail = (
            upgrade.effect(owned + 1)
            if not owned >= upgrade.max_stacks
            else upgrade.effect(owned)
        )
        if upgrade.hero:
            # A bloodline says whose it is: the shelf is shared, the gift is
            # not, and a row that did not say so would be a row bought by
            # mistake.
            from neverdeads_revenge.game.actors import HEROES

            detail = f"{HEROES[upgrade.hero].name}: {detail}"
        offers.append(
            Offer(
                key=key,
                section="BLOODLINES" if upgrade.hero else "UPGRADES",
                label=upgrade.name,
                detail=detail,
                price=price,
                owned=owned,
                limit=upgrade.max_stacks,
                affordable=gold >= price,
            )
        )

    for key in getattr(progress, "wild_stock", ()):
        offer = WILD_OFFERS.get(key)
        if offer is None:
            continue
        owned = 0
        limit = 0
        if offer.permanent is not None:
            upgrade = META_UPGRADES[offer.permanent]
            owned = progress.upgrades.get(offer.permanent, 0)
            limit = upgrade.max_stacks
        offers.append(
            Offer(
                key=key,
                section="WILD OFFERS",
                label=offer.name,
                detail=offer.pitch,
                price=offer.price,
                catch=offer.catch,
                owned=owned,
                limit=limit,
                affordable=gold >= offer.price,
            )
        )

    return offers


def roll_wild_stock(rng: Rng) -> list[str]:
    """Two offers off the rotating shelf, without repeating one.

    A shelf that can show the same offer twice is a shelf with one offer on it.
    """
    keys = rng.shuffled(list(WILD_OFFERS))
    return keys[:WILD_SLOTS]


# -- buying -----------------------------------------------------------------


@dataclass(slots=True)
class Loadout:
    """What the shop sends into the next run."""

    upgrades: dict[str, int] = field(default_factory=dict)
    #: Item keys bought and not yet used: draughts go in the pack, weapons and
    #: coats go on.
    pending: tuple[str, ...] = ()
    #: Wild offers bought and not yet spent.
    wilds: tuple[str, ...] = ()


def loadout_from(progress) -> Loadout:
    """The loadout the shop has paid for, and then takes off the books.

    Consumed rather than copied: a draught bought for this run is drunk in this
    run, and leaving it in the shop would sell the same potion forever.
    """
    loadout = Loadout(
        upgrades=dict(progress.upgrades),
        pending=tuple(progress.pending),
        wilds=tuple(progress.wilds),
    )
    progress.pending.clear()
    progress.wilds.clear()
    return loadout


def buy(progress, offer: Offer) -> str:
    """Sell ``offer``. Returns the line the shop shows.

    Raises :class:`ShopError` when the shop says no, so the screen has exactly
    one thing to catch rather than a set of conditions to re-check.
    """
    if offer.maxed:
        raise ShopError(f"{offer.label} is already yours.")
    if progress.gold < offer.price:
        raise ShopError(f"{offer.price} coins, and you have {progress.gold}.")

    progress.gold -= offer.price

    if offer.section in ("UPGRADES", "BLOODLINES"):
        progress.upgrades[offer.key] = progress.upgrades.get(offer.key, 0) + 1
        return f"{offer.label} improved. It will still be there next time."

    if offer.section == "WILD OFFERS":
        wild = WILD_OFFERS[offer.key]
        if wild.permanent is not None:
            progress.upgrades[wild.permanent] = (
                progress.upgrades.get(wild.permanent, 0) + 1
            )
            return f"{wild.name} signed. There is no tearing it up."
        progress.wilds.append(offer.key)
        return f"{wild.name} taken. It waits for your next run."

    # Supplies and gear: both are item keys, and both wait for the next run.
    progress.pending.append(offer.key)
    template = ITEMS[offer.key]
    where = "pack" if template.kind == "draught" else "hands"
    return f"{template.name} set aside for the next run, for the {where}."

