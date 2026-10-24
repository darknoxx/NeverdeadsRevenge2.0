"""The Almanac's other half: the monsters, written down once they are dead.

A page is not a stat block. The numbers are read off :data:`ENEMIES` when the
screen asks for them, so a monster that is tuned moves its page with it -- what
is written here by hand is the two things a table cannot hold: what the thing
does to you, and what the chronicle says it was.

Two more rules, both the book's:

 The key is the monster.* A display name is a sentence ("one who did not
  come back") and a key is an entry ("echo"), so a page is filed by key and read
  by name.
 Alphabetical, by the name on the page.* Not by floor and not by the order
  the dungeon rolls them: an almanac is for looking something up, and nobody
  looks a monster up by the floor it first stood on.
"""

from __future__ import annotations

from dataclasses import dataclass

from .actors import ENEMIES, NOTARY_BILL, NOTARY_MINIMUM, EnemyTemplate

__all__ = ["Entry", "ENTRIES", "entry", "stat_lines", "title_of"]


@dataclass(frozen=True, slots=True)
class Entry:
    """One page: the name, where it is met, and the two things a table cannot say.

    The numbers are deliberately not here. A page that carried its own copy of
    ``max_hp`` would be a page that went stale the next time a monster was tuned,
    and the Almanac would be the one place in the game that lied about the game.
    """

    key: str
    name: str
    glyph: str
    where: str
    #: What it does, in one sentence.
    rule: str
    #: And what a player does about it.
    answer: str
    #: The chronicle's own paragraph on it.
    lore: str

    @property
    def picture(self) -> str:
        """The figure on the page, by the path the front end will blit.

        Named after the name rather than the key, because the sheets were
        painted to the names -- and a name with a space in it is a file with an
        underscore. The one exception is a page whose figure is not its own: the
        echo wears the hero's front, and what it is made of is the shadow.
        """
        if self.key == "echo":
            return "sprites/atritas.png"
        return f"sprites/{self.name.replace(' ', '_')}.png"

#: Everything written on one page, in the order it is read.
#:
#: ``where`` is a phrase and not an int: the hunter is from the fifth floor on,
#: the lid is not on a floor at all, and the echo is one a run. A number that
#: three of them have to lie about is a number that is not the truth.
_LORE: dict[str, tuple[str, str, str, str, str]] = {
    "bone": (
        "skeleton",
        "floor 1",
        "Holds its ground until you close, and its armour takes one point off every blow.",
        "Pierce, a critical, or simply a bigger swing.",
        "Drilled once, and never dismissed. It still holds a line that was broken a long time ago, and it still counts cadence under its breath. It has one instruction left — hold — and armour everywhere the instruction has worn thin.",
    ),
    "briar": (
        "briar",
        "floor 2",
        "Every blow you land costs you 2 health, straight through armour.",
        "Few hard blows, or fire and poison. The thorns hate a wound.",
        "The gardener never left, and neither did the hedge. It grew through the gardener and kept going. It does not attack, exactly; it answers. Every answer has a thorn in it.",
    ),
    "debt": (
        "debt",
        "floor 5",
        "When it dies, the next fight on this floor has +2 damage and +25% health.",
        "Settle it last, when there is no next fight to pay for.",
        "A note, called in. It was something else once — a guest, a servant, a promise — and now it is only the amount owed. Killing it does not settle anything: the next room collects, and it will be wearing the interest.",
    ),
    "dying": (
        "already-dying",
        "floor 3",
        "Every blow it lands opens a wound on itself.",
        "Wait, evade, or land two quick blows. Ten health.",
        "A guest who was told the meal would be ready soon, and has been bleeding politely ever since. It does not want to kill you. It wants you to stay — and it opens its own veins to make the room feel occupied.",
    ),
    "eater": (
        "eater",
        "floor 7",
        "Every round it eats a wound off another monster and heals 4 for each stack.",
        "Kill it first, or use no wounds while it lives.",
        "The cook, and the garbage. It eats what the others leave — wounds, mostly — and grows on them. It does not hate your poisons; it is fed by them, which is why the room smells like a kitchen.",
    ),
    "echo": (
        "one who did not come back",
        "floor 6",
        "It wears the blade and coat of the best run on record, scaled to that run's depth.",
        "The wounds it does not carry are the lever. It is your own build, tested.",
        "The guest book. Every name that ever signed it is still in there, and the best of them — the furthest, the one who almost got out — has been copied out into the hall. It wears the face it signed with and carries what it carried. It is not haunting you. It is filing you.",
    ),
    "ghoul": (
        "ghoul",
        "floor 1",
        "Nothing but teeth: it walks at you and swings.",
        "Anything works. It is the body every other body is measured against.",
        "The house's first servant, and the only one it never taught a job to. It was buried in the cellar and the cellar kept it. It is not hungry for flesh — it is hungry for the idea of a meal, which is worse, because it never finishes.",
    ),
    "hunter": (
        "hunter",
        "floor 5 and deeper",
        "It knows where you are from the moment the floor exists, and it is coming.",
        "A boss with legs: 60-90 gold and a rule, if you can finish it.",
        "The house's bell, rung once, and then a shape that walks. It knows which room you are in from the moment the house knows, which is always. It is not fast because it is strong; it is fast because there is nothing else it has to do.",
    ),
    "hush": (
        "hush",
        "floor 2",
        "No kill point is paid while it stands, and no single blow takes more than 10 off it.",
        "Kill it first. A critical buys nothing here.",
        "A room where a promise was made and never kept, and the house kept the silence instead. While it stands, nothing you have earned is paid out: the purse stays shut, because the house is listening.",
    ),
    "idle": (
        "idle",
        "floor 3",
        "Asleep until it is struck or stood beside. It costs no turns while it sleeps.",
        "Walk past it. There is no page worth a fight you did not need.",
        "Something the house forgot to put away. It lies in the warm spot by the boiler and has been asleep so long that the dust has learned its shape. Wake it and it is only an animal with a hangover. Leave it, and it is a corridor you did not have to clear.",
    ),
    "judge": (
        "judge",
        "floor 6",
        "It never swings. Every round it reads your curses: 1 damage each, up to 3.",
        "Carry fewer curses, or kill it in four turns.",
        "The house's court, which never adjourned. It does not swing; it reads the charges — every curse you carry is a page it has already ruled on. It is the only thing down here that can hurt you with your own luck.",
    ),
    "kindly": (
        "kindly one",
        "floor 3",
        "It asks for 8 coin before the fight. Pay and it leaves; refuse and it is a fight.",
        "Pay when you are hurt. Eight coin is cheaper than half your health.",
        "A hand in the dark, with a price in it. The house is polite; it always asks before it takes. Eight coins, and it will close the door behind itself. Refuse, and the politeness comes off like a glove.",
    ),
    "leech": (
        "leech",
        "floor 5",
        "Blows do a quarter of their damage; wounds do double.",
        "Poison, bleed, fire, cold. With steel alone you are hitting a wall.",
        "The house's doctor. It does not want you dead; it wants you bled, because a wound is a door and it lives on what comes through. Steel it shrugs off. A cut it opens its mouth for.",
    ),
    "lid": (
        "lid",
        "anywhere, as a chest",
        "A chest with teeth: opening it gives no curse and no loot.",
        "Bad luck. What was inside is not yours; the jaw is.",
        "A cupboard that learned to be a cupboard very well. The house is fond of these: a thing that is furniture until you want something from it, and then it is a mouth. Every sixth cupboard in this place is one, and the house has never once apologised.",
    ),
    "mound": (
        "mound",
        "floor 2",
        "Slow, armoured and patient: it will not come to you.",
        "Walk away, or use the speed it does not have.",
        "The house's foundation, in a bad mood. It was a wall once. It remembers being a wall, and it resents the doorway you are standing in.",
    ),
    "notary": (
        "notary",
        "floor 5",
        f"Its health is the floor's kills: max({NOTARY_MINIMUM}, "
        f"{NOTARY_BILL} x kills already made here).",
        "Kill it before the floor is cleared. Afterwards it is a wall with your name on it.",
        "The house keeps books. This is what turns the pages: a small, patient thing with ink on its fingers. It is paid in deaths — the more of the house's guests you have already dismissed, the more of a case it has against you.",
    ),
    "ooze": (
        "ooze",
        "floor 1",
        "Forty-five health behind armour 2: small blows mostly bounce.",
        "Pierce, criticals, or patience. It cannot catch you.",
        "What the cellar does to a floor when nobody has walked on it for a hundred years. It has no mouth and no plan. It is the house's appetite, pooled, and it is very hard to cut something that has no edges.",
    ),
    "picker": (
        "picker",
        "floor 4",
        "Every blow it lands steals your gold, and at half health it leaves with it.",
        "Chase it if you can spare the turns. Its body pays everything back.",
        "The house's other guest: the one who takes the silver on the way out. It is not brave, not loyal, and not honest — which makes it the most human thing down here. It leaves when the purse is heavy and the fight is not.",
    ),
    "quiet": (
        "quiet",
        "floor 4",
        "While it lives you cannot drink.",
        "Kill it first. A quiet room at half health is already a loss.",
        "A guest who was told to be quiet and took it as a vocation. It has no weapon and no hurry. It simply holds a finger to its lips, and while it does, the pack will not open — the house hears a bottle the way it hears a promise.",
    ),
    "reaver": (
        "reaver",
        "floor 8",
        "Your weapon is gone for the length of the fight. It comes back afterwards.",
        "The free swing still works. Bring a draught, or do not take the fight.",
        "The bailiff. It comes for what you are carrying, not for what you are. It takes the blade out of your hand for the length of the visit, and it gives it back when the visit is over — the house is many things, but it is not a thief.",
    ),
    "twin": (
        "twin",
        "floor 4",
        "When one dies the other heals to full, and its damage doubles.",
        "Bring both down at once, or leave the first until the second is nearly dead.",
        "The house does not like a single guest. When it can, it books two. They are not brothers, whatever they look like: they are one entry written twice, and when you cross one out the other remembers being whole.",
    ),
    "unbroken": (
        "unbroken",
        "floor 6",
        "It never swings. Half of every blow you land comes straight back.",
        "Few big blows, or wounds -- they give nothing back. Or leave it.",
        "A statue of a guest who refused to leave, and was accommodated. It has not moved since and does not need to. Every blow you land on it comes back to you at half, because the house does not let anything be given away for free.",
    ),
    "viper": (
        "viper",
        "floor 1",
        "Every blow it lands leaves poison: 1 a round, for eight rounds.",
        "Kill it fast, then drink. The poison is a bill, not a wound.",
        "The house keeps a garden, and the garden keeps a snake. It does not bite to eat; it bites so that you carry something home with you. The poison is patient in the way the house is patient: it does not want you dead today, it wants you worse tomorrow.",
    ),
    "wraith": (
        "wraith",
        "floor 2",
        "Evasion 3: every blow you aim is thirty points less likely to land.",
        "Accuracy, an area trick, or a wound -- a wound does not have to hit.",
        "A draft with a grudge. The house has a hundred rooms and only one of them is cold; the wraith is what walked out of it. You cannot hit a draft, and it takes the warmth out of a room one breath at a time.",
    ),
}

#: The pages, alphabetical by the name at the top of each. Built once, because
#: the book is the same book every time it is opened.
ENTRIES: tuple[Entry, ...] = tuple(
    sorted(
        (
            Entry(
                key=key,
                name=name,
                glyph=ENEMIES[key].glyph,
                where=where,
                rule=rule,
                answer=answer,
                lore=lore,
            )
            for key, (name, where, rule, answer, lore) in _LORE.items()
        ),
        key=lambda page: page.name,
    )
)

#: And the same pages by key, for the one question that is asked by key.
_BY_KEY: dict[str, Entry] = {page.key: page for page in ENTRIES}


def entry(key: str) -> Entry | None:
    """The page for a monster, or ``None`` if the book has no such monster."""
    return _BY_KEY.get(key)


def title_of(page: Entry) -> str:
    """The page's heading: the monster's name, in the book's own voice."""
    return page.name.upper()


def stat_lines(page: Entry) -> tuple[str, str, str]:
    """The three lines of numbers, read off the monster that is actually in play.

    The notary is the one page whose health is a formula rather than a number:
    it bills the floor, so its page says so instead of printing the template's
    sixteen.
    """
    template: EnemyTemplate = ENEMIES[page.key]
    stats = template.stats
    health = (
        f"HP max({NOTARY_MINIMUM}, {NOTARY_BILL} x kills)"
        if page.key == "notary"
        else f"HP {stats.max_hp}"
    )
    return (
        f"{health}   damage {stats.damage[0]}-{stats.damage[1]}   speed {stats.speed:.2f}",
        f"armour {stats.armor}   evasion {stats.evasion}   accuracy {stats.accuracy}",
        f"gold {template.gold[0]}-{template.gold[1]}",
    )
