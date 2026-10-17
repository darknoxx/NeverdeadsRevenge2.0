"""The SDL front end: the same cells, the same face, a different blitter.

The question these hold down is the one the whole port turns on -- *does the game
really come apart from Qt?* -- and it comes in two halves. The first is
measurement: the same typeface at the same size has to give the same cell, or
every layout in the game (all of which counts in cells) lands somewhere else. The
second is that painting needs nothing from the game but cells.

The numbers are the contrast here rather than a comparison in-process, and the
reason is measured rather than assumed: **Qt's font database and pygame's font
module do not survive each other in one process.** Both orders were tried, half a
dozen times, and the process dies. That is why the two front ends are two front
ends -- and it is also, now, a rule the port is built to keep.

The rule is sharper than it sounds. It is *fonts* that do not cross, not the
toolkits: the arena's whole `draw` path -- plate, log, verbs, order strip -- was
measured and never asks Qt for a typeface, so the second front end hands it a grid
and gets a real fight back. What it must not do is use the Qt screen's *pixel*
staging, which measures a letter to size a shadow, and which is the one thing here
that has been given a cell port of its own.

And the last test in this file is the one the whole port is for: it *blocks* the
PySide6 import in a process of its own and plays a run -- title, roster, floor,
walk. Whatever is on that path has to be free of Qt, and the day something stops
being free of it, that test says so by name instead of by segfault. It grows as
the port does: the arena is not on it yet.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from neverdeads_revenge.desktop.pattern import PatternBuffer
from neverdeads_revenge.desktop.theme import BACKGROUND, Style, parse_style

FONT = "src/neverdeads_revenge/desktop/fonts/DejaVuSansMono.ttf"

ROOT = Path(__file__).resolve().parent.parent


def _sdl():
    """The SDL pieces, imported and initialised only when a test wants them."""
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    # The full init, because a Surface needs more of SDL than freetype alone
    # brings up. It is also the thing that fights with Qt's font *database* when
    # the two meet -- see the note at the top of this file. Nothing in the game
    # asks Qt for a font once this has run.
    pygame.init()
    from neverdeads_revenge.sdl_front.font import SdlFont
    from neverdeads_revenge.sdl_front.paint import paint

    return SdlFont(FONT), paint


def _play_out(app, limit: int = 400) -> int:
    """Let the fight play itself out, a frame at a time. Returns the frames used.

    A round on the second front end is *watched* now, not read: the arena takes
    the player's choice and queues the round at once -- which is what makes a
    fight decidable -- and the frames after it are the playback. Every test that
    used to read a result off the same keypress has to let those frames happen,
    which is exactly the difference this session made.
    """
    frames = 0
    while app.screens[-1].busy and frames < limit:
        app.tick(1 / 30.0)
        frames += 1
    return frames



def test_the_sdl_cell_is_the_cell_the_qt_build_has():
    """Ten by twenty, and the number is the whole port.

    The game lays every panel out in cells and never in pixels, which is what
    makes a second front end possible at all -- and it is only true while the
    face measures the same on both sides. Measured against the Qt build:
    ``QFontMetrics`` gives 10x20 at pixel size 16, and SDL_ttf gives an advance
    of 10.0 and a line height of 19 at 16 points and 72 dpi, which is 10x20 once
    the extra pixel that keeps a descender inside the cell is added.

    If this fails, the layout has moved and *every* screen needs to be looked at.
    """
    font, _ = _sdl()
    assert (font.cell_w, font.cell_h) == (10, 20), (
        "the SDL face does not measure what the Qt build measures"
    )
    assert font.ascent == 15, "the baseline moved, and everything sits on it"


def test_a_grid_of_cells_paints_where_the_cells_are():
    """Painting needs a buffer and a font, and nothing else from the game.

    Checked as *facts about the picture* rather than against the Qt one: pygame
    and Qt cannot both be initialised in one process, and a test that needs them
    to be is a test that cannot run. The colour of a pixel where a panel was
    drawn and the colour of one where a letter was is what the painter promised,
    and that is what is asked.
    """
    font, paint = _sdl()
    pygame = __import__("pygame")

    grid = PatternBuffer(8, 3)
    grid.put(0, 0, "#", parse_style("red"))
    panel = Style(fg=parse_style("green").fg, bg=parse_style("#123456").fg)
    grid.fill_row(1, " ", panel)
    grid.text(0, 2, "ab", parse_style("bold white"))

    surface = paint(grid, font)

    assert surface.get_size() == (80, 60), "the picture is not cells times pixels"

    # The wall is *in* its cell and not on its corner: a glyph is drawn inside
    # the ten by twenty square, and a test that read the square's own top-left
    # pixel would be reading the dungeon behind it.
    wall = [
        surface.get_at((x, y))
        for y in range(0, font.cell_h)
        for x in range(0, font.cell_w)
    ]
    assert any((one.r, one.g, one.b) == (170, 0, 0) for one in wall), (
        "the wall was not drawn in its own colour"
    )

    # A panel is opaque, and it is opaque *behind* the letters on it: that is the
    # rule the whole menu system is built on, and it is the painter's to keep.
    inside = surface.get_at((40, 25))
    assert (inside.r, inside.g, inside.b) == (0x12, 0x34, 0x56), (
        f"the panel did not fill its row: {inside}"
    )

    # And a space writes nothing, which is what two thousand of them a frame
    # depend on.
    empty = surface.get_at((70, 25))
    assert (empty.r, empty.g, empty.b) == (0x12, 0x34, 0x56), (
        "an empty cell wrote over the panel it was standing on"
    )
    # And the row of text drew its own letters, in the colour they were given.
    text_row = [
        surface.get_at((x, y))
        for y in range(40, 60)
        for x in range(0, 20)
    ]
    white = parse_style("bold white").fg
    assert any((one.r, one.g, one.b) == tuple(white) for one in text_row), (
        f"the bold white letters were not drawn: {white}"
    )


def test_the_same_screen_renders_without_qt_in_the_room():
    """The title screen, drawn with a stub app and nothing else.

    The screen reads exactly two things off the application -- whether there is a
    run to continue, and the best score -- and everything else it wants is the
    buffer in its hand. That is the measurement worth having: a screen whose
    whole interface is a buffer and a key name is a screen that can be shown by
    anything, which is what the probe in ``tools/sdl_probe.py`` writes out.
    """
    from neverdeads_revenge.desktop.screens.title import TitleScreen

    font, paint = _sdl()

    class Stub:
        class Progress:
            best_score = 1234

        progress = Progress()

        def has_saved_run(self) -> bool:
            return True

    grid = PatternBuffer(96, 27)
    TitleScreen().draw(grid, Stub())
    surface = paint(grid, font)

    inked = sum(
        1
        for y in range(0, surface.get_height(), 4)
        for x in range(0, surface.get_width(), 4)
        if surface.get_at((x, y))[:3] != tuple(BACKGROUND)
    )
    assert inked > 200, f"the title screen came out nearly empty: {inked} cells of ink"


def test_a_run_starts_and_the_hero_walks_with_no_qt_in_the_room():
    """The whole loop of the game, on SDL: choose a hero, begin, walk.

    This is the probe's real question asked the blunt way -- does a *run* work on
    a front end that is not Qt? -- and it is answered by driving the same three
    screens the Qt build drives, with the same key names, against the same rules.
    Nothing here is a mock-up of the game: `start_run` makes the floor, the
    screens read it, and the painter draws what they wrote.
    """
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)

    assert type(app.screens[-1]).__name__ == "TitleScreen"

    app.key("enter")  # NEW RUN
    assert type(app.screens[-1]).__name__ == "HeroSelectScreen", (
        "the roster did not open"
    )

    app.key("enter")  # pick the first hero
    app.key("escape")  # the prologue, skipped
    assert type(app.screens[-1]).__name__ == "GameScreen", "the floor did not open"
    assert app.run is not None, "there is no run behind the screen"

    # Walk. A room has a floor in at least one direction, and a hero who cannot
    # take a step is a front end that is not passing anything on.
    here = app.run.player.position
    for direction in ("right", "down", "left", "up"):
        app.key(direction)
        if app.run.player.position != here:
            break
    assert app.run.player.position != here, "the hero could not take a step"
    assert app.run.player.steps == 1, "the step was not counted"
    # And *silence* is the right answer here, in both front ends: a step logs
    # nothing, and what the sound layer plays is the loudest thing that happened.
    # Fights, stairs and levels make a noise; walking does not.
    assert app.played == []

    # And the picture is the grid the game drew, at the size its panels need.
    assert app.grid.cols >= 76 and app.grid.rows >= 24
    assert app._surface is not None and app._surface.get_size() == (
        app.grid.cols * app.font.cell_w,
        app.grid.rows * app.font.cell_h,
    )


def test_a_monster_is_walked_into_fought_and_the_floor_comes_back():
    """The whole loop of a fight, on the second front end.

    The floor hands the fight over, the arena opens with the *real* rules behind
    it, the player swings, the monster dies, and the dungeon is still there
    underneath -- which is the promise the arena was built on and the thing a
    port is most likely to lose. Nothing here is a mock-up: the same
    ``open_fight`` builds the room and the same ``resolve_player_attack`` lands
    the blow.

    It is also the test that says the font rule holds: the arena reuses the Qt
    screen's panels, which touch no typeface, and stages the figures in cells
    itself. If either half starts asking Qt for a font, this process dies rather
    than fails, which is the loudest failure in the file.
    """
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy
    from neverdeads_revenge.sdl_front.app import SdlApp
    from neverdeads_revenge.sdl_front.arena import SdlArena
    from neverdeads_revenge.world.tiles import Tile

    app = SdlApp(seed=3)
    app.key("enter")  # NEW RUN
    app.key("enter")  # the first hero
    app.key("escape")  # the prologue, skipped

    state = app.run
    here = state.player.position
    beside = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(beside, Tile.FLOOR)
    ghoul = make_enemy(ENEMIES["ghoul"], beside)
    ghoul.stats.hp = 1  # one blow and it is over
    state.enemies.append(ghoul)
    state.turn_queue.add(ghoul)
    state.refresh_vision()

    app.key("right")  # walk into it
    _turn_it_over(app)

    assert isinstance(app.screens[-1], SdlArena), "the fight did not open"
    assert app.screens[-1].battle.enemies, "the arena is empty"

    # The arena is a two-step menu, in both front ends: a letter *picks* the
    # verb and enter swings it. That is the game's own flow and not a detail of
    # the port, which is why the test walks through it rather than calling the
    # screen's chooser directly.
    app.key("a")      # pick ATTACK
    app.key("enter")  # and swing it

    assert not ghoul.alive, "the blow did not land"
    assert state.kills == 1, "the kill did not count for the run"

    # The rules decided at the *swing* -- that is what makes a fight decidable --
    # and the room has not caught up yet: the round is queued and being played,
    # one beat at a time, exactly as it is under Qt.
    arena = app.screens[-1]
    assert arena.busy, "the round was over before it was played"
    arena = app.screens[-1]
    frames = _play_out(app)
    assert frames > 4, f"the round was not played, it was snapped ({frames} frames)"
    assert not arena.busy, "the fight is still talking after playing out"

    # And the fight says how it ended. The panel is the arena's own -- the same
    # box, rule and hint the Qt build blits -- and it is painted *over* the stage
    # now that the stage is a picture, so the check is the panel and its place
    # rather than the grid, which the floor is painted over.
    panel, vx, vy = arena.arena._verdict_panel(
        app.grid.cols, app.grid.rows, app.font
    )
    said = "".join(cell.char for row in panel.cells for cell in row)
    assert "VICTORY" in said, "the fight ended without saying so"
    assert (vx + panel.cols) * app.font.cell_w <= app._surface.get_width(), (
        "the verdict panel lands outside the picture"
    )
    assert (vy + panel.rows) * app.font.cell_h <= app._surface.get_height(), (
        "the verdict panel lands outside the picture"
    )

    app.key("enter")  # leave the verdict

    assert type(app.screens[-1]).__name__ == "GameScreen", (
        "the floor did not come back"
    )
    # And the floor stopped him *in front of* the monster rather than walking him
    # onto it: the fight took the place of the step, which is the same trade the
    # rules make in both front ends -- and it is why a room can be cleared without
    # ever standing where a monster stood.
    assert state.player.position == here, "the hero walked onto the corpse's square"
    assert ghoul not in state.living_enemies, "the dead thing is still on the floor"


def test_the_arena_writes_its_panels_and_leaves_the_figures_to_the_art():
    """Which pass owns what: the panels are cells, a painted monster is not a letter.

    The whole point of the panel split is that this is *readable* without Qt: the
    plate with the purse, the four verbs, the order strip, the log. The fight
    itself moved on: a figure the sheets have a picture for is left to the painter,
    because a letter written here would stand *through* the sprite pasted over it.
    """
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy
    from neverdeads_revenge.sdl_front.app import SdlApp
    from neverdeads_revenge.sdl_front.arena import SdlArena
    from neverdeads_revenge.world.tiles import Tile

    app = SdlApp(seed=3)
    app.key("enter")  # NEW RUN
    app.key("enter")  # the first hero
    app.key("escape")  # the prologue, skipped

    state = app.run
    here = state.player.position
    beside = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(beside, Tile.FLOOR)
    vipers = make_enemy(ENEMIES["viper"], beside)
    state.enemies.append(vipers)
    state.turn_queue.add(vipers)
    state.refresh_vision()

    app.key("right")  # walk into it
    _turn_it_over(app)

    arena = app.screens[-1]
    assert isinstance(arena, SdlArena), "the fight did not open"

    picture = "\n".join("".join(cell.char for cell in row) for row in app.grid.cells)
    # The verbs, which is the panel the player actually has to read, and the plate,
    # which is where the purse and the kill count live.
    assert "ATTACK" in picture, "the verb panel is missing"
    assert "NOXX" in picture, "the plate is missing"

    # A fast hero acts first, so the room opens in silence and the log is empty
    # until something happens. That is the rules' own shape and not the port's.
    assert arena.arena.lines == [], "the log spoke before anything did"

    # The monster has a picture, so its cell holds no letter: that is the rule the
    # second pass depends on, checked where the staging actually stands it.
    figure = next(
        one
        for one in arena.arena._figures(app.grid.cols, app.grid.rows, app.font)
        if one.actor is vipers
    )
    assert figure.art is not None, "the sheets have no picture for the viper"
    cell = app.grid.cells[figure.row][figure.cx // app.font.cell_w]
    assert cell.char != vipers.glyph, "a letter is standing under the sprite"

    # Then the blow, and the fight's voice arrives with it -- a frame or two into
    # the playback and not on the keypress, because the animation comes first and
    # every display and calculation after it. That ordering is the game's own rule
    # and it is why this test has to let the round play before it reads anything.
    app.key("a")
    app.key("enter")
    _play_out(app)
    log = [line.text for line in arena.arena.lines]
    assert any(vipers.name in line for line in log), f"the log is silent: {log}"
    picture = "\n".join("".join(cell.char for cell in row) for row in app.grid.cells)
    assert vipers.name in picture, "the log panel did not draw what the fight said"


def test_the_arena_paints_the_flagstones_and_the_monsters_on_them():
    """The second pass, asked of the pixels: a room recedes, and a monster stands in it.

    Two facts that only a painted room can have. The floor is laid in flagstones
    and darkened a row at a time -- heavier the further back -- which is the whole
    of how distance is drawn here, and is why the far row must measure darker than
    the near one. And the sprite is a *picture*: the colours the PNG carries have
    to be on the frame where the staging put the figure, or the monster is a name
    in a log and nothing else.
    """
    font, _ = _sdl()
    from neverdeads_revenge.desktop.screens.battle import THICKNESS
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy
    from neverdeads_revenge.sdl_front.app import SdlApp
    from neverdeads_revenge.sdl_front.paint import load
    from neverdeads_revenge.world.tiles import Tile

    app = SdlApp(seed=3)
    app.key("enter")  # NEW RUN
    app.key("enter")  # the first hero
    app.key("escape")  # the prologue, skipped

    state = app.run
    here = state.player.position
    beside = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(beside, Tile.FLOOR)
    ghoul = make_enemy(ENEMIES["ghoul"], beside)
    state.enemies.append(ghoul)
    state.turn_queue.add(ghoul)
    state.refresh_vision()

    app.key("right")  # walk into it
    _turn_it_over(app)

    arena = app.screens[-1]
    surface = app._surface
    assert surface is not None, "nothing was painted at all"

    cols, rows = arena.arena._dims(app)
    field = arena.arena._field(cols, rows, app.font.cell_w, app.font.cell_h)
    top, cell_h = int(field["top"]), int(field["cell_h"])

    def brightness(y: int) -> float:
        row = [surface.get_at((x, y)) for x in range(surface.get_width())]
        return sum(one.r + one.g + one.b for one in row) / (len(row) * 3)

    # Sampled through the *middle* of a row of stones and not on its first pixel:
    # a flagstone's edge is transparent and lets the grid underneath show, which is
    # the whole point of the art being laid over the alphabet and not instead of it.
    far, near = (
        brightness(top + cell_h // 2),
        brightness(top + (int(field["cells_h"]) - 1) * cell_h + cell_h // 2),
    )
    assert far < near, f"the room does not recede: far {far:.1f} vs near {near:.1f}"

    # And the monster itself: the painted figure lands where the staging puts it.
    # Measured by *withdrawing* the pass and looking at what changes -- a sprite is
    # blended and not stamped (its edges are soft), so matching its exact colours on
    # a dark floor would be a test of the blender, not of the port.
    figure = next(
        one
        for one in arena.arena._figures(cols, rows, app.font)
        if one.actor is ghoul
    )
    art = load(figure.art)
    assert art is not None, "the sheets have no picture for the ghoul"
    baseline = figure.row * font.cell_h - THICKNESS
    box = (
        max(0, figure.cx - art.get_width() // 2),
        max(0, baseline - art.get_height()),
        min(surface.get_width(), figure.cx + art.get_width() // 2),
        min(surface.get_height(), baseline),
    )
    painted = surface.copy()
    arena._stage.figure = lambda *args, **rest: None  # no picture, no figure
    app.redraw()
    bare = app._surface
    changed = sum(
        1
        for x in range(box[0], box[2])
        for y in range(box[1], box[3])
        if painted.get_at((x, y)) != bare.get_at((x, y))
    )
    assert changed > 200, f"the monster left {changed} pixels on the frame"


def test_a_run_starts_in_a_process_where_qt_does_not_exist():
    """Qt is not installed -- which is exactly what Android looks like.

    This is the port's promise asked the blunt way: block the import entirely, in
    a process of its own, and *play* the game. Nothing is mocked. The same title,
    the same roster, the same floor, the same rules -- and if anything on that
    path reaches for Qt, the process dies with an ImportError that says where,
    instead of the segfault two toolkits in one process would give.

    It covers a whole run of the *room*: the title, the roster, the floor, a walk
    -- and now a fight, which was the half of the game that needed Qt for its
    panels a session ago. What is still painted in Qt is the *turning* between a
    floor and a fight, and that is the next one to come across.

    The imports inside the child are deliberate and are the whole point: a test
    that imported the app *here* would have Qt in the process already.
    """
    code = textwrap.dedent(
        """
        import sys


        class NoQt:
            \"\"\"Nothing named PySide6 may be imported. Not even to ask a path.\"\"\"

            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] == "PySide6":
                    raise ImportError(f"no Qt here: {name}")


        sys.meta_path.insert(0, NoQt())

        from neverdeads_revenge.sdl_front.app import SdlApp

        app = SdlApp(seed=3)
        assert type(app.screens[-1]).__name__ == "TitleScreen", "the title did not open"
        app.key("enter")
        assert type(app.screens[-1]).__name__ == "HeroSelectScreen", "no roster"
        app.key("enter")
        assert type(app.screens[-1]).__name__ == "PrologueScreen", "no premise"
        app.key("escape")  # the premise, skipped
        assert type(app.screens[-1]).__name__ == "GameScreen", "no floor"

        here = app.run.player.position
        for direction in ("right", "down", "left", "up"):
            app.key(direction)
            if app.run.player.position != here:
                break
        assert app.run.player.position != here, "the hero could not take a step"
        assert app._surface is not None, "the floor was never painted"

        # And into a fight: the arena draws its plate, its log, its verbs and its
        # monsters -- the same panels the Qt build draws -- with no Qt in the
        # process at all. A kill, and the floor underneath is still there.
        from neverdeads_revenge.game.actors import ENEMIES, make_enemy
        from neverdeads_revenge.world.tiles import Tile

        state = app.run
        beside = (state.player.position[0] + 1, state.player.position[1])
        state.dungeon_map.set_tile(beside, Tile.FLOOR)
        ghoul = make_enemy(ENEMIES["ghoul"], beside)
        ghoul.stats.hp = 1  # one blow and it is over
        state.enemies.append(ghoul)
        state.turn_queue.add(ghoul)
        state.refresh_vision()

        app.key("right")
        # The floor turns into the fight first -- and it does that without Qt
        # too, which is part of the point of this walk: the turning is one of the
        # game's own screens and has no toolkit in it either.
        frames = 0
        while type(app.screens[-1]).__name__ != "SdlArena" and frames < 400:
            app.tick(1 / 30.0)
            frames += 1
        assert type(app.screens[-1]).__name__ == "SdlArena", "the turning never finished"
        app.key("a")      # pick ATTACK
        app.key("enter")  # and swing it
        assert not ghoul.alive, "the blow did not land"
        assert state.kills == 1, "the kill did not count"
        frames = 0
        while app.screens[-1].busy and frames < 400:
            app.tick(1 / 30.0)
            frames += 1
        assert frames > 4, "the fight did not play out"
        app.key("enter")  # leave the verdict
        assert type(app.screens[-1]).__name__ == "GameScreen", "the floor did not return"
        print("NOQT-OK")
        """
    )
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "NOQT-OK" in result.stdout, result.stdout


def test_the_roster_paints_the_hero_on_the_second_front_end():
    """The same hero on the same card, put there by a painter that has no Qt in it.

    A screen hands over ``Placed`` records -- what, and where -- and *whichever*
    application is drawing puts them down. This is the second one doing it: the
    front view, at the roster's own common height, in the band the grid left for
    it. Asked as the number of colours in that band, which is exactly the fact
    the Qt build's own roster test asks of its frame: a painted figure is a
    hundred colours wide and a block letter is one.
    """
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)
    app.key("enter")  # NEW RUN, onto the roster

    screen = app.screens[-1]
    assert type(screen).__name__ == "HeroSelectScreen", "the roster did not open"
    hero = screen.current
    assert hero is not None

    placed = screen.art(app)
    assert placed, "the roster asked for no picture at all"
    assert placed[0].art == f"sprites/portraits/{hero.name}.png", placed[0].art
    assert placed[0].height > 0, "the picture was asked for at no height"

    def band() -> set:
        return {
            app._surface.get_at((x, y))[:3]
            for x in range(cx - 40, cx + 40)
            for y in range(baseline - 90, baseline)
        }

    cx, baseline = screen._where
    painted = band()
    assert len(painted) > 20, (
        f"the band is {len(painted)} colours, so the hero is still a letter"
    )

    # And with nothing to place -- a hero the sheets have no picture of -- the
    # card falls back to the alphabet, which the grid has already drawn. Withdrawn
    # at the *sheets*, not at the screen: `draw` decides the place afresh every
    # frame, so a screen told to forget it would simply decide again.
    from neverdeads_revenge.desktop.screens import hero_select

    real = hero_select.exists
    hero_select.exists = lambda name: False  # noqa: E731 - one line, one meaning
    try:
        app.redraw()
        assert screen.art(app) == [], "a picture was asked for with nowhere to put it"
        lettered = band()
    finally:
        hero_select.exists = real
    assert len(lettered) < len(painted) / 4, "the fallback is not a letter"


def test_the_animation_comes_first_and_the_displays_after_it():
    """The game's own rule, on the second front end: the blow, *then* the reading.

    On the frame the player swings, the fight is already *decided* -- the rules
    resolve at the swing, which is what makes a fight decidable and not a lottery
    -- and nothing of it is *shown*: the log is still empty, the bar still says
    what the monster had, and the number over its head is written down but not
    yet readable. A few frames later all three arrive together, at the impact.

    That gap is the whole of what a playback is for, and it is the one thing a
    front end that resolves a round at once cannot have.
    """
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy
    from neverdeads_revenge.sdl_front.app import SdlApp
    from neverdeads_revenge.world.tiles import Tile

    app = SdlApp(seed=3)
    app.key("enter")  # NEW RUN
    app.key("enter")  # the first hero
    app.key("escape")  # the prologue, skipped

    state = app.run
    here = state.player.position
    beside = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(beside, Tile.FLOOR)
    ghoul = make_enemy(ENEMIES["ghoul"], beside)
    ghoul.stats.hp = 40  # it will live through this
    state.enemies.append(ghoul)
    state.turn_queue.add(ghoul)
    state.refresh_vision()

    app.key("right")
    _turn_it_over(app)
    arena = app.screens[-1]
    assert not arena.busy, "the fight opened mid-round"

    app.key("a")      # pick ATTACK
    app.key("enter")  # and swing it

    # The rules have taken the damage already -- that is what deciding at the
    # swing means -- and the room has shown none of it.
    assert ghoul.stats.hp < 40, "the blow was never decided"
    assert arena.arena.lines == [], "the log spoke before the sword landed"
    assert arena.arena._shown[id(ghoul)] == 40, "the bar dropped before the blow"

    # Then the strike begins, and the number is *written down* -- and not yet
    # readable: a number over a monster before the blow reaches it is the fight
    # telling the player the future.
    for _ in range(30):
        app.tick(1 / 30.0)
        if arena.arena._popups:
            break
    assert arena.arena._popups, "no number was ever written down"
    assert arena.arena._popups[0].age < 0, "the number was readable before the blow"
    assert arena.arena.lines == [], "the log spoke while the sword was in the air"

    # And at the impact the number becomes readable, the log says what happened,
    # and the bar drops to where the rules left the monster: three things, one
    # moment, in this order and no other.
    _play_out(app)
    log = [line.text for line in arena.arena.lines]
    assert any("ghoul" in line for line in log), f"the log never spoke: {log}"
    assert arena.arena._shown[id(ghoul)] == ghoul.stats.hp, (
        "the bar did not catch up with the rules"
    )


def test_a_damage_number_is_painted_over_the_monster_that_took_it():
    """A number over a head, in the second front end's own pixels.

    The Qt build draws it in a big face with a dark copy under it; this one draws
    it in the same big face, one font size up from the grid, over the figure's own
    line. What is asserted is the fact that a test can see: ink, where the number
    is, on the frame that the fight said it was readable on.
    """
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy
    from neverdeads_revenge.sdl_front.app import SdlApp
    from neverdeads_revenge.world.tiles import Tile

    app = SdlApp(seed=3)
    app.key("enter")
    app.key("enter")
    app.key("escape")  # the prologue, skipped

    state = app.run
    beside = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(beside, Tile.FLOOR)
    ghoul = make_enemy(ENEMIES["ghoul"], beside)
    ghoul.stats.hp = 40
    state.enemies.append(ghoul)
    state.turn_queue.add(ghoul)
    state.refresh_vision()

    app.key("right")
    _turn_it_over(app)
    arena = app.screens[-1]
    app.key("a")
    app.key("enter")

    # One frame past the impact: the number is readable, and it is on the frame.
    for _ in range(60):
        app.tick(1 / 30.0)
        landed = [one for one in arena.arena._popups if one.age >= 0]
        if landed:
            break
    assert landed, "the number never became readable"
    number = min(landed, key=lambda one: one.age)
    box = (
        round(number.x - 40),
        number.y - app.font.cell_h * 2 - 30,
        round(number.x + 40),
        number.y,
    )
    surface = app._surface
    seen = {
        surface.get_at((x, y))[:3]
        for x in range(max(0, box[0]), min(surface.get_width(), box[2]))
        for y in range(max(0, box[1]), min(surface.get_height(), box[3]))
    }
    assert len(seen) > 3, f"the number left no ink over the monster: {len(seen)} colours"


def test_the_small_face_is_the_same_size_on_both_sides():
    """Seven by fourteen, and it is the number the whole lower layout turns on.

    The sidebar's lower rows and the log are drawn one size down, and the *layout*
    of both is computed from that cell -- which is why the two front ends measure
    it the same way the grid measures its own. Measured against the Qt build in a
    process of its own, for the reason at the top of this file: ``BitmapFont(11)``
    gives 7x14 there, and this has to agree or the sidebar drifts a row.
    """
    from neverdeads_revenge.sdl_front.font import SdlFont

    _sdl()  # a pygame up, which is all this needs of it
    small = SdlFont(FONT, 11)
    assert (small.cell_w, small.cell_h) == (7, 14), (
        "the small face does not measure what the Qt build measures"
    )


def test_the_floor_shows_the_log_and_the_sidebar_on_the_second_front_end():
    """The two smaller-face passes, asked of the frame.

    The combat log is how the game talks to the player -- what was found, what
    bit them, what the floor is -- and the sidebar's lower rows are the rest of
    the run at a glance. Both are drawn straight onto the frame after the grid on
    the Qt side, and this is the same pass with a pygame painter, reading the same
    rows from the same spec. What is asserted is that there is ink where the spec
    says: a panel of background with words in it.
    """
    from neverdeads_revenge.desktop.render import log_text, sidebar_text
    from neverdeads_revenge.desktop.theme import BACKGROUND
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)
    app.key("enter")  # NEW RUN
    app.key("enter")  # the first hero
    app.key("escape")  # the prologue, skipped

    surface = app._surface
    face = app.font_small
    assert app.run.log, "the run said nothing to begin with"

    rect, rows = log_text(
        app.run,
        app.grid.cols,
        app.grid.rows,
        app.font.cell_w,
        app.font.cell_h,
        face.cell_w,
        face.cell_h,
    )
    assert rows, "the log's spec is empty"
    ink = sum(
        1
        for x in range(rect[0], min(surface.get_width(), rect[0] + rect[2]))
        for y in range(rect[1], min(surface.get_height(), rect[1] + rect[3]))
        if surface.get_at((x, y))[:3] != tuple(BACKGROUND)
    )
    assert ink > 100, f"the log panel is blank: {ink} pixels of ink"

    out, _rule = sidebar_text(
        app.run,
        app.grid.cols,
        app.grid.rows,
        app.font.cell_w,
        app.font.cell_h,
        face.cell_w,
        face.cell_h,
    )
    below = min(one.y for one in out)
    ink = sum(
        1
        for x in range(0, surface.get_width())
        for y in range(below, surface.get_height())
        if surface.get_at((x, y))[:3] != tuple(BACKGROUND)
    )
    assert ink > 100, f"the sidebar's lower rows are blank: {ink} pixels of ink"



def _turn_it_over(app, limit: int = 400) -> None:
    """Play the turning out, the way a player does: by waiting.

    Walking into a monster does not open the arena any more, on either front end
    -- the floor *turns* into the fight, and that moment takes about a second. So
    a test that used to walk in and look straight at the arena has to let it
    happen, which is what the app's own clock is for.
    """
    frames = 0
    while type(app.screens[-1]).__name__ != "SdlArena" and frames < limit:
        app.tick(1 / 30.0)
        frames += 1
    assert type(app.screens[-1]).__name__ == "SdlArena", "the turning never finished"
    assert frames > 2, "the turning was skipped rather than played"



def _fight_with_a_monster(seed: int = 3):
    """An app, a floor, and one monster walked into: the fixture most want."""
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy
    from neverdeads_revenge.sdl_front.app import SdlApp
    from neverdeads_revenge.world.tiles import Tile

    app = SdlApp(seed=seed)
    app.key("enter")
    app.key("enter")
    app.key("escape")  # the prologue, skipped
    state = app.run
    beside = (state.player.position[0] + 1, state.player.position[1])
    state.dungeon_map.set_tile(beside, Tile.FLOOR)
    monster = make_enemy(ENEMIES["ghoul"], beside)
    monster.stats.hp = 40
    state.enemies.append(monster)
    state.turn_queue.add(monster)
    state.refresh_vision()
    app.key("right")
    _turn_it_over(app)
    return app, monster


def _changed(before, after, box) -> int:
    """How many pixels in ``box`` the second frame moved."""
    return sum(
        1
        for x in range(box[0], box[2])
        for y in range(box[1], box[3])
        if before.get_at((x, y)) != after.get_at((x, y))
    )


def test_aiming_puts_a_marker_over_the_monster_that_is_being_aimed_at():
    """The arrow, asked of the frame: without it there is no question to read.

    A trick that needs a target asks one, and the arena answers by standing a
    blade over the monster the choice is on. Measured by *withdrawing* the aim
    rather than by hunting for a colour: the monster's own sprite is green too,
    so the fact worth holding is that aiming changes the frame above it and
    nothing else does.
    """
    app, monster = _fight_with_a_monster()
    arena = app.screens[-1]
    arena.arena.aiming = False
    app.redraw()
    plain = app._surface.copy()

    arena.arena.aiming = True
    arena.arena.target = 0
    app.redraw()
    aimed = app._surface

    figure = next(
        one
        for one in arena.arena._figures(app.grid.cols, app.grid.rows, app.font)
        if one.actor is monster
    )
    top = figure.row * app.font.cell_h - 90
    box = (
        max(0, figure.cx - 40),
        max(0, top),
        min(app._surface.get_width(), figure.cx + 40),
        figure.row * app.font.cell_h,
    )
    assert _changed(plain, aimed, box) > 10, "aiming left no mark on the monster"
    # And it is *above* the monster and not over its body: the same box one line
    # down is where the sprite is, and a marker there would be a marker nobody
    # could read a monster through.
    low = (box[0], figure.row * app.font.cell_h - 30, box[2], figure.row * app.font.cell_h)
    assert _changed(plain, aimed, low) == 0, "the marker was drawn over the monster"


def test_a_monsters_wounds_are_worn_at_the_end_of_its_bar():
    """The symbols and the stack number, asked of the frame.

    The bar says how much of a monster is left; the row beside it says what is
    taking it, which a light around the figure never could. And the number only
    appears once a wound is *stacked*: a wound that says "1" on every monster is
    a number nobody reads.
    """
    app, monster = _fight_with_a_monster()
    arena = app.screens[-1]
    arena.arena._wearing[id(monster)] = ()
    arena.arena._depths[id(monster)] = {}
    app.redraw()
    clean = app._surface.copy()

    figure = next(
        one
        for one in arena.arena._figures(app.grid.cols, app.grid.rows, app.font)
        if one.actor is monster
    )
    cells = max(8, min(14, figure.cells * 2))
    right = round(figure.cx + cells * app.font.cell_w / 2)
    box = (
        right,
        figure.row * app.font.cell_h,
        min(app._surface.get_width(), right + 60),
        figure.row * app.font.cell_h + 40,
    )

    arena.arena._wearing[id(monster)] = ("bleed",)
    arena.arena._depths[id(monster)] = {"bleed": 1}
    app.redraw()
    worn = _changed(clean, app._surface, box)
    assert worn > 20, f"the wound was not worn: {worn} pixels"

    arena.arena._depths[id(monster)] = {"bleed": 3}
    app.redraw()
    stacked = _changed(clean, app._surface, box)
    assert stacked > worn, (
        f"the stack number did not appear: {worn} pixels worn, {stacked} stacked"
    )


def test_the_heros_own_wounds_are_worn_on_his_plate():
    """The hero's row, in the one place that owns his own numbers.

    A wound is what is eating him, and the plate is where his own facts live --
    health, kills, the purse. It is drawn in the same symbols and by the same
    helper as a monster's row, which is the promise both rows keep: one symbol,
    learned once.
    """
    app, _monster = _fight_with_a_monster()
    arena = app.screens[-1]
    hero = arena.battle.hero
    arena.arena._wearing[id(hero)] = ()
    arena.arena._depths[id(hero)] = {}
    app.redraw()
    clean = app._surface.copy()

    arena.arena._wearing[id(hero)] = ("burn",)
    arena.arena._depths[id(hero)] = {"burn": 2}
    app.redraw()

    x, y, width, height = arena.arena._areas(app.grid.cols, app.grid.rows)["plate"]
    box = (
        x * app.font.cell_w,
        y * app.font.cell_h,
        (x + width) * app.font.cell_w,
        (y + height) * app.font.cell_h,
    )
    assert _changed(clean, app._surface, box) > 20, "the hero's wounds were not shown"


def test_the_command_line_can_start_the_second_front_end():
    """The door: ``ndr2 --sdl``, answered before anything touches Qt.

    A front end that runs without Qt is only a claim until something starts it
    on a machine that has none. So: block the import, in a process of its own,
    and call the command line -- and let the window open with a stand-in for the
    loop, because the loop is the part that never returns. What is checked is
    what matters: the flag was answered *before* the Qt import below it, the app
    was built, and ``--battle-scene`` put the arena on top of the stack.
    """
    code = textwrap.dedent(
        """
        import sys


        class NoQt:
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] == "PySide6":
                    raise ImportError(f"no Qt here: {name}")


        sys.meta_path.insert(0, NoQt())

        from neverdeads_revenge.sdl_front import app as sdl_app

        opened = {}


        def look_instead_of_loop(self, **rest):
            opened["top"] = type(self.screens[-1]).__name__
            opened["fighting"] = getattr(self.screens[-1], "battle", None) is not None
            opened["fps"] = self.show_fps


        sdl_app.SdlApp.open_window = look_instead_of_loop

        from neverdeads_revenge.__main__ import main

        code_back = main(["--sdl", "--battle-scene", "--seed", "3", "--fps"])
        assert code_back == 0, "the command line did not finish cleanly"
        assert opened["top"] == "SdlArena", opened
        assert opened["fighting"], "the arena opened with nothing in it"
        assert opened["fps"], "the frame counter flag was dropped on the way in"
        print("CLI-OK")
        """
    )
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "CLI-OK" in result.stdout, result.stdout


def test_the_menu_keys_open_the_shared_screens_on_the_second_front_end():
    """Shop, scoreboard, chronicle, pause, pack, character, legend: all of them.

    These are not screens this front end has; they are the *game's* screens, and
    the application they are handed has to answer everything they ask for. That is
    the whole list, and it is checked the blunt way: press the key, look at what
    is on top.
    """
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)
    assert type(app.screens[-1]).__name__ == "TitleScreen"
    for key, opened in (
        ("s", "ShopScreen"),
        ("h", "ScoreboardScreen"),
        ("l", "ChronicleScreen"),
    ):
        app.key(key)
        assert type(app.screens[-1]).__name__ == opened, (
            f"{key} did not open the {opened}"
        )
        app.key("escape")
        assert type(app.screens[-1]).__name__ == "TitleScreen", "escape did not come back"

    app.key("enter")  # NEW RUN
    app.key("enter")  # the first hero
    app.key("escape")  # the prologue, skipped
    assert type(app.screens[-1]).__name__ == "GameScreen"
    for key, opened in (
        ("escape", "PauseScreen"),
        ("c", "CharacterScreen"),
        ("i", "PackScreen"),
        ("l", "LegendScreen"),
        ("?", "HelpScreen"),
    ):
        app.key(key)
        assert type(app.screens[-1]).__name__ == opened, (
            f"{key} did not open the {opened}"
        )
        app.key("escape")
    assert type(app.screens[-1]).__name__ == "GameScreen", "escape did not come back"


def test_every_menu_is_qt_free_too():
    """The same walk as the test above, in a process where Qt does not exist.

    A menu is a screen like any other, and the ones this front end borrows are the
    game's own -- so the claim to hold is that *the whole of it* is free of Qt,
    not just the parts that were easy. Blocked, pressed, drawn: any screen that
    reached for a toolkit would die here with the import that did it.
    """
    code = textwrap.dedent(
        """
        import sys


        class NoQt:
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] == "PySide6":
                    raise ImportError(f"no Qt here: {name}")


        sys.meta_path.insert(0, NoQt())

        from neverdeads_revenge.sdl_front.app import SdlApp

        app = SdlApp(seed=3)
        for key in ("s", "h", "l"):
            app.key(key)
            app.key("escape")
        app.key("enter")
        app.key("enter")
        for key in ("escape", "c", "i", "l", "?"):
            app.key(key)
            app.key("escape")
        assert type(app.screens[-1]).__name__ == "GameScreen", "not back on the floor"
        assert app._surface is not None, "the floor was not painted"
        print("MENUS-OK")
        """
    )
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "MENUS-OK" in result.stdout, result.stdout


def test_the_room_has_walls_on_the_second_front_end():
    """Three planes of stone, asked of the frame and of the cache.

    The far wall faces the camera and needs no shear; the two at the sides are the
    floor's own edges standing up. Both are built once per window size -- a shear
    is a column of one-pixel strips at a walking offset, which is nothing to do
    once and far too much to do every frame -- so the test asks two things: that
    there is stone in the band above the floor, and that the second frame is a
    blit of the same surface rather than another build.
    """
    from neverdeads_revenge.desktop.theme import BACKGROUND
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3, battle_scene=True, backdrop=False)
    arena = app.screens[-1]
    surface = app._surface
    cols, rows = arena.arena._dims(app)
    field = arena.arena._field(cols, rows, app.font.cell_w, app.font.cell_h)

    stone = sum(
        1
        for x in range(0, surface.get_width(), 3)
        for y in range(round(field["wall_top"]), round(field["top"]), 3)
        if surface.get_at((x, y))[:3] != tuple(BACKGROUND)
    )
    assert stone > 200, f"the wall band is empty: {stone} pixels of stone"

    key = tuple(sorted(field.items()))
    built = arena._stage._walls.get(key)
    assert built is not None, "the wall was not built at all"
    app.redraw()
    assert arena._stage._walls[key] is built, "the wall was built a second time"


def test_the_floor_turns_into_the_fight_on_the_second_front_end():
    """The moment itself: the step, the letter, the white, and the hand-over.

    Walking into a monster does not cut to the arena on either front end any
    more: the floor *turns* into the fight, and the turning is one of the game's
    own screens. On this front end it is wrapped -- the wrapper adds a painter,
    and the screen inside owns the age, the sting and the hand-over -- so what is
    checked here is that both halves are doing their job: the moment is on top,
    a drummed key does not cut it, the letter is growing, and the arena stands
    where the floor was when it is done.
    """
    from neverdeads_revenge.sdl_front.app import SdlApp
    from neverdeads_revenge.sdl_front.turning import SdlTurning

    app = SdlApp(seed=3)
    app.key("enter")
    app.key("enter")
    app.key("escape")  # the prologue, skipped
    state = app.run
    beside = (state.player.position[0] + 1, state.player.position[1])

    from neverdeads_revenge.game.actors import ENEMIES, make_enemy
    from neverdeads_revenge.world.tiles import Tile

    state.dungeon_map.set_tile(beside, Tile.FLOOR)
    monster = make_enemy(ENEMIES["ghoul"], beside)
    state.enemies.append(monster)
    state.turn_queue.add(monster)
    state.refresh_vision()

    app.key("right")
    turning = app.screens[-1]
    assert isinstance(turning, SdlTurning), "the floor did not turn"

    # A key goes nowhere: a moment a drummed key can cut short is a moment the
    # player never sees.
    app.key("enter")
    assert isinstance(app.screens[-1], SdlTurning), "a key cut the turning short"

    # The letter is coming at the camera, and it is *growing*: the size is the
    # screen's own number, so a test can read it off an early frame and a late one.
    app.tick(0.3)
    early = turning.turning.frame(float(app._surface.get_width()), float(app._surface.get_height()), app.font.cell_w, app.font.cell_h, app)
    app.tick(0.35)
    late = turning.turning.frame(float(app._surface.get_width()), float(app._surface.get_height()), app.font.cell_w, app.font.cell_h, app)
    assert early is not None and early.letter is not None
    assert late is not None and late.letter is not None
    assert late.letter.size > early.letter.size, "the letter is not coming closer"
    assert late.dim > early.dim, "the room is not going under"

    # And it hands the room over: the arena stands where the turning was, with
    # the floor still underneath it.
    for _ in range(60):
        if type(app.screens[-1]).__name__ == "SdlArena":
            break
        app.tick(1 / 30.0)
    assert type(app.screens[-1]).__name__ == "SdlArena", "the turning never finished"
    assert len(app.screens) == 2, "the floor was lost in the hand-over"
    assert type(app.screens[0]).__name__ == "GameScreen", "the floor is not underneath"


def test_the_second_front_end_has_a_crt():
    """The same shader, through moderngl, asked of the pixels.

    Scanlines are the honest thing to ask for, because they are a fact about rows:
    the shader darkens every other row of the *display's* own raster, so an even
    row and an odd row of the result measure differently -- and with the toggle off
    they do not. That is the whole of what a scanline is, and it is the one effect
    that needs no eye to check.
    """
    font, paint = _sdl()
    try:
        import moderngl
    except ImportError:  # pragma: no cover - the dev extra is not always there
        return
    from neverdeads_revenge.desktop.crt_gl import CrtSettings
    from neverdeads_revenge.sdl_front.glass import SdlGlass

    try:
        moderngl.create_standalone_context(require=120).release()
    except Exception:  # pragma: no cover - no driver, no glass
        return

    grid = PatternBuffer(96, 27, font)
    grid.text(2, 3, "SCANLINES AND BLOOM", parse_style("bold white"))
    grid.fill_row(1, " ", Style(fg=parse_style("grey30").fg, bg=parse_style("grey11").fg))
    source = paint(grid, font)
    buffer = source.get_size()
    display = (buffer[0] * 2, buffer[1] * 2)  # a whole-number scale, so no bars

    def rows(image, parity: int) -> float:
        picks = [image.get_at((x, y)) for y in range(parity, image.get_height(), 2) for x in range(0, image.get_width(), 7)]
        return sum(one.r + one.g + one.b for one in picks) / (len(picks) * 3)

    glass = SdlGlass(CrtSettings(scanlines=True, bloom=False), buffer, display)
    lit = glass.draw(source)
    assert lit.get_size() == display, "the glass did not draw the whole display"
    assert rows(lit, 0) / rows(lit, 1) > 1.15, "the scanlines are not there"

    glass.settings.scanlines = False
    plain = glass.draw(source)
    assert rows(plain, 0) / rows(plain, 1) < 1.05, "the scanlines did not turn off"
    glass.release()


def _pressed(code, repeat: bool = False):
    """A real SDL key press, the way the window loop makes one."""
    import pygame

    event = pygame.event.Event(pygame.KEYDOWN, key=code, unicode="")
    event.repeat = repeat
    return event


def test_a_real_key_press_reaches_the_screen_it_is_meant_for():
    """The seam every other test in this file could not reach: a real SDL event.

    Everything else here drives `key` with a name and a made-up event, which is
    not what happens in a window -- and that is exactly how a real bug hid: the
    event object was passed where a bool belonged, so `isAutoRepeat()` answered
    yes to everything, and every menu in the game swallowed every key it was
    given. The window was up, it repainted thirty times a second, and it was
    dead. So this feeds *events*, the way `open_window` does.
    """
    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)
    assert type(app.screens[-1]).__name__ == "TitleScreen"

    app.feed(_pressed(pygame.K_n))  # a letter picks its line outright
    assert type(app.screens[-1]).__name__ == "HeroSelectScreen", (
        "the title swallowed a real key press"
    )

    app.feed(_pressed(pygame.K_RETURN))
    assert type(app.screens[-1]).__name__ == "PrologueScreen", "the premise did not open"
    app.feed(_pressed(pygame.K_ESCAPE))
    assert type(app.screens[-1]).__name__ == "GameScreen", "the run did not begin"

    here = app.run.player.position
    for code in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_LEFT, pygame.K_UP):
        app.feed(_pressed(code))
        if app.run.player.position != here:
            break
    assert app.run.player.position != here, "a real arrow key did not move the hero"


def test_a_held_key_is_not_a_second_press():
    """The other half of it: a *held* key is not another press.

    Menus answer one press and not thirty a second, which is what keeps a key held
    from the screen before this one out of the shop on the way past. That guard is
    also why the bug above stayed invisible: it swallowed everything, and
    swallowing everything looks exactly like nothing being wrong.
    """
    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)
    app.feed(_pressed(pygame.K_n, repeat=True))
    assert type(app.screens[-1]).__name__ == "TitleScreen", "a held key was answered"
    app.feed(_pressed(pygame.K_n))
    assert type(app.screens[-1]).__name__ == "HeroSelectScreen", (
        "the key was still being treated as held"
    )


def test_closing_the_window_closes_the_game():
    """The X in the corner, which did nothing at all for a while.

    `quit` is the one shape a front end with no window object has to invent: a
    flag the loop reads. It has to be the flag the QUIT event actually clears.
    """
    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)
    assert app._running, "the loop was not running to begin with"
    app.feed(pygame.event.Event(pygame.QUIT))
    assert not app._running, "the window was asked to close and did not"


def test_a_saved_run_can_be_picked_back_up():
    """Continue, on this front end: the same file, the same loader as Qt's.

    Worth a test of its own because it is the one path that reads something
    written by *another* build -- an older version of the game, or the same one
    yesterday -- and getting it wrong is either a crash on the title screen or a
    run that comes back with none of its history in it.
    """
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.savegame import dump
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.persistence import load_run, save_run
    from neverdeads_revenge.sdl_front.app import SdlApp

    state = start_run(HEROES["noxx"], 3)
    state.dungeon_map  # built with the run; nothing else needed to save it
    save_run(dump(state))

    app = SdlApp(seed=3)
    assert app.has_saved_run(), "the save did not land"
    app.feed(_pressed(__import__("pygame").K_c))
    assert type(app.screens[-1]).__name__ == "GameScreen", "the run did not come back"
    assert app.run is not None and app.run.depth == state.depth, "not the same run"
    assert load_run() is None, "the save was left on disk while being played"


def test_a_save_from_another_version_is_an_empty_slot_not_a_crash():
    """Nonsense on disk is discarded, the way the Qt build discards it."""
    from neverdeads_revenge.persistence import load_run, save_run
    from neverdeads_revenge.sdl_front.app import SdlApp

    save_run({"not": "a run at all"})
    app = SdlApp(seed=3)
    app.feed(_pressed(__import__("pygame").K_c))
    assert type(app.screens[-1]).__name__ == "TitleScreen", "a bad save was opened"
    assert load_run() is None, "a bad save was left lying there"


def test_a_pinned_seed_is_the_same_dungeon_and_seed_zero_counts():
    """`--seed`: the same floor twice, and zero is a number like any other.

    The seed is what makes a report reproducible ("on floor 2 there is a monster
    in the wall"), so it has to actually pin -- and it has to pin for *every*
    value, including the one a truth test throws away. Fingerprinted by the seed,
    where the hero wakes up and what is standing around him, which is what a
    player would recognise as "the same floor".
    """

    from neverdeads_revenge.sdl_front.app import SdlApp

    def floor_of(app):
        return (
            app.run.seed,
            app.run.player.position,
            sorted((one.name, one.position) for one in app.run.enemies),
        )

    first = SdlApp(seed=7)
    _begin_the_run(first)
    same = SdlApp(seed=7)
    _begin_the_run(same)
    assert floor_of(first) == floor_of(same), "the same seed gave two dungeons"

    _begin_the_run(first)  # a second run in the same session
    assert floor_of(first) == floor_of(same), "a pinned seed was re-rolled"

    zero = SdlApp(seed=0)
    _begin_the_run(zero)
    assert zero.run.seed == 0, "seed 0 was thrown away as if it were nothing"


def _pressed(code, repeat: bool = False):
    """A real SDL key press, the way the window loop makes one."""
    import pygame

    event = pygame.event.Event(pygame.KEYDOWN, key=code, unicode="")
    event.repeat = repeat
    return event


def test_a_real_key_press_reaches_the_screen_it_is_meant_for():
    """The seam every other test in this file could not reach: a real SDL event.

    Everything else here drives `key` with a name and a made-up event, which is
    not what happens in a window -- and that is exactly how a real bug hid: the
    event object was passed where a bool belonged, so `isAutoRepeat()` answered
    yes to everything, and every menu in the game swallowed every key it was
    given. The window was up, it repainted thirty times a second, and it was
    dead. So this feeds *events*, the way `open_window` does.
    """
    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)
    assert type(app.screens[-1]).__name__ == "TitleScreen"

    app.feed(_pressed(pygame.K_n))  # a letter picks its line outright
    assert type(app.screens[-1]).__name__ == "HeroSelectScreen", (
        "the title swallowed a real key press"
    )

    app.feed(_pressed(pygame.K_RETURN))
    assert type(app.screens[-1]).__name__ == "PrologueScreen", "the premise did not open"
    app.feed(_pressed(pygame.K_ESCAPE))
    assert type(app.screens[-1]).__name__ == "GameScreen", "the run did not begin"

    here = app.run.player.position
    for code in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_LEFT, pygame.K_UP):
        app.feed(_pressed(code))
        if app.run.player.position != here:
            break
    assert app.run.player.position != here, "a real arrow key did not move the hero"


def test_a_held_key_is_not_a_second_press():
    """The other half of it: a *held* key is not another press.

    Menus answer one press and not thirty a second, which is what keeps a key held
    from the screen before this one out of the shop on the way past. That guard is
    also why the bug above stayed invisible: it swallowed everything, and
    swallowing everything looks exactly like nothing being wrong.
    """
    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)
    app.feed(_pressed(pygame.K_n, repeat=True))
    assert type(app.screens[-1]).__name__ == "TitleScreen", "a held key was answered"
    app.feed(_pressed(pygame.K_n))
    assert type(app.screens[-1]).__name__ == "HeroSelectScreen", (
        "the key was still being treated as held"
    )


def test_closing_the_window_closes_the_game():
    """The X in the corner, which did nothing at all for a while.

    `quit` is the one shape a front end with no window object has to invent: a
    flag the loop reads. It has to be the flag the QUIT event actually clears.
    """
    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)
    assert app._running, "the loop was not running to begin with"
    app.feed(pygame.event.Event(pygame.QUIT))
    assert not app._running, "the window was asked to close and did not"


def test_a_saved_run_can_be_picked_back_up():
    """Continue, on this front end: the same file, the same loader as Qt's.

    Worth a test of its own because it is the one path that reads something
    written by *another* build -- an older version of the game, or the same one
    yesterday -- and getting it wrong is either a crash on the title screen or a
    run that comes back with none of its history in it.
    """
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.savegame import dump
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.persistence import load_run, save_run
    from neverdeads_revenge.sdl_front.app import SdlApp

    state = start_run(HEROES["noxx"], 3)
    state.dungeon_map  # built with the run; nothing else needed to save it
    save_run(dump(state))

    app = SdlApp(seed=3)
    assert app.has_saved_run(), "the save did not land"
    app.feed(_pressed(__import__("pygame").K_c))
    assert type(app.screens[-1]).__name__ == "GameScreen", "the run did not come back"
    assert app.run is not None and app.run.depth == state.depth, "not the same run"
    assert load_run() is None, "the save was left on disk while being played"


def test_a_save_from_another_version_is_an_empty_slot_not_a_crash():
    """Nonsense on disk is discarded, the way the Qt build discards it."""
    from neverdeads_revenge.persistence import load_run, save_run
    from neverdeads_revenge.sdl_front.app import SdlApp

    save_run({"not": "a run at all"})
    app = SdlApp(seed=3)
    app.feed(_pressed(__import__("pygame").K_c))
    assert type(app.screens[-1]).__name__ == "TitleScreen", "a bad save was opened"
    assert load_run() is None, "a bad save was left lying there"



def test_a_held_key_repeats_at_the_pace_the_game_asks_for():
    """SDL has to be *told* to repeat, and the screens have their own rules.

    Two halves, and both were missing. SDL makes no repeat events at all unless
    asked, so holding a direction did nothing and every step cost a press. And
    once it does repeat, the floor walks on it -- "a held direction is one
    gesture" -- but no faster than the hero's own pace, which is the rule this
    asks for directly rather than by walking him into a wall.
    """
    import time

    import pygame

    from neverdeads_revenge.game.pace import action_gap
    from neverdeads_revenge.sdl_front.app import SdlApp

    assert pygame.key.get_repeat() != (0, 0), "SDL was never asked to repeat a key"

    app = SdlApp(seed=3)
    app.key("enter")
    app.key("enter")
    app.key("escape")  # the prologue, skipped
    screen = app.screens[-1]

    screen._last_move.clear()
    app.feed(_pressed(pygame.K_RIGHT, repeat=True))
    assert "right" in screen._last_move, "a held direction was refused outright"
    first = screen._last_move["right"]

    app.feed(_pressed(pygame.K_RIGHT, repeat=True))
    assert screen._last_move["right"] == first, "the repeat outran the hero's pace"

    time.sleep(action_gap(app.run.player.speed) + 0.02)
    app.feed(_pressed(pygame.K_RIGHT, repeat=True))
    assert screen._last_move["right"] > first, "a held direction never arrives again"


def test_a_cell_becomes_the_pixel_the_camera_puts_it_at():
    """Where a coin's sparks go: the game's own translation, not a multiplication.

    The grid is the *camera*, so a square at ``(38, 9)`` is somewhere else on the
    screen. Multiplying by the cell size -- which is what this did -- puts every
    spray half a cell up and to the left of the thing it belongs to, and further
    out the further the hero has walked, which is what the coins did.
    """
    from neverdeads_revenge.desktop.render import screen_point
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3)
    app.key("enter")
    app.key("enter")
    app.key("escape")  # the prologue, skipped
    here = app.run.player.position

    theirs = screen_point(
        app.run, here, app.cols, app.rows, app.font.cell_w, app.font.cell_h
    )
    ours = app.screen_point(here)
    assert ours == theirs, "the cell was not translated the way the game translates it"
    assert ours != (here[0] * app.font.cell_w, here[1] * app.font.cell_h), (
        "the camera was ignored"
    )


def test_a_side_wall_is_sheared_from_its_own_middle():
    """The shear, as arithmetic: a column's offset is measured from the tile's centre.

    A wall is the floor's own edge standing up, and the stone on it is *centred*
    on that edge. Measuring the shift from the tile's left edge instead -- which
    is what this did -- moves the whole plane half a stone along its own axis:
    half a tile to the left and half up, which is exactly the gap that showed
    between the side walls and the far one.
    """
    import pygame

    from neverdeads_revenge.sdl_front.stage import _shear_into

    tile = pygame.Surface((6, 4), pygame.SRCALPHA)
    tile.fill((200, 30, 30, 255))
    canvas = pygame.Surface((40, 40), pygame.SRCALPHA)
    # ux, uy = (0.5, 1.0): a plane leaning to the right, like the left-hand wall.
    _shear_into(canvas, tile, 0.5, 1.0, 20.0, 20.0, -4.0)
    inked = [
        (x, y)
        for x in range(40)
        for y in range(40)
        if canvas.get_at((x, y))[:3] == (200, 30, 30)
    ]
    left = min(x for x, _ in inked)
    right = max(x for x, _ in inked)
    top = min(y for _, y in inked)
    bottom = max(y for _, y in inked)
    assert (left, top, right, bottom) == (18, 13, 21, 21), (left, top, right, bottom)


def test_the_frame_counter_is_there_when_it_is_asked_for():
    """``--fps``: a number in the corner, and nothing in the corner without it.

    Measured against the same frame drawn without it, because the corner is not
    empty anyway -- the sidebar's last rows are right there.
    """
    from neverdeads_revenge.sdl_front.app import SdlApp

    counted = SdlApp(seed=3, battle_scene=True, fps=True)
    for _ in range(4):
        counted.tick(1 / 30.0)
    assert counted.frames > 1.0, f"no frames were counted: {counted.frames}"

    quiet = SdlApp(seed=3, battle_scene=True, fps=False)
    for _ in range(4):
        quiet.tick(1 / 30.0)

    corner = (
        counted._surface.get_width() - 90,
        counted._surface.get_height() - 30,
        counted._surface.get_width(),
        counted._surface.get_height(),
    )
    ink = _changed(quiet._surface, counted._surface, corner)
    assert ink > 30, f"the counter was not drawn: {ink} pixels"


def test_the_picture_is_fitted_to_the_window_it_is_actually_in():
    """Full screen is a different window, and the picture has to follow it.

    Which it did not: the present step scaled by the number the command line
    asked for and never looked at the window again, so a full-screen picture
    stayed its own size in a corner with the rest of the screen black. The scale
    and the centring are reckoned from the window's *current* size now.
    """
    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3, scale=1, no_sound=True)
    app.redraw()
    base = app._buffer_size()
    assert app._shown == base, "the picture was not even its own size"

    pygame.display.set_mode((base[0] * 2, base[1] * 2))
    app._fit()
    assert app._shown == (base[0] * 2, base[1] * 2), "a doubled window doubled nothing"
    assert app._shown_at == (0, 0), "a picture that fits exactly is not centred"

    # A window that is not a whole multiple of the picture: the leftover room
    # becomes *cells* and not bars, which is the Qt build's rule and the reason a
    # 1440p monitor is full of dungeon rather than framed in black.
    pygame.display.set_mode((base[0] + 40, base[1] + 60))
    app._fit()
    assert app._shown == (base[0] + 40, base[1] + 60), "the picture left the window"
    assert app._shown_at == (0, 0), "there is a bar left over"
    assert app._buffer_size() == (base[0] + 40, base[1] + 60), "the grid did not grow"


def test_the_glass_hears_about_a_window_that_changed():
    """The same for the shader: its uniform, and the viewport it draws into.

    The viewport is the one that showed: it is the framebuffer's, its origin is
    the bottom left, and a glass that never moves it draws the game into that
    corner and leaves everything else black -- which is what full screen looked
    like.
    """
    try:
        import moderngl
    except ImportError:  # pragma: no cover - the dev extra is not always there
        return
    from neverdeads_revenge.desktop.crt_gl import CrtSettings
    from neverdeads_revenge.sdl_front.glass import SdlGlass

    try:
        context = moderngl.create_standalone_context(require=120)
    except Exception:  # pragma: no cover - no driver, no glass
        return
    glass = SdlGlass(CrtSettings(), (960, 540), (960, 540), context=context)
    glass.fit((1920, 1080), 2, (0, 0))
    assert glass.display_size == (1920, 1080), "the glass kept the old window size"
    assert (glass.scale, glass.offset) == (2, (0, 0)), "the glass kept the old fit"
    assert tuple(glass.program["resolution"].value) == (1920.0, 1080.0)
    assert glass.ctx.viewport == (0, 0, 1920, 1080), "the viewport was left in a corner"
    glass.release()


def test_full_screen_re_fits_the_picture_to_the_screen(monkeypatch):
    """F11: the window is the whole screen now, so the picture follows it.

    Asked of the numbers, because a test has no screen: the window is *told* to
    be the size of one. What went wrong is worth keeping in mind -- the picture
    stayed its own size in the bottom left corner, because the GL viewport's
    origin is the bottom left and nothing had moved it -- so the facts here are
    the scale and the centring, both of which have to come from the window and
    neither of which may be left at the size the command line asked for.
    """
    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    screen = (2048, 1152)
    app = SdlApp(seed=3, scale=1, no_sound=True)
    app.redraw()
    base = app._buffer_size()

    # A window manager, in two lines: the window is the size of the screen once
    # it is full, and its own size again when it comes back. (A test has no
    # screen, and a window that never changed size would prove nothing.)
    live = {"full": False}
    monkeypatch.setattr(
        pygame.display,
        "get_window_size",
        lambda: screen if live["full"] else base,
    )

    def toggle() -> None:
        live["full"] = not live["full"]

    monkeypatch.setattr(pygame.display, "toggle_fullscreen", toggle)

    # And the other way a window can go full screen: without a glass the app asks
    # for a full-screen *surface*, so the flag has to be watched there too.
    real_mode = pygame.display.set_mode

    def fake_mode(size=(0, 0), flags=0, **rest):
        live["full"] = bool(flags & pygame.FULLSCREEN)
        return real_mode(size, flags, **rest)

    monkeypatch.setattr(pygame.display, "set_mode", fake_mode)

    app.feed(_pressed(pygame.K_F11))
    assert app._fullscreen, "F11 did not ask for full screen"
    # Full screen uses the *screen*: the grid grows to the room there is, so what
    # is left over is an integer remainder and not a pair of bars. Less than one
    # cell at this scale, which is the most a whole-number scale can leave.
    scale = app._scale_for(*screen)
    assert app._shown[0] > base[0] * 2, "the picture did not grow with the screen"
    assert app._shown_at[0] < app.font.cell_w * scale, "there is a bar left over"
    assert app._shown_at[1] < app.font.cell_h * scale, "there is a bar left over"

    app.feed(_pressed(pygame.K_F11))
    assert not app._fullscreen, "F11 did not come back"
    assert app._shown == base, "the picture did not shrink back"


def _begin_the_run(app, hero: str = "noxx") -> None:
    """Begin a run the way a player does, premise and all.

    The prologue is the game's first screen between the choice and the floor: it
    waits for a *held* enter and escape skips it. Every test that wants a floor
    has to get past it, and doing it through the app's own key handling means the
    prologue is exercised every time.
    """
    app.begin_run(hero)
    # Once per session, which is the point of it: a second run in the same
    # session goes straight to the floor, and that is the game's own rule.
    if type(app.screens[-1]).__name__ == "PrologueScreen":
        app.key("escape")
    assert type(app.screens[-1]).__name__ == "GameScreen", "no floor"


def _app_with_a_run(seed: int = 3):
    """An SDL app with a real run behind it: what the menus need to be asked."""
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=seed, no_sound=True)
    _begin_the_run(app)
    return app


def test_the_character_sheet_draws_with_something_worn():
    """Reported from a real keyboard: 'c' with an item equipped crashed the game.

    The sheet wanted the frame's width, and asked the *application* for its
    private buffer -- which the Qt build has and this one never did. So: an item
    in a slot, and the screen drawn, which is the whole of what the report says.
    """
    from neverdeads_revenge.desktop.screens.menus import CharacterScreen
    from neverdeads_revenge.world.items import ITEMS, make_item

    app = _app_with_a_run()
    weapon = next(key for key, one in ITEMS.items() if one.slot == "weapon")
    app.run.player.equipment["weapon"] = make_item(ITEMS[weapon])

    app.feed(_pressed(__import__("pygame").K_c))
    assert type(app.screens[-1]).__name__ == "CharacterScreen", "the sheet did not open"
    assert app._surface is not None, "nothing was drawn"
    assert CharacterScreen is not None  # the import above is the point


def test_every_shared_menu_draws_on_the_second_front_end():
    """All of them, because the bug was one screen reaching into the app.

    A screen belongs to the *game* and is drawn by whichever application is
    running it, so anything a screen asks of the app is a promise both have to
    keep. The character sheet broke that promise; this walks the rest of the
    list -- every menu the game can put on the stack -- so the next one that
    reaches for something only one front end has says so here.
    """
    from neverdeads_revenge.desktop.screens.dialogs import ConfirmScreen, InfoScreen
    from neverdeads_revenge.desktop.screens.game_over import (
        GameOverScreen,
        NameEntryScreen,
    )
    from neverdeads_revenge.desktop.screens.menus import (
        CharacterScreen,
        ChronicleScreen,
        HelpScreen,
        LegendScreen,
        PackScreen,
        ScoreboardScreen,
        ShopScreen,
    )
    from neverdeads_revenge.desktop.screens.pause import PauseScreen
    from neverdeads_revenge.world.items import ITEMS, make_item

    app = _app_with_a_run()
    state = app.run
    weapon = next(key for key, one in ITEMS.items() if one.slot == "weapon")
    state.player.equipment["weapon"] = make_item(ITEMS[weapon])
    state.gold = 120

    screens = [
        PauseScreen(),
        HelpScreen(),
        CharacterScreen(state),
        PackScreen(state),
        LegendScreen(state),
        ShopScreen(),
        ScoreboardScreen(),
        ChronicleScreen(),
        ConfirmScreen("WELL?", "A question with two answers."),
        InfoScreen("A GIFT", "something", "and what it does"),
        GameOverScreen(state, won=True, best=99, can_rewind=True),
        NameEntryScreen(state.score, ""),
    ]
    for screen in screens:
        name = type(screen).__name__
        app.screens = [screen]
        app.redraw()
        assert app._surface is not None, f"{name} drew nothing at all"


def test_a_second_run_in_one_session_is_a_second_dungeon():
    from neverdeads_revenge.sdl_front.app import SdlApp
    """Two NEW RUNs are two dungeons -- unless the player pinned the seed.

    Which is subtler than it sounds: rolling a fresh seed and *keeping* it gives
    every run in one session the same floor, and it looks like the seed flag
    working. The Qt build has a comment about exactly that; this front end grew
    the bug anyway, which is what a test is for.
    """

    def floor_of(app):
        return (
            app.run.seed,
            app.run.player.position,
            sorted((one.name, one.position) for one in app.run.enemies),
        )

    loose = SdlApp(seed=None)
    _begin_the_run(loose)
    first = floor_of(loose)
    loose.begin_run("noxx")
    assert floor_of(loose) != first, "the second run was the same dungeon"

    pinned = SdlApp(seed=7)
    _begin_the_run(pinned)
    kept = floor_of(pinned)
    pinned.begin_run("noxx")
    assert floor_of(pinned) == kept, "a pinned seed stopped pinning"


def test_the_arena_door_works_without_a_seed():
    """``--battle-scene`` and no ``--seed``: a random fight, not a TypeError.

    A seed of ``None`` is a legitimate state -- "the player did not pin one" --
    and it has to be turned into a number before anything is generated.
    """
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=None, battle_scene=True, no_sound=True)
    assert app.run is not None, "the arena opened with no run behind it"
    assert isinstance(app.run.seed, int), f"a seed of {app.run.seed!r}"
    assert type(app.screens[-1]).__name__ == "SdlArena"


def _released(code):
    """A real SDL key release, the way the window loop makes one."""
    import pygame

    return pygame.event.Event(pygame.KEYUP, key=code, unicode="")


def test_the_prologue_waits_for_a_held_key_and_a_tap_banks_nothing():
    """A hold bar is not a keypress: a tap goes nowhere, a hold goes on.

    Which needs two things this front end only got today: SDL actually *making*
    repeats, and the key coming *up* being handed to the screen. Without the
    second, a single tap fills the bar by itself -- the fill is wall-clock time
    from the first press -- and the prologue walks through on a press nobody held.
    """
    import time

    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3, no_sound=True)
    app.feed(_pressed(pygame.K_n))
    app.feed(_pressed(pygame.K_RETURN))
    assert type(app.screens[-1]).__name__ == "PrologueScreen", "no premise to skip"

    # A tap: down and up again, with no repeat in between.
    app.feed(_pressed(pygame.K_RETURN))
    app.feed(_released(pygame.K_RETURN))
    time.sleep(1.2)  # the fill is wall-clock, so it gets the time it wants
    assert type(app.screens[-1]).__name__ == "PrologueScreen", "a tap walked through"

    # A hold: down, and then repeating at the pace a held key actually repeats
    # (SDL's own, every sixty-odd milliseconds). The pace matters -- a gap longer
    # than the hold itself means nothing can still be down, and the fill goes
    # cold -- so a test that pressed twice a second apart would be testing the
    # focus-loss rule instead of the hold.
    app.feed(_pressed(pygame.K_RETURN))
    for _ in range(16):
        time.sleep(0.09)
        app.feed(_pressed(pygame.K_RETURN, repeat=True))
        if type(app.screens[-1]).__name__ == "GameScreen":
            break
    assert type(app.screens[-1]).__name__ == "GameScreen", "a held key did not get through"


def test_the_premise_is_told_once_per_session():
    """The prologue is between the choice and the floor -- the first time.

    A second run in the same session starts on the floor, which is the Qt build's
    rule ("told once"), and the reason `prologue_seen` is a session flag and not a
    setting.
    """
    from neverdeads_revenge.sdl_front.app import SdlApp

    from neverdeads_revenge.sdl_front.app import SdlApp as _Same

    assert SdlApp is _Same

    app = SdlApp(seed=3, no_sound=True)
    app.begin_run("noxx")
    assert type(app.screens[-1]).__name__ == "PrologueScreen"
    app.key("escape")

    app.begin_run("noxx")  # the session has already been told
    assert type(app.screens[-1]).__name__ == "GameScreen", "the premise was told twice"


def test_a_glass_key_says_what_it_did():
    """F2 and friends: the setting changes and the frame says so.

    The Qt build writes the note *into* the pattern buffer; this front end has a
    picture already, so it goes on the picture -- same words, same two seconds,
    same row. Either way it matters: a CRT setting that changed with no
    acknowledgement is a key that might not have worked.
    """
    import time

    import pygame

    from neverdeads_revenge.desktop.theme import BACKGROUND
    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3, battle_scene=True, no_sound=True)
    app.feed(_pressed(pygame.K_F2))
    assert app.glass_note is not None, "the key said nothing"
    note, _until = app.glass_note
    assert note.startswith("SCANLINES"), note

    surface = app._surface
    ink = sum(
        1
        for x in range(0, surface.get_width(), 3)
        for y in range(surface.get_height() // 2 - app.font.cell_h, surface.get_height() // 2)
        if surface.get_at((x, y))[:3] != tuple(BACKGROUND)
    )
    assert ink > 20, "the note is not on the frame"


def test_a_new_screen_wants_a_fresh_press():
    """Holding enter through a screen change must not answer the next one.

    Reported: hold enter to start, the hold bar fills, and the screens after it
    are run through -- the name entry behind the death screen among them. The bar
    was never the problem; the *repeats* were, arriving at a screen that had never
    been told the key was already down. A key that was down before this screen
    existed has to come up and be pressed again, and holds still get their food
    once it is this screen's key.
    """
    import time

    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3, no_sound=True)
    app.feed(_pressed(pygame.K_n))
    assert type(app.screens[-1]).__name__ == "HeroSelectScreen"

    app.feed(_pressed(pygame.K_RETURN))  # the run begins, and the key stays down
    assert type(app.screens[-1]).__name__ == "PrologueScreen"

    for _ in range(16):  # the key is still held: its repeats must be ignored
        time.sleep(0.09)  # at the pace a held key actually repeats -- long
        app.feed(_pressed(pygame.K_RETURN, repeat=True))  # enough to fill the bar
    assert type(app.screens[-1]).__name__ == "PrologueScreen", (
        "a hold carried over and walked through the premise"
    )

    app.feed(_released(pygame.K_RETURN))  # up ...
    app.feed(_pressed(pygame.K_RETURN))  # ... and down again: now it is this screen's
    for _ in range(16):
        time.sleep(0.09)
        app.feed(_pressed(pygame.K_RETURN, repeat=True))
        if type(app.screens[-1]).__name__ == "GameScreen":
            break
    assert type(app.screens[-1]).__name__ == "GameScreen", "a fresh hold did not work"


def test_the_grid_comes_from_the_window_like_the_qt_build(monkeypatch):
    """A 1440p screen full of dungeon instead of two bars: the Qt build's rule.

    Integer scaling is the promise -- "a character is always a character and never
    a smear" -- so the scale can only step in whole numbers, and on a 2560x1440
    monitor the next step up does not fit. The Qt build's answer is to spend what
    is left on *cells*: the same 2x, a 128x36 grid, no bars. That rule was missing
    here, and the numbers are worth holding down because they are the ones the
    game's panels were laid out for.
    """
    import pygame

    from neverdeads_revenge.sdl_front.app import SdlApp

    app = SdlApp(seed=3, no_sound=True)
    for size, scale, grid in (
        ((960, 540), 1, (96, 27)),  # the window both front ends start with
        ((1920, 1080), 2, (96, 27)),
        ((2560, 1440), 2, (128, 36)),  # the one that used to be two black bars
        ((1366, 768), 1, (136, 38)),
    ):
        assert app._scale_for(*size) == scale, size
        assert app._grid_size(*size) == grid, size

    # And the picture really does fill it: 128 cells at two pixels is 2560.
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (2560, 1440))
    app._fit()
    assert (app.cols, app.rows) == (128, 36), "the grid did not follow the window"
    assert app._shown == (2560, 1440), "the picture did not fill the screen"
    assert app._shown_at == (0, 0), "there is a bar left over"


def test_the_arena_can_be_one_painting_instead_of_tiles():
    """The backdrop: one picture where the floor and three walls used to be.

    The game ships *no* painting -- the room it draws is the tiles, and that is
    what the Qt build has and what this one falls back to. So this is a dial for
    looking at art, and the fact worth holding down is that the dial is the only
    difference: same arena, same staging, same figures, and the room under them
    comes from somewhere else.

    Asked by difference, because a painting has no colour the tiles cannot have.
    """
    from neverdeads_revenge.sdl_front.app import SdlApp

    painted = SdlApp(seed=3, battle_scene=True, no_sound=True, backdrop=True)
    tiled = SdlApp(seed=3, battle_scene=True, no_sound=True, backdrop=False)
    arena = painted.screens[-1]
    cols, rows = arena.arena._dims(painted)
    areas = arena.arena._areas(cols, rows)
    cell_w, cell_h = painted.font.cell_w, painted.font.cell_h
    _, wall_y, _, _ = areas["wall"]
    _, ground_y, _, ground_h = areas["ground"]
    box = (
        0,
        wall_y * cell_h,
        painted._surface.get_width(),
        (ground_y + ground_h) * cell_h,
    )
    assert _changed(tiled._surface, painted._surface, box) > 2000, (
        "the backdrop changed nothing in the room"
    )
    # And it is the painting's own colours, not a tint: greens for the vines.
    surface = painted._surface
    greenish = sum(
        1
        for x in range(0, surface.get_width(), 5)
        for y in range(box[1], box[3], 5)
        if surface.get_at((x, y))[1] > surface.get_at((x, y))[0] + 12
    )
    assert greenish > 20, "the painting does not look like itself"
