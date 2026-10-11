"""The prologue and the map legend.

Both live here, in the headless layer, for a reason that is not tidiness: the
legend is generated from :class:`~neverdeads_revenge.world.tiles.Tile` and
``ENEMIES`` and ``ITEMS`` themselves, so a new terrain type, monster or draught
cannot be added without it noticing. Deriving the text rather than writing it
twice is what keeps the sidebar from quietly going stale.

The prologue is plain data. It is shown once per session, before floor 1, and it
is the only place the game's premise is stated in prose -- everything afterwards
has to work without being told again.

It is written in the second person and never names the hero. More heroes are
coming, and a backstory that says "Noxx" is a backstory that has to be rewritten
for each of them; one that says "you" belongs to whoever the player picked.
"""

from __future__ import annotations

from ..game.actors import ENEMIES, HEROES, Hero, scale_template
from ..game.npcs import NPC_GLYPH
from ..world.generator import ESCAPE_DEPTH
from ..world.items import CHEST_GLYPH, COIN_GLYPH, ITEMS
from ..world.tiles import Tile

__all__ = [
    "PROLOGUE",
    "PROLOGUE_TITLE",
    "PROLOGUE_HINT",
    "GOAL_HINT",
    "terrain_help",
    "enemy_legend",
    "item_legend",
    "legend_rows",
]

#: The one line a player must never have to guess at.
#:
#: The prologue asks whether there is a way out; this answers it and says where,
#: in the panel that is on screen at every moment. Kept here rather than in the
#: widget so the width test can measure it like any other legend line.
GOAL_HINT = f"the way out is on floor {ESCAPE_DEPTH}"

#: Shown above the story. The premise in one sentence, for a player skimming.
PROLOGUE_TITLE = "Death is not the end. You were not granted even that."

#: The story, told once per session.
#:
#: The beats are the user's: the battle on Mount Karpas, the falling axe, the
#: blackness that was not peaceful, the body returned, the question of a way out.
#: Everything else is rhythm -- the strongest line here is the shortest ("And the
#: axe."), and it only works because the line before it is long. Nothing explains
#: a mechanic; mechanics are explained when they are met.
#:
#: The line lengths are load-bearing. The pane does not scroll (any key dismisses
#: the screen, so a player who needed to scroll could not), which means the story
#: has to fit a 34-row terminal. Most lines are kept under 70 characters so they
#: occupy one row each; the three that run long do so on purpose, for the beat
#: they land on. ``tests/test_ui.py`` asserts the whole thing still fits.
PROLOGUE: tuple[str, ...] = (
    "The last thing you remember is Karpas. The pass in the mountains, the mud, "
    "the cold coming up through your boots.",
    "And the axe. It hung above you a long time. Long enough to count the notches.",
    "Then black. Not the black behind the eyes -- the black that owns them.",
    "It was not still, and it was not kind. It pressed against you, and it was "
    "pleased.",
    "You cannot say how long. Forever is for people who still have time.",
    "Then pain in the dark. That is how you knew the body was yours again.",
    "You opened your eyes. Nothing opened with them.",
    "The emptiness had given back your hands, your breath, your weight. Under your "
    "palms, stone. Ahead of you, a cold that has a direction.",
    "So down, then. Whatever door leads out of this, it is not behind you.",
)

#: The last line on the prologue screen, set apart from the story.
#:
#: The story ends on a decision ("so down, then"); this is the hook that turns the
#: decision into a reason. It answers the question the user's original asked --
#: whether there is a way out of the emptiness -- without doing the arithmetic of
#: which floor, which the sidebar already states exactly.
PROLOGUE_HINT = "There is a way out. It is under everything."


#: Terrain worth explaining. VOID and FLOOR are omitted on purpose: void is
#: "not yet seen", which the player learns from the dimming, and floor is the
#: default the eye assumes. GRASS and WATER are omitted too: they are pure
#: decoration, and the panel has to stay short enough to fit the sidebar without
#: the bottom of it -- the loot and the goal -- falling off the screen.
#:
#: DOOR is omitted for a different reason, and it is the honest one: the tile is
#: fully specified and the field of view has a test for it, but the generator
#: has never placed one. A reference that lists a thing no floor contains is a
#: reference that teaches the player to look for something that is not there.
LEGEND_TERRAIN: tuple[Tile, ...] = (
    Tile.WALL,
    Tile.RUBBLE,
    Tile.STAIRS_DOWN,
    Tile.RIFT,
    Tile.SPRING,
)


def item_legend() -> list[tuple[str, str]]:
    """``(glyph, meaning)`` for what can be picked up.

    Draughts keep a row each, because the difference between a potion and an
    elixir is the decision the player is making. Everything wearable shares one
    row of glyphs, because the difference between a blade and a coat is not a
    decision the map asks you to make -- and because the panel is clipped and
    three separate rows for them cost the sidebar a row it did not have.

    A row may carry more than one glyph. The widget colours each of them, so
    ``) [ "`` still reads as three things rather than one odd one.

    The chest is a row of its own: it is not loot, it is a question.
    """
    rows: list[tuple[str, str]] = []
    for template in ITEMS.values():
        if template.chest_only or template.slot is not None:
            continue
        rows.append((template.glyph, f"{template.name}, heals {template.heal}"))
    # The order the glyphs are first declared in, so the row matches the order
    # the map's own reference lists them in.
    worn = " ".join(
        dict.fromkeys(t.glyph for t in ITEMS.values() if t.slot is not None)
    )
    rows.append((worn, "weapon, armour, amulet"))
    rows.append((CHEST_GLYPH, "a chest, and a price"))
    # The chronicle is deliberately *not* here, and the reason is what this
    # panel is for: everything else on it is a thing to avoid or a thing to
    # take, and a page is neither. It is also the one mark on the map that has
    # nothing to do with the run -- a player who picks one up finds out what it
    # is from the message, and the curiosity of a `?` that the legend does not
    # explain is the right feeling to meet a collectible with.
    #
    # The honest reason is also the plain one: the panel is clipped, and it had
    # exactly thirteen rows to give.
    rows.append((COIN_GLYPH, "coins, for the shop"))
    # The spring is terrain, but it is the one tile with a rule attached, so it
    # earns a row here rather than living only in the help screen.
    rows.append((Tile.SPRING.glyph, "a spring, lifts a curse"))
    return rows


def enemy_legend(depth: int = 1, hero: Hero | None = None) -> list[tuple[str, str]]:
    """``(glyph, meaning)`` for the player's own marker and every enemy.

    Built from the live templates, so adding a monster to ``ENEMIES`` adds it
    here without a second edit. The numbers are the ones that matter when a
    fight goes wrong: how fast it moves and how hard it hits.

    ``depth`` matters. Monsters get tougher as the run goes down, and a sidebar
    that kept quoting floor-1 numbers next to a floor-8 map would be lying to the
    player at exactly the moment they need the truth. The kinds listed stay the
    same at every depth -- a monster that only appears from floor 6 would need a
    different panel, not a longer one.

    ``hero`` matters for the same reason. The panel says "you" beside a glyph,
    and which glyph that is depends on who the player picked; hardcoding the
    first hero would label the wrong letter once the roster grew, which is
    exactly what happened when it did.
    """
    if hero is None:
        hero = next(iter(HEROES.values()))
    rows: list[tuple[str, str]] = [
        (hero.glyph, "you"),
    ]
    for template in ENEMIES.values():
        scaled = scale_template(template, depth)
        low, high = scaled.stats.damage
        speed = scaled.stats.speed
        pace = "slow" if speed < 0.85 else "even" if speed < 1.15 else "fast"
        # One line per monster, abbreviated. The panel lives in the sidebar next
        # to the map, and the map needs the rows more than the prose does: full
        # sentences cost two lines per monster and push the terrain half, which
        # is the half a new player actually needs, off the bottom.
        rows.append(
            (
                template.glyph,
                f"{template.name} {pace} {scaled.stats.max_hp}hp {low}-{high}d",
            )
        )
    return rows


def legend_rows(depth: int = 1, hero: Hero | None = None) -> list[tuple[str, str]]:
    """The always-on legend: you, the monsters, then the loot.

    Terrain is deliberately *not* here. ``LEGEND_TERRAIN`` is static -- a wall is
    a wall on every floor -- while the monsters' numbers change every descent and
    the loot is what keeps a run alive. Only the second kind earns a permanent
    place next to the map; the first is a reference you look up once, and it lives
    in the help text where there is room for it.

    That split is not just tidiness. The panel is clipped rather than scrolled,
    and every row spent on "patchy grass" is a row that could push the rift --
    the thing the whole run is for -- off the bottom of the sidebar.

    A row with an empty glyph is a section break, or a continuation line when it
    carries text of its own; the widget decides how to render it.

    No blank line between the monsters and the loot: the panel is clipped, and
    the chest row made it one line too long. The glyphs separate the sections
    well enough without spending a row on it.
    """
    return [
        *enemy_legend(depth, hero),
        # Not a monster and not loot, but it is on the map and it is the only
        # mark there that will not hurt you. One row, and the row is worth it:
        # everything else in this panel is a thing to avoid or a thing to take.
        (NPC_GLYPH, "somebody to talk to"),
        *item_legend(),
    ]


def terrain_help() -> str:
    """The static terrain reference, formatted for the help text."""
    return "\n".join(f"[bold]{tile.glyph}[/] {tile.description}" for tile in LEGEND_TERRAIN)