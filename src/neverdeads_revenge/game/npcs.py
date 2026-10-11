"""The people down here.

Not monsters and not heroes. Something that was returned, or something that never
left: standing in a room, willing to say one true thing about the place.

They carry no mechanics at all yet -- no quest, no trade, no reward -- and that is
deliberate. A line of lore is the cheapest thing in the game to add and the most
expensive to get wrong, so the first version is one sentence and no promise. A
quest is a promise, and a promise needs a system behind it before it can be kept.

They are also the game's **unreliable narrators**, and that is the design of what
they say. The chronicle -- the pages a player collects -- is the official history.
These people are what is left of the world that history happened to, and each of
them needs something to be true in order to keep going, so their version of the
old stories is bent to fit it:

    the Tally        trusts a ledger over the floor, and invents the numbers
    Vesper           names a different promiser every time she tells it
    the Ninth        has three tenth floors, one per reason for turning back
    Cinder           needs a place in the great story, and is only the ash
                     that did not stand up
    the Lamplighter  lights the way for followers who are not there
    the Sexton       digs up the erased names and writes them back wrong
    the Listener     needs the thunderclap to mean Shocker is alive
    the Vessel       reads an illness as having been chosen
    the Wright       cannot bear that the machine might not be understood
    the Copyist       fills the gaps in the chronicle with what he invents

The Sexton is the key to all of it: *the wrong ones hold better*. A history
written back wrong is why the rest of them disagree -- not carelessness, but one
man manufacturing the false version and the others living in it.

Nobody here recognises the hero. They talk about the Lords as absent legends, and
whether the hero is one of them is the player's to notice, not theirs.

Lives in ``game/`` for the same reason the curses do: the generator places *an*
NPC and does not need to know what any of them say, so it is handed the keys.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Npc", "NPCS", "NPC_GLYPH", "NPC_COLOR", "npc_by_key"]

#: What one looks like. One glyph and one colour for all of them, the way every
#: weapon is a ``)``: which one it is belongs in the dialog, not on the map.
#:
#: ``8`` reads as a hooded figure without being a letter, which matters -- the
#: convention here is that capitals are heroes and lowercase are monsters, and
#: neither is true of these.
NPC_GLYPH = "8"

#: Pale periwinkle. The palette is genuinely full at this point: this is one of
#: the two colours left that clear the perceptual-distance test against every
#: other mark on the map, and it clears it by four thousand six hundred.
NPC_COLOR = "#c0c0ff"


@dataclass(frozen=True, slots=True)
class Npc:
    """Somebody with nothing to sell and something to say."""

    key: str
    name: str
    #: What they say, one line per meeting. Several rather than one so that
    #: walking past the same person twice is not the same sentence twice.
    lines: tuple[str, ...]


#: Everyone who can be met. The names are people's names, because they are
#: people: the dungeon did to them what it did to the hero, or they have simply
#: been here longer.
NPCS: dict[str, Npc] = {
    "tally": Npc(
        key="tally",
        name="the Tally",
        lines=(
            "Nine came down before you. I counted them in. I did not count them out.",
            "Four came down before the nine. I did not know their names then. I have "
            "written them down since: Fire, Ice, Earth, and the one who never sat "
            "still.",
            "The ledger says forty-one. The floor says thirty-eight. I trust the "
            "ledger. A floor is not a witness.",
            "The one called Fire went out on a plain. I have the date. Nobody else "
            "has the date. That is how you know it is mine.",
            "You are the tenth. I have written it down. Do not ask me where.",
            "I counted a shadow once, at the foot of a stair. It had no number, so I "
            "gave it one. It has not moved since. I check.",
            "Numbers are the only honest thing here. Everything else lies about "
            "how long it has been.",
            "There is a number past which the counting stops being counting and "
            "becomes a confession. I am not near it. I am not near it.",
        ),
    ),
    "vesper": Npc(
        key="vesper",
        name="Vesper",
        lines=(
            "I was promised a morning. I have stopped expecting it, and I still "
            "wake at the same time.",
            "It was the one in gold who promised. He had a sword he would not lift, "
            "and a voice that carried further than the sword would have. He said "
            "there would be a morning after this.",
            "The dark has an hour it likes best. You will know it when your lamp "
            "stops helping.",
            "There were four of them once, and one was kind. That is the one who "
            "promised. I do not remember which. A promise does not need a face to "
            "keep.",
            "I have been promised twice. The second time I did not look up. It is "
            "easier to keep a promise you have not seen the face of.",
            "The morning is a place, not a time. I am sure of that much. Somewhere "
            "north, past the snow, where a hall used to be warm.",
            "If you find the way out, do not look back at me. I would follow, and "
            "I am not fit to.",
        ),
    ),
    "ninth": Npc(
        key="ninth",
        name="the Ninth",
        lines=(
            "I was the ninth. I got as far as the stairs, and I turned around.",
            "You have the axe's mark on you. I can see it from here. So can the "
            "others.",
            "Do not ask what is on the tenth floor. Ask what is under it.",
            "The tenth floor is a machine. Iron the size of houses, still running, "
            "and no one built it. I heard it through the stone. That is why I "
            "turned.",
            "The tenth floor is a plain of ash with a wind on it that comes from "
            "nowhere. You cannot cross it. I tried. That is why I turned.",
            "The tenth floor is nothing at all. No stairs, no rift. Just the dark, "
            "looking back. That is why I turned.",
            "People hear the reason they can live with. I have told you mine three "
            "times and you have heard three floors. That is not my fault. That is "
            "how a story gets out.",
            "Ask the one who waits for a morning. She has a floor in mind too. Take "
            "whichever of ours frightens you less. That is what I did, and I am "
            "still here.",
        ),
    ),
    "cinder": Npc(
        key="cinder",
        name="Cinder",
        lines=(
            "I keep a fire. It does not warm anything. I keep it because the dark "
            "hates it.",
            "Everything here has burned once already. That is why it is so cold.",
            "I was on the plain when the Fire went out. Close enough to be made of "
            "it. Some of me still is.",
            "There was a man made of that ash. Not me. I was the ash that did not "
            "stand up.",
            "Touch nothing that glows. That is not light. That is attention.",
            "He came back, the one they burned. He walks down here with a shadow "
            "that watches me. I do not say his name. He does not care for it.",
            "Fire does not die. It only finds somewhere else to be. I am somewhere "
            "else. So are you, if you sit with it a while.",
            "They gave the earth's fire a name and it did not want it. Names are "
            "heavy. I have carried mine a long while and I never asked for it "
            "either.",
        ),
    ),
    "lamplighter": Npc(
        key="lamplighter",
        name="the Lamplighter",
        lines=(
            "I light them on the way down. I have never lit one on the way back up.",
            "There is a floor where the lamps go out as you pass. Do not stop to "
            "relight them.",
            "A light is a promise that the room has an edge. It has never been "
            "more than that.",
            "I light them for whoever is behind me. There is nobody behind me. I "
            "have checked. I check every floor.",
            "The last light of a day is the longest. If you are ever above ground "
            "at that hour, do not stand still in it. That is when the ash gathers.",
            "There is a light down here that no lamp made and nothing puts out. I "
            "have not lit it. I have only watched it move.",
            "Someone has to go first. It was never going to be someone who came "
            "back.",
            "I saw him once. Gold, all of him, walking north. I lit the way after "
            "him so he could find it home. He did not.",
        ),
    ),
    "sexton": Npc(
        key="sexton",
        name="the Sexton",
        lines=(
            "I dig. There is nobody to bury, so I dig for the digging.",
            "Every floor has a room that is smaller on the inside. You will find "
            "it. You always do.",
            "The emptiness was pleased. I heard it too. I have not slept since.",
            "The stones had the names struck off. I know who struck them. I will "
            "not say. I was not there, and that is not the same as saying I did "
            "not.",
            "I put the names back when I find the pieces. Sometimes I put them back "
            "wrong. The wrong ones hold better. The right ones fall off by spring.",
            "There was a Lord of growing things. Root and thorn. His name is in the "
            "spoil somewhere. I will find it. I have been finding it a long time.",
            "I dug up a shadow once with no depth to it. Flat as a page. I put it "
            "back. It did not want to be put back.",
            "Four have come down looking for the way out. I buried none of them. "
            "They are where they fell. I only dig.",
        ),
    ),
    "listener": Npc(
        key="listener",
        name="the Listener",
        lines=(
            "Quiet. That is not me being rude. It is the whole of what I do.",
            "There was a Lord of the thunder. He went into a machine and the "
            "machine took him. That is the story. Stories are what people tell "
            "when they have stopped waiting.",
            "On clear nights there is one clap of thunder and no lightning under "
            "it. I have heard it nine times. Once it was closer.",
            "A man who is dead does not make a sound. A man who is somewhere else "
            "might. I have decided which one that clap is.",
            "The machine is still down there. It is bigger than the floors you have "
            "walked. You have been walking through its ribs.",
            "I do not go looking. If you go looking you arrive, and then you know, "
            "and then there is nothing left to listen for.",
            "If you hear it, do not count it. Counting turns a sound into a fact, "
            "and a fact can be wrong.",
        ),
    ),
    "vessel": Npc(
        key="vessel",
        name="the Vessel",
        lines=(
            "Do not stand too near. The ground under me is warm. It has been warm "
            "for a while now.",
            "There was a Lord of the earth, and they took his mud and rocks and "
            "gave it to someone else. They will not do that twice. The earth is "
            "looking for a place to be.",
            "I shake in the night. That is not fear. Fear does not move the floor.",
            "A man came down here and told me I was ill. He was a kind man. He is "
            "also a man who has never had a mountain move under him.",
            "When it comes up through me I will not be able to hold it. I have "
            "made peace with that. I only ask that it comes up here, and not "
            "somewhere with people.",
            "You are looking at me the way the kind man did. That is all right. You "
            "will feel it when you stand where I stood.",
            "There is a garden somewhere in the spoil. Root and thorn. The Sexton "
            "knows. Do not ask the Sexton anything. He will tell you.",
        ),
    ),
    "wright": Npc(
        key="wright",
        name="the Wright",
        lines=(
            "I build small things. They do nothing. That is the point of them. A "
            "thing that does nothing cannot be blamed.",
            "The great machine was made. By hands. By hands like mine, and I have "
            "never met the hands, and that is the only part I cannot stand.",
            "They say it is older than the four Lords. People say that about "
            "anything they cannot open.",
            "Lightning went into it and the machine went out of the world. That is "
            "not a god. That is a door, and the door was opened, and nobody wrote "
            "down how.",
            "I have drawn it from the sounds it makes. I am close. When I am "
            "finished I will build a small one, and it will do nothing, and I will "
            "be satisfied.",
            "Do not tell me it cannot be understood. I have understood worse. I "
            "understood the dark once, for an afternoon.",
            "Everything here was made. The stone, the stairs, the rules. Even the "
            "way out was made, by someone, and they did not make it easy, because "
            "they did not make it for us.",
        ),
    ),
    "copyist": Npc(
        key="copyist",
        name="the Copyist",
        lines=(
            "Mind the ink. It is not dry and it never will be. That is this place. "
            "Nothing here dries.",
            "I am writing it all down. Someone has to. The book up there is in "
            "pieces, and the pieces keep moving.",
            "Where a page is missing I write what was probably on it. That is not "
            "lying. That is repair.",
            "I have written the same sentence four ways. One of them is true. I "
            "keep all four. The true one will not mind waiting.",
            "The one who gave himself -- I had it. He gave himself on a plain, at "
            "the end of the day, and the ash stood up. I have that part right. I am "
            "less sure about the day.",
            "You found a page. I can tell. You have the look of someone who has "
            "been given something and does not know what to do with it. Read it. Do "
            "not bring it to me. I will only fix it.",
            "The names that were struck off the stones -- I put some of them back. "
            "Not the Sexton. Me. He digs. I decide.",
            "If you find a page that contradicts me, keep it. I am not the book. I "
            "am the weather over the book.",
        ),
    ),
}


def npc_by_key(key: str | None) -> Npc | None:
    """The person with this key, or ``None``."""
    return NPCS.get(key) if key else None
