"""The fight, as cells: the real arena's panels, and a round that resolves at once.

This is the same seam job the theme and the grid already had, one screen further
along, and it came out cleaner than expected. The arena *says* almost everything
it has to say in cells -- the plate with the purse and the kill count, the log,
the four verbs, the order strip, and the monsters' own health bars, all of it
``buffer.text(...)`` and ``self._bar(...)`` rather than a painter. Measured, that
whole ``draw`` path asks Qt for no typeface, which is why this screen can hand it
a grid and get a real fight back.

What the Qt screen does in *pixels* is the stage: painted tiles, sprites at their
own size, sparks, flashes, a shaking glass. So the figures are written here as the
letters they have always been, in their own colours, which is exactly what the
dungeon drew a moment before the fight -- and the positions come from the arena's
own staging, so there is one layout and not two.

One deliberate difference: there is no playback. The Qt arena resolves a round
into a queue of events and plays them a beat at a time, because every beat is a
picture -- a number over a head, a shove, a colour across the room -- and those
are measured in pixels of a Qt typeface, which this front end must not ask for.
There is nothing to watch here anyway, so a round is *read* rather than watched:
the lines go into the log, the verdict goes up, and the screen's own resync puts
the bars, the badges and the plate where the rules already put them. That is the
terminal game's own tempo.
"""

from __future__ import annotations

from ..desktop.screens.battle import LOG_LINES, BattleScreen
from ..desktop.theme import parse_style
from ..game.battle import Over, Said

__all__ = ["SdlArena"]


class SdlArena:
    """The arena's own panels, and the stage written in the alphabet."""

    modal = False

    def __init__(self, battle) -> None:
        self.battle = battle
        #: The Qt fight, used for everything that is not pixels: its panels, its
        #: verbs, its order strip, its health bars, and the whole of the rules
        #: behind them. It is never asked to `paste`, and never asked to `step`,
        #: which are the two places its painting lives.
        self.arena = BattleScreen(battle)
        # Whatever happened before the hero's first command -- anything quicker
        # than he is acts first, and that is where a slow hero's fight opens with
        # a blow already thrown at him. The Qt build plays those as the queue is
        # played; there is no playing here, so they are read before the first
        # frame is drawn. (For the fastest hero in the roster that queue is empty,
        # which is a measurement and not a shortcut.)
        self._settle(None)

    # -- the picture --------------------------------------------------------
    def draw(self, buffer, app) -> None:
        self.arena.draw(buffer, app)
        cell_w = max(1, buffer.font.cell_w)
        for figure in self.arena._figures(buffer.cols, buffer.rows, buffer.font):
            x = int(figure.cx) // cell_w
            row = int(figure.row)
            if 0 <= x < buffer.cols and 0 <= row < buffer.rows:
                buffer.put(x, row, figure.glyph, parse_style(figure.colour))
        if self.arena.verdict is not None:
            self._verdict(buffer)

    def _verdict(self, buffer) -> None:
        """What the fight came to, stamped over the stage the way Qt blits it.

        The panel is the arena's own -- the same box, the same rule, the same
        hint -- asked for as cells and copied whole, spaces and all, so that it is
        opaque here exactly as it is opaque there. Written *into* the grid rather
        than over it, because a grid has no second layer: this front end has no
        pasted figures to cover, so the panel cannot land under anything.
        """
        panel, x, y = self.arena._verdict_panel(
            buffer.cols, buffer.rows, buffer.font
        )
        for py in range(panel.rows):
            for px in range(panel.cols):
                cell = panel.cells[py][px]
                buffer.put(x + px, y + py, cell.char, cell.style)

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
                        "victory" if event.won else "stairs" if event.escaped else "death"
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
