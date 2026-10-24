"""BattlePanels: one part of the fight screen."""

from __future__ import annotations

import math
from ...game.battle import (
    ATTACK,
    FLEE,
    ITEM,
    SPECIAL,
    VERBS,
)
from ...game.specials import (
    special_by_key,
)
from ..chrome import ASH, BLOOD, BONE, box, rule
from ..pattern import PatternBuffer
from ..render import log_style
from ..theme import Colour, Style, parse_style


from .battle_shared import (
    FLOOR_NEAR,
    FLOOR_NEAR_ALT,
    FLOOR_FAR,
    FLOOR_FAR_ALT,
    TAPER,
    POINT,
    HOLLOW,
    POINT_COLOUR,
    LEVEL_UP,
    LEVEL_UP_COLOUR,
    STATUS_COLOURS,
)


class BattlePanels:
    def _draw_ground(
        self, buffer: PatternBuffer, area: tuple[int, int, int, int]
    ) -> None:
        """Rows of filled tiles, staggered, narrowing and fading as they recede.

        Row ``i`` counts from the far edge down to the hero's feet. Its inset
        grows with the distance to the back, and its tone falls off on the way,
        so the same two colours in the same two glyphs turn into a floor that
        goes somewhere.
        """
        x0, y0, width, height = area
        if width < 8 or height < 3:
            return
        back_inset = max(1, round(width * TAPER))
        for i in range(height):
            depth = i / (height - 1)
            inset = round((1.0 - depth) * back_inset)
            # Half a tile of stagger per row: this is the whole of the
            # isometric illusion. Two cells are one tile, so the phase is a cell.
            phase = i % 2
            for x in range(inset, width - inset):
                alt = ((x + phase) // 2) % 2 == 0
                buffer.put(x0 + x, y0 + i, " ", Style(bg=self._tile(depth, alt)))

    @staticmethod
    def _tile(depth: float, alt: bool) -> Colour:
        """The floor's colour at ``depth``: 0 at the far edge, 1 at the hero.

        Mixed on the three channels and not through a toolkit: two palette colours
        and a tone between them is arithmetic, and the *grid* floor that wears it
        is the half of this screen that has to work without one.
        """
        near, far = (FLOOR_NEAR, FLOOR_FAR) if alt else (FLOOR_NEAR_ALT, FLOOR_FAR_ALT)
        return Colour(
            int(far.r + (near.r - far.r) * depth),
            int(far.g + (near.g - far.g) * depth),
            int(far.b + (near.b - far.b) * depth),
        )

    def _draw_health(
        self, buffer: PatternBuffer, area: tuple[int, int, int, int]
    ) -> None:
        """Under each monster *that has no picture*, the part of it that is left.

        The fallback and not the bar: a figure the sheets have art for gets its
        stripe over its head in the paste, and a stripe here as well would be a
        second one -- which is what it looked like the moment the two places came
        apart. For a figure with no art the letter is the monster, the floor is the
        only room there is, and this is the sole place its health can be said.
        """
        font = buffer.font
        for figure in self._figures(buffer.cols, buffer.rows, font):
            if figure.actor is self.battle.hero or figure.art is not None:
                continue
            total = max(1, figure.actor.max_hp)
            shown = self._shown.get(id(figure.actor), figure.actor.stats.hp)
            cells = max(8, min(14, figure.cells * 2))
            left = round(figure.cx / font.cell_w) - cells // 2
            # In the figure's own row, which is the one its feet are at the top
            # of: a bar a row lower was a bar floating about on its own. Rounded,
            # because a bar written into the grid lands on whole rows and a figure
            # may be standing on half of one.
            self._bar(buffer, left, round(figure.row), cells, shown / total, thin=True)

    def _draw_log(self, buffer: PatternBuffer, area: tuple[int, int, int, int]) -> None:
        """The lines the fight speaks in, newest last, in the dungeon's colours.

        The same mapping the dungeon log uses, which is the point: a curse is
        the same red here as it is down there, and a kill is the same bad news.

        Behind the words is a strip of the dungeon's own black, the width of the
        frame: this is read over a *painting* now, and a line of prose on stone is
        a line nobody reads. Three rows for three lines and not a row more: a row
        of black under the words was a row of black hanging under them.
        """
        from ..theme import BACKGROUND

        x, y, width, height = area
        if width < 20:
            return
        for row in range(y, y + height):
            buffer.fill_row(row, " ", Style(bg=BACKGROUND))
        shown = self.lines[-height:]
        for index, line in enumerate(shown):
            text = line.text[: max(0, width - 4)]
            style = parse_style(log_style(line.kind))
            buffer.text(x + 2, y + index, text, style)
            if index == len(shown) - 1:
                buffer.put(x, y + index, "►", style)

    def _draw_plate(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The hero's plate: who he is, how much of him is left, what he carries."""
        hero = self.battle.hero
        title = hero.name.upper()
        box(buffer, x, y, width, height, title=title, border=BLOOD, fill=True)
        if height < 4 or width < 14:
            return
        shown = self._shown.get(id(hero), hero.stats.hp)
        total = max(1, hero.max_hp)
        bar = min(12, max(4, width - 22))
        buffer.text(x + 2, y + 1, "HP", parse_style(ASH))
        self._bar(buffer, x + 5, y + 1, bar, shown / total)
        buffer.text(x + 6 + bar, y + 1, f" {shown:>2}/{total}", parse_style(BONE))
        if height >= 5:
            draughts = len(self.state.floor_draughts)
            marks = "●" * min(3, draughts) + "○" * max(0, 3 - draughts)
            pack = len([item for item in self.state.inventory if item.heal > 0])
            buffer.text(x + 2, y + 2, f"PACK {pack}", parse_style(ASH))
            buffer.text(x + 10, y + 2, marks, parse_style("dim #a855f7"))
        if height >= 6:
            # The purse, as stones rather than as a bar: one mark a point, filled
            # and hollow. The old line here said whether the *void* was ready,
            # which told the player about one trick out of eight; this says what
            # there is to spend, and the price of everything is on the list.
            points = self.kill_points
            top = self._plate["top"]
            # The number stays, small beside it, because at a deep level the
            # stones run out of room before the purse runs out of points.
            room = max(3, width - 14)
            shown = min(top, room)
            filled = min(points, shown)
            buffer.text(x + 2, y + 3, "KP", parse_style(ASH))
            buffer.text(x + 5, y + 3, POINT * filled, parse_style(POINT_COLOUR))
            buffer.text(
                x + 5 + filled, y + 3, HOLLOW * (shown - filled), parse_style("grey23")
            )
            buffer.text(
                x + 6 + shown, y + 3, f"{points}/{top}", parse_style(ASH)
            )
        if height >= 5:
            # The same count the side panel keeps, because a level is the one
            # thing a fight is *for* and the player should not have to leave the
            # room to find out how close it is.
            to_go = self._plate["kills"]
            level = self._plate["level"]
            buffer.text(
                x + 2,
                y + 4,
                f"{to_go} KILLS TO LVL {level + 1}" if to_go else "THE LAST LEVEL",
                parse_style(ASH),
            )
        if (self.picking or self.aiming) and height >= 7:
            # Escape is a step *back* in the two menus and nothing anywhere else
            # -- there is no way out of a fight but through it -- so the plate only
            # says anything about it while there is somewhere to go back to. The
            # line it used to carry ("leave the arena") was a promise no key could
            # keep.
            buffer.text(x + 2, y + height - 2, "esc  back", parse_style(ASH))

    def _draw_commands(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The verbs, arranged the way every menu in this game is.

        The ask is drawn dim when the dark will not answer: a verb that costs a
        turn to refuse is a verb that punishes curiosity.
        """
        if self.picking:
            # The list takes the whole strip rather than the verbs' half of it:
            # five names and a sentence about the chosen one do not fit in a
            # column three lines tall, and a list nobody can read is a list
            # nobody can choose from.
            self._draw_specials(
                buffer,
                self._areas(buffer.cols, buffer.rows)["plate"][0],
                y,
                buffer.cols - 2 * self._areas(buffer.cols, buffer.rows)["plate"][0],
                height,
            )
            return
        if self.aiming:
            self._draw_targets(buffer, x, y, width, height)
            return
        box(buffer, x, y, width, height, title="COMMAND", border=BLOOD, fill=True)
        if height < 4 or width < 12:
            return
        on_pad = getattr(buffer, "pad", False)
        if on_pad:
            # A pad has no letters: X and Y are direct, and A confirms whatever
            # the marker is on -- so only the two shortcuts are advertised, and
            # the label closes up where there is no shortcut to show.
            keys = {ATTACK: "", SPECIAL: "X ", ITEM: "Y ", FLEE: ""}
        else:
            keys = {ATTACK: "a ", SPECIAL: "s ", ITEM: "i ", FLEE: "f "}
        rows = [(keys[verb], verb.upper()) for verb in VERBS[: height - 2]]
        chosen = self.verb if self.verb < len(rows) else 0
        ready = self.battle.special_ready()
        for index, (key, label) in enumerate(rows):
            lit = index == chosen
            marker = "►" if lit else " "
            verb = VERBS[index]
            if lit:
                style = parse_style(f"bold {BONE}")
            elif verb == SPECIAL and not ready:
                style = parse_style("grey23")
            else:
                style = parse_style(ASH)
            buffer.text(x + 2, y + 1 + index, f"{marker} {key} {label}", style)
            if verb == ATTACK:
                self._draw_wield(buffer, x + 14, y + 1 + index, width - 16)

    def _draw_wield(
        self, buffer: PatternBuffer, x: int, y: int, room: int
    ) -> None:
        """What the blade in his hand does, beside the verb that swings it.

        Short, and in the colours the wounds are drawn in on the monsters: the
        menu and the room say the same thing, so a player learns the vocabulary
        once. `( = X` when his hand is empty -- which is worth saying, because
        fighting bare-handed is a *choice* the game lets him make.

        Read from the equipment and not remembered, so a weapon swapped mid-floor
        shows up here before the next swing rather than after it.
        """
        keys = self.state.player.weapon_inflicts
        if not keys:
            buffer.text(x, y, "( = X", parse_style("grey30"))
            return
        column = buffer.text(x, y, "( = ", parse_style(ASH))
        for index, key in enumerate(keys):
            if index:
                column = buffer.text(column, y, " + ", parse_style(ASH))
            if column - x >= room:
                return
            column = buffer.text(column, y, key, parse_style(STATUS_COLOURS[key]))

    def _draw_targets(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """Who the arrow is on, said in words.

        The one place in a fight where a monster's name is written on a panel
        rather than spoken in the log: a name under a figure would be a label on
        the room, but this is the *choice*, and a choice has to be readable. The
        arrow on the floor and the name in the panel are the same answer twice,
        which is how a player learns to trust the arrow.
        """
        trick = special_by_key(self._picked) if self._picked else None
        # The trick being aimed is named in the frame, because the aim is still
        # a choice about the *attack*: what is about to be thrown at one of them
        # has to stay in front of the player while they pick which one.
        title = "TARGET" if trick is None else f"TARGET  ·  {trick.name}"
        box(buffer, x, y, width, height, title=title, border=BLOOD, fill=True)
        if height < 3 or width < 12:
            return
        living = self._targets()
        chosen = self.target % len(living) if living else 0
        for index, enemy in enumerate(living[: max(1, height - 4)]):
            lit = index == chosen
            marker = "►" if lit else " "
            style = parse_style(f"bold {BONE}" if lit else ASH)
            buffer.text(x + 2, y + 1 + index, f"{marker} {enemy.name}"[: width - 2], style)
        if trick is not None and height >= 4:
            buffer.text(x + 2, y + height - 3, trick.effect[: width - 2], parse_style(BONE))
        buffer.text(x + 2, y + height - 2, "◄ ►  pick", parse_style(ASH))

    def _draw_order(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The next few turns, in the alphabet the whole game is made of.

        A glyph a turn, in the actor's own colour, the one being taken now the
        brightest of them: a player deciding what to do this turn is deciding
        against the next two, and this is that sentence written short.

        Letters and not names, and the *same* letters the room is drawn in -- ``N``
        for Noxx and whatever the ghoul is -- so the strip reads as part of this
        fight rather than as a legend about it.
        """
        if self.picking or self.battle.over or height < 3 or width < 8:
            # The list wants the whole strip when it is open, and a fight that is
            # over has no order left to show.
            return
        # A short box, sitting on the same line as the two beside it. The strip is
        # one row of letters, and a box the full height of the others would be a
        # box of mostly nothing.
        tall = min(height, 3)
        top = y + height - tall
        box(buffer, x, top, width, tall, title="ORDER", border=BLOOD, fill=True)
        row = top + 1
        shown = min(len(self._order), max(1, (width - 2) // 3))
        for index in range(shown):
            actor = self._order[index]
            # Bold for the turn being taken, plain for the rest: bright enough to
            # read, different enough to tell apart. A strip the player has to
            # squint at is a strip they will not look at.
            style = parse_style(f"bold {actor.color}" if index == 0 else actor.color)
            buffer.text(x + 2 + index * 3, row, actor.glyph, style)
            if index + 1 < shown:
                buffer.text(x + 3 + index * 3, row, ">", parse_style(ASH))

    def _draw_specials(
        self, buffer: PatternBuffer, x: int, y: int, width: int, height: int
    ) -> None:
        """The five, across the whole strip the panels share.

        Two columns, because five names and a sentence about the chosen one do
        not fit in a column three lines tall -- and the hint goes in the frame's
        own title row, which is the one line of a panel nobody minds sharing.

        The ones that cannot be spent are dim rather than hidden: a lock is a
        promise, and a name the player can read is what makes a level worth
        reaching for. *Why* one cannot be spent is the fight's to say, in the log,
        when it is asked for; a panel of reasons would be a manual.
        """
        # The purse is in the *frame* of the list and not only on the plate,
        # because the list is what covers the plate: a player choosing what to
        # spend has to be able to see what there is to spend.
        # The frame says what the panel is, what it costs and what the keys do --
        # in words a player has not had to learn from anywhere else. "The dark"
        # was the fight's own name for its tricks and it read as a mystery; the
        # purse is the same stones the plate counts.
        top = self._plate["top"]
        purse = POINT * min(self.kill_points, top) + HOLLOW * max(
            0, top - self.kill_points
        )
        box(
            buffer,
            x,
            y,
            width,
            height,
            title=f"SPECIAL ATTACKS      {purse}      enter  use      esc  back",
            border=BLOOD,
            fill=True,
        )
        if height < 4 or width < 24:
            return
        specials = self.battle.learned()
        rows = max(1, height - 4)
        # The list is as many columns as its tricks need and no more: two for a
        # kit of five or six, three for Noxx's eight. A fixed two columns would
        # have run his last three names off the right-hand edge of the panel.
        columns = max(1, min(3, math.ceil(len(specials) / rows)))
        column_w = width // columns
        for index, special in enumerate(specials):
            usable = self.battle.special_available(special)
            chosen = index == self.special
            marker = "►" if chosen else " "
            # The price, as stones, on every line and whether he can pay it or
            # not: a menu that hid what it cost would be a menu of surprises.
            # The number in front of it used to be a *keypress*, which is not a
            # thing to read a menu by.
            line = f"{marker} {special.name} {POINT * special.cost}"
            # Three steps and not two, and the gap between them wide: what he
            # can pay for is *bright*, what he cannot is barely there, and the
            # one under the marker is brighter still. The old middle step (ash
            # next to grey) was a difference the player had to hunt for.
            if not usable:
                style = parse_style("grey23")
            elif chosen:
                style = parse_style(f"bold {BONE}")
            else:
                style = parse_style("bold #b9b3c8")
            buffer.text(
                x + 2 + (index // rows) * column_w,
                y + 1 + (index % rows),
                line[: column_w - 2],
                style,
            )
        if specials:
            shown = specials[min(self.special, len(specials) - 1)]
            # What it *does* first, in the readable ink, and then how the fight
            # says it, dim: the numbers are the offer and the voice is the
            # colour. A list that only had the voice would be a list the player
            # has to guess their way through, and guessing is not a choice.
            buffer.text(x + 2, y + height - 3, shown.effect[: width - 4], parse_style(BONE))
            buffer.text(x + 2, y + height - 2, shown.blurb[: width - 4], parse_style(ASH))

    @staticmethod
    def _bar(
        buffer: PatternBuffer,
        x: int,
        y: int,
        cells: int,
        ratio: float,
        thin: bool = False,
    ) -> None:
        """A health bar: filled, then empty, in the colour the ratio has earned.

        ``thin`` draws it half a cell tall, which is what the floor wants -- a
        stripe under a monster rather than a second panel -- and the plate in the
        corner keeps its full height, because there the bar *is* the panel.
        """
        filled = max(0, min(cells, round(cells * ratio)))
        ink, hollow = ("▄", "▄") if thin else ("█", "░")
        colour = (
            "bright_green"
            if ratio > 0.5
            else "bright_yellow"
            if ratio > 0.25
            else "bright_red"
        )
        buffer.text(x, y, ink * filled, parse_style(colour))
        buffer.text(x + filled, y, hollow * (cells - filled), parse_style("grey19"))
    def _level_up(self, app) -> None:
        """The arrow rising off the hero, and the note that goes with it.

        A popup like a damage number and deliberately *not* one: it is bigger,
        it is gold, it starts a little higher than a number lands so the two
        never share a spot, and it drifts up and fades exactly the way a number
        does -- which is the joke of it. The loudest thing in the room is a
        number about somebody else; this is the quiet one about him.
        """
        figure = self._figure_of(self.battle.hero, app)
        if figure is None:
            return
        popup = self._popup(LEVEL_UP, LEVEL_UP_COLOUR, figure, app, True)
        popup.y -= 12  # clear of the damage numbers, which land on the same head
        self._popups.append(popup)
        rumble = getattr(app, "rumble", None)
        if rumble is not None:
            rumble(0.25, 0.7, 120)
        # And *now* the plate may say it: the count, the level and the purse all
        # move with the arrow, which is the moment the level happened for the
        # player rather than the moment the rules worked it out.
        self._reading()
        app.play("level_up")

    def _took_a_turn(self, actor) -> None:
        """The strip moves on: whoever acted is done and the rest come up.

        Dropped up to *and including* them, and not simply off the front: a turn
        whose events are not all blows -- the hero finding a note for his sword,
        a monster swinging at where he was -- would otherwise leave the strip one
        turn behind for the rest of the round.
        """
        for index, waiting in enumerate(self._order):
            if waiting is actor:
                del self._order[: index + 1]
                return

    def _verdict_panel(
        self, cols: int, rows: int, font
    ) -> tuple[PatternBuffer, int, int]:
        """What the fight came to, as a panel of cells and where it lands.

        Built here and not drawn, because *where* it goes is the arena's business
        and *what* it says is the fight's -- and because a second front end wants
        the same panel without a painter. Set on the *stage* and not in the middle
        of the glass: the last lines of the fight are the only account of how it
        ended, and a panel dropped over them would be covering the story with its
        title.
        """
        text = self.verdict or ""
        width = min(cols - 6, max(24, len(text) + 10))
        height = 5
        areas = self._areas(cols, rows)
        _, wall_y, _, wall_h = areas["wall"]
        _, log_y, _, _ = areas["log"]
        top = wall_y + wall_h
        x = max(0, (cols - width) // 2)
        y = max(0, min(log_y - height, top + (log_y - top - height) // 2))

        panel = PatternBuffer(width, height, font)
        colour = {"YOU DIED": BLOOD, "VICTORY": "bright_yellow"}.get(text, ASH)
        box(panel, 0, 0, width, height, border=colour, fill=True)
        ink = parse_style(f"bold {BONE}")
        left = 3 + max(0, (width - 6 - len(text)) // 2)
        panel.text(left, 2, text, ink)
        rule(panel, 1, height - 2, width - 2, ASH)
        panel.text(2, height - 1, "enter  leave the arena", parse_style(ASH))
        return panel, x, y

