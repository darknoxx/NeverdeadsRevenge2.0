# Waiting to be ported

The Qt build's screen tests, parked while the Qt build was removed. They are
`.pending` and not `.py` so that nothing collects them.

**64 of the 140 are ported** and live in `tests/test_screens.py` -- the title,
the prologue, the pause, the dialogs and the simple menus. The harness now sends
a tap as a down *and* an up (the app marks a key held through a screen change
stale), draws through `_blit_art(screen)`, and uses `desktop.pattern` instead of
the old `buffer`.

What is left, and why it needs a glance per test:

1. **`SdlArena(battle)` vs `BattleScreen(battle)`.** The SDL arena is the
   painter; anything that calls the screen's own machinery (`_choose`,
   `_figures`, `aiming`, `picking`) wants `BattleScreen`. Fourteen tests call
   methods the painter does not have.
2. **Deleted Qt hooks.** `_paste_shadow` / `_paste_figure` and the two
   `..._on_qt` tests are from the old painter. Drop the hooks' tests; keep the
   rule if it still exists in `SdlArena`/`Stage`.
3. **Renamed APIs.** `SdlApp._tick` -> `tick`, `_buffer` -> `grid`, the effects
   module is `sdl_front.effects`, `VOID` and `ChronicleScreen` were renamed,
   `Action.WAIT` is gone (there is no wait verb: take a step), `ShopScreen`'s
   body size moved, and `SdlTurning` no longer carries its battle.
4. **A few flow assertions** were written for the old title/arena flow; check
   them against the screen that is actually there.

Everything in this file is coverage the current suite does not have -- the arena
and its wounds, the shop, the pack, the chronicle and level-up -- so it is worth
the walk.
