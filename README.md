# Unprepared

A stealth & theft RPG built with **pygame** and **PyOpenGL**.
Sneak through a small town, pick locks, pickpocket NPCs, loot shelves,
fence stolen goods and stay out of sight of the guards who remember what
you did - and will fine or jail you for it.

```
python main.py
```

The game opens on a start menu (Continue / New Game / Load Game / Graphics
Settings / Exit - *Continue* appears once there is a save and picks up the
newest one). On first launch it benchmarks the renderer for a moment and picks
a graphics preset; change it any time from the menu.

| Key | Action |
| --- | --- |
| `W A S D` / mouse | move / look |
| `Left Shift` / `Left Ctrl` | sprint / toggle crouch (the camera drops, you move at half speed; crouching is the *theft* stance - no sprinting while crouched) |
| `E` | interact: open/close doors (whatever part of the door is under the crosshair), talk or trade, search shelves, tables and lockboxes, mine ore (with a pickaxe), forge lockpicks at the anvil |
| crouch + `E` | pick a locked door or lockbox, or pick an NPC's pockets (within 2.5 units) |
| `1` | toggle torch (carrying a lit one is the law after dark) |
| `T` | wait one hour (in a jail cell: asks whether to wait out the whole sentence) |
| `F5` / `F9` | quick save / quick load (`savegame.json`); named saves from the pause menu go to `saves/` next to it |
| `F3` | performance overlay (fps, frame phases, draw counts) |
| `Esc` | pause menu (Resume / Save Game / Load Game / Graphics / Exit to Menu); inside a screen or question: back out |
| `Enter` / `Esc` (or `Y` / `N`) | answer a yes/no question |
| `Tab ↑ ↓ Enter Esc` | trade / pickpocket / container screens: Tab switches column, Enter moves one item (or grabs a handful of coins) |
| `↑ ↓` | scroll the inventory panel (outside menus) |
| `← → Space Esc` | lockpicking mini-game |

## Requirements

```
pip install -r requirements.txt          # pygame, PyOpenGL, numpy
pip install -r requirements-dev.txt      # + pytest (for the test suite)
```

GLU is **not** required (the renderer builds its own projection/view matrices).
numpy is used for the NPC navigation grid. Lighting uses a small GLSL 1.20
shader when available and falls back to fixed-function lighting otherwise
(the *low* preset uses the fallback on purpose).

## Commands

| Command | What it does |
| --- | --- |
| `python main.py` | play |
| `python tools/textures/gen_textures.py [--out DIR] [--seed N] [--only key ...]` | regenerate the procedural PNG textures in `assets/textures/` (21 keys: ground, wall, building, wood, door, roof, roof_slate, stone, ore, iron, lockbox, sun_glow, ...) |
| `python tools/benchmark.py [--frames N] [--presets low medium high] [--json out.json]` | open the window, render fixed camera views at each preset and print avg/worst frame times per phase plus the preset the game would auto-select |
| `./run_tests.sh [fast]` | the whole test suite (`fast` = headless only); display tests run under `xvfb-run` automatically when there is no `$DISPLAY` |
| `pytest -m "not display"` | unit tests + scenario goldens (~75 s) |
| `UNPREPARED_UPDATE_GOLDENS=1 pytest tests/regression` | re-record the scenario goldens after an intended behaviour change (review the diff) |
| `python -m tests.parity.render_gallery [scenario ...]` | render the capture frames of scripted scenarios to `tests/parity/_artifacts/gallery/` for eyeballing |

## Project layout

```
main.py                 thin entry point
unprepared/             the game package (see docs/ARCHITECTURE.md)
  config.py             every tunable number in one place (frozen dataclasses)
  graphics.py           GraphicsSettings: presets high/medium/low, persisted next to the save
  perf.py               FrameProfiler, renderer detection, preset recommendation
  ui.py                 Menu / MenuItem (pure data + callbacks)
  core/                 3D math, message log, day/night rules
  entities/             Item (ownership), Door (leaf / bars), Player, NPC (+ memories, purse), SkillTree
  world/                data-driven levels (areas, buildings, jail), World state (indoors, solid people,
                        curfews), NPC navigation grid (A*), save slots (v5)
  systems/              movement, collision, targeting (crosshair ray), transfer screens, lockpicking,
                        progression (one XP/odds rule for every skill), stealth checks, commerce,
                        crafting, justice (fines, eviction, jail)
  game.py               headless simulation + action API (no pygame / OpenGL imports)
  input/                key bindings, pygame event -> action mapping
  rendering/            textures, primitives (doors, bars, tables), atmosphere, shaders, lighting, models,
                        sky (sun halo, stars), buildings (floors, ceilings, roofs), scene, text, HUD + menus
  app.py                pygame window, screens (start / playing / pause / save / load / confirm / graphics), main loop
assets/textures/        PNG textures (missing ones render as a magenta placeholder)
tools/                  texture generator CLI, benchmark CLI
tests/                  unit, regression (goldens), parity (vs the frozen prototype), display suites
docs/ARCHITECTURE.md    design notes, extension guide, change log
```

## Gameplay notes

* **Routines.** NPCs sleep, eat, work and patrol on daily schedules, walking
  path-found routes and operating the doors they are allowed through. Barnaby
  trades from behind his counter 08:00-13:00 and 14:00-20:00 (the shop door is
  unlocked - not opened - for business), eats stew from his back-room table and
  locks his house whenever he is out or asleep. Raz the fence lives in the
  hideout; three guards rotate 8-hour shifts out of the guard house, and Jailer
  Hesk keeps the jail.
* **Doors and keys.** Owning a door does not open it: every NPC needs the key
  item in its pockets (guards carry a guard-house key; Hesk also the cell key).
  NPCs shut behind them whatever they opened, relock what was locked and always
  lock their own doors - even ones you unlocked. Keys you use only *unlock*;
  press `E` again to open. A beam tops every doorway. Every NPC gets a fresh set
  of keys and supplies at midnight (guards daily, Barnaby and Raz every third day).
* **Indoors and out.** Buildings have floors, ceilings and roofs, and their walls
  muffle sound: footsteps in the street reach a sleeper inside at a quarter of
  their noise, so running past the guard house wakes nobody - running around
  *inside* it does. A shout for the guards carries across town in the open and
  about half as far through walls; only guards within earshot come running.
  Every room has a wall lantern and every table a candle (generated from the
  level, so new houses are lit automatically); NPCs light their torches wherever
  it is actually dark - outdoors at night or in an unlit room - and put them out
  when they step into the light.
* **Solid people.** You cannot walk through NPCs and they cannot walk through you
  or each other: someone in the way is stepped around, a crowd converging on one
  spot stands *around* it, and an NPC hemmed in for long gives up and tries again
  on the hour.
* **Seen vs heard.** Noise only wakes NPCs and makes guards walk over to look;
  it never raises the alarm by itself. Being *seen* does: suspicion builds with
  visibility and distance inside an NPC's field of view, and at 100 the crime
  is declared. Sneaking (crouch-moving) is a skill roll once a second - success
  hides you from that NPC's sight; your Sneak skill also quietens your steps.
  Guards tell you off once - "you there, what are you skulking about for?" - and
  give you a few seconds to comply before the alarm can go up; the same warning
  is not repeated for a while. A guard's dressing-down is delivered to your face:
  you turn to look at them.
* **Trust, trespass and curfews.** Houses, the guard house and the jail cell are
  restricted; lingering there without being trusted (Raz trusts you in the
  hideout) earns a warning and mounting suspicion. A fence's house is always open
  to you by day - the standing rule - and nobody, guards included, objects. Even
  a welcome guest is asked to leave late at night: the host asks, waits, asks
  again and finally shows you the door. After dark the law requires a lit torch. The jail house itself is
  public and its door is never locked - only the barred cell is off limits.
* **Crimes, fines and jail.** Each guard keeps a memory of your crimes -
  witnessed ones for 3-5 weeks, reported ones for 3-5 days. The next time a
  guard with a grudge sees you, any screen you had open closes, you turn to face
  them, stolen goods go back to their owners and you are charged the fines: pay
  up (and, if you were somewhere you had no business being, get thrown out), or
  go to jail. Your controls lock for a couple of seconds while it sinks in, and
  the march to the cell waits a moment longer before the screen fades. Jail means gold confiscated, your belongings locked in the
  confiscation lockbox (except one lockpick), one day per 20 g owed (1-14 days),
  the screen fading to black and back in the cell. The cell is a barred gate that
  is *sealed* while you are inside - the jailer never opens it to check on you,
  however much noise you make. You are released at 06:00 on your last day: the
  bars and the lockbox are opened, your things are yours to take back (never
  "stolen"), and the jailer waits - even in the middle of the night - until you
  have left before going back to his routine. Picking your way out earlier is a
  jailbreak. Press `T` in the cell to wait out the whole sentence.
* **Merchants and money.** Everyone carries coin: guards a little, Barnaby and
  Raz a lot, so they can pay for what you sell (a merchant who cannot afford
  something says so). Purses are topped back up every three days with the
  restock, never cut. Pickpocketing shows the victim's purse as the first row -
  each lift grabs up to 20 coins. Merchants never sell their keys; crouch and
  pick their pockets instead (or plant something on them). Shop shelves can be
  looted - in view of the shopkeeper that is shoplifting, unless your Stealing
  skill keeps it unnoticed; he counts stock when opening and closing and shouts
  for the guards, who come to take the report and note whether they saw you
  lurking there. Stolen goods show a red `(S)` tag; a fence launders what it buys.
* **Skills.** Six skills - Sneak, Lockpicking, Pickpocket, Stealing, Barter,
  Smithing - all follow one rule: rewards pour in early and dwindle as the skill
  grows (an elite earns about a fifth of a novice's XP for the same deed), odds
  climb smoothly towards near-certainty (an elite sneak is all but invisible at
  noon in front of a guard, an elite pickpocket barely ever fumbles), and the
  value of what you handle sets the reward (a 300 g necklace teaches far more
  than a spool of thread; a sleeping victim less than an awake one; a guard more
  than a merchant). Failing still teaches a little. Sneak XP flows whenever you
  crouch-move: a trickle even when alone, more near anyone who has not noticed
  you (sleepers and turned backs alike - pottering about a sleeping shopkeeper's
  house is the classic way to train early on), a stream right under an awake
  nose, more for guards. Barter improves prices. Smithing decides the
  anvil: a novice often ruins the ore and gets one pick when it works; an elite
  gets up to fifteen picks per ore.
* **Day and night.** Sun (with its halo) and moon cross the sky, stars come out,
  fog closes in after dark and torches (yours and the guards') light the way.

## Tests

```
./run_tests.sh              # everything (display tests under xvfb-run when headless)
./run_tests.sh fast         # headless suite: unit tests + scenario goldens
pytest -m display           # OpenGL smoke tests, menu driving, benchmark tool, prototype parity
```

* `tests/unit` - ~530 unit tests for every module (entities, world, systems, game API, input, save slots, menus, textures, perf).
* `tests/regression` - 28 scripted play-throughs (`tests/parity/scenarios.py`)
  replayed headlessly and compared with committed golden state files
  (`UNPREPARED_UPDATE_GOLDENS=1` re-records). Pixel goldens (local,
  renderer-specific) can be recorded the same way for `test_pixel_goldens.py`.
* `tests/parity` - runs the **original prototype** (frozen in `tests/baseline/`)
  side by side with the game for the player-loop scenarios that must still
  match, checks the prototype's crash is fixed and that ESC now pauses instead
  of quitting, plus randomised checks of the perception rules kept verbatim.
* `tests/display` - launches the real app: default and custom resolutions, a
  missing-asset run, `python main.py`, the start/pause/save/load/confirm/graphics
  menus driven by synthetic key events (including Continue and Exit to Menu), and
  `tools/benchmark.py`.

See `docs/ARCHITECTURE.md` for the design and the change log.
