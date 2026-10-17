"""The turning, painted by pygame: the shared screen's numbers, this front end's pixels.

The step between a floor and a fight belongs to the *game*, and it is one screen:
it ages, it decides when the room is handed over, it plays the sting and shakes
the glass. What it does not do is draw -- it works out a `Turn`, and a painter
paints it. This is the second painter.

So there is one idea of what the turning is, in one file, with two renderings:
a `QPainter` with ellipses and text, and this with `pygame.draw` on a transparent
sheet. The rings are ellipses and not circles because the room is a floor seen at
an angle, and the letter is the monster's own glyph at thirteen times a cell --
the same letter that was standing on the floor a moment ago, which is the promise
the arena was built on.
"""

from __future__ import annotations

from ..desktop.screens.base import Screen
from ..desktop.screens.encounter import BLOW, EncounterScreen, Letter, Turn
from ..desktop.theme import parse_style

__all__ = ["SdlTurning"]


class SdlTurning(Screen):
    """One step, played on this front end: the same screen, the same clock."""

    modal = False

    def __init__(self, trigger, battle) -> None:
        #: The game's own screen, which owns the age, the sting and the hand-over.
        #: This wrapper adds a painter and nothing else.
        self.turning = EncounterScreen(trigger, battle)
        self._sheet = None
        self._faces: dict[int, object] = {}

    # -- the game's own screen, unchanged -----------------------------------
    def draw(self, buffer, app) -> None:
        self.turning.draw(buffer, app)

    def step(self, dt: float, app) -> None:
        self.turning.step(dt, app)

    def key(self, name, event, app) -> bool:
        return self.turning.key(name, event, app)

    @property
    def animating(self) -> bool:
        return True

    # -- and the painting ---------------------------------------------------
    def paint_over(self, surface, app) -> None:
        """The three movements, over whatever the floor drew."""
        import pygame

        font = app.font
        width, height = surface.get_size()
        turn = self.turning.frame(
            float(width), float(height), font.cell_w, font.cell_h, app
        )
        if turn is None:
            return
        blow = tuple(parse_style(BLOW).fg)

        # Everything thin and translucent goes on one sheet and is blitted once:
        # the dark, the rings, the streaks and the white are all the same kind of
        # thing, and pygame's own draw calls do not blend.
        if self._sheet is None or self._sheet.get_size() != surface.get_size():
            self._sheet = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        sheet = self._sheet
        sheet.fill((0, 0, 0, 0))
        if turn.dim > 0:
            sheet.fill((0, 0, 0, round(255 * turn.dim)))
        for ring in turn.rings:
            pygame.draw.ellipse(
                sheet,
                (*blow, max(0, ring.alpha)),
                pygame.Rect(
                    round(ring.x - ring.rx),
                    round(ring.y - ring.ry),
                    round(ring.rx * 2),
                    round(ring.ry * 2),
                ),
                max(1, ring.width),
            )
        for streak in turn.streaks:
            pygame.draw.line(
                sheet,
                (*blow, max(0, streak.alpha)),
                (round(streak.x0), round(streak.y0)),
                (round(streak.x1), round(streak.y1)),
                2,
            )
        if turn.white > 0:
            sheet.fill((*blow, round(255 * turn.white)))
        surface.blit(sheet, (0, 0))

        # And the letter over the top of all of it, in the same big face the Qt
        # build measures: thirteen cells tall at the end, which is bigger than
        # the room it is standing in.
        if turn.letter is not None:
            self._letter(surface, app, turn.letter)

    def _face(self, path: str, size: int):
        """The big face the letter is drawn in, made once per size.

        The letter grows from one cell to thirteen over half a second, and a face
        is not a thing to build sixty times a second on the way.
        """
        from .font import SdlFont

        face = self._faces.get(size)
        if face is None:
            face = SdlFont(path, max(8, size))
            self._faces[size] = face
        return face

    def _letter(self, surface, app, letter: Letter) -> None:
        """The monster's letter, at its size and in its own colour.

        Two passes, a dark copy under a bright one, so the edge of it is the
        game's own edge and not a drop shadow -- the same two passes every letter
        in this game gets.
        """
        face = self._face(app.font.path, letter.size)
        ink = parse_style(letter.colour).fg
        left = round(letter.x - face.cell_w / 2)
        top = round(letter.y - face.cell_h / 2)
        for offset, colour in ((round(letter.weight), (0, 0, 0)), (0, ink)):
            glyph = face.glyph(letter.glyph, colour, bold=True)
            if glyph is not None:
                surface.blit(glyph, (left, top + offset))
