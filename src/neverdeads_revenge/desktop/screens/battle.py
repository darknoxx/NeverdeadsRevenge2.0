from __future__ import annotations

from typing import Any
from ...game.battle import (
    ATTACK,
    FLEE,
    ITEM,
    SPECIAL,
    VERBS,
    Battle,
    Said,
)
from ...game.specials import (
    special_by_key,
)
from ...game.state import LogKind
from ..padmap import BATTLE as BATTLE_PAD
from ..pattern import PatternBuffer
from .base import Screen





from .battle_shared import (
    FLOOR_NEAR,
    FLOOR_NEAR_ALT,
    FLOOR_FAR,
    FLOOR_FAR_ALT,
    WALL_NEAR,
    WALL_MID,
    WALL_FAR,
    THICKNESS,
    TAPER,
    POINT,
    HOLLOW,
    POINT_COLOUR,
    LEVEL_UP,
    LEVEL_UP_COLOUR,
    ORDER_SHOWN,
    STAGE,
    AIMED,
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
    DRIFT_RISE,
    DRIFT_SCALE,
    ARROW,
    FLAIR_COLOURS,
    STATUS_COLOURS,
    STATUS_LOOKS,
    STATUS_SOUNDS,
    STATUS_ICONS,
    STATUS_BADGE,
    STATUS_ROW_IN,
    STATUS_ROW_DOWN,
    STATUS_GAP,
    MONSTER_BADGE,
    MONSTER_BADGE_GAP,
    STATUS_SLOT,
    FAR_LIGHT,
    WALL_STONES,
    FLOOR_BONES,
    GONE_LIFE,
    WALL_LIFE,
    SINK_LIFE,
    SINK_DROP,
    PAGE_AFTER,
    FLOURISH_LIFE,
    SPARKS,
    SELF_LOOKS,
    SHAKES,
    THROWN,
    SHOVES,
    SHOVE,
    CRIT_SHOVE,
    HITSTOP,
    CRIT_STOP,
    HITSTOPS,
    FLASH_LIFE,
    FLASH_ALPHA,
    FLASH_HARD_ALPHA,
    HARD_BLOWS,
    BEAT,
    LINE_BEAT,
    END_BEAT,
    POPUP_LIFE,
    BOB_SPEED,
    BOB_HEIGHT,
    STRIKE,
    IMPACT_AT,
    JOLT,
    JOLT_PIXELS,
    LOG_LINES,
    Popup,
    Wash,
    Staged,
)

__all__ = ["BattleScreen", "FLOOR_NEAR", "FLOOR_NEAR_ALT", "FLOOR_FAR", "FLOOR_FAR_ALT", "WALL_NEAR", "WALL_MID", "WALL_FAR", "THICKNESS", "TAPER", "POINT", "HOLLOW", "POINT_COLOUR", "LEVEL_UP", "LEVEL_UP_COLOUR", "ORDER_SHOWN", "STAGE", "AIMED", "ROWS", "ECHO_STEP", "ECHO_LANE", "PANEL_ROWS", "LOG_ROWS", "ORDER_CELLS", "PANEL_FLOOR", "ARC_ROWS", "HERO_CLEARANCE", "HERO_CLEARANCE_CELLS", "HERO_DROP", "STAGE_LIFT", "MONSTER_SIZES", "HERO_SIZE", "DRIFT_LIFE", "DRIFT_RISE", "DRIFT_SCALE", "ARROW", "FLAIR_COLOURS", "STATUS_COLOURS", "STATUS_LOOKS", "STATUS_SOUNDS", "STATUS_ICONS", "STATUS_BADGE", "STATUS_ROW_IN", "STATUS_ROW_DOWN", "STATUS_GAP", "MONSTER_BADGE", "MONSTER_BADGE_GAP", "STATUS_SLOT", "FAR_LIGHT", "WALL_STONES", "FLOOR_BONES", "GONE_LIFE", "WALL_LIFE", "SINK_LIFE", "SINK_DROP", "PAGE_AFTER", "FLOURISH_LIFE", "SPARKS", "SELF_LOOKS", "SHAKES", "THROWN", "SHOVES", "SHOVE", "CRIT_SHOVE", "HITSTOP", "CRIT_STOP", "HITSTOPS", "FLASH_LIFE", "FLASH_ALPHA", "FLASH_HARD_ALPHA", "HARD_BLOWS", "BEAT", "LINE_BEAT", "END_BEAT", "POPUP_LIFE", "BOB_SPEED", "BOB_HEIGHT", "STRIKE", "IMPACT_AT", "JOLT", "JOLT_PIXELS", "LOG_LINES", "Popup", "Wash", "Staged"]

from .battle_playback import BattlePlayback
from .battle_panels import BattlePanels
from .battle_stage import BattleStage


class BattleScreen(BattlePlayback, BattlePanels, BattleStage, Screen):
    """The stage, and one fight, played a beat at a time."""

    PAD = BATTLE_PAD

    def __init__(self, battle: Battle) -> None:
        self.battle = battle
        self.state = battle.state
        self.verb = 0
        self.target = 0
        #: Whether the five are being looked at: SPECIAL opens a list rather than
        #: spending the first one it finds, because a player who cannot choose is
        #: not being offered anything.
        self.picking = False
        self.special = 0
        #: Whether the arrow is out on the room, waiting for a monster to be
        #: walked to and taken. The trick is chosen first and the *victim* second:
        #: a turn that named a monster in the rules and hid it from the player
        #: would be a choice made by whoever was standing under the arrow.
        self.aiming = False
        #: Where the aim was opened from, so escape goes back there: ``"list"``
        #: for the five, ``"verbs"`` for the command panel.
        self._aim_from = "verbs"
        #: Which of the five the aim is going to spend. The list picks the trick
        #: and the arrow picks the monster, so the trick has to be kept.
        self._picked: str | None = None
        #: The fight's last few lines, in the log's own colours.
        self.lines: list[Said] = []
        #: The round being played back, one event per beat. The opening round is
        #: queued here rather than in a call the caller has to remember: anything
        #: quicker than the hero acts before the first command, and that has to
        #: happen the moment the fight opens or it never happens at all.
        self._queue = list(battle.begin())
        self._beat = 0.0
        self._popups: list[Popup] = []
        #: What the health bars show, which lags the state by exactly the blows
        #: that have been played rather than the ones that have been rolled.
        self._shown: dict[int, int] = {}
        self.verdict: str | None = None
        self._size: tuple[int, int] | None = None
        #: The grid this screen was last drawn into, kept because the paste step
        #: needs one part of it *again*: the panels are cells, the cells are under
        #: the art, and the menu has to end up on top of whoever is standing in
        #: front of it. The same reason ``_size`` is kept -- a painter that paints
        #: in two passes has to agree with itself about the first one.
        self._grid = None
        #: Where the painting's *wall* begins, in frame pixels from the top. Set by
        #: the front end that owns the artwork -- it is the one line only it knows,
        #: because it depends on where the painting was placed -- and no monster
        #: stands above it. ``None`` is a room of cells, which has no wall line.
        self.stage_horizon: float | None = None
        #: The arena's own clock, in seconds. The idle breath and every phase of
        #: a strike are read off it, so nothing here owns a timer.
        self._clock = 0.0
        #: Who is mid-strike: ``id(attacker) -> (id(target), when it began)``.
        self._strikes: dict[int, tuple[int, float]] = {}
        #: The shadow out over the monsters: ``(art, x, bottom, when)`` per enemy
        #: the trick opened. Not a particle -- it is a *sprite*, drawn by the
        #: pixel pass, and it is what the wound it left behind looks like.
        self._drift: list[tuple[str, float, float, float]] = []
        #: What the shadow killed, on its way down: the figure it was, going
        #: black and sinking. Kept apart from the room's ordinary fade because the
        #: void takes a thing down rather than letting it go.
        self._sinking: list[tuple[str, float, float, float]] = []
        self._sinking_ids: set[int] = set()
        #: Who was struck: when the blow inside their strike lands, and the
        #: colour the trick that landed it is painted in.
        self._hurts: dict[int, tuple[float, str, str]] = {}
        #: Who has just been thrown back, by how far and when. A knockback is a
        #: *place* and not a colour, so it is kept apart from the flashes.
        self._knocked: dict[int, tuple[float, float]] = {}
        #: The room holding still on a landed blow, in seconds left to hold.
        self._hitstop = 0.0
        self._order: list = list(battle.upcoming(ORDER_SHOWN + 2))
        #: Sparks owed to blows that have not landed yet: a shower over a monster
        #: the sword has not reached is the fight telling the player the future,
        #: in the same way a number is. ``(when, point, colour, how many)``.
        self._showers: list[tuple[float, tuple[float, float], str, int]] = []
        #: Lines that describe a blow that has not landed yet. The log is read
        #: left to right and top to bottom, so a sentence about a hit has to wait
        #: for the hit -- see :meth:`_play`.
        self._late: list[tuple[float, Said]] = []
        #: The wash over the room on a landed blow. The loudest thing here and
        #: the cheapest -- and named apart from the white flash a *sprite* wears,
        #: which is the blow's mark on the figure rather than on the room.
        self._wash: Wash | None = None
        #: Who has been *seen* to die, and when: the frame the killing blow
        #: landed, not the moment the rules decided it. Everything that reads a
        #: figure's aliveness for the picture reads this instead.
        self._dying: dict[int, float] = {}
        #: THE ALMANAC's queue. A monster killed for the first time is written
        #: down the moment the room notices it, and *shown* once the room has
        #: finished letting the body go: a page over the death would be the book
        #: covering the fight it describes.
        self._pages_due: list[str] = []
        #: The aspect cards, after the pages: a first kill and the dark's mark
        #: are two notes, and the page is the larger one.
        self._aspects_due: list[tuple[str, str]] = []
        self._page_at: float | None = None
        #: What this screen has already looked at, so the same kill is not filed
        #: on every frame it is drawn.
        self._filed: set[str] = set()
        self._filed_aspects: set[tuple[str, str]] = set()
        #: The verdict the fight has earned and not yet *shown*. It waits for the
        #: book: a page written by the last blow is read before the room says who
        #: won, or the player leaves on the verdict and the page is never seen.
        self._outcome: str | None = None
        self._victory_sound: str | None = None
        #: Whether a page's card is open over the room. Set when one is pushed,
        #: cleared by the card itself when it is read -- the arena is not stepped
        #: while a dialog is on top of it, so a timer here would be guessing.
        self._card_open = False
        #: And which wounds have been *seen*: the same rule one step further, for
        #: the badge row. The rules inflict a wound at the swing -- they resolve
        #: the whole turn at once -- and the room must not: a badge that turned up
        #: while the sword was still in the air is the fight telling the player
        #: the ending of the sentence they are in the middle of.
        self._wearing: dict[int, tuple[str, ...]] = {}
        #: And how deep each of those is, read at the same moment: the badge
        #: carries a number once a wound is more than one stack, and a number
        #: that arrived before its blow would be the same lie as a badge that did.
        self._depths: dict[int, dict[str, int]] = {}
        #: Who the fight still owes a look at, and when. Everything in here is
        #: read at the frame it comes due, which is always the frame a blow lands
        #: in or a wound bites -- never the frame the rules knew.
        self._wounds_due: list[tuple[float, Any]] = []
        self._catching_up()
        #: The three numbers on the plate that a *level* moves -- the count, the
        #: level, and how wide the purse is -- read the way the bars are read and
        #: not live: the rules raise a level the moment the kill resolves, and the
        #: fight must not say so until the arrow is going up. Everything else on
        #: the plate is the hero's own turn rather than a blow's, and stays live.
        self._plate: dict[str, int] = {}
        self._reading()
        #: What a trick left standing on the *hero*: its look, its colour, when.
        self._self: tuple[str, str, float] | None = None
        #: A trick that was not a blow: its word, and when it happened. Only the
        #: hero raises one, and only one at a time -- a wall and an aura at once
        #: would be two answers to one turn.
        self._flourish: tuple[str, float] | None = None

    @property
    def clock(self) -> float:
        """How far the fight's playback has run, in seconds."""
        return self._clock

    @property
    def wash(self):
        """The full-frame colour a landed blow is washed with, or ``None``."""
        return self._wash

    @wash.setter
    def wash(self, value) -> None:
        self._wash = value

    @property
    def popups(self):
        """The damage numbers currently on their way up."""
        return self._popups

    @property
    def hurts(self):
        """Which figures are flashing, and in what colour."""
        return self._hurts

    @property
    def knocked(self):
        """Which figures are shoved, and when they land."""
        return self._knocked

    @property
    def sinking(self):
        """Which figures are falling out of the room."""
        return self._sinking

    @property
    def shown(self):
        """How much of each figure's health the room has shown."""
        return self._shown

    @property
    def depths(self):
        """How deep each figure stands, for the bars and badges."""
        return self._depths

    @property
    def strikes(self):
        """The blows in flight, and their beats."""
        return self._strikes

    @property
    def drift(self):
        """How much the room is drifting under the playback."""
        return self._drift

    def dims(self, app):
        """The grid the screen is drawn into."""
        return self._dims(app)

    def floor_row(self, cols: int, rows: int) -> int:
        """The row the room's floor is on."""
        return self._floor_row(cols, rows)

    def worn(self, actor):
        """The wounds the room has shown on this actor so far."""
        return self._worn(actor)

    def figures(self, cols: int, rows: int, font):
        """The staged figures for this window."""
        return self._figures(cols, rows, font)

    def areas(self, cols: int, rows: int):
        """Where the panels, lines and plate sit, in cells."""
        return self._areas(cols, rows)

    def field(self, cols: int, rows: int, cell_w: int, cell_h: int):
        """The floor in pixels."""
        return self._field(cols, rows, cell_w, cell_h)

    def fade(self, actor_id: int) -> float:
        """How much of a figure is still in the room, 0 to 1."""
        return self._fade(actor_id)

    def strike_pose(self, figure, figures, home, cell_w, cell_h):
        """Where a striker is mid-blow, or ``None`` if standing still."""
        return self._strike_pose(figure, figures, home, cell_w, cell_h)

    def knockback(self, figure, cell_h: int) -> int:
        """How far up the room a shoved figure is."""
        return self._knockback(figure, cell_h)

    def jolt(self, figure) -> int:
        """How far a struck figure is shaking."""
        return self._jolt(figure)

    def verdict_panel(self, cols: int, rows: int, font):
        """The panel a finished fight leaves, and where it lands."""
        return self._verdict_panel(cols, rows, font)

    def draw(self, buffer: PatternBuffer, app, ground: bool = True) -> None:
        #: The size this screen is being drawn at, remembered: the letters are
        #: placed in pixels and the paste step has to agree with the grid pass
        #: about where the floor is, and the grid pass is the one that knows.
        self._size = (buffer.cols, buffer.rows)
        self._grid = buffer
        buffer.clear()
        areas = self._areas(buffer.cols, buffer.rows)
        # The cell floor is a *dial*, because a front end with a painting for a
        # room has no use for it: two thousand of the frame's cells written and
        # then written again in the room's own black was a millisecond a frame
        # thrown away. The painter's room is not a thing this screen knows about,
        # so it is told.
        if ground:
            self._draw_ground(buffer, areas["ground"])
        self._draw_health(buffer, areas["ground"])
        # The log lives at the *top* of the frame: the room has the bottom now,
        # and a fight's account of itself belongs where the eye goes first.
        self._draw_log(buffer, (0, 0, buffer.cols, areas["log"][3]))
        self._draw_plate(buffer, *areas["plate"])
        self._draw_commands(buffer, *areas["commands"])
        self._draw_order(buffer, *areas["order"])

    def key(self, name: str, event, app) -> bool:
        if name == "m":
            # The book, mid-fight. It is the one screen the game lets you open
            # here: reading is not a turn, and a monster's page is worth more
            # than a pause. It opens at the bestiary, because a fight's question
            # is always about a monster.
            app.open_almanac(tab=1)
            return True
        if name == "v":
            self._inspect(app)
            return True
        if self.battle.over:
            # The fight is decided, but the arena may still be playing the last
            # blow: leaving on a keypress before the verdict has been shown would
            # be the player skipping the one thing they just earned. And the
            # verdict itself waits for the book, so the page is read first.
            if not self.busy and name in ("enter", "return", "space"):
                if self._outcome is not None or self._pages_due:
                    return True
                app.leave_battle()
            return True
        if self.picking:
            # The five, being looked at: everything goes to the list until it is
            # closed, escape included -- *there* escape is the way back and not
            # the way out, and the list has to hear it before the arena does.
            return self._pick_special(name, app)
        if self.aiming:
            # The arrow, being walked across the room: everything goes to the aim
            # until a monster is taken or the choice is given back.
            return self._aim(name, app)
        if name == "escape":
            # There is no way out of a fight but through it. Fleeing is a *verb*
            # with a price -- everything still standing gets a blow at the hero's
            # back -- and a key that walks out for nothing would make every
            # encounter in the dungeon optional.
            if not event.isAutoRepeat():
                # Once per press: a held key used to write the same line sixty
                # times and push everything else out of the log.
                self.lines = [
                    *self.lines,
                    Said("The only way out of this is through it.", LogKind.PLAIN),
                ][-LOG_LINES:]
            return True
        if self.busy:
            # The fight is talking. It will not be interrupted mid-sentence, or
            # a player drumming on the keyboard would be choosing the next verb
            # for a blow they have not seen land yet.
            return True
        # No arrow here. A target is picked *after* the trick is picked, in the
        # one place where the fight is going to read it: aiming at a monster
        # before knowing what is being aimed would be choosing the answer to a
        # question nobody has been asked yet.
        if name == "up":
            self.verb = (self.verb - 1) % len(VERBS)
            return True
        if name == "down":
            self.verb = (self.verb + 1) % len(VERBS)
            return True
        shortcut = {"a": ATTACK, "s": SPECIAL, "i": ITEM, "f": FLEE}
        if name in shortcut:
            self.verb = VERBS.index(shortcut[name])
            self._confirm(app)
            return True
        if name in ("enter", "return", "space"):
            self._confirm(app)
            return True
        return True

    def _confirm(self, app) -> None:
        """Take the highlighted verb.

        SPECIAL is a door rather than a verb: the hero has five ways to spend a
        turn and the player is entitled to pick which. The first available one is
        not good enough, because a choice nobody can make is not a choice -- and
        neither is a monster nobody was shown. So the two verbs that are *aimed*
        open the arrow instead of spending the turn: the trick first, the victim
        second, both of them on the screen.
        """
        if VERBS[self.verb] == SPECIAL:
            if not self.battle.learned():
                # Nothing learned yet: there is no list to open, and a panel with
                # nothing in it is worse than a key that says no.
                app.play("error_locked")
                return
            self.picking = True
            self.special = 0
            return
        if VERBS[self.verb] in AIMED:
            self.aiming = True
            self._aim_from = "verbs"
            self._picked = None
            return
        self._choose(app)

    def _walk(self, step: int, app) -> None:
        """Move the arrow to another monster, and say so.

        The blip is not decoration. A cursor that moves in silence makes the
        player look down at the panel to find out whether the key registered,
        and a fight is watched on the floor.
        """
        living = self._targets()
        if not living:
            return
        self.target = (self.target + step) % len(living)

    def _aim(self, name: str, app) -> bool:
        """A monster is being walked to, and the next enter spends the turn.

        Left and right cross the room, the blip marks every step of it, and the
        note on the way in is the commitment: the arrow says *which*, and the
        ears say that the choice was taken.
        """
        # Left and right only, and not up and down: the row of monsters runs
        # across the room, and a key that walked the arrow "up" would walk it
        # along an axis the room does not have.
        if name in ("left", "h"):
            self._walk(-1, app)
            return True
        if name in ("right", "l"):
            self._walk(1, app)
            return True
        if name in ("escape", "backspace"):
            # Back where the choice came from, with the trick still picked: the
            # aim is a step in a menu and not a trap.
            self.aiming = False
            if self._aim_from == "list":
                self.picking = True
            return True
        if name in ("enter", "return", "space", "a"):
            self.aiming = False
            self._choose(app, special=self._picked)
            return True
        return True

    def _list_rows(self, app) -> int:
        """How many names fit in one column of the list, as it is drawn now.

        Asked rather than assumed: the wall the list is drawn on is sized from
        the window, and a jump that used the wrong number would land in the
        middle of the other column.
        """
        cols, rows = self._dims(app)
        return max(1, self._areas(cols, rows)["commands"][3] - 4)

    def _inspect(self, app) -> None:
        """R3: the Almanac, open at what is being fought.

        The target is the monster the arrow is on, or the first one standing.
        A page that has not been written stays unwritten -- the fight is not a
        way around the collection -- but the page that *is* written answers
        "what does this thing do to me" without leaving the room.
        """
        living = self.battle.living_enemies()
        if not living:
            return
        target = living[self.target % len(living)]
        from .almanac import AlmanacScreen

        app.push(AlmanacScreen(tab=1, select=target.key))

    def _pick_special(self, name: str, app) -> bool:
        """What he has learned, being looked at: pick one, or come back."""
        specials = self.battle.learned()
        if not specials:
            # Nothing on the menu and no way to have got here: the verbs refuse
            # to open an empty list, and this is the guard for anything that
            # finds another road in.
            self.picking = False
            app.play("error_locked")
            return True
        # The number keys still work and are no longer *shown*: the list carries
        # the price of each trick where the number used to be, and a shortcut is
        # a convenience for the player who already knows the list by heart.
        index = {str(digit): digit - 1 for digit in range(1, 10)}.get(name)
        if name in ("escape", "backspace"):
            self.picking = False
            return True
        rows = self._list_rows(app)
        if name in ("up", "w"):
            self.special = (self.special - 1) % len(specials)
            return True
        if name in ("down", "s"):
            self.special = (self.special + 1) % len(specials)
            return True
        if name in ("left", "h", "right", "l"):
            # The list is two columns, so across is a whole column away -- and it
            # stays where it is rather than wrapping, because a jump that lands
            # somewhere unrelated is a jump that loses the player's place.
            jump = -rows if name in ("left", "h") else rows
            moved = self.special + jump
            if 0 <= moved < len(specials):
                self.special = moved
            return True
        if index is None and name in ("enter", "return", "space"):
            index = self.special
        if index is None or index >= len(specials):
            return True
        chosen = specials[index]
        if self.battle.special_available(chosen):
            self.picking = False
            if not chosen.needs_target:
                # Set on himself, or through everything standing: there is nobody
                # to walk the arrow to, and asking would be asking a question the
                # fight was never going to read.
                self._choose(app, special=chosen.key)
                return True
            # The trick is picked, and the *victim* is still to be picked: the
            # list closes and the arrow takes over, on the floor where the
            # monsters are, with the trick kept for whoever it ends up on.
            self.aiming = True
            self._aim_from = "list"
            self._picked = chosen.key
        else:
            # Locked, or already spent this fight. Answered out loud and not with
            # silence: the same note for a refusal as for a commitment is a menu
            # the player cannot read with their ears.
            app.play("error_locked")
        return True

    @property
    def kill_points(self) -> int:
        """How much of the purse the tricks are paid from is left."""
        return self.state.kill_points

    @property
    def busy(self) -> bool:
        """Whether the fight still has something to say or show.

        Talking, and only talking: the keyboard is held while the round is being
        played, because a player drumming on enter would be choosing the next
        verb for a blow they have not seen land.

        *Talking* and not *fading*: the damage numbers are deliberately not in
        here. They are the fight's last word about a blow that has already
        landed, and a number on its way out is not a reason to hold the player's
        hands -- it used to be three quarters of a second of pure waiting every
        single round, which is exactly the wait a fight should never have.
        """
        return bool(self._queue) or self._beat > 0

    @property
    def animating(self) -> bool:
        """A fight always breathes, so the arena is always being repainted."""
        return True

    def step(self, dt: float, app) -> None:
        """A frame went by: age the numbers, and land the next event.

        Everything the fight does is on this clock -- the beat between blows and
        the life of a damage number -- because a screen that kept a timer of its
        own would keep running after the window it is drawn in has gone.
        """
        if self._hitstop > 0:
            # The room holds still on a landed blow: no clock, no breath, no
            # beat. Three frames in which nothing moves is the difference between
            # a hit that lands on something and a number that arrives politely --
            # and it is spent *inside* the beat, so the round is not longer.
            self._hitstop = max(0.0, self._hitstop - dt)
            return
        self._clock += dt
        if self._drift:
            # Gone once they have faded: a run of forty fights must not carry
            # forty ghosts.
            self._drift = [
                one for one in self._drift if self._clock - one[3] < DRIFT_LIFE
            ]
        if self._sinking:
            self._sinking = [
                one for one in self._sinking if self._clock - one[3] < SINK_LIFE
            ]
            if not self._sinking:
                self._sinking_ids.clear()
        if self._wash is not None and not self._wash.spent and self._clock >= self._wash.when:
            # The blow landed inside this frame, so the room stops for the next
            # few: the hitstop is spent *at* the impact and not at the swing.
            self._wash.spent = True
            self._hitstop = self._wash.stop
        self._fall_due(app)
        for popup in self._popups:
            # A number on its way *to* the fight and not out of it: it goes live
            # on the frame the blow lands, and the bar drops with it. Both are one
            # fact -- how much of whom -- and a bar that went down while the sword
            # was still in the air was the fight spending the blow for the player.
            if popup.age < 0 <= popup.age + dt:
                if popup.damage:
                    before = self._shown.get(popup.target_id, popup.damage)
                    self._shown[popup.target_id] = max(0, before - popup.damage)
                if popup.sound:
                    app.play(popup.sound)
                if popup.killed:
                    # *Now* it dies, which is the moment the number came off it.
                    # The rules knew at the swing; the room is told here, and the
                    # two moments are different on purpose.
                    self._dying[popup.target_id] = self._clock
            popup.age += dt
        self._popups = [popup for popup in self._popups if popup.age < Popup.LIFE]
        self._write_the_pages(app)
        self._settle(app)
        if self._beat > 0:
            self._beat = max(0.0, self._beat - dt)
            return
        if not self._queue:
            self._resync()
            return
        event = self._queue.pop(0)
        self._play(event, app)
        self._beat = self._beat_for(event)

    def _targets(self) -> list:
        """Who the choice can be on: the monsters the stage is actually showing.

        The stage holds three. A bigger fight is a second row and a wider glass
        (M3), and until there is one, an arrow that could point at a monster the
        player cannot see would be pointing at nothing.
        """
        return [enemy for enemy in self.battle.enemies[:STAGE] if enemy.stats.alive]

    def _choose(self, app, *, special: str | None = None) -> None:
        """Take the highlighted verb, and queue the round it sets off."""
        living = self._targets()
        target = living[self.target % len(living)] if living else None
        # The state is decided the instant the player commits; what the screen
        # shows is not, and this is where the two are told apart.
        self._snapshot()
        self._queue = list(self.battle.choose(VERBS[self.verb], target, special=special))
        self._beat = 0.0
        # The strip the player is about to watch: the round that was just decided,
        # in the order it was decided, and then what the queue says comes after it
        # -- with enough runway that counting the round off the front never leaves
        # the strip shorter than the row it draws.
        played = self.battle.turns()
        self._order = [*played, *self.battle.upcoming(ORDER_SHOWN + len(played))]
        # The confirmation, and only one of it: a trick and a draught have a
        # voice of their own, and a blip over the top of the dark's own sound
        # would be a stutter rather than a flourish. Everything else -- a swing,
        # a guard, a run for it -- has nothing to say for itself yet, so the note
        # that the key registered is all the player hears until it lands.
        from ...desktop.audio import cast_sound

        if VERBS[self.verb] == SPECIAL:
            trick = special_by_key(special) if special else None
            app.play(cast_sound(special, trick.look if trick else ""))
        elif VERBS[self.verb] == ITEM:
            app.play("potion_use")
        elif VERBS[self.verb] == FLEE:
            app.play("dash_roll")
        else:
            app.play("weapon_draw")
        if not living:
            self._resync()

