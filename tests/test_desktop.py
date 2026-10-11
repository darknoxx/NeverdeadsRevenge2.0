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


# -- the zoom -----------------------------------------------------------------
def test_the_zoom_targets_about_a_hundred_columns(qapp):
    from neverdeads_revenge.desktop.app import TARGET_COLS, DesktopApp

    app = DesktopApp(seed=1, no_sound=True)
    scale = app._scale_for(1920, 1080)

    # Two-pixel cells on a 1080p screen: a *zoom into* the field, not a fill of
    # it. The old fill gave one-pixel cells and a 190-column grid.
    assert scale == 2
    app.view.resize(1920, 1080)
    cols, rows = app._grid_size()
    assert cols <= TARGET_COLS + 20, f"{cols} columns is not a zoom"
    assert rows < 30, f"{rows} rows is not a zoom"


def test_the_zoom_is_a_whole_number_and_never_exceeds_what_fits(qapp):
    from neverdeads_revenge.desktop.app import DesktopApp

    app = DesktopApp(seed=1, no_sound=True)
    for width, height in ((1920, 1080), (2560, 1440), (3840, 2160), (1366, 768)):
        scale = app._scale_for(width, height)
        assert scale >= 1
        assert scale <= app._max_scale(width, height), (width, height)


def test_zooming_out_gives_back_more_of_the_map(qapp):
    from neverdeads_revenge.desktop.app import DesktopApp

    app = DesktopApp(seed=1, no_sound=True)
    app.view.resize(1920, 1080)
    zoomed = app._grid_size()
    app.zoom = 1
    wider = app._grid_size()

    assert wider[0] > zoomed[0] and wider[1] > zoomed[1]


def test_the_zoom_is_remembered(qapp, tmp_path, monkeypatch):
    from neverdeads_revenge.desktop import settings
    from neverdeads_revenge.desktop.app import DesktopApp

    monkeypatch.setenv("NEVERDEADS_REVENGE_HOME", str(tmp_path))
    app = DesktopApp(seed=1, no_sound=True)
    app.view.resize(1920, 1080)
    app._nudge_zoom(-1)

    written = settings.load_settings()
    assert written["zoom"] == 1
    assert written["scanlines"] is True


# -- the version, the corner, and the pixels ----------------------------------
def test_the_version_is_drawn_thick():
    from neverdeads_revenge.desktop.blocks import render_word

    small = render_word("2.0")
    big = render_word("2.0", scale=2)

    assert small, "the block font cannot spell its own version"
    assert len(big) == len(small) * 2
    assert all(len(b) == len(s) * 2 for s, b in zip(small, big))


def test_the_log_starts_away_from_the_vignette_corner(font, state):
    from neverdeads_revenge.desktop.buffer import PatternBuffer
    from neverdeads_revenge.desktop.render import BOTTOM, draw_game

    buffer = PatternBuffer(100, 34, font)
    draw_game(buffer, state)

    # The newest line sits somewhere in the bottom row; its first cells are left
    # blank so the CRT's corner does not eat the start of a combat line.
    found = False
    for row in range(buffer.rows - BOTTOM, buffer.rows):
        if buffer.cells[row][3].char != " ":
            found = True
            assert buffer.cells[row][0].char == " "
            assert buffer.cells[row][1].char == " "
            assert buffer.cells[row][2].char == " "
    assert found, "no log line was drawn"
    assert BOTTOM == 10


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
