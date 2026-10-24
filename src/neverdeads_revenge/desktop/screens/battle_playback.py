"""BattlePlayback: one part of the fight screen."""

from __future__ import annotations

import math
from ...game.battle import (
    Mended,
    Flourish,
    Guarded,
    Over,
    Said,
    ShadowStruck,
    Struck,
)
from ...game.specials import (
    PAINT_THE_WALLS_RED,
    special_by_key,
)
from ...game.statuses import status_by_key
from ..art import exists as art_exists
from ..art import size as art_size
from ..theme import parse_style
from .pages import the_page, write_the_page


from .battle_shared import (
    THICKNESS,
    ORDER_SHOWN,
    FLAIR_COLOURS,
    STATUS_COLOURS,
    STATUS_LOOKS,
    STATUS_SOUNDS,
    STATUS_ICONS,
    GONE_LIFE,
    PAGE_AFTER,
    FLOURISH_LIFE,
    SPARKS,
    SHAKES,
    SHOVES,
    SHOVE,
    CRIT_SHOVE,
    HITSTOP,
    CRIT_STOP,
    HITSTOPS,
    FLASH_ALPHA,
    FLASH_HARD_ALPHA,
    HARD_BLOWS,
    BEAT,
    LINE_BEAT,
    END_BEAT,
    STRIKE,
    IMPACT_AT,
    JOLT,
    JOLT_PIXELS,
    LOG_LINES,
    Popup,
    Wash,
    Staged,
)


class BattlePlayback:
    def _strike_pose(
        self,
        figure: Staged,
        figures,
        home: int,
        cell_w: int,
        cell_h: int,
    ) -> tuple[int, int, float, float] | None:
        """Where a striker is, how solid, and *how big* -- ``None`` if standing still.

        The blow is a blink: the striker goes out where it stands, comes back in
        beside whatever it is hitting, and is gone again before the beat that
        started it is over. Nothing *travels* -- a fight this size has no room for
        a walk, and a monster that walked over would make every round twice as
        long as the blow it holds -- but the eye reads the two places as one
        movement, which is the whole trick.

        And the two places are at two *depths*: the hero's row is the front of the
        room and the monsters' row is the far half of it, so a figure that crosses
        the room is drawn at the size the place it stands in has. The scale jumps
        exactly where the figure is invisible -- out at one end and not yet in at
        the other -- so the jump is never seen; what is seen is a hero who is
        smaller where he is further away, and a monster who is bigger where it has
        come close. The installed pictures are the *front* size and the *far*
        size, which is why one of them halves and the other doubles.
        """
        #: A front-of-the-room figure, drawn where the monsters stand, is half its
        #: own size; a monster drawn where the hero stands is at the size it was
        #: exported at. It is one ratio -- the room's two depths -- and it is used
        #: in both directions.
        far = 0.5
        near = 2.0
        strike = self._strikes.get(id(figure.actor))
        if strike is None:
            return None
        target_id, began, flair = strike
        look = self._look(flair)
        progress = (self._clock - began) / STRIKE
        if progress >= 1.0:
            del self._strikes[id(figure.actor)]
            return None
        near_x, near_y = self._beside_target(
            figure, target_id, figures, home, cell_w, cell_h
        )
        # Who is crossing the room, and so which size it is drawn at over there:
        # the hero and his shadow stand in the front and go far; a monster stands
        # far and comes to the front.
        at_home = figure.actor is self.battle.hero or figure.actor is self.state.atritas
        over_there = far if at_home else near
        if look in ("shadow", "trail", "orb"):
            # None of these moves the hero. The shadow is a second figure going
            # instead of him, the trail is where he *is* -- a step so quick that
            # the room cannot follow it -- and the orb is *thrown*: he stands
            # still and the dark does the travelling.
            return figure.cx, home, 1.0, 1.0
        if look == "dissolve":
            # Giving in: he is not in the room for the middle of it.
            return figure.cx, home, 0.10 if 0.22 < progress < 0.78 else 1.0, 1.0
        if progress < 0.20:  # out, where it stands
            return figure.cx, home, 1.0 - progress / 0.20, 1.0
        if progress < 0.34:  # in, beside the one being hit
            return near_x, near_y, (progress - 0.20) / 0.14, over_there
        if progress < 0.70:  # the blow itself
            return near_x, near_y, 1.0, over_there
        if progress < 0.84:  # out again, over there
            return near_x, near_y, 1.0 - (progress - 0.70) / 0.14, over_there
        return figure.cx, home, (progress - 0.84) / 0.16, 1.0  # back home

    @staticmethod
    def _look(flair: str) -> str:
        """How a blow was struck, as its own word -- or ``""`` for a plain one.

        The rules say which *trick* was used; what that trick looks like is the
        screen's to know, so a hero can get a look without the fight learning a
        colour.
        """
        special = special_by_key(flair) if flair else None
        return special.look if special is not None else ""

    def _fade(self, actor_id: int) -> float:
        """How much of a figure is still in the room: 1 until it is killed, 0 gone.

        The rules kill at the swing and the room lets go at the *blow*, which is
        a fifth of a second later -- and then it does not leave a dimmed corpse
        lying about, it lets the whole figure go. A dead monster is not a monster
        in half a light: it is one that was there and now is not.
        """
        if actor_id in self._sinking_ids:
            # The void's kill has its own way of leaving, and two of them at once
            # would be one corpse drawn twice.
            return 0.0
        when = self._dying.get(actor_id)
        if when is None:
            return 1.0
        age = self._clock - when
        if age >= GONE_LIFE:
            return 0.0
        return max(0.0, 1.0 - age / GONE_LIFE)

    def _knockback(self, figure: Staged, cell_h: int) -> int:
        """How far up the room a shoved figure is, right now.

        Up the room and not across it, because the floor runs away towards the
        top: a shove that moved a monster sideways would be a monster standing
        somewhere it is not, which is the one thing the isometric view cannot
        afford. ``push`` is in cell heights, so the bell's throw and a stick hit
        are the same movement at two sizes.
        """
        knocked = self._knocked.get(id(figure.actor))
        if knocked is None:
            return 0
        when, push = knocked
        age = self._clock - when
        if age < 0:
            return 0
        if age > FLOURISH_LIFE:
            del self._knocked[id(figure.actor)]
            return 0
        # Out fast, home slowly: a knock is not a shove back into place.
        out = min(1.0, age / 0.14)
        back = max(0.0, (age - 0.30) / (FLOURISH_LIFE - 0.30))
        return round(cell_h * push * out * (1.0 - back))

    def _jolt(self, figure: Staged) -> int:
        """How far a struck figure is shaking, in pixels, right now."""
        struck = self._hurts.get(id(figure.actor))
        if struck is None:
            return 0
        age = self._clock - struck[0]
        if age < 0:
            return 0
        if age > JOLT:
            del self._hurts[id(figure.actor)]
            return 0
        return round(math.sin(age * 46.0) * JOLT_PIXELS)

    def _reading(self) -> None:
        """Take down what the plate is allowed to say about the level.

        Not a cache: a *reading*, taken at the moments the fight is not being
        watched -- the first frame, the end of a round -- and at the one moment
        it is being watched and ought to move, which is the level-up's own
        animation. The rules are a moment ahead of the room everywhere else too;
        this is the same promise the health bars keep.
        """
        self._plate = {
            "kills": self.state.kills_to_level,
            "level": self.state.level,
            "top": max(1, self.state.kill_points_max),
        }

    def _snapshot(self) -> None:
        """Freeze what the bars say, so the playback can move them itself."""
        for actor in [self.battle.hero, *self.battle.enemies]:
            self._shown[id(actor)] = actor.stats.hp
        self._catching_up()
        self._reading()

    def _catching_up(self, actor=None) -> None:
        """Read the rules' own wounds, for the badge row to catch up with.

        Called where the fight is *not being watched* -- the first frame, and
        the moment a round has finished being played -- so that a row can never
        arrive before the thing it is about. When an actor is named, only that
        one is read: that is the call the playback makes, one actor at a blow.
        """
        actors = (
            [actor]
            if actor is not None
            else [self.battle.hero, *self.battle.enemies]
        )
        for one in actors:
            self._wearing[id(one)] = self._worn_for(one)
            self._depths[id(one)] = dict(one.status_stacks)

    def _worn_for(self, actor) -> tuple[str, ...]:
        """What the *rules* say this figure is wearing, as a badge row."""
        return tuple(sorted(key for key in actor.statuses if key in STATUS_ICONS))

    def _worn(self, actor) -> tuple[str, ...]:
        """What the *room* has shown so far. Empty until an animation says so."""
        return self._wearing.get(id(actor), ())

    def _fall_due(self, app) -> None:
        """Everything that was owed to a blow, once its moment has come.

        The lines that describe a hit, and the sparks it throws: both are the
        blow's, both are timed off it, and neither is allowed to arrive early --
        a fight that reads out a hit before it happens has told the player the
        ending of the sentence they are in the middle of.
        """
        if self._late:
            due = [line for when, line in self._late if self._clock >= when]
            self._late = [(when, line) for when, line in self._late if self._clock < when]
            for line in due:
                self.lines = [*self.lines, line][-LOG_LINES:]
                self._level_line(line, app)
        if self._showers:
            due = [one for one in self._showers if self._clock >= one[0]]
            self._showers = [one for one in self._showers if self._clock < one[0]]
            for _when, point, colour, count in due:
                app.effects.spark(point, colour, count)
        if self._wounds_due:
            # And the wounds, on the same clock as the numbers and the sparks:
            # this is the frame a blow lands in, and a wound belongs to the blow
            # that made it -- not to the swing, and not to the rules.
            due = [actor for when, actor in self._wounds_due if self._clock >= when]
            self._wounds_due = [
                (when, actor) for when, actor in self._wounds_due if self._clock < when
            ]
            for actor in due:
                self._catching_up(actor)

    def _delay_to_impact(self, line: Said) -> float | None:
        """How long this line waits: until the *blow it belongs to* lands.

        Not a flat beat. A killing blow writes several lines -- the kill, the
        level, the kill points, the trick learned -- and the blow itself is played
        after all of them, so a flat delay put four lines into the log and the
        death a quarter of a second later. The wait walks the queue to the next
        blow and adds up the beats it will take to get there.

        ``None`` when there is no blow ahead at all: a line marked ``waits`` with
        nothing to wait for is read like any other rather than held forever.
        """
        ahead = self._queue
        cut = next((i for i, one in enumerate(ahead) if isinstance(one, Struck)), None)
        if cut is None:
            return None
        between = sum(self._beat_for(one) for one in ahead[:cut])
        return self._beat_for(line) + between + IMPACT_AT

    def _level_line(self, line: Said, app) -> None:
        """The one line in a fight that gets a picture of its own.

        The arrow over his head, and the note that goes with it -- fired when the
        *line* arrives rather than when it is queued. It used to fire at the
        start of the line's beat, which put the arrow over the hero a good third
        of a second before the killing blow had landed: the rules had worked out
        the death and the room had not shown it yet.
        """
        if line.text.startswith("Level "):
            self._level_up(app)

    @staticmethod
    def _beat_for(event) -> float:
        """How long this event holds the stage.

        A blow is *watched* and gets the full beat; a line is read at a glance
        and gets a fifth of one. Splitting them is the whole of the fight's pace:
        a round is a handful of blows and twice as many lines, and one number for
        both was the fight narrating at the speed it strikes.
        """
        if isinstance(event, Said):
            return LINE_BEAT
        if isinstance(event, Over):
            return END_BEAT
        return BEAT

    def _resync(self) -> None:
        """Truth, once the round has finished being played."""
        for actor in [self.battle.hero, *self.battle.enemies]:
            self._shown[id(actor)] = actor.stats.hp
        self._catching_up()
        # And the plate reads again, so a kill that did *not* raise a level still
        # moves its count -- at the end of the round, which is where the next
        # choice is made and nothing is in the middle of being watched.
        self._reading()
        # And the order: `upcoming` already begins with the turn in flight, so
        # standing still and mid-swing give the same strip and nothing slides. A
        # couple spare, so that the row the panel draws is never shorter than the
        # row it drew a moment ago.
        self._order = list(self.battle.upcoming(ORDER_SHOWN + 2))

    def _play(self, event, app) -> None:
        """One event, on the screen and in the ear."""
        if isinstance(event, Said):
            # The log is the fight's voice, and its voice does not run ahead of
            # its hands: a line the rules marked as the blow's *waits* for the
            # blow, and turns up on the frame the sword does. Lines about
            # anything else -- a draught, a retreat, a wound ticking -- are read
            # at once, because there is nothing for them to wait on.
            wait = self._delay_to_impact(event) if event.waits else None
            if wait is not None:
                self._late.append((self._clock + wait, event))
            else:
                self.lines = [*self.lines, event][-LOG_LINES:]
                self._level_line(event, app)
            return
        if isinstance(event, ShadowStruck):
            # The shadow went for somebody: the ghost over them, and -- if that
            # was the end of them -- the body going black and down.
            figure = self._figure_of(event.actor, app)
            if figure is not None:
                feet = float(figure.row * app.font.cell_h - THICKNESS)
                bottom = feet
                art = "sprites/atritas.png"
                if art_exists(art):
                    # *Above* them and not on them: the monster is going down
                    # under the ghost's feet, and one sprite over another is one
                    # of the two not being seen.
                    measured = art_size(figure.art) if figure.art else None
                    if measured is not None:
                        bottom = feet - measured[1] - 4
                    self._drift.append(
                        (art, float(figure.cx), bottom, self._clock)
                    )
                if event.killed:
                    self._sinking.append(
                        (figure.art, float(figure.cx), bottom, self._clock)
                    )
                    self._sinking_ids.add(id(event.actor))
            return
        if isinstance(event, Flourish):
            status = status_by_key(event.flair)
            if status is not None:
                self._wound(event.actor, status, app)
                return
            self._flourish = (event.flair, self._clock)
            look = self._look(event.flair)
            self._self = (look, FLAIR_COLOURS.get(event.flair, "#ffffff"), self._clock)
            if event.flair == PAINT_THE_WALLS_RED:
                # One shadow over each of them, leaving the wound behind. Placed
                # from the staging rather than from the log: the thing has to come
                # out of *their* squares.
                art = "sprites/atritas.png"
                if art_exists(art):
                    for enemy in self.battle.living_enemies():
                        figure = self._figure_of(enemy, app)
                        if figure is None:
                            continue
                        self._drift.append(
                            (
                                art,
                                float(figure.cx),
                                float(
                                    figure.row * app.font.cell_h - THICKNESS
                                ),
                                self._clock,
                            )
                        )
            point = self._point_of(event.actor, app)
            if point is not None:
                app.effects.spark(
                    point, FLAIR_COLOURS.get(event.flair, "#ffffff"), SPARKS.get(look, 20)
                )
            if look == "aura":
                point = self._point_of(event.actor, app)
                if point is not None:
                    app.effects.spark(
                        point, FLAIR_COLOURS.get(event.flair, "#ffffff"), 26
                    )
            return
        if isinstance(event, Guarded):
            # A guard is the hero's turn and carries his *name*: the strip is
            # about actors, and there is exactly one actor a guard can belong to.
            self._took_a_turn(self.battle.hero)
            point = self._point_of(self.battle.hero, app)
            if point is not None:
                app.effects.spark(point, "grey70", count=8)
            return
        if isinstance(event, Over):
            if not event.won and not event.escaped:
                # The run ended in here, and a death is not held up for a page:
                # the summary is about the run, and the run is what is standing
                # behind the arena.
                self.verdict = "YOU DIED"
                rumble = getattr(app, "rumble", None)
                if rumble is not None:
                    rumble(1.0, 0.8, 450)
                app.leave_battle()
                app.show_game_over(won=False)
                return
            # The verdict is *earned* here and *shown* by :meth:`_settle`: a page
            # written by the last blow comes first, because a dialog that turns
            # up after the player has already left is a page that was written and
            # never read.
            self._outcome = "VICTORY" if event.won else "YOU GOT AWAY"
            # A death is scored once, by the summary that follows it: playing it
            # here too gave the arena's deaths a doubled sting.
            self._victory_sound = "quest_complete" if event.won else "dash_roll"
            self._settle(app)
            return
        if isinstance(event, Mended):
            # The draught on the bars' own clock: the rules mend at the keypress,
            # and a bar that waited for the end of the round made the potion look
            # as if it had worked after the monster's blow.
            self._shown[id(event.actor)] = event.hp
            return
        if isinstance(event, Struck):
            self._took_a_turn(event.actor)
            self._land(event, app)

    def _write_the_pages(self, app) -> None:
        """File what this fight has killed, and say so when the room is quiet.

        The dungeon's half is ``state.defeated``: every death passes through the
        one door, whatever killed the thing -- a blow, a wound, the shadow -- so
        the book does not have to know how. The book's half is the player's
        progress, and the two are *not* the same clock: the page is written at
        once (a kill is a kill), and shown after the playback, because a dialog
        is something the player reads rather than something the fight talks over.
        """
        for key in self.battle.state.defeated:
            if key in self._filed:
                continue
            self._filed.add(key)
            if write_the_page(app, key):
                self._pages_due.append(key)
        if self.busy or not self._pages_due:
            self._page_at = None
            return
        if self._page_at is None:
            self._page_at = self._clock + PAGE_AFTER
            return
        if self._clock < self._page_at:
            return
        self._page_at = None
        card = the_page(self._pages_due.pop(0), on_done=self._card_read)
        if card is not None:
            self._card_open = True
            app.push(card)

    def _card_read(self, _value=None) -> None:
        """The page has been closed. The room may speak again."""
        self._card_open = False

    def _settle(self, app) -> None:
        """Show the verdict once the book has had its say.

        Three things hold it back, and each of them is a way the player could
        otherwise miss the page: the round is still being played, a page is
        still queued, or a page is on screen over the room. The last one is why
        this is asked every frame rather than fired with the event -- the arena
        is not stepped while a dialog is on top of it, so the frame after the
        card closes is the first frame the verdict may arrive on.
        """
        if self.verdict or self._outcome is None:
            return
        if self.busy or self._pages_due or self._card_open:
            return
        self.verdict = self._outcome
        self._outcome = None
        if self._victory_sound is not None:
            app.play(self._victory_sound)
            self._victory_sound = None

    def _land(self, struck: Struck, app) -> None:
        """A blow landing: a number, a shove, and a sound that matches it."""
        outcome = struck.outcome
        if outcome.hit:
            # The pad says it in the hand: a heavy low for a blow, a small sharp
            # one on top for a crit, and a longer shake for the killing one.
            rumble = getattr(app, "rumble", None)
            if rumble is not None:
                if outcome.killed:
                    rumble(0.8, 0.4, 140)
                elif outcome.crit:
                    rumble(0.5, 0.6, 90)
                else:
                    rumble(0.35, 0.15, 55)
        figure = self._figure_of(struck.target, app)
        if figure is not None:
            text = str(outcome.damage) if outcome.hit else "miss"
            colour = (
                "#ffd34d"
                if outcome.crit
                else struck.target.color
                if outcome.hit
                else "grey70"
            )
            # The number waits for the blow. It is *set* when the swing starts --
            # there is one moment to write it down -- but it must not be read
            # before the sword is in the monster, so its clock starts negative
            # and it appears on the frame the impact falls in.
            number = self._popup(text, colour, figure, app, outcome.crit)
            number.age = -IMPACT_AT
            number.damage = outcome.damage if outcome.hit and not outcome.dodged else 0
            number.target_id = id(struck.target)
            number.killed = outcome.killed
            # The sound belongs to the *blow* and not to the swing, like the
            # number and the bar and the sparks: everything the player hears and
            # sees about a hit happens on the frame it lands in.
            from ...desktop.audio import cast_sound, weapon_sound

            if struck.actor is self.battle.hero:
                trick = special_by_key(struck.flair) if struck.flair else None
                number.sound = (
                    "kill"
                    if outcome.killed
                    else "critical_hit"
                    if outcome.crit
                    else cast_sound(struck.flair, trick.look if trick else "")
                    if trick is not None
                    else weapon_sound(self.state.player.weapon_inflicts)
                )
            else:
                number.sound = "player_hurt"
            if not outcome.hit:
                # A swing that met air is its own sound and not silence: the
                # player has to hear that the turn was spent and nothing landed.
                number.sound = "miss_dodge"
            self._popups.append(number)
            # Owed, and paid at the impact: a wound the blow inflicts is read on
            # the frame the number is, which is what "the sword did it" means.
            self._wounds_due.append((self._clock + IMPACT_AT, struck.target))
            if outcome.hit and not outcome.dodged:
                point = self._point_of(struck.target, app)
                if point is not None:
                    look = self._look(struck.flair)
                    app.view.shake(
                        strength=SHAKES.get(look, 4 if outcome.crit else 2), seconds=0.2
                    )
                # And the whole room takes it: a frame of the trick's own colour
                # across everything, which is what a blow sounds like with the
                # sound off. The heavy ones land harder than a stick does.
                self._wash_blow(struck, app)
        # The strike is recorded whether or not it lands: a swing that missed
        # was still a swing, and a hero who did not move would look like a hero
        # who did nothing.
        self._strikes[id(struck.actor)] = (
            id(struck.target),
            self._clock,
            struck.flair,
        )
        if outcome.hit and not outcome.dodged:
            look = self._look(struck.flair)
            when = self._clock + IMPACT_AT
            self._hurts[id(struck.target)] = (
                when,
                FLAIR_COLOURS.get(struck.flair, "#ffffff"),
                look,
            )
            # Thrown *back*: up the room, which is away from the hero, and back
            # again -- the dungeon's version of the bell only makes it walk. Every
            # other blow shoves a little of the same way, so that a hit moves
            # something whether or not there is a number over it.
            push = SHOVES.get(look, SHOVE) * (CRIT_SHOVE if outcome.crit else 1.0)
            self._knocked[id(struck.target)] = (when, push)
        if not outcome.hit:
            return
        # A shower of sparks in the trick's own colour, from the figure that took
        # it: the flashes say *where*, the particles say *how much*. Owed, not
        # thrown: it belongs to the impact and not to the swing, so it is put on
        # the same clock as everything else the blow does.
        look = self._look(struck.flair)
        point = self._point_of(struck.target, app)
        if point is not None:
            self._showers.append(
                (
                    self._clock + IMPACT_AT,
                    point,
                    FLAIR_COLOURS.get(struck.flair, "#ffffff"),
                    SPARKS.get(look, 16),
                )
            )


    def _wound(self, actor, status, app) -> None:
        """A wound biting: what the fight shows at the monster's own turn.

        The damage is the *domain's* and has already been taken -- on the turn
        the wound belongs to, which is the rule -- so this is only the reading of
        it: the figure flashes in the colour of what is eating it, a number comes
        off it, the bar drops to where the wound left it, and the shape goes out
        (a drip, a climb, a wave of heat, a breath of cold).

        Everything a blow gets except the blow. A wound is not a hit and must not
        look like one: it is the same monster, one turn later, still being eaten.
        """
        # Brighter than the light the wound *wears*, and not the same colour of it:
        # a bite that is the same green as the monster already is is a bite nobody
        # sees. The mark and the moment are two different things.
        colour = parse_style(STATUS_COLOURS.get(status.key, "#ffffff")).fg.lighter().name()
        look = STATUS_LOOKS.get(status.key, "")
        figure = self._figure_of(actor, app)
        if figure is None:
            return
        self._hurts[id(actor)] = (self._clock, colour, look)
        if status.damage:
            # The bar was at the *unwounded* value: the domain has already taken
            # the damage off the real actor, and this is the screen catching up.
            was = self._shown.get(id(actor), actor.stats.hp + status.damage)
            self._shown[id(actor)] = max(0, was - status.damage)
            number = self._popup(str(status.damage), colour, figure, app, False)
            number.age = -IMPACT_AT
            number.target_id = id(actor)
            # A wound that finished it is a *killing blow* like any other, and
            # the room has to let the figure go -- which it does off this flag.
            # It was only ever set by a sword, so a monster that bled to death
            # stayed standing there: no health, the fight over, and a corpse
            # the arena had never been told about.
            number.killed = actor.stats.hp <= 0
            self._popups.append(number)
        point = self._point_of(actor, app)
        if point is not None:
            app.effects.spark(point, colour, SPARKS.get(look, 16))
            app.view.shake(strength=2, seconds=0.12)
        # And the badge row catches up on the same frame the number does -- which
        # is also the frame a wound that has *run out* stops being worn, so the
        # row is never a list of problems the fight is finished with.
        self._wounds_due.append((self._clock + IMPACT_AT, actor))
        app.play(STATUS_SOUNDS.get(status.key, "hurt"))

    def _wash_blow(self, struck: Struck, app) -> None:
        """What a landed blow does to the *room*: it stops it, and it colours it.

        The two together are the weight. Everything else a hit has -- the shove,
        the sparks, the number -- happens inside a room that is carrying on as
        before, and a room that carries on is a room in which nothing much
        happened. Both are timed at the impact and not at the swing, so they land
        with the blow and not with the decision to throw it.
        """
        look = self._look(struck.flair)
        hard = struck.outcome.crit or look in HARD_BLOWS
        stop = max(
            HITSTOPS.get(look, HITSTOP),
            CRIT_STOP if struck.outcome.crit else 0.0,
        )
        self._wash = Wash(
            colour=FLAIR_COLOURS.get(struck.flair, "#ffffff"),
            when=self._clock + IMPACT_AT,
            strength=FLASH_HARD_ALPHA if hard else FLASH_ALPHA,
            stop=stop,
        )

    @staticmethod
    def _popup(text: str, colour: str, figure: Staged, app, crit: bool) -> Popup:
        """A number placed over the head it landed on, ready to rise.

        Hung on the figure's own *line* and not at the height it will be read at:
        how far above a head a number has to sit depends on the face it is drawn
        in -- over the arrow as well as over the letter, or the number a player is
        reading would stand exactly where the target marker is -- and that is the
        painter's business, the same way the verdict panel's place is. The number
        says what it is about; the painter puts it down.
        """
        return Popup(
            text=text,
            colour=colour,
            x=figure.cx,
            y=round(figure.row * app.font.cell_h - THICKNESS),
            crit=crit,
            size=figure.size,
        )

