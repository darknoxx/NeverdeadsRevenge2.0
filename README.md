# Neverdead's Revenge 2.0

**A turn-based dungeon roguelite, rendered as an old CRT.**

You are Noxx, and you were killed once. Death did not keep you, and the body
walked out of the dark with something left to settle. Under the mountains of
Karpas there is a dungeon for people like that: ten floors, monsters that get
harder every step down, chests that charge a curse before they open, and a
shop that sells time. Somewhere below, a rift tears the dark open. **The way out
is on floor ten.**

This is the desktop build of the **terminal roguelite Neverdead's Revenge**. The
dungeon, the monsters, the items, the curses, the gifts, the shop, the save
format and the balance are the same systems as the terminal game -- forked
wholesale and never changed to know a terminal stopped existing. What is new is
everything above them: a PySide6 window, a pattern buffer, and a shader that
puts scanlines, bloom and a toggleable barrel over the picture.

| | |
| --- | --- |
| <img src="docs/screenshots/01_title.png" alt="the title screen" /> | <img src="docs/screenshots/02_prologue.png" alt="the prologue" /> |
| the title, read sideways with `←` `→` | the premise, told once per session |

| | |
| --- | --- |
| <img src="docs/screenshots/03_dungeon.png" alt="floor four" /> | <img src="docs/screenshots/04_shop.png" alt="the shop" /> |
| floor four: the tide charged, a wound taken, the hour kept | the shop, sectioned and priced |

## How a run goes

A run is **ten floors**, each generated fresh: rooms, grass, rubble, a
cleansing spring, loot that may be standing under something you have to fight
for, and stairs down somewhere inconvenient. Enemies scale with the depth, so
the same floor ten that you barely survive at the start is the floor you have
to learn.

Fights are turn-based on an eight-way grid. Everything has speed, and speed
decides how often a turn arrives: Noxx at 1.50 acts half again as often as a
ghoul at 1.00. You win by trading hits better than the other thing, by using
what you carry, and by spending the ground you are standing on.

- **Health, armour, crit, evasion, accuracy** are the numbers that matter.
  Armour is a flat subtraction, so it is worth most against many small blows.
- **Statuses** do the slow work: bleeding, poisoned, burning and chilled all
  tick damage, and the sidebar counts down what is left of them.
- **REVENGE** is the run's own engine. Every kill charges it, and each hero
  collects it differently (see the heroes below). It lapses between floors, so
  it is a charge for the floor it was earned on, not a permanent stat.
- **The borrowed hour** is the undo. With that gift, once per floor the run can
  be turned back one turn, and the death screen offers it one last time: `r`
  takes the death back.

### The three heroes

| | name | title | the shape of it |
| --- | --- | --- | --- |
| **N** | Noxx | the swift one | Quick hands, quicker feet. Wins fights he should lose: strike, vanish, come back before they can swing. Fragile, but every opening is lethal. REVENGE: **BLACK TIDE** (speed). |
| **Y** | Yeti | the unmoved | Slow as a glacier and about as easy to move. Does not dodge and does not rush; everything that reaches him goes through the armour first, and most things do not. REVENGE: **FROZEN FORTRESS** (armour). |
| **W** | Walkyrion | the even blade | No weakness worth naming and no trick worth relying on. Strikes on time, takes the hit he has to, and is still standing when the screaming stops. REVENGE: **AURAL BLADE** (damage). |

## What is down there

### Loot and gear

- **Two draughts**: a potion (heals 8) and an elixir (heals 20). `q` drinks the
  cheapest one that covers the wound, because wasting half an elixir is the
  mistake everybody makes once. The **pack holds two things** to start with;
  the shop sells slots up to seven, each dearer than the last, and a full pack
  leaves the loot where it lies and says why.
- **Thirteen weapons** (the rusted tooth, the grey bite, the long hunger, the
  patient knife...) and **ten pieces of armour** (the thin hide, the rune
  plate, the ashfall cloak...), each with its own modifiers.
- **Five strange draughts**, none of them medicine: each lays a rule on the
  floor and lasts only until the stairs. THE THIN VEIL (nothing looks at you
  until you strike), THE KINDLED BREATH (every blow you land sets it burning),
  THE SHORT CROWN (every kill pays REVENGE twice), THE CARRION TONGUE (walk
  where something died and it feeds you), and THE DRUNKARD'S ROAD (your feet
  choose the way now). They spawn from their *own* budget, so the medicine is
  never thinned by them -- a floor holds its draughts and a curiosity or two --
  and `q` never touches one: the strange bottles are drunk by name, from the
  pack.
- **Fourteen amulets**, each a passive rule rather than a number: the last
  ember (every kill puts two health back), the coin hand (every coin is worth a
  quarter more), the wayfarer (you know the way out when you arrive), the
  mirror (whatever strikes you takes two back), the rune heart (+1 max health
  per floor down), and the rest.
- Gear **equips on pickup**, and whatever it replaces is set down beside you --
  so trying something on is always free, and nothing found can be lost by
  picking it up. Every pickup opens a page that says what it is and what it
  does, before you walk on with it.

### Curses and chests

A chest names its price before the lid moves: it will charge you a **curse**
for whatever is inside. You can pay and open it, or pay and leave the reward
where it lies to take **fame** instead -- and fame is score. There are thirteen
curses, and none of them is small:

| curse | what it takes |
| --- | --- |
| WITHER | a quarter of your health, taken now and for good |
| BLEED | a drop of blood every tenth step |
| FRAIL | two points of armour, gone |
| HEAVY | a quarter of your speed |
| DIM | your sight, cut to five paces |
| FAMINE | half of what every draught is worth |
| TITHE | a drop of blood for every thing you kill |
| COMPANY | two more shapes on every floor |
| HESITATION | every fifth turn, the step is not yours |
| ASHEN HAND | half of what every coin is worth |
| LONG DARK | your sight, cut to one pace |
| FEVER | your blows swing twice as wide |
| CRAWL | three of what you leave alive follows you down |

### Gifts

Gifts are **rule changes**, not loot names. Seventeen of them exist, and each
one rewrites a piece of the game while it is held:

| gift | the rule it changes |
| --- | --- |
| THE LONG REACH | your blow reaches two squares, and nothing solid in between |
| THE STEP BEHIND | every fifth step costs you no time at all |
| THE KIND DARK | every floor you descend lifts one curse |
| THE HOLLOW ROAD | walk into stone, at two health a square |
| THE BORROWED HOUR | once a floor, take back the last thing you did |
| THE ASH MARK | every blow you land leaves it burning |
| THE OPEN WOUND | your first blow on each thing leaves it bleeding |
| THE SLOW KNITTING | every twentieth step puts one health back |
| THE HUNGRY ROAD | every square you leave cuts whatever walks after you |
| MOMENTUM | the longer you walk one way, the harder your next blow lands |
| THE DEBT OF BLOOD | what you are made to bleed is owed back on your next blow |
| THE LAST BREATH | at three health or less: you hit twice as hard and are harder to hit |
| THE DARK KNOWS | you see every monster on the floor, through the walls |
| THE SALT CIRCLE | wait three turns in a row and nothing can reach you |
| THE BLOOD PRICE | every blow you take scatters coin at your feet |
| THE KINDNESS | whoever you meet hands you something to drink |
| NOTHING WASTED | a draught you drink shatters into everything beside you |

### The hunter

From the fifth floor on, sometimes, a hunter spawns: fast, scaled up, and
already moving. It knows where you are because that is all it does, and the game tells
you when a floor has one. Everything else has to see you before it comes for
you; the hunter does not.

### The shop

Between runs the shop spends the coins you died with. It is priced honestly:
what the purse cannot reach is drawn grey with the reason beside the price. The
shelves are sectioned -- **supplies, gear, amulets, upgrades, wild offers** --
and a purchase rings the till.

**Permanent upgrades** buy things that survive the run:

| upgrade | price | what it does | stacks |
| --- | --- | --- | --- |
| Vigour | 140g | +5 max health | up to 3 |
| Haste | 220g | +0.12 speed | up to 2 |
| Lantern | 180g | +1 sight | once |
| Pack | 100g, then 150, 200, 250, 300 | +1 pack slot -- the pack starts at 2 and stops at 7 | up to 5 |
| Blood Bargain | 170g | +0.15 speed, for good -- and -4 max health, for good | up to 2 |

**Wild offers** rotate between runs and sell exactly the risk their name
suggests. A deal whose cost is a footnote is not a decision, so every one reads
out its pitch and its catch before you take it:

| offer | price | the pitch | the catch |
| --- | --- | --- | --- |
| the blind box | 45g | something from the deep, unseen | you do not get to look first |
| the pact | 85g | coins are worth half again as much | you start cursed, and the dark picks |
| greed | 75g | coins are worth double | everything below is a fifth tougher |
| grave goods | 105g | grave iron in hand from the start | it is heavy, and it slows you down |
| second wind | 120g | the first killing blow does not land | once a run, and no more |
| the wager | 65g | a coin, thrown into the dark | one face a blade, the other a curse |
| the hollow tooth | 115g | every kill feeds you three | and no draught will ever stay down |
| the pilgrim's toll | 95g | coins are worth half again as much | the dark takes five for each floor |
| the count's favour | 125g | every thirteenth kill heals you whole | you do not want to know who counts |
| the mirror of hunger | 115g | a draught heals half again as much | and something drinks beside you |
| the nameless run | 105g | coins are worth double | and the score is worth half |

## The ultimates

Every hero has one ask a floor, bound to `f`, from **level 7** on. The
sidebar carries the promise: grey until the level, breathing in the hero's own
colour while it is live, grey again once the floor has had its answer.
(`--testrun` lowers the gate to level 1, for looking at them. Level seven is
about a floor or two of real clearing, so the ask belongs to a good run rather
than to a perfect one.)

| hero | the ask | what it does |
| --- | --- | --- |
| Noxx | **give in to the void** | Atritas, a dark shadow, walks beside him for 40 turns, hunting anything within five paces -- it blinks beside the thing it strikes, so you see it happen. Every wall is glass *while he walks*, and the walls close again over whatever the hero never actually saw. The price: one heart's worth every eighth turn, never the last one -- and every kill the shadow makes hands one heart back, so wading into a group pays. |
| Yeti | **build the Frozen Fortress** | A wall of ice rises nearby with twice Yeti's health. Everything hostile on the floor -- hunter included -- prefers it to Yeti and chews on it instead. It lasts 80 turns or until it breaks, and while it stands the whole floor lies on white with every creature and every item drawn black. The price: the cold closes Yeti's sight to five paces. |
| Walkyrion | **shatter the golden bell** | He drives his blade into the floor. Three paces of ground answer: walls come down to plain floor (the dungeon's own edge stays), everything hostile there is cut and thrown two paces, and anything that dies pays out like any kill. A room, not a duel. |

## Between the runs

- **The chronicle** collects **37 torn pages** found on the floors. Each page is
  prose, and once found it is in the book for good; the chronicle shows the full
  text of every page you have, and marks the ones you have not.
- **The board** keeps every finished run, best first, with the name you left.
- **Fame** is score: a chest's curse taken for the reward pays you nothing, but
  a chest's reward *left* for the curse pays a point of fame, which raises the
  run's score multiplier.
- **The prologue** tells the premise once per session, between the hero choice
  and floor one. After that the game starts without a speech.
- **Save and continue**: `s` in the pause writes the run in progress to
  `run.json`; the title then offers it back as `c CONTINUE`. Picking it up
  consumes the slot and restores the run whole -- floor, health, turns walked.
  A save from another build is refused rather than crashing.

## The CRT

The picture is a **pattern buffer**: a grid of characters turned into one flat
image, which a fragment shader then draws with scanlines, bloom and a barrel
distortion. The scale lands the grid near **a hundred columns** -- one pixel per
character step on a small laptop, two on 1080p, four on 4K -- and the frame is
letterboxed exactly where the number does not divide.

Small text is not a smaller dungeon. The log keeps a face of its own, drawn
straight onto the frame, with the sidebar's curses, gifts, effects and statuses
above a rule and the legend of glyphs under another.

| key | what it does |
| --- | --- |
| `F11` | fullscreen, and back (the game **starts** fullscreen) |
| `F2` | scanlines on/off |
| `F3` | bloom on/off |
| `F4` | the CRT's curve on/off |

The glass remembers its effects between runs, and every toggle is announced on
the glass itself.

## Controls

| key | what it does |
| --- | --- |
| arrows, `wasd`, `hjk` | move (`l` is the legend now) |
| `y` `u` `b` `n` (and Home/PgUp/End/PgDn) | move diagonally |
| `.` or `space` | wait a turn |
| `enter` | interact: loot, stairs, spring, chest, or speak |
| `>` | take the stairs down |
| `q` | drink the cheapest draught that covers the wound |
| `i` | the pack -- `↑↓` choose, `enter` drink it, `x` set it down |
| `l` | the legend of glyphs |
| `f` | the hero's ultimate, once a floor (see above) |
| `c` | the hero sheet |
| `?` | controls and reference |
| `r` | the borrowed hour |
| `esc` | pause (`r`/`esc` resume, `c` controls, `s` save and quit, `q` to title, `m` sound) |

The menus are read sideways: `←` `→` choose, `enter` takes, or press the letter
of the row you want. The **legend of glyphs** lives in its own menu (`l`) --
the sidebar keeps the run, the reference lives one key away. The pause offers
**CONTROLS**, and the title offers **DELETE PROGRESS**: it asks for the word
DELETE to be typed out, because a confirm key is a reflex and a word is a
decision. Dialogs never answer their own opening press, and the two
screens that want a *held* key -- the prologue and the death tally -- fill a bar
while it is held and refuse taps, so nothing walks through them by accident.
The page that opens when something is picked up -- a blade, a curse, a gift --
closes on `enter` (or `escape`) and on nothing else: a wraith's curse lands
mid-fight, and the direction key already under your thumb should not be the
thing that eats it.

## Getting started

```sh
./install.sh
```

The installer creates a `.venv` in this directory, installs the game and its
dependencies into it, checks that PySide6 and miniaudio import, and on Linux
adds the game to the applications menu with a real icon -- no sudo, nothing
outside `$HOME`. Run it again any time; it reuses what is already there.
`--dry-run`, `--no-desktop`, `--python PATH` and `--uninstall` are supported.

By hand, if you prefer:

```sh
python3 -m venv .venv
./.venv/bin/pip install -e '.[dev]'
./ndr2
```

`ndr2` runs the windowed game and takes the flags the terminal build had:

```sh
./ndr2 --seed 42     # the same dungeon, again
./ndr2 --no-sound    # start silent
./ndr2 --sound-log   # every sound decision, to /tmp/ndr2-sound.log
./ndr2 --testrun     # the chronicle unlocked and the purse full
```

The game needs a display: the design is the screen. Headless environments run
the test suite instead, offscreen:

```sh
./.venv/bin/pytest -q      # 1,388 tests, engine and UI both
```

## How it is put together

```text
src/neverdeads_revenge/
  core/ world/ game/ persistence.py   the game itself -- no screen anywhere
  desktop/                            the PySide6 presentation layer
    theme.py    the palette, and Rich styles translated
    font.py     a monospaced cell, drawn without antialiasing
    buffer.py   the grid of characters -> an image
    crt.py      the shader: integer scaling, scanlines, bloom, geometry
    render.py   the map, the sidebar and the log strip, as cells
    effects.py  the moving pixels: blood, coins, sparks, and the shake
    app.py      the window, the keys, the loop, the settings
    screens/    every menu and dialog, drawn and key-routed
tests/                                engine and UI, 1,388 at this writing
```

The engine (`core/`, `world/`, `game/`) never imports a UI. The game is a
library that a second client could drive, and the desktop is one client of it.

## Save data

2.0 keeps its own profile in `~/.local/share/neverdeads_revenge2/`, separate
from the terminal build on purpose: experimenting here never touches a terminal
run's scores or chronicle, and the other way around.

## Licence

MIT. See `LICENSE`.
