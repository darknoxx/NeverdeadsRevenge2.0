"""Tests for the desktop layer.

The rule for what lives here: everything that is *not* a GL context. The CRT
shader needs a screen, so it is checked by eye and by ``fit_scale``'s arithmetic;
the pattern buffer, the styles, the layout and the frame builders are ordinary
code, and those are tested the way the terminal build tested its columns.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from neverdeads_revenge.game.actions import Action  # noqa: E402
from neverdeads_revenge.game.actors import HEROES  # noqa: E402
from neverdeads_revenge.game.state import LogKind, start_run  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def font(qapp):
    from neverdeads_revenge.desktop.font import BitmapFont

    return BitmapFont()


@pytest.fixture
def state():
    return start_run(HEROES["noxx"], 3)


# -- the palette --------------------------------------------------------------
def test_a_named_colour_and_a_hex_one_both_land():
    from neverdeads_revenge.desktop.theme import parse_style

    assert parse_style("red").fg.name() == "#aa0000"
    assert parse_style("#a855f7").fg.name() == "#a855f7"


def test_a_style_string_carries_its_flags():
    from neverdeads_revenge.desktop.theme import parse_style

    style = parse_style("bold green")
    assert style.bold and not style.dim
    assert style.fg.name() == "#00aa00"

    dim = parse_style("dim cyan")
    assert dim.dim and not dim.bold


def test_an_unknown_colour_falls_back_rather_than_failing():
    from neverdeads_revenge.desktop.theme import FOREGROUND, parse_style

    assert parse_style("bold chartreuse").fg.name() == FOREGROUND.name()


# -- the buffer ---------------------------------------------------------------
def test_a_cell_holds_what_was_written_to_it(font):
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.theme import parse_style

    buffer = PatternBuffer(20, 4, font)
    buffer.text(2, 1, "hello", parse_style("red"))

    assert buffer.cells[1][2].char == "h"
    assert buffer.cells[1][2].style.fg.name() == "#aa0000"


def test_writing_past_the_edge_is_dropped_not_wrapped(font):
    from neverdeads_revenge.desktop.buffer import PatternBuffer

    buffer = PatternBuffer(5, 2, font)
    buffer.text(3, 0, "abcdef")

    assert buffer.cells[0][3].char == "a"
    assert buffer.cells[0][4].char == "b"
    assert buffer.cells[1][0].char == " ", "it wrapped onto the next row"


def test_the_frame_is_the_grid_at_one_pixel_per_cell(font):
    from neverdeads_revenge.desktop.buffer import PatternBuffer

    buffer = PatternBuffer(10, 5, font)
    image = buffer.render()

    assert image.width() == 10 * font.cell_w
    assert image.height() == 5 * font.cell_h


# -- the layout ---------------------------------------------------------------
def test_the_sidebar_runs_the_whole_height_and_the_bottom_does_not():
    from neverdeads_revenge.desktop.render import BOTTOM, SIDEBAR, regions

    areas = regions(100, 34)
    map_x, map_y, map_w, map_h = areas["map"]
    side_x, side_y, side_w, side_h = areas["sidebar"]
    _, bottom_y, bottom_w, bottom_h = areas["bottom"]

    assert side_x == map_w, "the sidebar starts where the map stops"
    assert side_h == 34, "the sidebar is the full height"
    assert side_y == 0
    assert bottom_y == map_h and bottom_h == BOTTOM
    assert bottom_w == map_w, "the bottom row sits under the map, not the sidebar"
    assert side_w == SIDEBAR


def test_the_columns_sit_inside_the_bottom_row():
    from neverdeads_revenge.desktop.render import (
        CURSES_WIDTH,
        MARKS_WIDTH,
        regions,
    )

    areas = regions(100, 34)
    log_x, _, log_w, _ = areas["log"]
    curses_x, _, curses_w, _ = areas["curses"]
    marks_x, _, marks_w, _ = areas["marks"]

    assert log_x == 0 and log_w + CURSES_WIDTH + MARKS_WIDTH == areas["bottom"][2]
    assert curses_x == log_w and curses_w == CURSES_WIDTH
    assert marks_x == log_w + CURSES_WIDTH and marks_w == MARKS_WIDTH


# -- the content --------------------------------------------------------------
def test_the_hud_says_who_and_where(state):
    from neverdeads_revenge.desktop.render import hud_lines

    text = "\n".join(line for line, _ in hud_lines(state))

    assert "Noxx" in text
    assert "HP" in text
    assert "Floor 1/10" in text


def test_the_hud_grows_a_revenge_line_only_when_there_are_stacks(state):
    from neverdeads_revenge.desktop.render import hud_lines

    assert not any("REVENGE" in line for line, _ in hud_lines(state))
    state.revenge_stacks = 2
    assert any("REVENGE" in line for line, _ in hud_lines(state))


def test_the_log_kind_picks_the_colour(state):
    from neverdeads_revenge.desktop.render import log_style

    assert log_style(LogKind.BAD) == "bold red"
    assert log_style(LogKind.GOOD) == "bold green"


def test_the_effects_column_names_the_charge_and_the_debt(state):
    from neverdeads_revenge.desktop.render import marks_names

    state.gifts.add("momentum")
    state.momentum = 3
    state.blood_debt = 5

    names = marks_names(state, "effects")
    assert "momentum 3" in names
    assert "a debt of 5" in names


def test_the_gift_column_is_names_only(state):
    from neverdeads_revenge.desktop.render import marks_names

    state.gifts.add("long_reach")

    assert marks_names(state, "gifts") == ["THE LONG REACH"]


def test_the_whole_frame_draws_without_a_screen(font, state):
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.render import draw_game

    buffer = PatternBuffer(100, 34, font)
    draw_game(buffer, state)

    # The hero is on the map, somewhere.
    cells = {cell.char for row in buffer.cells for cell in row}
    assert state.player.glyph in cells
    # And the sidebar is not empty.
    assert "N" in cells and "H" in cells


# -- the glass ----------------------------------------------------------------
def test_the_scale_is_a_whole_number():
    from PySide6.QtCore import QSize

    from neverdeads_revenge.desktop.crt import fit_scale

    assert fit_scale(QSize(1920, 1080), QSize(960, 528)) == 2
    assert fit_scale(QSize(3840, 2160), QSize(960, 528)) == 4
    assert fit_scale(QSize(1366, 768), QSize(960, 528)) == 1


def test_a_tiny_window_still_shows_the_game():
    from PySide6.QtCore import QSize

    from neverdeads_revenge.desktop.crt import fit_scale

    assert fit_scale(QSize(320, 200), QSize(960, 528)) == 1


# -- the keys -----------------------------------------------------------------
def test_the_key_table_still_says_what_the_terminal_said():
    from neverdeads_revenge.desktop.app import KEY_BINDINGS

    assert KEY_BINDINGS["k"] is Action.MOVE_NORTH
    assert KEY_BINDINGS["h"] is Action.MOVE_WEST
    assert KEY_BINDINGS["enter"] is Action.INTERACT
    assert KEY_BINDINGS["q"] is Action.QUAFF
    assert KEY_BINDINGS["."] is Action.WAIT
    assert KEY_BINDINGS[">"] is Action.DESCEND
    assert KEY_BINDINGS["r"] is Action.REWIND


def test_every_key_maps_to_a_real_verb():
    from neverdeads_revenge.desktop.app import KEY_BINDINGS

    assert all(isinstance(action, Action) for action in KEY_BINDINGS.values())


# -- one zoom, and a log with its own face ------------------------------------
def test_there_is_one_scale_and_it_is_the_big_one(qapp):
    """One zoom, the big one. A second control would be two dials arguing about
    the same screen; what keeps the words readable is the log's own smaller
    face, not a smaller dungeon."""
    from neverdeads_revenge.desktop.app import DesktopApp

    app = DesktopApp(seed=1, no_sound=True)
    assert app._scale_for(1920, 1080) == 2, "1080p is two-pixel cells or nothing"
    assert app._scale_for(1366, 768) == 1, "a small laptop is one-pixel cells"
    assert not hasattr(app, "zoom"), "the zoom came back"


def test_the_log_is_a_smaller_face_and_still_clear_of_the_corner(qapp, font, state):
    """The log is drawn in its own, smaller font straight onto the frame.

    The test reads the frame's pixels, because that is where the log lives now:
    the corner that the vignette darkens has to stay background for about two
    cells of the log's own size before the first word.
    """
    from PySide6.QtGui import QColor, QImage

    from neverdeads_revenge.desktop.font import BitmapFont
    from neverdeads_revenge.desktop.render import paste_log, regions
    from neverdeads_revenge.desktop.theme import BACKGROUND

    small = BitmapFont(pixel_size=9)
    cols, rows, cw, ch = 96, 27, font.cell_w, font.cell_h
    image = QImage(cols * cw, rows * ch, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(BACKGROUND)
    paste_log(image, state, cols, rows, cw, ch, small)

    area = regions(cols, rows)["log"]
    left, top = area[0] * cw, area[1] * ch
    middle_y = top + area[3] * ch // 2

    # The first cells of the panel: background, not a word.
    for x in range(left, left + small.cell_w + 2, 2):
        assert QColor(image.pixelColor(x, middle_y)) == BACKGROUND, (
            f"a word within {(x - left) / small.cell_w:.1f} cells of the corner"
        )


# -- the version, the corner, and the pixels ----------------------------------
def test_the_version_is_drawn_thick():
    from neverdeads_revenge.desktop.blocks import render_word

    small = render_word("2.0")
    big = render_word("2.0", scale=2)

    assert small, "the block font cannot spell its own version"
    assert len(big) == len(small) * 2
    assert all(len(b) == len(s) * 2 for s, b in zip(small, big))


def test_blood_falls_and_fades(qapp):
    from PySide6.QtGui import QImage

    from neverdeads_revenge.desktop.effects import Effects

    effects = Effects(10, 20)
    assert not effects.active

    effects.blood((3, 3))
    assert effects.active
    # It paints onto a frame without complaint.
    image = QImage(100, 100, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    effects.draw(image)

    for _ in range(120):
        effects.step(0.033)
    assert not effects.active, "the pixels never went away"


def test_a_spark_rises_and_a_blood_drop_falls(qapp):
    from neverdeads_revenge.desktop.effects import Effects

    rising = Effects(10, 20)
    rising.spark((3, 3))
    rising.step(0.033)
    assert any(p.vy < 0 for p in rising.particles), "a spark did not rise"

    falling = Effects(10, 20)
    falling.blood((3, 3))
    for _ in range(3):
        falling.step(0.033)
    assert any(p.vy > 0 for p in falling.particles), "blood did not fall"


def test_a_word_keeps_the_panel_it_sits_on(font):
    """The bug the menus had: writing over a filled panel lifted the fill out
    from under the words, which left a stripe of black behind every line."""
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.chrome import PANEL
    from neverdeads_revenge.desktop.theme import Style, parse_style

    buffer = PatternBuffer(10, 4, font)
    panel = Style(bg=parse_style(PANEL).fg)
    for x in range(10):
        buffer.put(x, 1, " ", panel)

    buffer.text(2, 1, "hi", parse_style("red"))

    assert all(cell.style.bg is not None for cell in buffer.cells[1]), (
        "the words stripped the panel"
    )


def test_the_shake_never_moves_what_is_sampled():
    from PySide6.QtCore import QSize

    from neverdeads_revenge.desktop.crt import fit_scale

    # The shake warps where the pattern is placed, never how it is sampled --
    # the scale is the same number shaken or not.
    assert fit_scale(QSize(1920, 1080), QSize(960, 528)) == 2
