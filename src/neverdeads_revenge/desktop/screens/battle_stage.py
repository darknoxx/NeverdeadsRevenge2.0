"""BattleStage: one part of the fight screen."""

from __future__ import annotations

import math
from ..art import exists as art_exists
from ..art import size as art_size


from .battle_shared import (
    _picture,
    THICKNESS,
    TAPER,
    STAGE,
    ROWS,
    ECHO_STEP,
    ECHO_LANE,
    PANEL_ROWS,
    LOG_ROWS,
    ORDER_CELLS,
    PANEL_FLOOR,
    ARC_ROWS,
    HERO_CLEARANCE,
    HERO_CLEARANCE_CELLS,
    HERO_DROP,
    STAGE_LIFT,
    MONSTER_SIZES,
    HERO_SIZE,
    DRIFT_LIFE,
    WALL_STONES,
    FLOOR_BONES,
    _scatter,
    Staged,
)


class BattleStage:
    def panel_band(self, cols: int, rows: int) -> tuple[int, int]:
        """The rows the three panels own: the fight's own layer, top to bottom.

        The panels are written into the grid, and the grid is *under* the art -- so
        a figure standing in front of them is painted over the menu that is asking
        about it. Both painters put this band down a second time once the figures
        are in place, which is what keeps the menu on top of whoever is standing in
        front of it: the hero is covered by the plate he is standing in, and the
        list of tricks covers him entirely.

        A band and not the three areas, because which panel is showing is the
        screen's business: the verbs, the list of the five, the target row and the
        plate all come and go inside these rows.
        """
        plate = self._areas(cols, rows)["plate"]
        return plate[1], plate[1] + plate[3]

    def _dims(self, app) -> tuple[int, int]:
        """The grid this screen is drawn into: its own record, or the app's."""
        if self._size is not None:
            return self._size
        return (int(getattr(app, "cols", 0)), int(getattr(app, "rows", 0)))

    def _areas(self, cols: int, rows: int) -> dict[str, tuple[int, int, int, int]]:
        """Where the pieces sit, in cells: wall, ground, log, plate, commands.

        Five bands, bottom to top: the panels, the lines the fight speaks in,
        the floor, and the strip the walls stand up into. The wall strip is
        reserved rather than overlaid -- a wall drawn over the floor would be a
        wall standing in front of the hero.
        """
        margin = max(1, min(3, cols // 24))
        # The panels and the log are *always* this tall, whatever the window did to
        # the grid. They used to shrink on a short grid -- seven rows above
        # twenty-six, five above sixteen -- which was written for a tiny window and
        # fired on a wide one: a 21:9 monitor derives 114x24, and the same game came
        # up with a shorter ORDER strip, a shorter log, and the hero standing twenty
        # pixels lower in his own plate. The composition is not a function of how
        # many cells the window happened to fit.
        panel_h = PANEL_ROWS
        # One row of air under the panels and not the margin's three: the room has
        # more use for those rows than the frame has for a border, and the log has
        # moved out of the bottom anyway.
        panel_y = max(1, rows - panel_h - 1)
        log_h = LOG_ROWS
        log_y = max(1, panel_y - log_h)
        wall_h = max(2, min(3, rows // 8))
        wall_y = margin
        ground_y = min(log_y - 1, wall_y + wall_h)
        ground_h = max(1, log_y - ground_y)
        # The strip is reserved *before* the panels -- and the panels are then
        # what takes the leftover, capped as they always were. That is the fix:
        # the strip used to be the leftover itself, which reads fine on a wide
        # grid and is nothing on a narrow one (two cells at eighty columns, none
        # at all on a handheld's sixty-odd), and it is the thing a player reads
        # while deciding. At ninety-six columns the cap is what pays for it,
        # exactly as it always did: 36 + 36 + 16 and the margins are 96.
        panel_w = max(PANEL_FLOOR, min((cols - margin * 3 - ORDER_CELLS) // 2, 36))
        order_x = margin + panel_w + 1
        order_w = max(0, cols - margin - panel_w - order_x - 1)
        return {
            "wall": (margin, wall_y, max(1, cols - margin * 2), wall_h),
            "ground": (margin, ground_y, max(1, cols - margin * 2), ground_h),
            "log": (margin, log_y, max(1, cols - margin * 2), log_h),
            "plate": (margin, panel_y, panel_w, panel_h),
            "commands": (max(0, cols - margin - panel_w), panel_y, panel_w, panel_h),
            "order": (order_x, panel_y, order_w, panel_h),
        }

    def _field(
        self, cols: int, rows: int, cell_w: int, cell_h: int
    ) -> dict[str, float]:
        """The floor in pixels, plus the one number the walls are built from.

        Everything that has to agree about the room reads this: the tiles, the
        shadows, the two side walls and their shear. ``edge`` is one point of
        floor going away from the viewer.
        """
        x0, y0, width, height = self._areas(cols, rows)["ground"]
        inset = max(1, round(width * TAPER))
        left, right = x0 * cell_w, (x0 + width) * cell_w
        top, bottom = y0 * cell_h, (y0 + height) * cell_h
        dx = inset * cell_w
        dy = bottom - top
        length = math.hypot(dx, dy) or 1.0
        wx, wy, ww, wh = self._areas(cols, rows)["wall"]
        return {
            "wall_top": float(wy * cell_h),
            "wall_h": float(wh * cell_h),
            "left": left,
            "right": right,
            "top": top,
            "bottom": bottom,
            "width_px": right - left,
            "height_px": dy,
            "inset_px": dx,
            "cell_w": cell_w,
            "cell_h": cell_h,
            "cells_x0": x0,
            "cells_y0": y0,
            "cells_w": width,
            "cells_h": height,
            "edge_x": dx / length,
            "edge_y": -dy / length,
            "edge_len": length,
        }

    def _figures(self, cols: int, rows: int, font) -> list[Staged]:
        """The staged figures for this window.

        Worked out per call rather than kept: the staging carries *which* monster
        the choice is on, and a cache that remembered the arrow would leave it
        pointing at whoever was chosen when the window was last resized.
        """
        return self._stage(self._field(cols, rows, font.cell_w, font.cell_h))

    def _floor_row(self, cols: int, rows: int) -> int:
        """The row the room's floor is on: the foot of the ground band.

        One number, asked of the layout, and the painting is fitted to it -- which
        is the other way round from fitting the staging to the painting, and the
        right way round: the room's floor is where the game's own furniture leaves
        it, and that is a fixed number of rows above the panels at every window.
        """
        _x, y0, _w, ground_h = self._areas(cols, rows)["ground"]
        return y0 + ground_h - 1

    def _row_for(self, depth: float, lift: float, y0: int, height: int) -> float:
        """Where a monster stands, in rows: the room's floor, and the depth from it.

        One rule for both kinds of room, and the *rows* are the truth in both: the
        floor is the foot of the ground band -- a fixed number of rows above the
        panels, at every window -- and a depth walks back from there by a fixed
        number of rows. It used to be a share of the band's own height, which is
        how the same fight came out spread further apart on a taller window; the
        grid decides how much floor there *is*, not how deep a lane stands.

        ``ARC_ROWS`` is the row of twenty pixels the staging was tuned at: a lane
        twelve hundredths of a depth behind the front one stands one row further
        back, and the front one stands on the floor line itself.
        """
        return (y0 + height - 1) - STAGE_LIFT - (1.0 - depth) * ARC_ROWS - lift

    def _stage(self, field: dict[str, float]) -> list[Staged]:
        """Who stands where: the monsters in the far half, the hero in front.

        The monsters are the actors themselves, in the order they were met --
        their glyph, their colour, their depth. Nothing is invented here: a fight
        against three vipers is three v's on the floor, and a fight against one
        is one v in the middle of it.
        """
        cell_w = int(field["cell_w"])
        cell_h = int(field["cell_h"])
        x0, y0 = int(field["cells_x0"]), int(field["cells_y0"])
        width, height = int(field["cells_w"]), int(field["cells_h"])
        centre = x0 + width // 2
        living = self._targets()
        # The arrow is out only while something is being aimed: it marks the
        # *question*, and there is no question on the floor until a trick has
        # asked one.
        marked = living[self.target % len(living)] if self.aiming and living else None
        # And the crowd: a trick that hits the room puts the marker over every
        # one of them while it is chosen, before a single arrow is walked. The
        # cursor is a promise about who takes it, and "everybody" is a promise
        # one arrow cannot make.
        crowd = self.crowd_chosen()
        if marked is None and crowd is False and self.single_chosen() and living:
            # A single-target trick being looked at, before the arrow is walked:
            # one cursor, on the one it would go to if it were confirmed now.
            marked = living[self.target % len(living)]
        scale = 1.35 if width >= 120 else 1.0
        # The room's floor, in rows: the band's own foot, or -- when the room is a
        # Where the hero will stand, in rows -- the monsters are kept off his head
        # below, and that rule does not care whether the room is a painting.
        hero_row = y0 + height - 1 + HERO_DROP - STAGE_LIFT
        # And never into the panels: a floor line low enough to be *inside* the
        # menu is a floor line the menu is standing on, so the monsters stop at the
        # first row above it. The grid's own size, which this screen is told every
        # time it is drawn -- the field below is the *room's* band and does not know
        # where the panels are.
        size = self._size or (0, 0)
        lowest = (
            max(1, self._areas(*size)["plate"][1] - 1)
            if size[0] and size[1]
            else y0 + height
        )
        # The back of the room: no monster stands above the wall. A lane with a
        # nudge of its own can cross it -- the middle of three is the only one that
        # has a nudge, which is why it is the only one that ever ended up in the
        # wall -- and the line is the artwork's, not the lane's.
        highest = -1e9
        if self.stage_horizon is not None:
            highest = (self.stage_horizon + THICKNESS) / max(1, cell_h)
        monsters = self.battle.enemies[:STAGE]
        places = ROWS.get(len(monsters), ROWS[STAGE])
        staged: list[Staged] = []
        for index, enemy in enumerate(monsters):
            lane, depth, lift = places[min(index, len(places) - 1)]
            size = round(MONSTER_SIZES[min(index, len(MONSTER_SIZES) - 1)] * scale)
            # The echo is the one monster drawn at the hero's own size, because
            # it *is* the hero -- a shade of the run that got furthest, wearing
            # its face. So it is staged where the hero is staged: on his line,
            # a step behind him. Deeper into the room and its bar would be over
            # the top of the frame, because the bar follows the picture; closer
            # and it would be standing inside him, which is a shadow nobody sees.
            echo = getattr(enemy, "behaviour", "") == "echo"
            # Its own picture when its name is not the file: the echo wears the
            # front of a hero, and the file is a portrait, not a monster.
            art = enemy.art or _picture(enemy.base_name or enemy.name)
            if echo:
                # The lane beside the hero rather than the one it was given: at
                # the hero's height, the middle lane is behind his head, and a
                # shadow the hero is standing in front of is a shadow nobody
                # sees.
                lane = ECHO_LANE
            cx = (centre + round(lane * width) + 1) * cell_w
            # Standing over the hero is the one place a monster may not be: he is
            # the near figure and the plate is his home, and on a short frame -- a
            # very wide monitor derives fewer rows than a tall one -- the painting's
            # floor line and the panel band come close enough for a collision. The
            # room compresses instead, and only there.
            if abs(cx - (centre + 1) * cell_w) <= HERO_CLEARANCE_CELLS * cell_w:
                floor_here = min(lowest, hero_row - HERO_CLEARANCE)
            else:
                floor_here = lowest
            staged.append(
                Staged(
                    actor=enemy,
                    glyph=enemy.glyph,
                    colour=enemy.color,
                    size=size,
                    cx=cx,
                    affix=enemy.affixes[0] if enemy.affixes else None,
                    warden=enemy.warden,
                    row=(
                        hero_row - ECHO_STEP
                        if echo
                        else min(
                            floor_here,
                            max(highest, self._row_for(depth, lift, y0, height)),
                        )
                    ),
                    cells=self._span(art, cell_w),
                    chosen=enemy is marked or crowd,
                    art=art,
                    phase=index * 1.9,
                )
            )
        # Atritas, when the trick has called him: a figure beside the hero and on
        # his own row, because a shadow that stands in the hero's place is a
        # The shadow himself is not staged: he is not standing in the room, he is
        # *moving through* it -- a sprite over whichever monster he went for, one
        # strike at a time. A figure beside the hero was a shadow doing nothing,
        # which is exactly what he looked like.
        hero = self.battle.hero
        size = round(HERO_SIZE * scale)
        art = _picture(hero.name)
        if hero.name == "Noxx" and self.shadow_is_out():
            # The thing that lives in him is over the monsters; the body it lives
            # in is drawn without it until it comes back.
            bare = _picture("noxx_noatritas")
            if art_exists(bare):
                art = bare
        staged.append(
            Staged(
                actor=hero,
                glyph=hero.glyph,
                colour=hero.color,
                size=size,
                # A trick that is only about him puts the cursor over *him*: the
                # floor is where the fight says who a thing is for, and "this one"
                # is an answer about the hero too.
                chosen=self.self_chosen(),
                cx=(centre + 1) * cell_w,
                row=y0 + height - 1 + HERO_DROP - STAGE_LIFT,
                cells=self._span(art, cell_w),
                art=art,
                # In front of the row and out of step with it: the hero breathes
                # on his own, as somebody standing still in front of a crowd does.
                phase=len(monsters) * 1.9 + 0.9,
            )
        )
        return staged

    def _beside_target(
        self,
        figure: Staged,
        target_id: int,
        figures,
        home: int,
        cell_w: int,
        cell_h: int,
    ) -> tuple[int, int]:
        """Where a striker appears, relative to the one it is hitting.

        The hero comes at the monsters from the front, so he lands low and to the
        left of his target -- standing *in front of* it, both of them visible.
        A monster comes for the hero from beyond him, so it lands high and to the
        right: behind him, and under him, because the floor runs away towards the
        top of the room and the hero is standing nearer to the player than it is.
        """
        behind = figure.actor is not self.battle.hero
        for other in figures:
            if id(other.actor) == target_id:
                if behind:
                    return other.cx + cell_w * 3, other.row * cell_h - cell_h
                return other.cx - cell_w * 3, other.row * cell_h + cell_h * 4 // 5
        return figure.cx, home

    @staticmethod
    def _stone(along: int, course: int) -> str:
        """Which stone is at this place in a wall, by name: mostly plain,
        sometimes not.

        Chosen from the place in the wall and not rolled for, so the scattered
        vines stay where they grew: a room that re-dressed itself every frame
        would be a room made of flicker. Named and not loaded -- the same split
        the floor's stones keep -- so a front end with no QPainter can lay the
        same wall.
        """
        return WALL_STONES[_scatter(along, course) % len(WALL_STONES)]

    @staticmethod
    def _floor_stone(along: int, row: int, light: bool) -> str:
        """Which flagstone is here, by name: the tone the checker wants, and
        sometimes what is lying on it.

        Chosen from the place and not rolled for, for the same reason the wall's
        scatter is: bones stay where they were left. Named rather than loaded,
        because *which* stone belongs at a place is the room's rule and loading
        it is the painter's business -- which is what lets a blitter with no
        painter at all lay the same floor.
        """
        tone = "a" if light else "b"
        if _scatter(along, row) % FLOOR_BONES == 0:
            return f"floor_{tone}_bones"
        return f"floor_{tone}"

    @staticmethod
    def _span(art: str | None, cell_w: int) -> int:
        """How many cells wide the pool of shadow under a figure has to be.

        The picture's own width when there is one -- read off the file, because
        how wide a picture is is a fact about the picture -- and two cells when
        there is not: the letter that stands in for it is one cell of the grid,
        and the grid is what this is measured against. Nothing here needs a font,
        which is the point: a shadow belongs to the room and not to the painting.
        """
        measured = art_size(art) if art is not None else None
        if measured is None:
            return 2
        return max(2, round(measured[0] / cell_w))

    def shadow_is_out(self) -> bool:
        """Whether the thing that lives in Noxx is somewhere else.

        Two ways that happens: a FRIENDS LIKE THESE ghost over the room, or the
        void itself let out for forty turns. Either way the body stands without
        its shadow, because the shadow is not in it.
        """
        if self.battle.state.atritas is not None:
            return True
        return any(
            self._clock - when < DRIFT_LIFE for _art, _x, _y, when in self._drift
        )

    def self_chosen(self) -> bool:
        """Whether the attack being looked at is one that lands on the hero."""
        if not self.picking:
            return False
        specials = self.battle.learned()
        if not specials:
            return False
        chosen = specials[min(self.special, len(specials) - 1)]
        return (
            not chosen.needs_target
            and not chosen.all_enemies
            and self.battle.special_available(chosen)
        )

    def single_chosen(self) -> bool:
        """Whether the attack being looked at is one that goes to *one* monster."""
        if not self.picking:
            return False
        specials = self.battle.learned()
        if not specials:
            return False
        chosen = specials[min(self.special, len(specials) - 1)]
        return chosen.needs_target and self.battle.special_available(chosen)

    def crowd_chosen(self) -> bool:
        """Whether the attack being looked at is one that hits everybody.

        Read off the list while it is open: the highlighted trick, if it is an
        ``all_enemies`` one and he can pay for it. The area's own kind of cursor
        then goes over every living monster, the way a spell that says "all"
        does in the games this one learned its manners from.
        """
        if not self.picking:
            return False
        specials = self.battle.learned()
        if not specials:
            return False
        chosen = specials[min(self.special, len(specials) - 1)]
        return chosen.all_enemies and self.battle.special_available(chosen)

    def _figure_of(self, actor, app) -> Staged | None:
        cols, rows = self._dims(app)
        for figure in self._figures(cols, rows, app.font):
            if figure.actor is actor:
                return figure
        return None

    def _point_of(self, actor, app) -> tuple[float, float] | None:
        """Where a figure stands on the frame, in pixels, for the picture stuff."""
        figure = self._figure_of(actor, app)
        if figure is None:
            return None
        _, cell_h = app.font.cell_w, app.font.cell_h
        # Rounded, because a figure may stand on half a row and a pixel a
        # painter is handed is a whole one.
        return (figure.cx, int(figure.row * cell_h))

