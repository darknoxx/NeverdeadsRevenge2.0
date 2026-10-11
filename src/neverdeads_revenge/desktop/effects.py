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

    # -- the two the game asks for -----------------------------------------
    def blood(self, cell, count: int = 22) -> None:
        """A thing came apart. Heavy, red, and it falls."""
        self.burst(
            cell,
            count=count,
            colour="#c81e1e",
            speed=70.0,
            life=0.7,
            size=2,
            gravity=220.0,
        )

    def spark(self, cell, colour: str = "bright_green", count: int = 18) -> None:
        """A rule was gained, or a level. Light, and it rises."""
        self.burst(
            cell,
            count=count,
            colour=colour,
            speed=45.0,
            life=0.9,
            size=1,
            gravity=-40.0,
        )

    # -- the machine --------------------------------------------------------
    def burst(
        self,
        cell,
        *,
        count: int,
        colour: str,
        speed: float,
        life: float,
        size: int,
        gravity: float,
    ) -> None:
        """Throw ``count`` pixels out of the middle of a cell."""
        cx = (cell[0] + 0.5) * self.cell_w
        cy = (cell[1] + 0.5) * self.cell_h
        tint = QColor(colour)
        for _ in range(count):
            angle = self._rng.uniform(0.0, math.tau)
            power = speed * self._rng.uniform(0.35, 1.0)
            span = life * self._rng.uniform(0.6, 1.15)
            # Scattered out of the cell rather than born at its centre, so the
            # very first frame already reads as a burst and not as a dot.
            self.particles.append(
                Particle(
                    x=cx + self._rng.uniform(-self.cell_w * 0.5, self.cell_w * 0.5),
                    y=cy + self._rng.uniform(-self.cell_h * 0.5, self.cell_h * 0.5),
                    vx=math.cos(angle) * power,
                    vy=math.sin(angle) * power + gravity * -0.02,
                    life=span,
                    ttl=span,
                    colour=tint,
                    size=size,
                )
            )

    def step(self, dt: float, gravity: float = 220.0) -> None:
        """Advance every particle, and drop the dead ones."""
        alive: list[Particle] = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0.0:
                continue
            p.vy += gravity * dt
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
