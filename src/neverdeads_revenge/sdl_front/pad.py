"""The pad: an Xbox controller, said the way the screens already listen.

Every screen in this game answers a *name* -- ``"up"``, ``"enter"``, ``"escape"``
-- and none of them knows what a keyboard is. That is what a second front end
could be built on, and it is what a controller can be built on too: a pad is a
third source for the same words, and this module's whole job is translation.

Three things make the translation less trivial than a lookup table:

* **Repeats.** SDL gives a keyboard its repeats for free; a pad has none. Walking
  and the hold-to-continue screens both need them, so a held button and a held
  direction send one press and then the same cadence the keyboard uses.
* **The context.** The same button means different things -- B is the bag on the
  floor and "back" in a fight -- so the top screen says what it wants
  (``Screen.PAD``) and the pad is told on every poll.
* **The sticks are two controls each.** The left stick and the D-pad are the same
  direction (eight of them on the floor, four in a menu), and the right stick is
  a *scroll wheel* -- pages, not directions, and only where a screen reads them.

Nothing here knows a rule about the game. It knows buttons, sticks and the names
of keys.
"""

from __future__ import annotations

from ..desktop.padmap import DEFAULT

__all__ = ["Pad", "BUTTONS", "DEADZONE", "REPEAT_DELAY", "REPEAT_RATE"]

#: SDL's game-controller button order, which the platform's mapping database
#: normalises every pad to: A, B, X, Y, LB, RB, Back, Start, L3, R3. The names
#: are the *physical* ones, because the layout is written in those.
BUTTONS: dict[int, str] = {
    0: "south",   # A
    1: "east",    # B
    2: "west",    # X
    3: "north",   # Y
    4: "lb",
    5: "rb",
    6: "back",
    7: "start",
    8: "l3",
    9: "r3",
}

#: How far the stick has to leave the middle before it counts as a direction.
DEADZONE = 0.35
#: A held direction or button: one press, a pause, then the keyboard's cadence.
REPEAT_DELAY = 0.40
REPEAT_RATE = 0.06
#: The right stick is a page key, not a direction: one page per flick, and a
#: cooldown so a long push does not turn into a flip-book.
SCROLL_DEADZONE = 0.6
SCROLL_EVERY = 0.30

#: Eight directions, by the sign of the two axes. The names are the *key* names
#: the floor already uses for diagonals (home/pageup/end/pagedown), which is why
#: a stick can walk a diagonal without any screen learning a new word.
STICK_KEYS: dict[tuple[int, int], str] = {
    (0, -1): "up",
    (0, 1): "down",
    (-1, 0): "left",
    (1, 0): "right",
    (-1, -1): "home",      # north-west
    (1, -1): "pageup",     # north-east
    (-1, 1): "end",        # south-west
    (1, 1): "pagedown",    # south-east
}


class Pad:
    """One or more game controllers, as a source of key names."""

    def __init__(self, devices=None) -> None:
        self.devices: list = list(devices or [])
        #: Buttons that were down at the last poll, by their SDL number.
        self._down: set[int] = set()
        #: How long each held button has been down, and when it may repeat.
        self._held: dict[int, float] = {}
        self._next: dict[int, float] = {}
        #: The direction the left stick / D-pad is holding, if any.
        self._direction: str | None = None
        self._direction_held = 0.0
        self._direction_next = 0.0
        #: The right stick's own clock: one page per push, not per frame.
        self._scroll_held = 0.0
        #: Buttons that were already down when the screen changed: they must be
        #: released and pressed again, exactly like a key held through a menu.
        self._stale: set[int] = set()

    # -- the devices --------------------------------------------------------
    @classmethod
    def open(cls) -> "Pad":
        """Every controller SDL knows about, or an empty pad."""
        import pygame

        try:
            pygame.joystick.init()
            devices = [
                pygame.joystick.Joystick(index)
                for index in range(pygame.joystick.get_count())
            ]
            for device in devices:
                device.init()
            return cls(devices)
        except Exception:
            # No joystick subsystem, no pad: a front end that refuses to start
            # because a controller is missing is a front end that lost a player.
            return cls()

    def forget(self) -> None:
        """A screen changed: nothing it hears may be a button already held."""
        self._stale |= set(self._down)
        self._held.clear()
        self._next.clear()
        self._direction = None
        self._direction_held = 0.0
        self._direction_next = 0.0
        self._scroll_held = 0.0

    def rumble(self, low: float, high: float, ms: int = 90) -> None:
        """Shake what is holding it, if the pad can.

        Low for weight (a monster's blow), high for the small sharp things (a
        crit, a level). A pad without rumble is not an error: a controller is
        still a controller.
        """
        for device in self.devices:
            shake = getattr(device, "rumble", None)
            if shake is None:
                continue
            try:
                shake(low, high, ms)
            except Exception:
                pass

    # -- one frame ----------------------------------------------------------
    def poll(self, dt: float, mapping: dict[str, str | None], *, diagonals: bool,
             scroll: bool) -> list[tuple[str, str, bool]]:
        """What the pad did this frame, as ``(name, kind, repeat)``.

        ``kind`` is ``"key"`` for a mapped button or direction and ``"up"`` for a
        release -- the hold screens need to know when a button came up, or a tap
        banks itself. ``scroll`` asks for the right stick's page keys, which only
        a screen that reads pages should ask for.
        """
        events: list[tuple[str, str, bool]] = []
        if not self.devices:
            return events

        pressed = self._pressed()
        for number in sorted(pressed - self._down):
            self._held[number] = 0.0
            self._next[number] = REPEAT_DELAY
            if number in self._stale:
                continue
            name = mapping.get(BUTTONS.get(number, ""))
            if name is not None:
                events.append((name, "key", False))
        for number in sorted(self._down - pressed):
            self._held.pop(number, None)
            self._next.pop(number, None)
            self._stale.discard(number)
            name = mapping.get(BUTTONS.get(number, ""))
            if name is not None and number not in self._stale:
                events.append((name, "up", False))
        self._down = pressed

        # Held buttons repeat: the hold bars *are* repeats, and a step held down
        # is the same gesture on a pad as on a key.
        for number in sorted(pressed):
            if number in self._stale or number not in self._held:
                continue
            self._held[number] += dt
            name = mapping.get(BUTTONS.get(number, ""))
            if name is None:
                continue
            if self._held[number] >= self._next[number]:
                self._next[number] = self._held[number] + REPEAT_RATE
                events.append((name, "key", True))

        events += self._walk(dt, mapping, diagonals)
        if scroll:
            events += self._page(dt, mapping)
        return events

    # -- what the pad is doing right now -----------------------------------
    def _pressed(self) -> set[int]:
        """Every button down on any device. One player, one set of hands."""
        held: set[int] = set()
        for device in self.devices:
            for number in BUTTONS:
                try:
                    if device.get_button(number):
                        held.add(number)
                except Exception:
                    continue
        return held

    def _stick(self) -> tuple[float, float]:
        """Which device is being pushed, and how far. The first one wins."""
        for device in self.devices:
            hats = getattr(device, "get_numhats", lambda: 0)()
            if hats:
                try:
                    hx, hy = device.get_hat(0)
                except Exception:
                    hx = hy = 0
                if (hx, hy) != (0, 0):
                    return float(hx), float(-hy)  # hate the hat's y: up is -1
            try:
                ax = device.get_axis(0)
                ay = device.get_axis(1)
            except Exception:
                continue
            if abs(ax) >= DEADZONE or abs(ay) >= DEADZONE:
                return ax, ay
        return 0.0, 0.0

    def _walk(self, dt: float, mapping: dict[str, str | None],
              diagonals: bool) -> list[tuple[str, str, bool]]:
        """The left stick and the D-pad: a held direction, with repeats."""
        ax, ay = self._stick()
        target: str | None = None
        if ax or ay:
            dx = 0 if abs(ax) < DEADZONE else (1 if ax > 0 else -1)
            dy = 0 if abs(ay) < DEADZONE else (1 if ay > 0 else -1)
            if not diagonals and dx and dy:
                # A menu has four directions and not eight: the stronger axis is
                # the one the player meant.
                if abs(ax) >= abs(ay):
                    dy = 0
                else:
                    dx = 0
            target = STICK_KEYS.get((dx, dy))
            if target is not None:
                target = mapping.get(target, target)

        events: list[tuple[str, str, bool]] = []
        if target != self._direction:
            if self._direction is not None:
                events.append((self._direction, "up", False))
            self._direction = target
            self._direction_held = 0.0
            self._direction_next = REPEAT_DELAY
            if target is not None:
                events.append((target, "key", False))
            return events
        if target is None:
            return events
        self._direction_held += dt
        if self._direction_held >= self._direction_next:
            self._direction_next = self._direction_held + REPEAT_RATE
            events.append((target, "key", True))
        return events

    def _page(self, dt: float, mapping: dict[str, str | None]) -> list[tuple[str, str, bool]]:
        """The right stick: pages, not directions."""
        down = 0.0
        for device in self.devices:
            try:
                down = device.get_axis(3)
            except Exception:
                down = 0.0
            if abs(down) >= SCROLL_DEADZONE:
                break
        name = None
        if down >= SCROLL_DEADZONE:
            name = "pagedown"
        elif down <= -SCROLL_DEADZONE:
            name = "pageup"
        if name is None:
            self._scroll_held = 0.0
            return []
        self._scroll_held += dt
        if self._scroll_held < SCROLL_EVERY:
            return []
        self._scroll_held = 0.0
        return [(name, "key", False)]


#: Re-exported so a caller can ask for the default map without another import.
DEFAULT_MAP = DEFAULT
