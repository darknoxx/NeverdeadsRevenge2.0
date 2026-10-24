"""AppPaint: one part of the SDL application."""

from __future__ import annotations

import time
from ..desktop.theme import BACKGROUND, Colour
from .paint import paint




class AppPaint:
    def redraw(self) -> None:
        """Draw the stack into the grid, and the grid onto the window."""
        from ..desktop.pattern import PatternBuffer

        # The grid is reused and cleared rather than rebuilt. A frame of this game
        # is two thousand six hundred cells, and a fresh buffer every frame was two
        # thousand six hundred cells and their styles made again to hold the same
        # blanks. The *shape* can change -- the window moves, and the grid is
        # derived from it -- so the shape is what is checked.
        if (self.grid.cols, self.grid.rows) != (self.cols, self.rows):
            self.grid = PatternBuffer(self.cols, self.rows, self.font)
        else:
            self.grid.font = self.font
            self.grid.clear()
        self.grid.pad = self.pad_active
        mark = time.perf_counter() if self._timing_now else 0.0
        # A dialog is a window, not a room: the stack under it is drawn in full,
        # and the box is laid on the finished frame afterwards. Everything the
        # box does not cover stays exactly as it was. An opaque menu is a room
        # and roots the stack at itself, as it always did.
        top = len(self.screens) - 1
        overlay = top if top > 0 and self._is_dialog(top) else None
        content = top if overlay is None else self._content_under(overlay)

        start = 0
        for index in range(content + 1):
            screen = self.screens[index]
            if getattr(screen, "modal", False) and getattr(screen, "opaque", True):
                start = index
        for index in range(start, content + 1):
            # A dialog under a dialog is waiting its turn: only the topmost one
            # is drawn, so three cards pushed by one announcement are three
            # cards read in turn instead of three boxes on top of each other.
            if index != content and self._is_dialog(index):
                continue
            screen = self.screens[index]
            if self._timing_now:
                # Which screen the cells went to: a stack can hold the room and
                # the fight, and "cells 24" does not say whose 24 it was.
                drawn = time.perf_counter()
                screen.draw(self.grid, self)
                self._note(f"draw[{type(screen).__name__}]", drawn)
            else:
                screen.draw(self.grid, self)
        mark = self._note("cells", mark)
        # A screen may bring its own paper: the arena's painted room goes *under*
        # the cells, so the panels, the log and the sidebar sit on it instead of
        # on a black field beside it.
        # What the frame is made of is the screen *under* the dialog, not the
        # dialog: a box has no room behind it to paint.
        base_screen = self.screens[content]
        base = BACKGROUND
        paper = getattr(base_screen, "paper", None)
        if paper is not None:
            # A screen with no painting to show answers None, and flat paper is
            # what the frame wanted all along.
            base = paper(self.cols, self.rows, self.font) or BACKGROUND
        self._surface = paint(self.grid, self.font, base)
        mark = self._note("paint", mark)
        self._small_face(base_screen)
        mark = self._note("small", mark)
        # And a screen may paint straight onto the frame once the grid is drawn:
        # that is where the art lives -- sprites do not fit in a character cell.
        # It is called `paint_over` and not `paste`, which is Qt's name for the
        # same pass, because the Qt screens in this same stack have a `paste` too
        # and it wants a QImage: one name for two media is one crash waiting.
        paint_over = getattr(base_screen, "paint_over", None)
        if paint_over is not None:
            paint_over(self._surface, self)
        mark = self._note("art", mark)
        self._blit_art(base_screen)
        if overlay is not None:
            self._paint_overlay(self.screens[overlay])
        # And the pixels that are not the room: sparks thrown by whatever just
        # happened, drawn last so they land on top of everything.
        self.effects.draw(self._surface)
        self._draw_note()
        mark = self._note("effects", mark)
        if self.show_fps:
            self._draw_fps()
        self._present()
        self._note("present", mark)
        #: The picture is the screen's own from here until something changes it.
        self._dirty = False
        self._painted_at = time.monotonic()
        self._painted += 1

    def _is_dialog(self, index: int) -> bool:
        """Whether the screen at ``index`` is a box drawn over the stack."""
        screen = self.screens[index]
        return bool(getattr(screen, "modal", False)) and not getattr(
            screen, "opaque", True
        )

    def _content_under(self, overlay: int) -> int:
        """The screen a dialog stands on, skipping other waiting dialogs."""
        index = overlay - 1
        while index > 0 and self._is_dialog(index):
            index -= 1
        return max(0, index)

    def _paint_overlay(self, screen) -> None:
        """Lay a dialog's box over the finished frame.

        Its own cells are opaque; every cell it does not use stays transparent,
        which is the whole difference between a window and a room.
        """
        from ..desktop.pattern import PatternBuffer

        grid = PatternBuffer(self.cols, self.rows, self.font)
        grid.clear()
        grid.pad = self.pad_active
        screen.draw(grid, self)
        self._surface.blit(paint(grid, self.font, None), (0, 0))
        self._blit_art(screen)

    def _small_face(self, screen) -> None:
        """The sidebar's lower rows and the combat log, one size down.

        The Qt build draws these straight onto the frame after the grid, and this
        is the same pass with a pygame painter: the *rows* come from the shared
        specs in ``desktop/render.py`` -- what to say, where, in which colour --
        and only the blitting is this application's. That is why the two front
        ends can show the same sidebar without one of them owning the layout.
        """
        import pygame

        from ..desktop.render import log_text, sidebar_text
        from ..desktop.theme import BACKGROUND, parse_style

        if not getattr(screen, "smaller_face", False) or self.run is None:
            return
        face = self.font_small
        surface = self._surface
        rect, rows = log_text(
            self.run,
            self.grid.cols,
            self.grid.rows,
            self.font.cell_w,
            self.font.cell_h,
            face.cell_w,
            face.cell_h,
        )
        # The log's own panel, drawn solid: nothing is underneath it now that the
        # cells above it are clear.
        surface.fill(tuple(BACKGROUND), pygame.Rect(*rect))
        for ink in rows:
            self._put_small(surface, face, ink)
        out, rule, slots = sidebar_text(
            self.run,
            self.grid.cols,
            self.grid.rows,
            self.font.cell_w,
            self.font.cell_h,
            face.cell_w,
            face.cell_h,
            pad=self.pad_active,
        )
        for ink in out:
            self._put_small(surface, face, ink)
        for slot in slots:
            self._put_slot(surface, slot)
        if rule is not None:
            surface.fill(
                tuple(parse_style("grey30").fg),
                pygame.Rect(rule[0], rule[2], rule[1] - rule[0], 1),
            )

    def _put_small(self, surface, face, ink) -> None:
        """One row of the small face: a string, blitted a glyph at a time."""
        from ..desktop.theme import parse_style

        colour = parse_style(ink.colour).fg
        for index, char in enumerate(ink.text):
            if char == " ":
                continue
            glyph = face.glyph(char, colour)
            if glyph is not None:
                surface.blit(glyph, (ink.x + index * face.cell_w, ink.y))

    def _draw_fps(self) -> None:
        """How fast this is going, in the corner, when ``--fps`` asked for it.

        Bottom right, on its own dark patch so it can be read over a sidebar: it
        is a developer's number and not part of the fiction, so it is allowed to
        sit on top of one.
        """
        import pygame

        from ..desktop.theme import BACKGROUND

        text = f"{self.frames:4.1f} fps"
        face = self.font_small
        width = len(text) * face.cell_w + 6
        height = face.cell_h + 4
        left = max(0, self._surface.get_width() - width)
        top = max(0, self._surface.get_height() - height)
        self._surface.fill(tuple(BACKGROUND), pygame.Rect(left, top, width, height))
        for index, char in enumerate(text):
            glyph = face.glyph(char, Colour(0xC8, 0xC8, 0xC8))
            if glyph is not None:
                self._surface.blit(
                    glyph, (left + 3 + index * face.cell_w, top + 2)
                )

    def _blit_art(self, screen) -> None:
        """The pictures a screen asked for, put where it asked for them.

        The same ``Placed`` records the Qt build blits, read by a painter that has
        never heard of Qt: the screen says what and where, and this puts it down.
        Which is the whole reason the records exist -- one roster, two frames.
        """
        import pygame

        from .paint import load

        for piece in screen.art(self):
            art = load(piece.art)
            if art is None:
                continue
            width = max(
                1, round(art.get_width() * piece.height / max(1, art.get_height()))
            )
            if piece.smooth:
                scaled = pygame.transform.smoothscale(art, (width, piece.height))
            else:
                # A whole multiple, and nearest: the sprite keeps every pixel it
                # was painted with instead of averaging them into a blur.
                scaled = pygame.transform.scale(art, (width, piece.height))
            self._surface.blit(
                scaled,
                (
                    round(piece.centre - width / 2),
                    round(piece.bottom - piece.height),
                ),
            )

    def _put_slot(self, surface, slot) -> None:
        """One square of the pack: a frame, and what is in it.

        The squares are the run's, not an item sheet's: an unlocked slot is an
        empty box, a locked one is grey and crossed, and a draught is its own
        picture at a *whole* scale -- down by two or three for these bottles, so
        the sprite stays itself instead of being resampled into a smear.
        """
        import pygame

        from ..desktop.art import item_icon
        from ..desktop.theme import parse_style
        from ..world.items import ITEMS
        from .paint import load

        frame = pygame.Rect(slot.x, slot.y, slot.size, slot.size)
        pygame.draw.rect(surface, tuple(parse_style("grey23").fg), frame, 1)
        if slot.locked:
            grey = tuple(parse_style("grey19").fg)
            inset = max(6, slot.size // 5)
            pygame.draw.line(
                surface,
                grey,
                (frame.left + inset, frame.top + inset),
                (frame.right - inset, frame.bottom - inset),
            )
            pygame.draw.line(
                surface,
                grey,
                (frame.right - inset, frame.top + inset),
                (frame.left + inset, frame.bottom - inset),
            )
            return
        if slot.key is None:
            return
        cached = self._slot_faces.get((slot.key, slot.size))
        if cached is None:
            template = ITEMS.get(slot.key)
            icon = item_icon(template) if template is not None else None
            art = load(icon) if icon is not None else None
            if art is None:
                self._slot_faces[(slot.key, slot.size)] = None
                return
            room = max(1, slot.size - 8)
            largest = max(art.get_width(), art.get_height())
            factor = max(1, -(-largest // room))  # a whole step, up or down
            cached = pygame.transform.scale(
                art,
                (
                    max(1, art.get_width() // factor),
                    max(1, art.get_height() // factor),
                ),
            )
            self._slot_faces[(slot.key, slot.size)] = cached
        if cached is None:
            return
        surface.blit(
            cached,
            (
                frame.centerx - cached.get_width() // 2,
                frame.centery - cached.get_height() // 2,
            ),
        )

    def toggle_field_zoom(self) -> bool:
        """The overworld's field at twice the size, or its own, and remembered."""
        self.field_zoom = not self.field_zoom
        self._remember_glass()
        self._dirty = True
        return self.field_zoom

    def paint_field_zoom(self, surface, state) -> None:
        """The overworld's field, twice as large, over the cells the panels left.

        The map is drawn into a grid half as wide and half as tall -- the same
        drawing code, with a smaller camera -- painted as a picture, and doubled
        on the way to the frame. A character becomes four characters' worth of
        pixels, which is what a zoom *is*; the panels keep their size because
        they are read, not walked.
        """
        import pygame

        from ..desktop.render import FIELD_ZOOM, draw_field, regions

        map_x, map_y, map_w, map_h = regions(self.cols, self.rows)["map"]
        small = (max(1, map_w // FIELD_ZOOM), max(1, map_h // FIELD_ZOOM))
        if self._zoom_grid is None or (self._zoom_grid.cols, self._zoom_grid.rows) != small:
            from ..desktop.pattern import PatternBuffer

            self._zoom_grid = PatternBuffer(*small, self.font)
        grid = self._zoom_grid
        grid.clear()
        grid.pad = self.pad_active
        draw_field(grid, state, (0, 0, *small))
        field = paint(grid, self.font, BACKGROUND)
        surface.blit(
            pygame.transform.scale(
                field,
                (
                    small[0] * FIELD_ZOOM * self.font.cell_w,
                    small[1] * FIELD_ZOOM * self.font.cell_h,
                ),
            ),
            (map_x * self.font.cell_w, map_y * self.font.cell_h),
        )

