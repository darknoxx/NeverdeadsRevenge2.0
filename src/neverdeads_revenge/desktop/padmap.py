"""What a controller's buttons mean, screen by screen.

The keyboard is a vocabulary, and this is the same vocabulary spoken by a pad:
each physical button is translated to the *key name* a screen already answers.
That is why the screens did not have to learn anything -- and why the layout can
be read in one place.

The names on the left are the pad's own (``south`` is A, ``east`` is B, and so
on); the names on the right are keys the game already listens for. ``None``
means the button does nothing here, which is a decision and not an omission.

Two rules make the map readable:

* **A confirms and B goes back** everywhere. On the floor there is nothing to
  cancel, so B is the bag; in a fight B backs out one level and never flees.
* **A button means the same *kind* of thing in every context**: X is the big
  trick (ultimate, special), Y is the bottle (drink, item), the shoulders cycle
  (tabs, targets), the triggers page.
"""

from __future__ import annotations

__all__ = [
    "DEFAULT",
    "TITLE",
    "FLOOR",
    "BATTLE",
    "ALMANAC",
    "PAUSE",
    "SETTINGS",
    "CHEST",
    "CONFIRM",
    "TALLY",
    "NAME_ENTRY",
    "DELETE",
]

_PHYSICAL = ("south", "east", "west", "north", "lb", "rb", "lt", "rt",
             "start", "back", "l3", "r3")


def _map(**overrides: str | None) -> dict[str, str | None]:
    """The default map with this screen's answers on top."""
    layout: dict[str, str | None] = {
        "south": "enter",       # A
        "east": "escape",       # B
        "west": None,           # X
        "north": None,          # Y
        "lb": "[",
        "rb": "]",
        "lt": "pageup",
        "rt": "pagedown",
        "start": "escape",
        "back": "escape",
        "l3": None,
        "r3": None,
    }
    layout.update(overrides)
    return layout


#: Everything not listed: A confirms, B goes back, the triggers page, the
#: shoulders cycle, Start closes.
DEFAULT = _map()

#: The title. B quits nothing (a mis-press must not end the game); Start opens
#: the settings, which is the one menu a console player expects there.
TITLE = _map(start="e", back=None, lb=None, rb=None, lt=None, rt=None)

#: The floor: A does, B is the bag, X the ultimate, Y the bottle.
FLOOR = _map(
    east="i",
    west="f",
    north="q",
    lb="c",
    rb="l",
    l3="r",
    r3="?",
    back="m",
    lt=None,
    rt=None,
)

#: A fight: the four verbs on the four faces, and B always backs out one level.
#: Start does nothing -- the game does not pause in a fight -- and Back opens the
#: book, which is the one thing worth doing mid-round.
BATTLE = _map(
    # A confirms whatever is highlighted -- attack by default, and *flee* when
    # the row is on it. That is the whole reason B could be made a pure back
    # button: the way out of a fight lives in the row.
    south="enter",
    east="backspace",
    west="s",
    north="i",
    lb="left",
    rb="right",
    l3="r",
    r3="v",
    start=None,
    back="m",
    lt=None,
    rt=None,
)

#: The book: B closes, the shoulders turn the page of tabs, the triggers page.
ALMANAC = _map(east="escape", start="escape", back="escape")

#: The pause: B resumes, Back opens the book -- through the pause's own row,
#: because `m` is the sound toggle there.
PAUSE = _map(back="a")

#: The settings: A toggles, B leaves.
SETTINGS = _map(east="escape", start="escape", back="escape")

#: A chest asks its three questions: pay and take, pay and leave, walk away.
CHEST = _map(south="enter", west="f", east="escape", back="escape")

#: A yes/no question.
CONFIRM = _map(south="y", east="n", start="escape", back="escape")

#: The death tally: hold A to go on, X takes the run back.
TALLY = _map(south="enter", west="r", east="escape", start="escape", back="escape")

#: Erasing everything: there is nothing to type on a pad, so A is *held* instead
#: (the same deliberate gesture a typed word is).
DELETE = _map(south="hold", east="escape", start=None, back="escape")

#: The name entry: A accepts, X rolls a name, Y clears it.
NAME_ENTRY = _map(
    south="enter",
    east="backspace",
    west="random",
    north="clear",
    start="enter",
    back="escape",
    lb=None,
    rb=None,
    lt=None,
    rt=None,
)

assert set(DEFAULT) == set(_PHYSICAL), "a button is missing from the map"
