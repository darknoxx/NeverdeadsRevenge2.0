"""The app's shared vocabulary: the font, the grid floors and the key shape."""

from __future__ import annotations

from pathlib import Path


SMALL_PIXELS = 11

FONT = Path(__file__).resolve().parent.parent / "desktop" / "fonts" / "DejaVuSansMono.ttf"

MIN_COLS = 80
MIN_ROWS = 24

TARGET_COLS = 110


class KeyPress:
    """A key press, in the shape the screens already ask for.

    They want two things a name cannot carry: whether the key is *held* -- which
    the hold bars count -- and the character it types. Making the same two
    questions answerable here is the whole of what a front end owes a screen.
    """

    def __init__(self, repeat: bool = False, text: str = "") -> None:
        self._repeat = repeat
        self._text = text

    def isAutoRepeat(self) -> bool:  # noqa: N802 - Qt's spelling, and the screens'
        return self._repeat

    def text(self) -> str:
        return self._text


def dress_the_echo(enemies, scores) -> None:
    """The run that got furthest, worn by the echo.

    The chronicle remembers a name, a hero and what that run was carrying, and
    the echo is all three come back: it answers to the name on the board, it
    wears the *front* of the hero whose run it is -- so it walks towards the
    player rather than away, which is the whole difference between a shade and a
    stranger -- and it fights with the blade and the coat of that run, because a
    record that only remembered a number would be a number.

    A function of its own rather than four paragraphs inside the encounter: the
    dressing is a rule about the chronicle, and the call site is about a fight.
    """
    from ..game.actors import ENEMIES, HEROES, scale_template
    from ..world.items import ITEMS

    if not scores:
        return
    # The board is sorted by *score*, and the echo is the run that got
    # **furthest**: a shallow run that found two chests could outscore a deep one
    # and the echo would wear the wrong face. Depth first, score to break a tie.
    best = max(scores, key=lambda entry: (entry.depth, entry.score))
    for enemy in enemies:
        if enemy.behaviour != "echo":
            continue
        enemy.name = best.name
        enemy.stats = scale_template(ENEMIES["echo"], max(6, best.depth)).stats
        hero = HEROES.get(best.hero)
        if hero is not None:
            # The hero's own front, at the size heroes are drawn: it is not a
            # monster wearing a hero's face, it is the run itself, come back.
            # The arena stages it where it stages the hero, for that reason.
            enemy.art = f"sprites/portraits/{hero.name}.png"
        weapon = ITEMS.get(best.weapon)
        if weapon is not None and weapon.slot == "weapon":
            m = weapon.modifiers
            low, high = enemy.stats.damage
            enemy.stats.damage = (low + m.damage, high + m.damage)
            enemy.stats.crit_chance = min(1.0, enemy.stats.crit_chance + m.crit_chance)
            # Not only the numbers: a blade that opens a wound still opens one in
            # the hands of a shade. Pierce is the one that cannot be copied --
            # ``Actor.pierce`` is the player's own property -- and it is left out
            # rather than pretended.
            enemy.inflicts = tuple(weapon.inflicts)
            enemy.self_inflicts = tuple(weapon.self_inflicts)
        coat = ITEMS.get(best.armour)
        if coat is not None and coat.slot == "armour":
            enemy.stats.armor += coat.modifiers.armor
            enemy.stats.evasion += coat.modifiers.evasion
            enemy.thorns = coat.thorns


