"""SDL's keys, said the way the game says them.

Every screen in this game answers a *name* -- ``"up"``, ``"enter"``,
``"escape"`` -- and never a key code, which is the reason a second front end is
possible at all: the screens never learned what a Qt key is. This is the small
dictionary between SDL's codes and those names, and it is deliberately the same
vocabulary the Qt build uses, word for word, so the two front ends drive the same
game with the same keys.

Text -- the character a key types -- is the other half. The game uses it exactly
once, to fill in a name for the scoreboard, and a front end that could not say
what was typed would be a front end where the high-score table had no names in it.
"""

from __future__ import annotations

__all__ = ["NAMES", "name_of", "typed"]

#: ``pygame key constant -> the name the game answers to``. The same list the Qt
#: build keeps, because a second front end that spelled ``"return"`` where the
#: first spelled ``"enter"`` would be a second game.
NAMES: dict[int, str] = {
    "K_UP": "up",
    "K_DOWN": "down",
    "K_LEFT": "left",
    "K_RIGHT": "right",
    "K_HOME": "home",
    "K_PAGEUP": "pageup",
    "K_END": "end",
    "K_PAGEDOWN": "pagedown",
    "K_SPACE": "space",
    "K_RETURN": "enter",
    "K_KP_ENTER": "enter",
    "K_ESCAPE": "escape",
    "K_BACKSPACE": "backspace",
    "K_DELETE": "delete",
    "K_TAB": "tab",
    # Android's own back gesture. A handheld has one key a keyboard does not,
    # and everywhere in this game "back" is what escape means -- so it is spelled
    # that way and no screen had to learn a second word. Guarded like the rest:
    # a pygame built without Android support does not define it.
    "K_AC_BACK": "escape",
    **{f"K_F{n}": f"f{n}" for n in range(1, 13)},
}


def _table(pygame) -> dict[int, str]:
    return {
        getattr(pygame, name): spelled
        for name, spelled in NAMES.items()
        if hasattr(pygame, name)
    }


def name_of(event) -> str | None:
    """The name this key press answers to, or ``None`` if it is not one of them.

    Letters and digits are their own names -- ``a`` is ``"a"`` -- which is what
    the game's menus already expect, because that is how they were written for a
    terminal.
    """
    import pygame

    if event.key in _table(pygame):
        return _table(pygame)[event.key]
    character = typed(event)
    return character or None


def typed(event) -> str:
    """What this key press types, if anything. Lower case, like the game."""
    import pygame

    name = pygame.key.name(event.key)
    if len(name) == 1 and name.isprintable():
        return name.lower()
    if event.key == pygame.K_SPACE:
        return " "
    return ""
