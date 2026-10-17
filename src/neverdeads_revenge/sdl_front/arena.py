"""The fight, as cells and pixels: the real arena's panels, and a round read at once.

This is the same seam job the theme and the grid already had, one screen further
along. The arena *says* almost everything it has to say in cells -- the plate with
the purse and the kill count, the log, the four verbs, the order strip, and the
monsters' own health bars -- all of it ``buffer.text(...)`` and ``self._bar(...)``
rather than a painter. Measured, that whole ``draw`` path asks Qt for no typeface,
which is why this screen can hand it a grid and get a real fight back.

Then there is the second pass, which is where the *art* is: the flagstones, the
sprites standing on them, the shadows, the stripe under each monster. That one is
`stage.Stage`, and it is not a rewrite either -- the art is PNG files and both
toolkits read the same ones, and the geometry comes from the arena's own `_field`
and `_figures`. One room, two painters.

A figure the sheets have no picture for is written as its letter instead, which is
what the whole arena was for a session and what the art was added on top of: the
alphabet is still underneath every picture in this game.

One deliberate difference: there is no playback. The Qt arena resolves a round
into a queue of events and plays them a beat at a time, because every beat is a
picture -- a number over a head, a shove, a colour across the room -- and those
are measured in pixels of a Qt typeface, which this front end must not ask for.
There is nothing to watch here anyway, so a round is *read* rather than watched:
the lines go into the log, the verdict goes up, and the screen's own resync puts
the bars, the badges and the plate where the rules already put them. That is the
terminal game's own tempo -- and the reason the room stands still, which is what
the strike poses and the numbers are waiting on.
"""

from __future__ import annotations

from ..desktop.screens.base import Screen
from ..desktop.screens.battle import LOG_LINES, BattleScreen
from ..desktop.theme import parse_style
from ..game.battle import Over, Said
from .paint import paint
from .stage import Stage

__all__ = ["SdlArena"]


class SdlArena(Screen):
    """The arena's own panels, and the stage written in the alphabet."""

    def __init__(self, battle) -> None:
        self.battle = battle
        #: The Qt fight, used for everything that is not pixels: its panels, its
        #: verbs, its order strip, its staging, its floor's geometry, and the whole
        #: of the rules behind them. It is never asked to `paste` or to `step`,
        #: which are the two places its *own* painting lives -- the second pass
        #: here is `stage.Stage`, and the first is its `draw`.
        self.arena = BattleScreen(battle)
        #: The painted room: the flagstones, the sprites on them, the shadows and
        #: the stripes. Loaded once, because a room is painted every frame.
        self._stage = Stage()
        # Whatever happened before the hero's first command -- anything quicker
        # than he is acts first, and that is where a slow hero's fight opens with
        # a blow already thrown at him. The Qt build plays those as the queue is
        # played; there is no playing here, so they are read before the first
        # frame is drawn. (For the fastest hero in the roster that queue is empty,
        # which is a measurement and not a shortcut.)
        self._settle(None)

    # -- the picture --------------------------------------------------------
    def draw(self, buffer, app) -> None:
        """The first pass: the panels, and a letter for anything without art.

        The letters were the whole of the arena for a session and are the fallback
        now -- exactly the promise the art was added on top of. A figure the
        sheets have a picture for is left to the second pass, because a letter
        written here would stand *through* the sprite pasted over it.
        """
        self.arena.draw(buffer, app)
        cell_w = max(1, buffer.font.cell_w)
        for figure in self.arena._figures(buffer.cols, buffer.rows, buffer.font):
            if figure.sprite is not None:
                continue
            x = int(figure.cx) // cell_w
            row = int(figure.row)
            if 0 <= x < buffer.cols and 0 <= row < buffer.rows:
                buffer.put(x, row, figure.glyph, parse_style(figure.colour))

    def paint_over(self, surface, app) -> None:
        """The second pass: the room, painted.

        The Qt arena's own order, with the passes that are not here yet left out
        by name: floor, bars, shadows, figures, and the verdict over the top of
        them. Missing still are the walls, the wound rows, the arrow, the damage
        numbers, the strike poses and the colour wash -- the last three of which
        need a round to be *watched*, which this front end does not do.

        Called `paint_over` rather than `paste` because the Qt screens this app
        reuses have a `paste` of their own, and it takes a QImage.
        """
        cols, rows = self.arena._dims(app)
        font = app.font
        figures = self.arena._figures(cols, rows, font)
        field = self.arena._field(cols, rows, font.cell_w, font.cell_h)
        fades = {id(one.actor): self.arena._fade(id(one.actor)) for one in figures}
        self._stage.floor(surface, field)
        self._stage.health(
            surface, figures, font, self.arena._shown, self.battle.hero, fades
        )
        # The shadows first: they live on the floor, so a figure standing on one
        # stands on it rather than carrying it around.
        for figure in figures:
            self._stage.shadow(surface, figure, font, fades[id(figure.actor)])
        for figure in figures:
            self._stage.figure(
                surface, figure, font, self.arena._clock, fades[id(figure.actor)]
            )
        if self.arena.verdict is not None:
            self._verdict(surface, font, cols, rows)

    def _verdict(self, surface, font, cols: int, rows: int) -> None:
        """What the fight came to, over the stage the way Qt blits it.

        The panel is the arena's own -- the same box, the same rule, the same
        hint -- asked for as cells, painted by the grid painter, and laid on top.
        Painted rather than stamped into the grid because the *room* is painted
        over the grid: a panel written into it would be buried under the floor.
        """
        panel, x, y = self.arena._verdict_panel(cols, rows, font)
        surface.blit(paint(panel, font), (x * font.cell_w, y * font.cell_h))

    # -- the fight ----------------------------------------------------------
    def key(self, name, event, app) -> bool:
        used = self.arena.key(name, event, app)
        if used:
            self._settle(app)
        return used

    def _settle(self, app) -> None:
        """Read the round the player just set off, instead of watching it.

        Only what the *panels* read is kept: the lines the fight speaks, and the
        verdict when the fight is decided -- plus the app calls that end a run in
        here rather than on the floor. Everything else in the Qt arena's queue is
        a picture, and there are no pictures in a grid.

        Then the screen's own resync, which is the part worth reusing: it takes
        the bars, the badge row and the plate back off the rules, so the numbers
        on the panels are the rules' numbers and not a second accounting.
        """
        for event in self.arena._queue:
            if isinstance(event, Said):
                self.arena.lines = [*self.arena.lines, event][-LOG_LINES:]
            elif isinstance(event, Over):
                self.arena.verdict = (
                    "VICTORY"
                    if event.won
                    else "YOU GOT AWAY"
                    if event.escaped
                    else "YOU DIED"
                )
                if app is not None:
                    app.play(
                        "victory"
                        if event.won
                        else "stairs"
                        if event.escaped
                        else "death"
                    )
                if not event.won and not event.escaped and app is not None:
                    # The run ended in here. The arena steps out of the way
                    # first: the summary is about the run, and the run is what is
                    # standing behind the arena -- the same order the Qt build
                    # leaves in.
                    app.leave_battle()
                    app.show_game_over(won=False)
        self.arena._queue = []
        self.arena._beat = 0.0
        self.arena._resync()

    @property
    def busy(self) -> bool:
        """Never: a round here is read, not watched. Kept for the app's question."""
        return self.arena.busy
