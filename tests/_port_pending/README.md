# Waiting to be ported

The Qt build's screen tests, parked while the Qt build was removed. They are
`.pending` and not `.py` so that nothing collects them.

**87 of the 140 are ported** and live in `tests/test_screens.py` -- the title,
the prologue, the pause, the dialogs, the simple menus, the shop's shelf, the
trick list and the first half of the arena. The harness sends a tap as a down
*and* an up, draws through `desktop.pattern` and `_blit_art(screen)`, and reaches
the arena's screen through `screen.arena` where a test drives machinery rather
than pixels.

What is left, and why it needs a glance per test:

1. **The arena's playback clock.** The blow's lines, numbers, bars and order
   strip are timed off `BattleScreen`'s `_queue`/`_clock`/`_shown`; the tests
   read them on the old painter. Moving them to `screen.arena.*` gets the test
   started, but the assertions were written against the old beat constants.
2. **The turning wrapper.** `SdlTurning` wraps `EncounterScreen` as
   `screen.turning`; the tests that walk a step out still ask the wrapper for
   `battle`/`age` and render the old `PatternBuffer.render()`.
3. **The shop, pack and level-up flow.** A few dialogs and the summary answer
   differently than when the tests were written (the delete word, the name
   entry, the purchase bell).
4. **The old Qt painters.** `_paste_figure`/`_paste_shadow`, the flourish
   shapes and the tile-room fallback were replaced by `SdlArena`/`Stage`; those
   tests should be rewritten against the current painter or dropped.

Everything left is coverage the current suite does not have, so it is worth the
walk -- but it is a walk, not a mechanical sweep.
