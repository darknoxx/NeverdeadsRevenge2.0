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
everything above them: an SDL window, a pattern buffer, and a shader that
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
cleansing spring that washes a curse off for a price (45% of floors, and
**two** of them from the fifth floor down, where the chests have had time to
pile curses on), loot that may be standing under something you have to fight
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

### The four heroes

| | name | title | the shape of it |
| --- | --- | --- | --- |
| **N** | Noxx | the swift one | Quick hands, quicker feet. Wins fights he should lose: strike, vanish, come back before they can swing. Fragile, but every opening is lethal. REVENGE: **BLACK TIDE** (speed). |
| **Y** | Yeti | the unmoved | Slow as a glacier and about as easy to move. Does not dodge and does not rush; everything that reaches him goes through the armour first, and most things do not. REVENGE: **FROZEN FORTRESS** (armour). |
| **W** | Walkyrion | the even blade | No weakness worth naming and no trick worth relying on. Strikes on time, takes the hit he has to, and is still standing when the screaming stops. REVENGE: **AURAL BLADE** (damage). |
| **I** | Inferno | the short fuse | Hits hardest and dies soonest. Every blow is a gamble, and the fire only makes the odds louder. REVENGE: **WILD FIRE** (crit). |

### The Tenth Door

Once a run has escaped through the rift, the title offers **THE TENTH DOOR**:
the same dungeon, started on floor 10 with the house's credit -- level 18 and
three pieces from the deep. Every tenth floor from there is a landing with one
question. **Bank the run** and take the number it has, or **push on**: the next
ten floors are worth 1.25x more and pay 1.25x coin, but death takes the whole
wager -- score and purse both. Banking is the only way to keep the coin. The
first slice ends at the door; ring rules and boons come after it.

## What is down there

### Loot and gear

- **Two draughts**: a potion (heals 8) and an elixir (heals 20). `q` drinks the
  cheapest one that covers the wound, because wasting half an elixir is the
  mistake everybody makes once. The **pack holds two things** to start with;
  the shop sells slots up to seven, each dearer than the last, and a full pack
  leaves the loot where it lies and says why.
- **Twenty-seven weapons** (the rusted tooth, the grey bite, the long hunger, the
  frostbite...) and **ten pieces of armour** (the thin hide, the rune plate,
  the ashfall cloak...), each with its own modifiers.
- **Five strange draughts**, none of them medicine: each lays a rule on the
  floor and lasts only until the stairs. THE THIN VEIL (nothing looks at you
  until you strike), THE KINDLED BREATH (every blow you land sets it burning),
  THE SHORT CROWN (every kill pays REVENGE twice), THE CARRION TONGUE (walk
  where something died and it feeds you -- and while it works, the floor's
  dead show as dim blood spots), and THE GALLOWS ROAD (the dead hold the hunt
  back: nothing that hunts can walk where something died, though the hero
  can). They spawn from their *own* budget, so the medicine is
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
| THE SALT CIRCLE | the first blow of every fight is refused |
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

Two counters keep the shelf honest. Beside the purse, **upgrades 5/40** is the
whole permanent shelf bought so far -- the bloodlines included, wild offers not,
because those are a run's bargain. And every permanent row carries its own
**(3/5)**: the Vigour you hold against the Vigour there is.

**Permanent upgrades** buy things that survive the run:

| upgrade | price | what it does | stacks |
| --- | --- | --- | --- |
| Vigour | 140g, then dearer each time | +5 max health | up to 5 |
| Haste | 220g, then dearer each time | +0.12 speed | up to 3 |
| Whetstone | 140g | +1 damage | up to 3 |
| Edge | 180g | +5% crit chance | up to 3 |
| Lantern | 180g | +1 sight | once |
| Pack | 100g, then 150, 200, 250, 300 | +1 pack slot -- the pack starts at 2 and stops at 7 | up to 5 |
| Blood Bargain | 170g | +0.15 speed, for good -- and -4 max health, for good | up to 2 |

**Bloodlines** are one per hero, and each only works for its own -- the shelf
is shared, the gift is not. They are the reason to play all three:

| bloodline | hero | what it does | stacks |
| --- | --- | --- | --- |
| Bleeding Edge | Noxx | a crit leaves a wound that bleeds longer (+2 turns per stack) | up to 3 |
| Hoarfrost | Yeti | 15% chance per stack to freeze whoever strikes you | up to 3 |
| Ring of the Bell | Walkyrion | 20% chance per stack to throw what you hit | up to 3 |

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

- **The Almanac** is one book with four chapters, opened from the title (`a`) or
  from the pause menu mid-run. `←` `→` turn the tabs, or **LB**/**RB** with a
  pad, or `c` `b` `a` `w` to land on one directly.
  - **The chronicle** collects **37 torn pages** found on the floors. Each page
    is prose, and once found it is in the book for good; the chronicle shows the
    full text of every page you have, and marks the ones you have not.
  - **The bestiary** has a page for every monster in the dungeon -- **24** of
    them, alphabetical -- and a page is written the first time a run *kills*
    that monster. The page shows the figure at its painted size, its numbers
    (health, damage, speed, armour, evasion, gold), what its rule does, how it is
    answered, and a paragraph of its own. The figure is drawn at **twice** its
    painted size when the page is wide enough and at 1:1 when it is not -- never
    at some fraction in between, because a resampled monster is a blur and a
    whole step is not. Killing one for the first time opens
    the page in the fight, on a card, once the blow has finished landing.
  - **The armory** has a page for every blade in the game -- **26**, sorted by
    name without the article, since half of them are called "the something" --
    and a page is written the first time a run *takes one up* (a blade walked
    past is not a blade known). The page shows the painted blade at 1:1, what it
    adds and what it opens, where it comes from, and the house's paragraph on
    it. The pickup card says the page was written, so the find is announced once
    and not twice.
  - **The wardrobe** has a page for every coat in the game -- **10**, sorted the
    same way -- and a page is written the first time a run *puts one on*. Taking
    a coat up puts it on (what you took off stays on the floor), so the same act
    that changes the numbers writes the page. The page shows the painted coat at
    1:1, what it adds, where it comes from, a line of what it is, and the
    house's paragraph. Until a coat is worn its name is a row of question marks,
    like the blades'.
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
| `enter` | interact: loot, stairs, spring, chest, or speak |
| `>` | take the stairs down |
| `q` | drink the cheapest draught that covers the wound |
| `i` | the pack -- `↑↓` choose, `enter` drink it, `x` set it down (**X** on a pad) |
| `l` | the legend of glyphs |
| `f` | the hero's ultimate, once a floor (see above) |
| `c` | the hero sheet |
| `?` | controls and reference |
| `r` | the borrowed hour |
| `m` | the Almanac, from the floor or a fight (the pause opens it too) |
| `v` | in a fight: the Almanac, open at the enemy being aimed at |
| `esc` | pause (`r`/`esc` resume, `e` settings, `c` controls, `a` the Almanac, `z` field zoom, `s` save and quit, `q` to title, `m` sound) |

### The controller

An Xbox pad drives the whole game -- and anything SDL's mapping database knows,
which includes a DualShock, a DualSense and the Retroid's own controls. The
D-pad and the left stick both move, the shoulders cycle, the triggers page, and
the pad rumbles when a blow lands.

| pad | floor | fight | menus |
| --- | --- | --- | --- |
| left stick / D-pad | walk (eight directions) | aim and lists | navigate |
| **A** | the one useful thing | confirm the marked verb | confirm / buy |
| **B** | the pack | back one level | back |
| **X** | the ultimate | the tricks | set a bottle down (pack) |
| **Y** | drink | the draught | -- |
| **LB / RB** | sheet / legend | previous / next target | previous / next tab |
| **LT / RT** | -- | -- | page up / down |
| **L3** | the borrowed hour | -- | -- |
| **R3** | controls and reference | inspect the enemy | -- |
| **Back** | the Almanac | the Almanac | the Almanac (pause) |
| **Start** | pause | -- | close; on the title, the settings |

Two of those are worth spelling out. **Flee is never B**: the four verbs are a
row, the stick walks it, and A takes whatever the marker is on -- B only ever
backs out one step. And **the pad's hints follow it**: the moment it is the last
thing touched, the hints read A and B rather than enter and esc.

The name on the scoreboard is spelled the same way: the card ends a run with the
alphabet on it, the D-pad walks that alphabet, **A** takes the letter under the
cursor, **B** takes one back (and, with nothing left, keeps the name off the
board), and **Start** keeps it. **X** still rolls a name. A keyboard types as it
always did, and the cursor is only a convenience there.

### Settings

The title's **SETTINGS** row (`e`, or **Start** on a pad) is where the glass and
the sound live: full screen, scanlines, bloom, the CRT curve, and the sound.
`F11`, `F2`, `F3` and `F4` still do the same thing from the keyboard. The same
screen opens from the pause menu (`e` there too), so a setting can be changed
without leaving the run.

**Field zoom** is the pause menu's own switch (`z`), and it draws the overworld's
map at twice the size -- a character is four characters' worth of pixels, the
same drawing with a smaller camera -- and leaves the panels and the log at their
own size, because a room is walked in and a panel is read. It lives in the pause
because it is about the room under your feet; the title's settings are about the
glass. It is the overworld's alone: a fight is already drawn to fit its room.

The menus are read sideways: `←` `→` choose, `enter` takes, or press the letter
of the row you want. The Almanac is the one screen that is read like a page:
`←` `→` crosses between the names and the card, `↑` `↓` scrolls
whichever of the two you are in, and `↑` out of the top of a list reaches the
tab row, where `←` `→` pick the book -- chronicle, bestiary, armory (`c`, `b`,
`a` jump straight to one). The **legend of glyphs** lives in its own menu (`l`) --
the sidebar keeps the run, the reference lives one key away. At the foot of the
sidebar sits the **pack**: one square per slot the game can ever sell -- empty
while nothing is in it, the draught's own bottle once it is, and a grey cross for
a slot the shop has not sold yet. Above it are the two ways in: `q` (or **Y** on
a pad) drinks the smallest draught that covers the wound, `i` (or **B**) opens
the pack. The bottle is scaled by whole steps, so it stays the drawing it was. The pause offers
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
dependencies into it, checks that pygame and miniaudio import, and on Linux
adds the game to the applications menu with a real icon -- no sudo, nothing
outside `$HOME`. Run it again any time; it reuses what is already there.
`--dry-run`, `--no-desktop`, `--python PATH` and `--uninstall` are supported.

By hand, if you prefer:

```sh
python3 -m venv .venv
./.venv/bin/pip install -e '.[dev]'
./ndr2
```

`ndr2` runs the game and takes the flags the terminal build had:

```sh
./ndr2 --seed 42     # the same dungeon, again
./ndr2 --no-sound    # start silent
./ndr2 --sound-log   # every sound decision, to /tmp/ndr2-sound.log
./ndr2 --testrun     # the chronicle and the bestiary unlocked, and the purse full
./ndr2 --battle-scene  # straight into a fight
./ndr2 --windowed    # a window instead of the whole screen
```

And without a flag: type **`battle4ever`** on the title screen. It grants exactly what
`--testrun` grants -- 9999 coin, every page of the chronicle, of the bestiary and of the armory --
saves it at once, and answers with a sound.

### The window

The game is drawn by SDL and pygame. It was built twice for a while -- once on Qt
and once on SDL -- and the SDL one won: it plays the same run, draws the same
room, and builds for Windows and (in time) for Android, which Qt did not. So
there is one front end now, and `./ndr2` starts it -- one door, one name, one
parser, and the only launcher in the directory.

```sh
./ndr2 --seed 3 --fps                       # the frame counter, bottom right
./ndr2 --battle-scene --fps                 # straight into a fight
./ndr2 --timings                            # what each stage of the frame costs
```

Same keys, same saves, same settings. `F2`, `F3` and `F4` toggle the scanlines,
the phosphor glow and the CRT curve; `F11` is fullscreen. A machine that cannot
make a GL context gets a plain window instead of a refusal to start.

The game opens on the whole screen, and the grid is worked out from the display
rather than from a fixed window: 1280x800 -- a Steam Deck -- comes out at 128x40
cells with no bars, 1920x1080 at 96x27 with the picture doubled, 2560x1440 at
128x36. `--windowed` asks for a window instead, at the size `--scale` gives.

### Linux, and the Steam Deck

Every release carries an AppImage beside the `.exe`. It is one file, it needs no
installer and no root, and it keeps saves and profile outside itself:

```sh
chmod +x NeverdeadsRevenge2-x86_64.AppImage
./NeverdeadsRevenge2-x86_64.AppImage
```

On a Steam Deck: copy the file over in Desktop Mode, `chmod +x` it, then add it
to Steam under *Games -> Add a Non-Steam Game* and pick it from the list. Start
it once from the desktop first, so the profile is written where you expect it.
The image clears what a launcher puts in front of it (`LD_PRELOAD` and the Steam
runtime's library path) before the game starts: it carries its own Python and
SDL, and the graphics driver belongs to the operating system.
It fills the 1280x800 screen -- no bars, every cell a whole number of screen
pixels -- and the pad works as described above; the Deck's own controls need no
Steam Input layout of their own.

An AppImage mounts itself through FUSE, which SteamOS does not always ship. If
the image refuses to start with a message about FUSE, install it (`sudo pacman
-S fuse2` in a terminal, in Desktop Mode) or run the image without mounting it:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 ./NeverdeadsRevenge2-x86_64.AppImage
```

The image is built on Ubuntu 22.04 in CI, which is what the game promises and
what SteamOS can run. `packaging/linux/build_appimage.sh` makes the same image
locally, but only for the machine it was built on: glibc is forward compatible,
not backwards compatible.

It deliberately ships **no system libraries** -- the C++ runtime above all. A
bundled libstdc++ is put in front of the graphics driver's own, and a driver that
cannot load is a game with no CRT that works perfectly from source. SDL, the
Python runtime and the game are inside; the operating system's libraries are
left to the operating system.

The game needs a display: the design is the screen. Headless environments run
the test suite instead, offscreen:

```sh
./.venv/bin/pytest -q      # the whole suite, engine and UI both
```

## How it is put together

```text
src/neverdeads_revenge/
  core/ world/ game/ persistence.py   the game itself -- no screen anywhere
  desktop/                            the game's own shapes: cells, chrome, art
    theme.py    the palette, and Rich styles translated
    pattern.py  the grid of characters, and how it is read
    render.py   where the sidebar, the log and the plate go
    screens/    every menu and dialog, drawn and key-routed
  sdl_front/                          the window, and the pixels
    glass.py    the shader: integer scaling, scanlines, bloom, geometry
    arena.py    the painted arena: figures, bars and numbers
    paint.py    cells onto a surface, and the frame's paper
    effects.py  the moving pixels: blood, coins, sparks, and the shake
    app.py      the window, the keys, the loop, the settings
packaging/                            the frozen builds, one folder per platform
  windows/    PyInstaller spec for the .exe, and its icon
  linux/      PyInstaller spec, AppDir pieces and the AppImage script
tests/                                engine and UI, over 1,600 at this writing
```

The engine (`core/`, `world/`, `game/`) never imports a UI. The game is a
library that a second client could drive, and the desktop is one client of it.

## Save data

2.0 keeps its own profile in `~/.local/share/neverdeads_revenge2/`, separate
from the terminal build on purpose: experimenting here never touches a terminal
run's scores or chronicle, and the other way around.

Beside the saves is `run.log`: one short record per launch -- the build, the
display server, the grid, whether the frame goes through the glass, and what a
launcher put in front of the game. When Steam starts it, the first fifteen
seconds of frame reports go in as well, because a shortcut has no terminal to
read them in. It is overwritten each time and is only there to be sent with a
bug report.

## Licence

AGPL-3.0-or-later. See `LICENSE` for the text.

In short: play it, read it, change it, share it, sell it — but a copy you pass
on carries its source with it, under this same licence, and so does a version
you put on a server for others to play. There is no warranty.
