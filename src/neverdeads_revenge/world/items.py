"""Loot.

Items live in ``world/`` rather than ``game/`` for the same reason tiles do: the
generator has to place them, and the generator must not import the game layer.
An item is world content -- it exists on the map and can be seen, walked over and
picked up -- while what a *drink* does to your health is a game rule.

Right now everything is a healing draught. That is not a placeholder: a run has
one resource that runs out, health, and one way to get it back. Anything else
that could be found on the floor (a weapon, a scroll, a map) needs systems that
do not exist yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from neverdeads_revenge.core.rng import Rng

from .map import GroundItem
from .modifiers import Modifiers

__all__ = [
    "ItemTemplate",
    "ITEMS",
    "make_item",
    "make_chest",
    "make_coin",
    "roll_item",
    "roll_chest_contents",
    "loot_count",
    "equipment_count",
    "chest_count",
    "page_count",
    "make_page",
    "PAGE_GLYPH",
    "rare_find_count",
    "RARE_FIND_CHANCE",
    "RARE_FIND_DEPTH",
    "WEAPON_GLYPH",
    "WEAPON_COLOR",
    "ARMOUR_GLYPH",
    "ARMOUR_COLOR",
    "CHEST_GLYPH",
    "CHEST_COLOR",
    "COIN_GLYPH",
    "COIN_COLOR",
]


@dataclass(frozen=True, slots=True)
class ItemTemplate:
    """A kind of item, and what it does for you."""

    key: str
    name: str
    glyph: str
    color: str
    #: ``draught``, ``weapon`` or ``armour``. The legend groups by this, because
    #: one row per kind fits in the sidebar and one row per item does not.
    kind: str
    #: Health restored when drunk.
    heal: int = 0
    #: Which equipment slot it fills. ``None`` for something you drink.
    slot: str | None = None
    #: What wearing it changes.
    modifiers: Modifiers = Modifiers()
    #: Relative chance of being rolled for a floor.
    weight: float = 1.0
    #: How much ``weight`` grows per floor descended. Better things get more
    #: common as you go down, which is what makes a deep floor's loot worth the
    #: risk of the deep floor.
    #:
    #: For a ``chest_only`` item there is no floor table to grow on, so the same
    #: curve is applied to the chest's own table instead: a deep chest hands out
    #: the top of its tier. Without it a chest on floor nine gives the same
    #: thing as a chest on floor two, and by then every slot is filled.
    weight_growth: float = 1.0
    #: Never rolled onto a floor. Chests hand these out, and only chests.
    chest_only: bool = False
    #: Which amulet ability this grants, by key. ``None`` for everything that is
    #: not an amulet. The rule lives in :mod:`game.amulets`; this is only the
    #: name of it, the same way a chest carries a curse key.
    amulet: str | None = None
    #: Statuses a blow from this weapon leaves running, by key. Same idea: names,
    #: not rules. See :mod:`game.statuses`.
    inflicts: tuple[str, ...] = ()
    #: Damage dealt back to whatever lands a blow on the wearer. Only
    #: coats have it, and it is the one property that acts when the player
    #: is *hit* rather than when they swing.
    thorns: int = 0


#: Glyph and colour per kind of thing. Weapons and armour follow the old
#: roguelike convention -- ``)`` for a blade, ``[`` for something you wear --
#: because it costs nothing to be legible to people who already know it.
#: A page of the chronicle. A question mark because that is what it is until it
#: is read, and because every other glyph on the map is a thing to take or a
#: thing to avoid -- this one is a thing to *know*.
PAGE_GLYPH = "?"

#: The colour of a page: paper, which is nearly white and not quite. A hex
#: rather than a name because "bone" is not a colour Rich has ever heard of, and
#: the failure is a crash on the first frame a page is drawn on -- three tests
#: away from anything that mentions a page.
PAGE_COLOR = "#e8e8e0"

WEAPON_GLYPH = ")"
WEAPON_COLOR = "bright_white"
ARMOUR_GLYPH = "["
ARMOUR_COLOR = "#b87333"

#: An amulet. The old roguelike convention, and the reason grass had to move off
#: this glyph: it is the one mark a player already reads as "wear this".
AMULET_GLYPH = '"'
AMULET_COLOR = "#f472b6"

ITEMS: dict[str, ItemTemplate] = {
    # -- draughts ----------------------------------------------------------
    "potion": ItemTemplate(
        key="potion",
        name="potion",
        glyph="!",
        color="bright_red",
        kind="draught",
        heal=8,
        weight=5.0,
    ),
    "elixir": ItemTemplate(
        key="elixir",
        name="elixir",
        glyph="*",
        color="bright_magenta",
        kind="draught",
        heal=20,
        weight=2.0,
        weight_growth=1.25,
    ),
    # -- weapons -----------------------------------------------------------
    #
    # The name grows with the blade. "the rusted tooth" and "the last argument"
    # are both a ``)``, and the difference between them is meant to be audible
    # before any of the numbers are read.
    "tooth": ItemTemplate(
        key="tooth",
        name="the rusted tooth",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        modifiers=Modifiers(damage=1),
        weight=5.0,
    ),
    "bite": ItemTemplate(
        key="bite",
        name="the grey bite",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        modifiers=Modifiers(damage=2, crit_chance=0.05),
        weight=3.0,
        weight_growth=1.10,
    ),
    "hunger": ItemTemplate(
        key="hunger",
        name="the long hunger",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        modifiers=Modifiers(damage=2, crit_chance=0.10, crit_multiplier=0.2),
        weight=2.0,
        weight_growth=1.18,
    ),
    "sorrow": ItemTemplate(
        key="sorrow",
        name="the heavy sorrow",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        # Heavy: the most damage of the four and the only one that costs speed,
        # so "better weapon" is a decision rather than a straight upgrade.
        modifiers=Modifiers(damage=3, speed=-0.15),
        weight=1.6,
        weight_growth=1.15,
    ),

    "wound": ItemTemplate(
        key="wound",
        name="the thin wound",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        # The weakest blade in the game and the only cheap one that keeps working
        # after the swing: one point now and six more over the next three of the
        # monster's turns. Against a ghoul that makes it the best cheap weapon
        # there is, and against a wraith -- which takes those three turns quickly
        # -- it is better still.
        modifiers=Modifiers(damage=1),
        inflicts=("bleed",),
        weight=4.0,
    ),
    "rot": ItemTemplate(
        key="rot",
        name="the slow rot",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        # Eight turns of one. Against a crowd it is nothing at all; against the
        # one thing that will not die it is the entire plan, which is why a
        # patient player wants this over a heavier blade.
        modifiers=Modifiers(damage=2),
        inflicts=("poison",),
        weight=2.0,
        weight_growth=1.12,
    ),
    "winter": ItemTemplate(
        key="winter",
        name="the winter's tooth",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        # Yeti's ice in a blade: it cuts for two and makes whatever it touches
        # slow. Against the one thing that can outrun a careful player the slow
        # is worth more than the two points ever will be.
        modifiers=Modifiers(damage=2),
        inflicts=("chill",),
        weight=1.8,
        weight_growth=1.15,
    ),

    # -- armour ------------------------------------------------------------
    "thorn_coat": ItemTemplate(
        key="thorn_coat",
        name="the thorn coat",
        glyph=ARMOUR_GLYPH,
        color=ARMOUR_COLOR,
        kind="armour",
        slot="armour",
        # The Lord of Plants, who survives in the game only as a name in the
        # spoil. What grows out of this is not armour, it is a bad idea to touch:
        # the only coat that does something when the player is hit rather than
        # when they are not.
        modifiers=Modifiers(armor=1),
        thorns=2,
        weight=2.0,
        weight_growth=1.15,
    ),
    "hide": ItemTemplate(
        key="hide",
        name="the thin hide",
        glyph=ARMOUR_GLYPH,
        color=ARMOUR_COLOR,
        kind="armour",
        slot="armour",
        modifiers=Modifiers(armor=1),
        weight=5.0,
    ),
    "shroud": ItemTemplate(
        key="shroud",
        name="the grey shroud",
        glyph=ARMOUR_GLYPH,
        color=ARMOUR_COLOR,
        kind="armour",
        slot="armour",
        # Evasion is worth ten points of enemy hit chance per point, so one is
        # already a lot. Two measured as a 30-point swing and made the floor
        # loot worth more than the fights.
        modifiers=Modifiers(evasion=1),
        weight=3.0,
        weight_growth=1.10,
    ),
    "step": ItemTemplate(
        key="step",
        name="the swift step",
        glyph=ARMOUR_GLYPH,
        color=ARMOUR_COLOR,
        kind="armour",
        slot="armour",
        modifiers=Modifiers(speed=0.15, evasion=1),
        weight=2.0,
        weight_growth=1.15,
    ),
    "rune_plate": ItemTemplate(
        key="rune_plate",
        name="the rune plate",
        glyph=ARMOUR_GLYPH,
        color=ARMOUR_COLOR,
        kind="armour",
        slot="armour",
        # The best thing that ever lies on a floor, and rare enough that finding
        # one is a story. Armour two and nothing else: it has to stay clearly
        # under what a chest pays for, or the chest stops being worth the curse.
        modifiers=Modifiers(armor=2),
        weight=1.5,
        weight_growth=1.25,
    ),

    # -- amulets -----------------------------------------------------------
    #
    # A third slot, and the only one that grants an ability rather than a number.
    # The weak ones lie about and can be bought; the strong ones come out of
    # chests and from the shop. See :mod:`game.amulets` for what each one does --
    # the name here has to match the name there, which a test checks.
    "ember": ItemTemplate(
        key="ember",
        name="the last ember",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="ember",
        # Low, so an amulet is a find rather than the usual thing on the floor.
        weight=1.0,
    ),
    "coin_hand": ItemTemplate(
        key="coin_hand",
        name="the coin hand",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="coin_hand",
        weight=1.0,
    ),
    "marrow": ItemTemplate(
        key="marrow",
        name="the marrow",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="marrow",
        weight=1.0,
    ),
    "wayfarer": ItemTemplate(
        key="wayfarer",
        name="the wayfarer",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="wayfarer",
        weight=1.0,
    ),
    "rune_heart": ItemTemplate(
        key="rune_heart",
        name="the rune heart",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="rune_heart",
        chest_only=True,
        weight_growth=1.15
    ),
    "mirror": ItemTemplate(
        key="mirror",
        name="the mirror",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="mirror",
        chest_only=True,
        weight_growth=1.0
    ),
    "grave_ward": ItemTemplate(
        key="grave_ward",
        name="the grave ward",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="grave_ward",
        chest_only=True,
        weight_growth=1.08
    ),
    "deathwatch": ItemTemplate(
        key="deathwatch",
        name="the deathwatch",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="deathwatch",
        chest_only=True,
        weight_growth=1.0
    ),
    "long_hunger": ItemTemplate(
        key="long_hunger",
        name="the deep hunger",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="long_hunger",
        chest_only=True,
        weight_growth=1.15
    ),
    "patience": ItemTemplate(
        key="patience",
        name="the revenant's patience",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="patience",
        chest_only=True,
        weight_growth=1.15
    ),
    "second_mouth": ItemTemplate(
        key="second_mouth",
        name="the second mouth",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="second_mouth",
        chest_only=True,
        weight_growth=1.08
    ),
    "dead_weight": ItemTemplate(
        key="dead_weight",
        name="the dead weight",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="dead_weight",
        # The one amulet that costs a stat, and the reason it can afford to.
        modifiers=Modifiers(speed=-0.20),
        chest_only=True,
        weight_growth=1.08
    ),
    "patient_knife": ItemTemplate(
        key="patient_knife",
        name="the patient knife",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="patient_knife",
        chest_only=True,
        weight_growth=1.15
    ),
    "borrowed_face": ItemTemplate(
        key="borrowed_face",
        name="the borrowed face",
        glyph=AMULET_GLYPH,
        color=AMULET_COLOR,
        kind="amulet",
        slot="amulet",
        amulet="borrowed_face",
        chest_only=True,
        weight_growth=1.15
    ),
    # -- out of the chests -------------------------------------------------
    #
    # A tier of their own, never rolled onto a floor. Clearly better than
    # anything lying around, because the player paid for them with something
    # they cannot get back.
    "edge": ItemTemplate(
        key="edge",
        name="the runed edge",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        modifiers=Modifiers(damage=4, crit_chance=0.10),
        chest_only=True,
        weight_growth=1.0
    ),
    "argument": ItemTemplate(
        key="argument",
        name="the last argument",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        # The only blade that also defends. The strongest thing in the game that
        # is not grave iron, and the one that asks nothing of you for it.
        modifiers=Modifiers(damage=5, armor=1),
        chest_only=True,
        weight_growth=1.12
    ),
    "grave": ItemTemplate(
        key="grave",
        name="grave iron",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        modifiers=Modifiers(damage=6, speed=-0.20),
        chest_only=True,
        weight_growth=1.2
    ),
    "kiss": ItemTemplate(
        key="kiss",
        name="the ash kiss",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        # Fireking's ash in a blade. Three a turn for two turns on top of the
        # blow: the shortest and sharpest of the three, and the one that cares
        # least how long the fight is. Four raw, because a chest has to beat
        # everything that lies on a floor even before the burn is counted.
        modifiers=Modifiers(damage=4),
        inflicts=("burn",),
        chest_only=True,
        weight_growth=1.0,
    ),
    "thunder": ItemTemplate(
        key="thunder",
        name="the thunderclap",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        # Shocker's, out of the machine he walked into: a fast blade that leaves
        # what it hits slow, and the crit is the lightning finding the seam.
        modifiers=Modifiers(damage=4, crit_chance=0.15, speed=0.10),
        inflicts=("chill",),
        chest_only=True,
        weight_growth=1.05,
    ),
    "depthless": ItemTemplate(
        key="depthless",
        name="the depthless",
        glyph=WEAPON_GLYPH,
        color=WEAPON_COLOR,
        kind="weapon",
        slot="weapon",
        # The thing with no depth, in a blade. The only weapon in the game that
        # inflicts two things at once, and it costs speed, because carrying a
        # piece of that is not free.
        modifiers=Modifiers(damage=4, speed=-0.10),
        inflicts=("bleed", "poison"),
        chest_only=True,
        weight_growth=1.2,
    ),
    "warden": ItemTemplate(
        key="warden",
        name="warden plate",
        glyph=ARMOUR_GLYPH,
        color=ARMOUR_COLOR,
        kind="armour",
        slot="armour",
        modifiers=Modifiers(armor=3),
        chest_only=True,
        weight_growth=1.0
    ),
    "shade": ItemTemplate(
        key="shade",
        name="shade cloak",
        glyph=ARMOUR_GLYPH,
        color=ARMOUR_COLOR,
        kind="armour",
        slot="armour",
        modifiers=Modifiers(evasion=3),
        chest_only=True,
        weight_growth=1.05
    ),
    "ashfall": ItemTemplate(
        key="ashfall",
        name="the ashfall cloak",
        glyph=ARMOUR_GLYPH,
        color=ARMOUR_COLOR,
        kind="armour",
        slot="armour",
        # It is made of what the plain was covered in. Hard to hit and unpleasant
        # to touch -- the coat for a hero who would rather not be swung at at
        # all. One point of armour as well, because evasion two alone is level
        # with the best coat that lies on a floor, and a chest has to beat that.
        modifiers=Modifiers(evasion=2, armor=1),
        thorns=3,
        chest_only=True,
        weight_growth=1.1,
    ),
    "deep_plate": ItemTemplate(
        key="deep_plate",
        name="the deep plate",
        glyph=ARMOUR_GLYPH,
        color=ARMOUR_COLOR,
        kind="armour",
        slot="armour",
        # Four points of armour is the most anything in the game offers, and it
        # is paid for in speed: a hero who wears this has decided to be hit.
        modifiers=Modifiers(armor=4, speed=-0.15),
        chest_only=True,
        weight_growth=1.15,
    ),
    "burial": ItemTemplate(
        key="burial",
        name="the burial shroud",
        glyph=ARMOUR_GLYPH,
        color=ARMOUR_COLOR,
        kind="armour",
        slot="armour",
        # Two of everything and a little speed gone. The coat for a hero who has
        # decided the fight is going to be long.
        modifiers=Modifiers(armor=2, evasion=2, speed=-0.10),
        chest_only=True,
        weight_growth=1.15
    ),
}



#: What a chest looks like. Gold, because a chest is treasure before it is a
#: trap, and the dialog is where the trap gets said out loud.
CHEST_GLYPH = "&"
CHEST_COLOR = "bright_yellow"

#: Coins left by a dead monster.
COIN_GLYPH = "$"
COIN_COLOR = "#ffd700"


def make_coin(value: int) -> GroundItem:
    """A pile of coins on the floor."""
    return GroundItem(
        item_id="coin",
        name="coins",
        glyph=COIN_GLYPH,
        color=COIN_COLOR,
        kind="coin",
        gold=value,
    )


#: How often a chest holds a rule instead of a thing.
#:
#: A third. Rarer and the gifts are a rumour; commoner and the loot stops
#: mattering, which would be a shame -- the blade is half of what a chest is.
GIFT_CHANCE = 1 / 3


def page_count(depth: int) -> int:
    """How many pages a floor holds.

    One. There are thirty-seven of them and a run sees seven to ten floors, so a
    run is worth most of a chapter and the book is the work of four or five --
    which is what a collection is for. Two on a floor would make it a formality
    and one every other floor would make it a chore.
    """
    return 1


def make_page(number: int) -> GroundItem:
    """One page of the chronicle, lying on the floor.

    Its ``item_id`` carries the number as well as the field, so a page that goes
    through a save comes back as *that* page rather than as a generic one.
    """
    return GroundItem(
        item_id=f"page:{number}",
        name="torn page",
        glyph=PAGE_GLYPH,
        color=PAGE_COLOR,
        kind="page",
        page=number,
    )


def make_chest(
    curse_key: str,
    contents: ItemTemplate | None,
    gift: str | None = None,
) -> GroundItem:
    """A locked chest owing ``curse_key``, holding ``contents`` or ``gift``.

    Rolled when the floor is built rather than when the lid opens, so a seed
    still determines a whole run: what is in the chest is decided before the
    player has done anything to change the dice.

    A gift and contents are mutually exclusive -- a chest that held both would be
    two rewards for one price, and the price is the whole design.
    """
    return GroundItem(
        item_id="chest",
        name="ominous chest",
        glyph=CHEST_GLYPH,
        color=CHEST_COLOR,
        kind="chest",
        curse=curse_key,
        contents=make_item(contents) if contents is not None else None,
        gift=gift,
    )


def make_item(template: ItemTemplate) -> GroundItem:
    """Create a floor item from a template."""
    return GroundItem(
        item_id=template.key,
        name=template.name,
        glyph=template.glyph,
        color=template.color,
        heal=template.heal,
        kind=template.kind,
        slot=template.slot,
        modifiers=template.modifiers,
        amulet=template.amulet,
        inflicts=template.inflicts,
        thorns=template.thorns,
    )


def _weight_at(template: ItemTemplate, depth: int) -> float:
    if depth < 1:
        return template.weight
    return template.weight * template.weight_growth ** (depth - 1)


def roll_item(
    rng: Rng, depth: int = 1, kinds: tuple[str, ...] | None = None
) -> ItemTemplate:
    """Pick an item kind for a floor at ``depth``.

    ``kinds`` restricts the pool. Draughts and equipment are rolled separately
    rather than from one table, and that is not a detail: a single table cut the
    supply of healing to a quarter the moment equipment was added, and the game
    became far harder without anything obviously having changed.

    Chest-only things are never in the pool. They are not rarer, they are
    elsewhere.
    """
    pool = [
        t
        for t in ITEMS.values()
        if not t.chest_only and (kinds is None or t.kind in kinds)
    ]
    return rng.choice_weighted([(t, _weight_at(t, depth)) for t in pool])


#: How much likelier a chest is to hold a blade or a coat than an amulet.
#:
#: Evenly was right when the strong tier was four blades and coats. Now that it
#: holds fourteen things, an even split makes the blade the rare find and hands
#: out amulets three chests running -- which is the thing the third slot was
#: meant to fix. The chest is still not a second lottery: the player cannot
#: influence it either way, and that is what "not a lottery" has always meant
#: here. The mix is a design choice, not a dice roll.
CHEST_GEAR_BIAS = 4.0


def roll_chest_contents(
    rng: Rng, depth: int = 1, filled_slots: tuple[str, ...] = ()
) -> ItemTemplate:
    """What is inside a chest.

    Three things decide it, and all three exist because a chest that stops being
    worth opening is a chest the player learns to walk past:

    * A slot the player has not filled is preferred. The second chest should not
      be a second coat -- that was the complaint that started this.
    * A blade or a coat is likelier than an amulet, because there are more
      amulets than blades and an even split makes the blade the rare find.
    * Deeper chests hold better things, by each item's own ``weight_growth``.

    ``filled_slots`` comes from the game rather than from the map, the same way
    ``curse_keys`` does. The floor still decides what is in the chest -- the lid
    does not roll anything -- it just knows what you are already carrying when it
    decides.
    """
    strong = [t for t in ITEMS.values() if t.chest_only]
    unfilled = [t for t in strong if t.slot not in filled_slots]
    pool = unfilled or strong
    return rng.choice_weighted([(t, _chest_weight_at(t, depth)) for t in pool])


def _chest_weight_at(template: ItemTemplate, depth: int) -> float:
    """How likely a strong item is, in a chest at ``depth``."""
    base = CHEST_GEAR_BIAS if template.kind in ("weapon", "armour") else 1.0
    return base * template.weight_growth ** max(0, depth - 1)


def loot_count(depth: int) -> int:
    """How many draughts a floor holds.

    Deliberately stingy, and it grows slowly. Health is a run-long resource, so
    the supply of it is the difficulty dial that matters most: a floor that
    hands out four draughts is a floor where the monsters stop being scary.
    """
    return min(1 + depth // 3, 4)


def equipment_count(depth: int) -> int:
    """How many weapons and coats a floor holds, on top of the draughts.

    Its own budget, not a share of the draughts'. Kept small and grown slowly:
    equipment is never used up, so every piece is a permanent upgrade, and a
    floor that scatters three of them is handing out three of those across a run
    that only has ten floors. The strong tier is meant to be the chests.
    """
    return min(1 + depth // 5, 2)


#: How often a floor holds one of the chest-only things lying in the open.
RARE_FIND_CHANCE = 0.22

#: The floor a rare find can first appear on.
RARE_FIND_DEPTH = 4


def rare_find_count(rng: Rng, depth: int) -> int:
    """Whether this floor holds a strong thing lying around, uncursed.

    Never on the shallow floors. The strong tier is what a chest pays for with a
    curse, and handing one out free on floor two would make the chest the fool's
    bargain. Deeper down it starts to turn up, which is one more reason the deep
    floors are worth the risk of being deep.

    Takes the generator rather than being a plain probability so that it is
    decided by the run's seed like everything else: a floor has to be the same
    floor when it is regenerated.
    """
    if depth < RARE_FIND_DEPTH:
        return 0
    return 1 if rng.chance(RARE_FIND_CHANCE) else 0


def chest_count(depth: int) -> int:
    """How many chests a floor holds.

    Stingier than the equipment, and flatter: a chest is worth several floor
    finds and costs something permanent, so two on one floor is already a lot of
    deciding.
    """
    return min(1 + depth // 6, 2)