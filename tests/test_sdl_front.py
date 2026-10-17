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
that has been given a cell port of its own. The test at the bottom of the file
walks into a monster and fights it with nothing but cells in the room.
"""

from __future__ import annotations

from neverdeads_revenge.desktop.pattern import PatternBuffer
from neverdeads_revenge.desktop.theme import BACKGROUND, Style, parse_style

FONT = "src/neverdeads_revenge/desktop/fonts/DejaVuSansMono.ttf"


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

    # The round was *read*, not watched: the SDL arena has no playback, so there
    # is never anything mid-sentence when a key comes in. That is the whole of the
    # tempo difference between the front ends, and it is one boolean.
    arena = app.screens[-1]
    assert not arena.busy, "the arena is holding a beat it has nothing to show for"

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

    state = app.run
    here = state.player.position
    beside = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(beside, Tile.FLOOR)
    vipers = make_enemy(ENEMIES["viper"], beside)
    state.enemies.append(vipers)
    state.turn_queue.add(vipers)
    state.refresh_vision()

    app.key("right")  # walk into it

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
    assert figure.sprite is not None, "the sheets have no picture for the viper"
    cell = app.grid.cells[figure.row][figure.cx // app.font.cell_w]
    assert cell.char != vipers.glyph, "a letter is standing under the sprite"

    # Then the blow, and the fight's voice arrives with it: the line names the
    # monster, and the picture carries it because the log is still a cell panel.
    app.key("a")
    app.key("enter")
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
    from neverdeads_revenge.world.tiles import Tile

    app = SdlApp(seed=3)
    app.key("enter")  # NEW RUN
    app.key("enter")  # the first hero

    state = app.run
    here = state.player.position
    beside = (here[0] + 1, here[1])
    state.dungeon_map.set_tile(beside, Tile.FLOOR)
    ghoul = make_enemy(ENEMIES["ghoul"], beside)
    state.enemies.append(ghoul)
    state.turn_queue.add(ghoul)
    state.refresh_vision()

    app.key("right")  # walk into it

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
    art = arena._stage.sprite(ghoul.name)
    assert art is not None, "the sheets have no picture for the ghoul"
    baseline = figure.row * font.cell_h - THICKNESS
    box = (
        max(0, figure.cx - art.get_width() // 2),
        max(0, baseline - art.get_height()),
        min(surface.get_width(), figure.cx + art.get_width() // 2),
        min(surface.get_height(), baseline),
    )
    painted = surface.copy()
    arena._stage.figure = lambda *args, **rest: False
    app.redraw()
    bare = app._surface
    changed = sum(
        1
        for x in range(box[0], box[2])
        for y in range(box[1], box[3])
        if painted.get_at((x, y)) != bare.get_at((x, y))
    )
    assert changed > 200, f"the monster left {changed} pixels on the frame"
