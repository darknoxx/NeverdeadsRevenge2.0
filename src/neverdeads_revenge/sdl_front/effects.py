"""Pixels that move, for the second front end.

The same field of particles the Qt build keeps in ``desktop/effects.py``, drawn
by pygame instead: the *screen* says "something died there" and this throws
pixels at it, with the same numbers -- light, with its own gravity, because a
spark is not made of the same stuff as blood. Nothing here knows what a dungeon
is, which is what lets the arena ask for the same spray in either build.

The shake lives here too, because it is the same kind of thing: not a particle
but the *room* moving, which is the other half of what a landed blow does. The
application asks this for an offset and shifts the frame by it, which is what
"the glass shakes" means when the glass is a surface.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

__all__ = ["SdlEffects"]


@dataclass(slots=True)
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    ttl: float
    colour: tuple[int, int, int]
    size: int
    #: This particle's own gravity: a spark is light and should hang in the air
    #: before it sinks, not thump straight to the floor with everything else.
    g: float


class SdlEffects:
    """A field of particles, in buffer pixels, and the shake of the frame."""

    def __init__(self) -> None:
        self.particles: list[Particle] = []
        self._rng = random.Random()
        self._shake = 0.0
        self._left = 0.0

    def clear(self) -> None:
        self.particles.clear()

    # -- what a screen asks for ---------------------------------------------
    def spark(self, point, colour: str = "bright_green", count: int = 18) -> None:
        """A rule was gained, or a level. Light, and it rises."""
        from ..desktop.theme import parse_style

        self.burst(
            point,
            tuple(parse_style(colour).fg),
            count=count,
            speed=45.0,
            life=1.0,
            size=1,
            gravity=60.0,
            rise=35.0,
        )

    def blood(self, point, count: int = 22) -> None:
        """A thing came apart. Heavy, red, and it falls."""
        self.burst(
            point,
            (0xC8, 0x1E, 0x1E),
            count=count,
            speed=70.0,
            life=0.7,
            size=2,
            gravity=220.0,
            rise=4.0,
        )

    def coin(self, point, count: int = 16) -> None:
        """Money came into the hero's hand. It gleams and drifts."""
        self.spark(point, "#ffb000", count)

    def burst(
        self,
        point,
        colour,
        *,
        count: int,
        speed: float,
        life: float,
        size: int,
        gravity: float,
        rise: float = 0.0,
    ) -> None:
        """Throw ``count`` pixels at ``(x, y)``, in buffer pixels.

        Scattered around the point rather than born at it, so the first frame
        already reads as a burst and not as a dot.
        """
        for _ in range(count):
            angle = self._rng.uniform(0.0, math.tau)
            power = speed * self._rng.uniform(0.35, 1.0)
            span = life * self._rng.uniform(0.6, 1.15)
            spread = self._rng.uniform(0.0, 6.0)
            self.particles.append(
                Particle(
                    x=point[0] + math.cos(angle) * spread,
                    y=point[1] + math.sin(angle) * spread,
                    vx=math.cos(angle) * power,
                    vy=math.sin(angle) * power - rise,
                    life=span,
                    ttl=span,
                    colour=tuple(colour)[:3],
                    size=size,
                    g=gravity,
                )
            )

    # -- the clock ----------------------------------------------------------
    def step(self, dt: float) -> bool:
        """A frame went by: the pixels moved, and the glass stopped shaking.

        Returns whether anything *was* moving, so a painter can leave a still
        frame alone: a game that redraws a quiet room sixty times a second is a
        game spending a core on the same picture.
        """
        moving = bool(self.particles) or self._left > 0
        alive: list[Particle] = []
        for one in self.particles:
            one.life -= dt
            if one.life <= 0:
                continue
            one.vy += one.g * dt
            one.x += one.vx * dt
            one.y += one.vy * dt
            alive.append(one)
        self.particles = alive
        if self._left > 0:
            self._left = max(0.0, self._left - dt)
            if self._left == 0.0:
                self._shake = 0.0
        return moving

    def draw(self, surface) -> None:
        """The field, on the frame, in the buffer's own chunky pixels."""
        import pygame

        for one in self.particles:
            # Fading out on the way, the way everything in this game fades: the
            # phosphor stops holding it rather than the pixel shrinking away.
            fade = max(0.15, one.life / one.ttl)
            side = max(1, one.size)
            speck = pygame.Surface((side, side), pygame.SRCALPHA)
            speck.fill((*one.colour, round(255 * fade)))
            surface.blit(speck, (round(one.x), round(one.y)))

    # -- the shake ----------------------------------------------------------
    def is_shaking(self) -> bool:
        """Whether the glass is still moving under a blow."""
        return self._shake > 0.0

    def shake(self, strength: float = 2.0, seconds: float = 0.2) -> None:
        """A blow landed: shake the frame that hard, for that long.

        The stronger of the two wins over the one already running, so a crit in
        the middle of a stick hit still reads as a crit.
        """
        self._shake = max(self._shake, float(strength))
        self._left = max(self._left, float(seconds))

    def offset(self) -> tuple[int, int]:
        """Where the frame is being held right now, in pixels."""
        if self._shake <= 0.0 or self._left <= 0.0:
            return (0, 0)
        reach = self._shake
        return (
            round(self._rng.uniform(-reach, reach)),
            round(self._rng.uniform(-reach, reach)),
        )
