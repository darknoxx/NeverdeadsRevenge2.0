"""The pad, said in the game's own words.

Every screen in this game answers a *name* -- ``"up"``, ``"enter"``, ``"y"`` --
and never a key code, which is the reason a handheld is possible at all. A pad
is no different: its A is ``"enter"``, its B is ``"escape"``, and no screen ever
learns that a gamepad exists. What this module holds is the small table between
SDL's button numbers and those names.

Three things are written down here rather than discovered at runtime, because
each of them cost a session to find out:

* **Android numbers a pad's buttons differently from a PC.** SDL maps every
  Android keycode to an ``SDL_CONTROLLER_BUTTON_*`` index (``keycode_to_SDL`` in
  SDL's ``src/joystick/android/SDL_sysjoystick.c``) and *that index* is what
  pygame reports: the shoulders are 9 and 10, the stick clicks 7 and 8, Start 6
  and Select 4. Assuming the PC layout (L1 4, R1 5, L2 6, R2 7) quietly puts
  "escape" on L1 and nothing at all on R1.
* **A d-pad is usually a hat and sometimes four buttons.** On the handheld this
  was written for, the face buttons worked and the d-pad did nothing, because
  only the hat was being read -- so it is read as both.
* **The analog stick is not read for movement.** It drifts, and a drifting stick
  is not a metaphor: a resting stick on the bench reported itself as "down"
  forever and walked the player through the menus. It is still *shown* raw, on
  the bench, which is where a mapping is checked against a real pad.
"""

from __future__ import annotations

__all__ = [
    "BUTTONS",
    "DIRECTION_KEYS",
    "DPAD_BUTTONS",
    "DEADZONE",
    "HAT_DIRECTIONS",
    "button_name",
    "describe_pad",
    "dpad_direction",
    "stick_direction",
]

#: ``SDL button number -> the name the game answers to``, **on Android**.
#:
#: A = enter (the game's one verb: take, open, speak, descend), B = escape, X
#: drinks, Y opens the pack, Select pauses, Start opens the hero's own page,
#: either stick click is the ultimate, L1 borrows the hour, R1 waits, and the
#: two triggers are the legend and this page -- the two things nobody looks for
#: and the two things there is no other button left for.
BUTTONS: dict[int, str] = {
    0: "enter",  # A
    1: "escape",  # B
    2: "q",  # X -- quaff
    3: "i",  # Y -- the pack
    4: "select",  # Select -- the pause menu
    # Start pauses too, and not the hero's page: on a handheld the one button a
    # thumb reaches for when it wants the game to *stop* is Start, and a page
    # that opens instead is a page that has to be closed before the game can be
    # left. The sheet is one line away in the pause menu.
    6: "select",
    7: "f",  # L3 -- the ultimate
    8: "f",  # R3 -- the ultimate (either stick click)
    9: "r",  # L1 -- the borrowed hour
    10: "space",  # R1 -- wait
    15: "l",  # L2 -- the legend
    16: "?",  # R2 -- this page
}

#: The buttons SDL's controller layout reserves for a d-pad. A d-pad is usually
#: a *hat*, but a pad that reports none -- or that hides its d-pad among the
#: buttons -- puts it here.
DPAD_BUTTONS: dict[int, str] = {11: "up", 12: "down", 13: "left", 14: "right"}

#: A d-pad's eight positions, as the game's own key names.
#:
#: The dungeon walks diagonally -- ``y``/``u``/``b``/``n``, the terminal's numpad
#: letters -- so a pad pushed north-west is the key ``y`` and no screen had to
#: learn a second word for a direction.
DIRECTION_KEYS: dict[str, str] = {
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "nw": "y",
    "ne": "u",
    "sw": "b",
    "se": "n",
}

#: A d-pad's eight positions as a hat, shared by every reader of one.
HAT_DIRECTIONS: dict[tuple[int, int], str] = {
    (0, 1): "down", (0, -1): "up", (-1, 0): "left", (1, 0): "right",
    (-1, 1): "sw", (1, 1): "se", (-1, -1): "nw", (1, -1): "ne",
}

#: How far a stick has to move before it means anything. Hall-effect sticks
#: drift less than the old potentiometers, but a thumb resting on one is not a
#: decision, and 0.4 is the value that stopped a resting stick from walking.
DEADZONE = 0.4


def button_name(button: int) -> str | None:
    """The game's name for a pad button, or ``None`` if it has none."""
    return BUTTONS.get(button)


def dpad_direction(joystick) -> str | None:
    """The direction a d-pad is being pushed, or ``None`` if it is resting.

    Tried as a hat first -- the usual way -- and then as the four buttons SDL
    reserves for it, because a pad that reports no hat at all is exactly what
    the handheld this was written for turned out to be. Diagonals fall out of
    reading both axes at once, and the game is eight-way: a d-pad that only ever
    produced four directions would be half of itself.
    """
    if joystick.get_numhats():
        x, y = joystick.get_hat(0)
        if (x, y) != (0, 0):
            return HAT_DIRECTIONS.get((x, y))
    if joystick.get_numbuttons() > max(DPAD_BUTTONS):
        x = int(joystick.get_button(14)) - int(joystick.get_button(13))
        y = int(joystick.get_button(12)) - int(joystick.get_button(11))
        if (x, y) != (0, 0):
            return HAT_DIRECTIONS.get((x, y))
    return None


def stick_direction(joystick) -> str | None:
    """The direction a stick is being pushed, or ``None`` if it is resting.

    Read by the bench and not by the game: a stick is shown raw and is not
    walked with (see the module's own note). Kept here, beside the d-pad, so
    that the two readers of a pad agree about what a direction *is*.
    """
    if joystick.get_numaxes() < 2:
        return None
    x = joystick.get_axis(0)
    y = joystick.get_axis(1)
    left, right = x < -DEADZONE, x > DEADZONE
    up, down = y < -DEADZONE, y > DEADZONE
    if up and left:
        return "nw"
    if up and right:
        return "ne"
    if down and left:
        return "sw"
    if down and right:
        return "se"
    if up:
        return "up"
    if down:
        return "down"
    if left:
        return "left"
    if right:
        return "right"
    return None


def describe_pad(joystick) -> str:
    """One line saying what the pad is, for the bench and for a bug report.

    The name SDL reports and how many buttons, axes and hats it has: a mapping
    written for the wrong device is a mapping that gets debugged twice.
    """
    return (
        f"{joystick.get_name()}: {joystick.get_numbuttons()} buttons, "
        f"{joystick.get_numaxes()} axes, {joystick.get_numhats()} hats"
    )
