# Making Game Implementation Go Smoothly
## Lessons from the Prisoner's Dilemma and OCCLUEdo Ports

**Date:** 2026-03-04
**Author:** Claude (Sonnet 4.6), WSZ6-portal project

---

## Overview

This document reflects on the experience of implementing the Prisoner's Dilemma as a
SOLUZION6 game for the WSZ6-portal, drawing also on the earlier OCCLUEdo porting work.
It is intended as a practical guide for future developers — human or AI — who need to
add a new game to the portal.

The goal is not to document what was done, but to identify the patterns that made things
go smoothly, the specific points where things went wrong, and the practices that would
have prevented or caught those problems earlier.

---

## Part 1 — What Went Well

### 1.1 Reading a closely related example first

The single most effective practice was thoroughly reading the Rock-Paper-Scissors PFF
(`Rock_Paper_Scissors_SZ6.py`) before writing any code. RPS is also a 2-player
simultaneous-choice game, which meant it provided nearly all of the implementation
patterns needed: `parallel = True` on the choosing phase, `current_role_num` for the
Textual engine's turn-cueing logic, the `active_roles` list attribute, and the
`text_view_for_role()` masking pattern.

**Best practice:** Always identify the existing game that most closely resembles the one
you are about to build. Read it completely — not just the interesting parts — before
writing anything. Time spent reading code is never wasted.

### 1.2 Verifying arithmetic before writing GSL

Before writing `Test_PrisonersDilemma.gsl`, an independent Python assertion test was run
to verify the score sequence for the planned 5-round test scenario:

```
Round 1 (C,C): [0,0] → [3,3]    ✓
Round 2 (D,C): [3,3] → [8,3]    ✓
Round 3 (D,D): [8,3] → [9,4]    ✓
Round 4 (C,D): [9,4] → [9,9]    ✓
Round 5 (C,C): [9,9] → [12,12]  ✓
```

This meant the GSL file was written exactly once, with correct `Assert_state` values on
the first attempt. Trying to write test scripts by guessing expected values and correcting
them by running the test is painful and slow.

**Best practice:** For any game with numeric accumulation (scores, counts), manually
trace the arithmetic for your planned test scenario first. Write the GSL only after the
numbers are confirmed.

### 1.3 Running the PFF self-test before touching the portal

`Prisoners_Dilemma_SZ6.py` contains a `__main__` block that exercises every phase and
operator sequence end-to-end in the terminal. Running this caught the ASCII box alignment
bug (see §2.1) before the GSL test was even written, let alone run against the portal.

**Best practice:** Always write and run a standalone self-test in the PFF's `__main__`
block before attempting integration with the portal. Portal startup, venv activation, and
GSL execution add layers of friction. The self-test removes them.

### 1.4 Understanding the GSL command vocabulary before writing scripts

A critical early step was reading `commands.py` to confirm that `Op` takes
`<user> <operator_name>` (by name), not `<user> <index>`. The GSL spec itself says this
clearly, but seeing the implementation reinforced it. Had GSL scripts been written assuming
index-based `Op` calls, every `Op` line in the test would have been wrong.

**Best practice:** Read the GSL spec (`Game-Setup-Language-Spec.md`) before writing your
first GSL script. Pay special attention to: the `Op` syntax (name-based), the `Select_Game`
slug format, and how `Assert_state` handles nested keys and list indices.

### 1.5 Designing educational content as part of the game, not as an afterthought

The `jit_transition` messages and `goal_message()` analysis were designed alongside the
state machine, not added afterwards. Because game-theory concepts (Nash equilibrium, Pareto
optimality, Tit-for-Tat) were planned from the start, they shaped which state attributes
were needed (`choices`, `history`) and what the `reveal` phase had to expose.

Retrofitting educational content onto a working game would have required re-examining state
design. Doing it first kept the implementation coherent.

**Best practice:** For games with an educational purpose, write the educational messages
alongside the state machine design, not afterwards. The messages clarify what state
information must be preserved and surfaced.

---

## Part 2 — Trouble Spots and Gaps

### 2.1 Dynamic content in fixed-width ASCII boxes

**What happened:** The `_INTRO_TEXT` template contained a line like:

```python
f"║  This game lasts {max_rounds} rounds.  After each round...  ║"
```

The box was designed for `max_rounds=5` (1 digit). When `max_rounds` is a 2-digit number,
the line is one character longer, breaking the ASCII box borders.

**Fix:** A `_build_intro(max_rounds)` function was introduced. It constructs the
variable-length line separately and pads it to the box width using `ljust(62)`, then
substitutes it into a template string via `replace("__ROUNDS_LINE__", line)`.

**Lesson:** ASCII box art with embedded variable text is fragile. Either:
- Use `ljust` / `rjust` / `center` padding on every dynamic content line, or
- Avoid the pattern entirely: use the Textual `Panel` widget or the portal's HTML
  renderer to produce boxes programmatically.

If fixed-width boxes are unavoidable, write the self-test with at least two different
values of any configurable parameter (e.g., `max_rounds=5` and `max_rounds=10`) to
expose length mismatches.

### 2.2 The slug convention: hyphens vs. underscores

**What happened:** Both GSL scripts were initially written with `Select_Game prisoners_dilemma`
(underscore) because the PFF file and source directory use underscores (`Prisoners_Dilemma_SZ6.py`,
`prisoners_dilemma/`). But the portal slug convention uses hyphens (`prisoners-dilemma`),
matching `rock-paper-scissors`, `tic-tac-toe`, and `occluedo`.

The mismatch meant `Select_Game prisoners_dilemma` would silently fail to find the game
at runtime.

**Fix:** Both GSL files were updated to `Select_Game prisoners-dilemma` before the GSL
test was run.

**Lesson:** The slug-vs-directory naming convention is a perpetual source of confusion.

| Thing | Convention | Example |
|---|---|---|
| Portal slug (URL, database, `Select_Game`) | **kebab-case** (hyphens) | `prisoners-dilemma` |
| `source_subdir` in `install_test_game.py` | **snake_case** (underscores) | `prisoners_dilemma` |
| PFF filename | **Title_Snake_Case** | `Prisoners_Dilemma_SZ6.py` |
| VIS filename | **Title_Snake_Case** | `Prisoners_Dilemma_WSZ6_VIS.py` |

This table should be consulted at both the `install_test_game.py` entry and the GSL script
stages of any new game.

### 2.3 Deploying when the virtual environment is not activated

**What happened:** Running `python manage.py install_test_game` from a shell that had not
activated the `.venv` virtual environment failed with `ModuleNotFoundError: No module
named 'django'`.

**Fix:** `source .venv/bin/activate && python manage.py install_test_game`

**Lesson:** The venv is at `wsz6_portal/.venv/`. Every Django management command must
be run with this activated, or with the explicit `.venv/bin/python` prefix. The shell
environment persists between Bash tool calls in a session but does not carry over
automatically. Always prefix deployment commands with the venv activation.

### 2.4 The pff_loader module isolation trap (from OCCLUEdo)

This did not bite the Prisoner's Dilemma (which has no module-level state that the VIS
module needs), but it is worth documenting here because it will affect any future game
with private per-instance data (secret cards, randomised setups, hidden roles).

**What happens:** `pff_loader.py` registers every loaded PFF under a unique UUID-based
module name (`_pff_prisoners_dilemma_<uuid>`), not its original filename. This prevents
two concurrent sessions from sharing module-level globals — which was a bug in SZ6 v5.

The trap: if the VIS module tries to `import Prisoners_Dilemma_SZ6`, Python finds no
such key in `sys.modules` and loads a *fresh, uninitialized* copy of the file. Any
module-level variable that is only set during `initialize_problem()` will be `None` in
the freshly loaded copy, causing silent failures.

**The correct pattern for VIS modules that need per-game constants:**

1. Store the constants on `self.instance_data` inside `initialize_problem()`:
   ```python
   self.instance_data = sz.SZ_Problem_Instance_Data(d={...})
   self.instance_data.secret_value = computed_secret
   ```
2. Declare `instance_data=None` in the VIS module's `render_state` signature:
   ```python
   def render_state(state, role_num=None, instance_data=None):
       secret = instance_data.secret_value if instance_data else None
   ```
3. The engine's `render_vis_for_role()` uses `inspect.signature` to detect the
   `instance_data` parameter and pass it automatically. No changes to the engine
   are needed.

**Never use late imports of the PFF inside a VIS module.** Pass all data through
`state`, `instance_data`, or constructor parameters.

### 2.5 The `active_roles` attribute for GSL assertions

GSL's `Assert_view_exists` and `Assert_role_count` require the state object to have an
`active_roles` list. This is not enforced by the base framework — it is a convention
that must be set up by the PFF.

For Prisoner's Dilemma:
```python
self.active_roles = [PA, PB]  # PA=0, PB=1
```

This attribute needs to be set in `initialize_problem()` and preserved across state
copies. It is easy to forget when starting from scratch. Check the GSL spec for which
assertions require which state attributes and ensure the PFF provides them.

---

## Part 3 — What Could Be Simpler or More Robust

### 3.1 There is no game scaffold / template

Every new game currently starts by copying and modifying an existing PFF. This means
the developer has to know which example is closest to their game and understand all
the boilerplate.

A minimal scaffold PFF and VIS module — with clearly marked `# TODO` stubs for all
the parts that differ between games — would reduce errors and speed up implementation.
See §4.2 for a proposed template structure.

### 3.2 The GSL setup preamble is repeated in every script

Every GSL script begins with:
```gsl
Login admin pass1234 display:"Alice"
Select_Game <slug>
Create_Session name:"..."
Add_Player mock display:"Bob"
Assign_role Alice "Role A"
Assign_role Bob   "Role B"
Start_game
```

The `Include` command exists in the GSL spec for exactly this purpose. A set of
fixture files (e.g., `fixtures/two-player-ready.gsl`) would eliminate this repetition
and reduce the chance of getting the preamble wrong in individual test scripts.

### 3.3 `install_test_game` does not verify the VIS signature

When `install_test_game.py` copies the VIS file, it does not import it or check that
`render_state` has the right signature. A broken VIS module is only discovered at
runtime when the first player connects.

A lightweight check — `importlib` import + `inspect.signature` verification — run
as part of `install_test_game` would catch naming errors and missing functions
immediately at install time.

### 3.4 No automated GSL test run during deploy

The deploy process (`install_test_game` + restart) does not automatically run the
game's GSL test. Running the test is a manual step. Including a `--test` flag on
`install_test_game` that runs the associated GSL file (if one is specified in `GAME_DEFS`)
would make it impossible to deploy a broken game.

### 3.5 Plaintext passwords in GSL scripts are a recurring issue

Every GSL script created so far uses `Login admin pass1234 display:"Alice"`, and the spec
warns that this should be replaced with `Login admin $ADMIN_PASS`. But the environment
variable approach requires additional shell setup, and for developer scripts running in
api mode the plaintext password is convenient.

The cleanest resolution would be a development-only convention: always use `mock` as the
session owner in test scripts, so no real password appears:

```gsl
Login mock display:"Alice"     # temp account; no password
Add_Player mock display:"Bob"  # second temp account
```

This requires no environment variables and leaves no sensitive data in source control.

---

## Part 4 — Recommended Step-by-Step Workflow

The following process is ordered to catch problems as early as possible, at the
cheapest point in the development cycle.

### Step 0 — Design on paper first

Before opening an editor:

1. Write down the **phase names** and draw a **state machine diagram** showing which
   operator transitions to which phase.
2. List every **state attribute** with its type and initial value.
3. List every **operator** with: name, role (or `None` for shared), and precondition.
4. For multi-player games: decide whether any phase is **parallel** and what
   **role-aware information hiding** is required.
5. Identify the **closest existing game** in `game_sources/` to use as a reading example.

### Step 1 — Read the reference game thoroughly

Read the reference PFF top to bottom. Note specifically:
- How `initialize_problem()` sets up `self.instance_data`
- How operators use `state.parallel` and `state.current_role_num`
- The `active_roles` attribute
- The `text_view_for_role()` pattern (for parallel games)

### Step 2 — Implement the PFF

Follow the class structure of the reference game:
- `<Game>_Metadata` — inherits `SZ_Metadata`
- `<Game>_State` — inherits `SZ_State`, stores all game attributes
- `<Game>_Operator_Set` — inherits `SZ_Operator_Set`, one `SZ_Operator` per action
- `<Game>_Roles_Spec` — inherits `SZ_Roles_Spec`
- `<Game>_Formulation` — inherits `SZ_Formulation`, orchestrates the above

**Naming and file conventions:**
- File: `<Title_Snake_Case>_SZ6.py` in `game_sources/<snake_case>/`
- Module-level singleton: `PFF = <Game>_Formulation()`
- Do not put any game instance state in module-level globals if you intend to support
  multiple concurrent sessions; use `initialize_problem()` / `instance_data` instead.

**ASCII box art:** If used in `text_view()`, pad every dynamic-content line with
`ljust(width)` to keep box borders aligned regardless of parameter values.

### Step 3 — Run the standalone self-test

```bash
PYTHONPATH=/Users/slt/SZ6_Dev/Textual_SZ6 \
  python3 game_sources/<your_game>/<Your_Game>_SZ6.py
```

Verify every phase renders correctly, choices accumulate correctly, and `is_goal()` /
`goal_message()` fire at the right time. Fix all issues before proceeding.

### Step 4 — Implement the VIS module

Create `<Title_Snake_Case>_WSZ6_VIS.py` alongside the PFF. The public API is:

```python
def render_state(state, role_num=0, base_url='') -> str:
    ...
```

Add `instance_data=None` to the signature only if the game has per-instance constants
that the VIS module needs (see §2.4). Never import the PFF module from the VIS module.

Test by calling `render_state()` directly from a Python REPL with a manually constructed
state object.

### Step 5 — Register the game

Add an entry to `GAME_DEFS` in
`wsz6_portal/wsz6_admin/games_catalog/management/commands/install_test_game.py`:

```python
{
    'slug':          'my-game',           # kebab-case; must match Select_Game in GSL
    'name':          'My Game',
    'source_subdir': 'my_game',           # snake_case; directory under game_sources/
    'pff_file':      'My_Game_SZ6.py',
    'vis_file':      'My_Game_WSZ6_VIS.py',
    'brief_desc':    'One-sentence description shown on the games list page.',
    'min_players':   N,
    'max_players':   M,
},
```

Slug convention reminder: **hyphens in slug, underscores in source_subdir**.

### Step 6 — Deploy

```bash
cd /Users/slt/SZ6_Dev/WSP6-portal/Claudes-plan-2/wsz6_portal
source .venv/bin/activate
python manage.py install_test_game
```

Confirm the output shows `OK  '<Game Name>' created` (not `SKIP` or `WARN`).

### Step 7 — Write and run the GSL test

**Before writing the script:** trace the score/state arithmetic for your planned move
sequence by hand, and write down the expected values at each assertion point.

**Script structure:**
```gsl
# Test_MyGame.gsl
Login admin pass1234 display:"Alice"
Select_Game my-game                    # kebab-case slug
Create_Session name:"My Game smoke test"
Add_Player mock display:"Bob"
Assign_role Alice "Role A"
Assign_role Bob   "Role B"
Start_game

Assert_phase playing
Assert_state phase  intro
# ... exercise each phase, assert at each landmark ...
Assert_phase ended
```

**Run the test:**
```bash
cd wsz6_portal
source .venv/bin/activate
python manage.py run_gsl ../Test_MyGame.gsl
```

A clean exit-code-0 run means the core game logic works end-to-end through the portal
engine.

### Step 8 — Live session smoke test

```bash
python manage.py run_gsl ../Setup_MyGame_Live.gsl \
    --mode browser --headed --stay-open
```

Play through the game manually in the browser. Verify the VIS module renders each phase
correctly and that role-specific views show the right information.

### Step 9 — Commit and push

```bash
git add game_sources/<your_game>/
git add wsz6_portal/wsz6_admin/games_catalog/management/commands/install_test_game.py
git add WSP6-portal/Claudes-plan-2/Test_MyGame.gsl
git add WSP6-portal/Claudes-plan-2/Setup_MyGame_Live.gsl
git commit -m "Add <My Game> (PFF, VIS, GSL scripts)"
git push
```

---

## Part 5 — Checklist for New Game Implementations

Use this checklist when implementing a new game. Check each item off before moving to
the next stage.

### Design
- [ ] Phase names and state machine drawn on paper
- [ ] State attributes listed with types and initial values
- [ ] Operators listed with names, roles, and preconditions
- [ ] Parallel phases identified; role-aware hiding requirements noted
- [ ] Reference game selected and read completely

### PFF implementation
- [ ] `active_roles` set in `initialize_problem()` and preserved in `copy()`
- [ ] `parallel` flag set/cleared correctly as phase changes
- [ ] `current_role_num` maintained correctly for serial phases
- [ ] `jit_transition` cleared at the start of each phase (or set deliberately)
- [ ] Any per-instance constants stored on `self.instance_data`, not module globals
- [ ] ASCII box lines padded with `ljust()` if they contain dynamic content
- [ ] Standalone self-test (`__main__`) written and passes

### VIS module
- [ ] `render_state(state, role_num=0, base_url='')` signature present
- [ ] `instance_data=None` added only if needed; no PFF imports in the VIS file
- [ ] Each phase (`intro`, `choosing`, `reveal`, `game_over`, etc.) renders correctly
- [ ] Role-aware hiding works: player sees own info, opponent's info masked

### Registration
- [ ] Entry added to `GAME_DEFS` with correct slug (hyphens), source_subdir (underscores)
- [ ] `python manage.py install_test_game` runs cleanly (output: `OK  '...' created`)

### GSL test
- [ ] Expected state values verified by hand before writing the script
- [ ] All 4 outcome types (or equivalent logical paths) exercised
- [ ] `Assert_state` checks placed after every significant transition
- [ ] `Assert_phase ended` at the end
- [ ] Script runs with exit code 0

### Live test
- [ ] Browser-mode session opened and played to completion
- [ ] VIS module renders correctly in all phases
- [ ] Role-specific views correct for each player

### Documentation and commit
- [ ] Implementation report written in `game_sources/<your_game>/`
- [ ] All files staged and committed with a clear commit message
- [ ] Pushed to origin

---

## Part 6 — Quick Reference

### Key files and paths

| Purpose | Path |
|---|---|
| SOLUZION6 base library | `Textual_SZ6/soluzion6_02.py` |
| Game source files | `game_sources/<snake_case>/` |
| Deployed game files | `wsz6_portal/games_repo/<slug>/` |
| Game registration | `wsz6_portal/wsz6_admin/games_catalog/management/commands/install_test_game.py` |
| GSL test scripts | `WSP6-portal/Claudes-plan-2/Test_<Game>.gsl` |
| GSL live scripts | `WSP6-portal/Claudes-plan-2/Setup_<Game>_Live.gsl` |
| Portal CLAUDE.md | `WSP6-portal/Claudes-plan-2/wsz6_portal/CLAUDE.md` |
| GSL spec | `WSP6-portal/Claudes-plan-2/Game-Setup-Language-Spec.md` |
| VIS development guide | `WSP6-portal/Claudes-plan-2/Vis-Features-Dev/How-to-Code-Interactive-Visualizations-in-WSZ6.md` |
| pff_loader isolation doc | `WSP6-portal/Claudes-plan-2/Vis-Features-Dev/Experience_Porting_OCCLUEdo.md` |

### Django commands

```bash
# Always activate the venv first
source wsz6_portal/.venv/bin/activate

# Register/update all games
python manage.py install_test_game

# Run a GSL script in API mode
python manage.py run_gsl <file.gsl>

# Run a GSL script in browser mode
python manage.py run_gsl <file.gsl> --mode browser --headed --stay-open

# Start the server
bash start_server.sh
```

### State attributes required by GSL assertions

| GSL assertion | Required state attribute |
|---|---|
| `Assert_role_count N` | `state.active_roles` (a list) |
| `Assert_view_exists Alice "Role A"` | `state.active_roles` |
| `Assert_state parallel 1` | `state.parallel` (bool) |
| `Assert_state round_num N` | `state.round_num` |
| `Assert_state scores.0 N` | `state.scores` (a list) |

### VIS module render_state signatures

```python
# Minimal (no role-specific or per-instance data)
def render_state(state) -> str: ...

# With role-specific views (parallel/hidden-info games)
def render_state(state, role_num=0, base_url='') -> str: ...

# With per-instance constants (randomised setup, private hands)
def render_state(state, role_num=0, base_url='', instance_data=None) -> str: ...
```

The engine auto-detects which arguments to pass via `inspect.signature`. All three
signatures are backward-compatible with each other and with older games.

---

*End of guide*
