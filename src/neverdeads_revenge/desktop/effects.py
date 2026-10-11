"""Pixels that move.

The pattern buffer is a still image; this is the layer that is not. Particles
live in the buffer's own pixel space, so a burst is made of the same chunky
pixels as the rest of the game and the CRT pass scales it for free -- a spray of
blood is two-pixel specks, blown up by four, exactly as a ``*`` is.

Nothing here knows what a dungeon is. A screen says "something died there" and
this throws pixels at it; the colours and the counts are the screen's taste.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

__all__ = ["Effects"]


@dataclass(slots=True)
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    ttl: float
    colour: QColor
    size: int
    #: This particle's own gravity, because a spark is not made of the same
    #: stuff as blood: it is light, and it should hang in the air before it
    #: sinks, not thump straight to the floor with everything else.
    g: float


class Effects:
    """A field of particles, in buffer pixels."""

    def __init__(self, cell_w: int, cell_h: int) -> None:
        self.cell_w = cell_w
        self.cell_h = cell_h
        self.particles: list[Particle] = []
        self._rng = random.Random()

    @property
    def active(self) -> bool:
        return bool(self.particles)

    def clear(self) -> None:
        self.particles.clear()

    # -- the three the game asks for ----------------------------------------
    def blood(self, point, count: int = 22) -> None:
        """A thing came apart. Heavy, red, and it falls.

        ``point`` is the centre of the square it died on, already translated to
        buffer pixels by :func:`~neverdeads_revenge.desktop.render.screen_point`.
        """
        self.burst_at(point[0], point[1], count=count, colour="#c81e1e",
                      speed=70.0, life=0.7, size=2, gravity=220.0, rise=4.0)

    def coin(self, point, count: int = 16) -> None:
        """Money came into the hero's hand. It gleams and drifts."""
        self.spark(point, "#ffb000", count)

    def spark(self, point, colour: str = "bright_green", count: int = 18) -> None:
        """A rule was gained, or a level. Light, and it rises."""
        self.burst_at(point[0], point[1], count=count, colour=colour,
                      speed=45.0, life=1.0, size=1, gravity=60.0, rise=35.0)

    # -- the machine --------------------------------------------------------
    def burst_at(
        self,
        x: float,
        y: float,
        *,
        count: int,
        colour: str,
        speed: float,
        life: float,
        size: int,
        gravity: float,
        rise: float = 0.0,
    ) -> None:
        """Throw ``count`` pixels at ``(x, y)``, in buffer pixels.

        ``rise`` is a bias upward against the scatter, so blood gets a small
        upward kick before it falls and a spark steps off the floor.
        """
        tint = QColor(colour)
        for _ in range(count):
            angle = self._rng.uniform(0.0, math.tau)
            power = speed * self._rng.uniform(0.35, 1.0)
            span = life * self._rng.uniform(0.6, 1.15)
            # Scattered around the point rather than born at it, so the very
            # first frame already reads as a burst and not as a dot.
            self.particles.append(
                Particle(
                    x=x + self._rng.uniform(-self.cell_w * 0.5, self.cell_w * 0.5),
                    y=y + self._rng.uniform(-self.cell_h * 0.5, self.cell_h * 0.5),
                    vx=math.cos(angle) * power,
                    vy=math.sin(angle) * power - rise,
                    life=span,
                    ttl=span,
                    colour=tint,
                    size=size,
                    g=gravity,
                )
            )

    def step(self, dt: float) -> None:
        """Advance every particle, and drop the dead ones."""
        alive: list[Particle] = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0.0:
                continue
            p.vy += p.g * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive

    def draw(self, image: QImage) -> None:
        """Paint the particles onto a rendered frame."""
        if not self.particles:
            return
        painter = QPainter(image)
        painter.setPen(Qt.PenStyle.NoPen)
        for p in self.particles:
            colour = QColor(p.colour)
            colour.setAlphaF(max(0.0, min(1.0, p.life / p.ttl)))
            painter.fillRect(QRect(int(p.x), int(p.y), p.size, p.size), colour)
        painter.end()
