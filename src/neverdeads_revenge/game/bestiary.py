"""The Almanac's other half: the monsters, written down once they are dead.

A page is not a stat block. The numbers are read off :data:`ENEMIES` when the
screen asks for them, so a monster that is tuned moves its page with it -- what
is written here by hand is the two things a table cannot hold: what the thing
*does* to you, and what the chronicle says it was.

Two more rules, both the book's:

* **The key is the monster.** A display name is a sentence ("one who did not
  come back") and a key is an entry ("echo"), so a page is filed by key and read
  by name.
* **Alphabetical, by the name on the page.** Not by floor and not by the order
  the dungeon rolls them: an almanac is for *looking something up*, and nobody
  looks a monster up by the floor it first stood on.
"""

from __future__ import annotations

from dataclasses import dataclass

from .actors import ENEMIES, EnemyTemplate

__all__ = ["Entry", "ENTRIES", "entry", "stat_lines", "title_of"]


@dataclass(frozen=True, slots=True)
class Entry:
    """One page: the name, where it is met, and the two things a table cannot say.

    The numbers are deliberately *not* here. A page that carried its own copy of
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

        Named after the *name* rather than the key, because the sheets were
        painted to the names -- and a name with a space in it is a file with an
        underscore. The one exception is a page whose figure is not its own: the
        echo wears the hero's front, and what it is *made* of is the shadow.
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
    "dying": (
        "already-dying",
        "floor 3",
        "Every blow it lands opens a wound on itself.",
        "Wait, evade, or land two quick blows. Ten health.",
        "The wounded of Karpas, who were never allowed to finish. It is bleeding out and it wants company: every blow it lands opens a wound in itself as well, so the fight is a race between two clocks, and the only question is which of you has more time.",
    ),
    "briar": (
        "briar",
        "floor 2",
        "Every blow you land costs you 2 health, straight through armour.",
        "Few hard blows, or fire and poison. The thorns hate a wound.",
        "The Lord of Plants is the one the chronicle could not name — only \"root, and thorn, and leaf\". What is left of him grows where the old battles were, and it has learned the only lesson a plant can learn about war: whatever touches you, take something back.",
    ),
    "debt": (
        "debt",
        "floor 5",
        "When it dies, the next fight on this floor has +2 damage and +25% health.",
        "Settle it last, when there is no next fight to pay for.",
        "Neverdead's patience in a small body. It does not die in a way that settles anything: whatever kills it is paid by the next room, which will be wearing the debt when you meet it.",
    ),
    "eater": (
        "eater",
        "floor 7",
        "Every round it eats a wound off another monster and heals 4 for each stack.",
        "Kill it first, or use no wounds while it lives.",
        "The carrion of every battlefield, in one body. It eats the wounds off its friends the way the old armies ate the dead — and it grows on them. A wound is a thing it can take; a blade it cannot.",
    ),
    "ghoul": (
        "ghoul",
        "floor 1",
        "Nothing but teeth: it walks at you and swings.",
        "Anything works. It is the body every other body is measured against.",
        "The first thing Neverdead raised was not a soldier. It was a man who had been buried in a field and had been hungry for a long time before that. The raising took no words at all — only a hand laid on the ground — and the thing that stood up did not know it had died. It has been trying to remember ever since, and it eats what it finds while it tries.",
    ),
    "hunter": (
        "hunter",
        "floor 5 and deeper",
        "It knows where you are from the moment the floor exists, and it is coming.",
        "A boss with legs: 60-90 gold and a rule, if you can finish it.",
        "Neverdead's patience, sent ahead. It knows where you are from the moment the floor exists; the chronicle's line is that \"Neverdead himself would ever find some road by which to return\". The hunter is that road, walking.",
    ),
    "hush": (
        "hush",
        "floor 2",
        "No kill point is paid while it stands, and no single blow takes more than 10 off it.",
        "Kill it first. A critical buys nothing here.",
        "There is a silence in the Ice Palace that was never broken — the chronicle says only that the great hall \"grew silent\". This is what came out of it: a small grey thing that takes the purse away. A hero is his tricks, and the tricks are paid for; the hush simply stops the paying.",
    ),
    "idle": (
        "idle",
        "floor 3",
        "Asleep until it is struck or stood beside. It costs no turns while it sleeps.",
        "Walk past it. There is no page worth a fight you did not need.",
        "Something that was already old when the palace was built. It lies down where the floor is warmest and does not move; the ice grew over it, and the chronicle's line — \"beneath the ancient ice, something stirred\" — may or may not be about it. Wake it and it is only an animal. Leave it, and it is a corridor you did not have to fight through.",
    ),
    "judge": (
        "judge",
        "floor 6",
        "It never swings. Every round it reads your curses: 1 damage each, up to 3.",
        "Carry fewer curses, or kill it in four turns.",
        "The forgetting had a court. It does not swing; it reads the curses you carry aloud, and every one of them is a page it has already judged. The statues with broken faces are its work — the faces it did not break are the ones it reads from.",
    ),
    "kindly": (
        "kindly one",
        "floor 3",
        "It asks for 8 coin before the fight. Pay and it leaves; refuse and it is a fight.",
        "Pay when you are hurt. Eight coin is cheaper than half your health.",
        "The chronicle remembers a companion whose name Noxx could no longer recall. This is not him. It is the shape of him — the memory of a hand held out — and it asks for eight coins the way a memory asks to be paid attention to. Refuse, and the shape comes apart into the worst thing on the floor: thirty-six of health and a patience that is not kindness at all.",
    ),
    "leech": (
        "leech",
        "floor 5",
        "Blows do a quarter of their damage; wounds do double.",
        "Poison, bleed, fire, cold. With steel alone you are hitting a wall.",
        "Something that came out of the depthless shadow the chronicle could not describe: it has no reflection either, but it is not empty — it is full. Steel goes into it like a stone into water; a wound, though, opens it like a mouth.",
    ),
    "lid": (
        "lid",
        "anywhere, as a chest",
        "A chest with teeth: opening it gives no curse and no loot.",
        "Bad luck. What was inside is not yours; the jaw is.",
        "A thing that has learned the one trick the forgetting used: to look like furniture. It is a chest until the key turns, and then it is a jaw. The chronicle says the removed passages were taken \"so carefully that it is plain the forgetting was not the work of time alone\" — the lid is that care, with teeth.",
    ),
    "mound": (
        "mound",
        "floor 2",
        "Slow, armoured and patient: it will not come to you.",
        "Walk away, or use the speed it does not have.",
        "\"Not a creature at all,\" the old writers insist: a piece of Gaia's earth left standing when the rest of him went into Inferno. It does not hate you. It simply weighs more than you do, and it has been standing here since before your language had a word for standing.",
    ),
    "notary": (
        "notary",
        "floor 5",
        "Its health is the floor's kills: 12, plus 6 for every kill already made here.",
        "Kill it before the floor is cleared. Afterwards it is a wall with your name on it.",
        "The chronicle is a book with pages torn out; someone has been keeping the other ledger. It writes down every death on the floor, and it is paid in them: the more you have killed before you meet it, the larger it is. The old books say the forgetting \"was not the work of time alone\" — this is what the work looks like.",
    ),
    "echo": (
        "one who did not come back",
        "floor 6",
        "It wears the blade and coat of the best run on record, scaled to that run's depth.",
        "The wounds it does not carry are the lever. It is your own build, tested.",
        "Noxx's memories came \"without warning, as dreams come upon a man in sleep\": Fireking's warmth, a companion's face. This is the chronicle's other side — the run that got furthest, come back as a shape in that hero's face, wearing that run's blade and coat. It is not a ghost. It is a record that has learned to fight.",
    ),
    "ooze": (
        "ooze",
        "floor 1",
        "Forty-five health behind armour 2: small blows mostly bounce.",
        "Pierce, criticals, or patience. It cannot catch you.",
        "The chronicle says that on Fireking's last field \"the stones beneath his feet were melted\". Where that melt pooled and cooled, it kept a kind of appetite. It is not alive in any sense the old writers would have accepted. It is simply still hungry, and it is very hard to cut.",
    ),
    "picker": (
        "picker",
        "floor 4",
        "Every blow it lands steals your gold, and at half health it leaves with it.",
        "Chase it if you can spare the turns. Its body pays everything back.",
        "The looters came after the battles, not during them. It takes what it can reach, a handful at a time, and it does not stay for a fight it is losing — it is the only thing down here that understands the word \"profit\".",
    ),
    "quiet": (
        "quiet",
        "floor 4",
        "While it lives you cannot drink.",
        "Kill it first. A quiet room at half health is already a loss.",
        "The silence of the Ice Palace, given hands. It takes nothing from you but your voice: the pack stays shut, and a hero who cannot drink is a hero who has to think.",
    ),
    "reaver": (
        "reaver",
        "floor 8",
        "Your weapon is gone for the length of the fight. It comes back afterwards.",
        "The free swing still works. Bring a draught, or do not take the fight.",
        "The other shadow — the one with no depth — \"an object from another place, cut loose from whatever world had made it and left upon this one, as though it waited for a hand to take it up.\" It takes instead. The blade leaves your hand, and it keeps it until the room is done with you.",
    ),
    "bone": (
        "skeleton",
        "floor 1",
        "Holds its ground until you close, and its armour takes one point off every blow.",
        "Pierce, a critical, or simply a bigger swing.",
        "A ghoul is a body with a hunger; a skeleton is a body with a job. In the margin of one chronicle there is a note in a hand that is not the chronicler's: \"it holds the line better than the men did.\" Whoever wrote that fought beside one and lived.",
    ),
    "twin": (
        "twin",
        "floor 4",
        "When one dies the other heals to full, and its damage doubles.",
        "Bring both down at once, or leave the first until the second is nearly dead.",
        "Two of one. The old books say the four Lords each had a shadow that was not Atritas; this is the smallest of those. When one is cut down, the other remembers being whole — and stands up twice as angry.",
    ),
    "unbroken": (
        "unbroken",
        "floor 6",
        "It never swings. Half of every blow you land comes straight back.",
        "Few big blows, or wounds -- they give nothing back. Or leave it.",
        "A statue of a Lord whose face was struck off. The chronicle says the statues were broken; this one was not, and it has been standing in the dark ever since, returning half of everything that touches it. It does not attack. It has nothing left to attack for.",
    ),
    "viper": (
        "viper",
        "floor 1",
        "Every blow it lands leaves poison: 1 a round, for eight rounds.",
        "Kill it fast, then drink. The poison is a bill, not a wound.",
        "Neverdead's knowledge was not only of the dead. The viper's poison is the same argument the chronicle makes about him: it does not kill you at once. It makes you carry him, turn after turn, while you decide whether to finish the fight or run from what is already inside you.",
    ),
    "wraith": (
        "wraith",
        "floor 2",
        "Evasion 3: every blow you aim is thirty points less likely to land.",
        "Accuracy, an area trick, or a wound -- a wound does not have to hit.",
        "Atritas is the great shadow. These are the small ones: the same absence of reflection, the same sense that there is no bottom to them, in a thing the size of a man. The chronicle says that those who looked too long into the deep one felt themselves sinking. A wraith is what happens when someone does not look away in time.",
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
        "HP 12 + 6 a kill" if page.key == "notary" else f"HP {stats.max_hp}"
    )
    return (
        f"{health}   damage {stats.damage[0]}-{stats.damage[1]}   speed {stats.speed:.2f}",
        f"armour {stats.armor}   evasion {stats.evasion}   accuracy {stats.accuracy}",
        f"gold {template.gold[0]}-{template.gold[1]}",
    )
