# SOLUZION6 Alpha-Tester and Game-Creator Handbook

**Draft v0.1 — 2026-03-30**
**For:** Students alpha-testing SOLUZION6 and creating games with LLM-agent assistance
**Covers:** Text\_SOLUZION6 (terminal runner) and WSZ6-portal (browser multi-player portal)

---

## Table of Contents

- [A. What Is SOLUZION6?](#a-what-is-soluzion6)
- [B. Main Changes from SOLUZION5](#b-main-changes-from-soluzion5)
- [C. WSZ6-Portal Features](#c-wsz6-portal-features)
- [D. Installing Text\_SOLUZION6](#d-installing-textsoluzion6)
- [E. Installing WSZ6-Portal](#e-installing-wsz6-portal)
- [F. Running WSZ6-Portal](#f-running-wsz6-portal)
- [G. Creating Games for SOLUZION6](#g-creating-games-for-soluzion6)
- [H. Writing GSL Test Scripts](#h-writing-gsl-test-scripts)

---

## A. What Is SOLUZION6?

### A.1 Origins and Purpose

SOLUZION6 (SZ6) is the current version of a family of Python frameworks developed at the
University of Washington for representing **problems and games as formal state-space
search instances**. The framework was originally developed to support educational research
into structured problem solving. A "game" in SOLUZION terms is any problem where players
apply operators to states in order to reach a goal — this includes puzzles, multi-player
strategy games, simulations, and educational scenarios.

The word *SOLUZION* captures the central idea: the framework is about expressing problems
so that the path to a solution (or to any goal state) can be explored interactively or
automatically.

### A.2 Problem Formulation Files (PFFs)

The key unit of work in SOLUZION6 is the **Problem Formulation File (PFF)** — an ordinary
Python source file that describes one game or puzzle (or a family of related ones). A PFF
specifies:

**Required components:**
1. **Metadata** — a name, description, and version for the problem
2. **Initial state** — the starting configuration
3. **Operators** — the set of legal moves or actions a player can take
4. **Goal criterion** — a function that tests whether a state is a goal

**Optional components:**
- State visualization (text or graphical)
- Transition messages (feedback on what just happened)
- Player role specifications (for multi-player games)
- Data collection hooks (for research)

A single PFF can be loaded by multiple runners without modification:

- **Text\_SOLUZION6** — terminal-based, single-developer testing
- **WSZ6-portal** — web-based, real-time multi-player, research logging
- Future engines (Jupyter notebooks, solvers, AI search agents)

The PFF describes *what* the game is. The runner handles *how* it is displayed and *how*
players connect.

### A.3 Relationship to SOLUZION5

SOLUZION5 (and earlier versions) used a flat, convention-based approach: a game was a
Python module with specific global variables (`OPERATORS`, `ROLES_List`, etc.) and
functions (`create_initial_state`, `goal_test`). SOLUZION6 replaces all of that with a
formal Python class hierarchy imported from `soluzion6_02.py`. The conceptual model is
the same; the structure is more explicit and more maintainable.

---

## B. Main Changes from SOLUZION5

### B.1 Class-Based PFF Structure

**SOLUZION5:** A game module defined a set of global variables and functions using a
tagged comment convention. The framework identified these by name.

```python
# SOLUZION5 style (old)
OPERATORS = [Operator("Place Mark", ...), ...]
ROLES_List = [{"name": "X"}, {"name": "O"}]
def create_initial_state(): ...
def goal_test(state): ...
```

**SOLUZION6:** A game module defines subclasses of five base classes from `soluzion6_02.py`.

```python
# SOLUZION6 style (new)
class MyGame_Metadata(sz.SZ_Metadata): ...
class MyGame_State(sz.SZ_State): ...
class MyGame_Operator_Set(sz.SZ_Operator_Set): ...
class MyGame_Roles_Spec(sz.SZ_Roles_Spec): ...
class MyGame_Formulation(sz.SZ_Formulation): ...

PFF = MyGame_Formulation()  # module-level singleton
```

The runner finds the game by looking for an `SZ_Formulation` instance at module level.
Everything else is discovered through that object.

### B.2 Roles and Parallel Phases

**SOLUZION5:** `ROLES_List` was a plain list of dicts. Role-specific behavior was
ad hoc.

**SOLUZION6:** Roles are `SZ_Role` objects collected in an `SZ_Roles_Spec`. The state
carries two key attributes for role management:

| Attribute | Type | Meaning |
|---|---|---|
| `state.current_role_num` | int | Whose turn it is (for serial games) |
| `state.active_roles` | list[int] | Which roles are currently active |
| `state.parallel` | bool | If `True`, all active roles choose simultaneously |

When `parallel = True`, the Textual runner serializes choices via player cueing
and a `text_view_for_role()` masking method; the web portal collects choices
over WebSocket and applies them together.

### B.3 Parameterized Operators

**SOLUZION5:** Operators with arguments required custom input handling baked into
each game.

**SOLUZION6:** `SZ_Operator` has a `params` list. Each entry is a dict specifying
the parameter's name, type (`int`, `float`, or `str`), and optional `min`/`max`
bounds. The runner prompts for each argument automatically.

```python
SZ_Operator(
    name="Place_Mark",
    params=[
        {'name': 'row', 'type': 'int', 'min': 0, 'max': 2},
        {'name': 'col', 'type': 'int', 'min': 0, 'max': 2},
    ],
    state_xition_func=lambda state, args: place(state, args[0], args[1]),
)
```

### B.4 Per-Session Instance Data

**SOLUZION5:** Per-session state (e.g., randomized card deals) was often stored
in module-level globals, which broke concurrent sessions.

**SOLUZION6:** `SZ_Problem_Instance_Data` is created inside `initialize_problem()`
and stored on `self.instance_data`. Each session gets its own instance; no globals
are shared across concurrent sessions.

```python
def initialize_problem(self):
    deck = shuffle_deck()
    self.instance_data = sz.SZ_Problem_Instance_Data(d={'deck': deck})
    return MyGame_State()
```

### B.5 Visualization System

**SOLUZION5:** Visualization was game-engine-specific and not standardized.

**SOLUZION6 / WSZ6-portal:** A game may provide a companion `_WSZ6_VIS.py` file with
a `render_state()` function that returns an HTML or SVG string. The portal injects
this into the browser on each state update.

Interactive visualizations are supported through HTML `data-*` attributes:
- `data-op-index` — clicking the element applies that operator
- `data-op-args` — passes arguments to the operator
- `data-info` — hovering shows an information popup

### B.6 GSL Scripting for Automated Testing

**SOLUZION5:** No automated testing framework.

**SOLUZION6:** A small scripting language called **GSL (Game Setup Language)** lets
developers write test scripts that log in players, set up a session, apply operators,
and assert expected state values — all without a browser. See section H for details.

---

## C. WSZ6-Portal Features

### C.1 User Roles

The portal defines several account types. The ones most relevant to alpha testers are:

| Role | Can do |
|---|---|
| `ADMIN_GENERAL` | Everything |
| `SESSION_OWNER` | Create sessions, invite players, access their own session logs |
| `GAME_OWNER` | Install their own games, create sessions for those games |
| `PLAYER` | Join sessions to which they are invited |

Guest players (no portal account) can join sessions using an invite URL by choosing a
display name at the lobby. The dev setup (`create_dev_users`) creates accounts:
`admin`, `owner1`, `owner2`, `player1`, `player2` — all with password `pass1234`.

### C.2 Games Catalog

The **Games** page lists all installed games with their name, description, and player
count range. Admin and game-owner accounts can install new games from the management
interface. Players browse the catalog to see what is available.

Games have a status (`dev`, `beta`, `published`). Which account types can see each
status is configurable by the admin.

### C.3 Session Lifecycle

A **session** is a named encounter for a specific game. A **play-through** is one
complete run from initial state to goal (or interruption). The same session can host
multiple play-throughs (e.g., rematches).

The lifecycle:

1. **Create** — session owner picks a game and names the session. An invite URL is generated.
2. **Lobby** — players join via the invite URL or the sessions list. The owner assigns
   roles to players (or to bot players). Guest players pick a display name.
3. **Play** — the owner clicks "Start Game". Players see the current state and the
   operators available to them.
4. **Pause / Resume** — the session owner can pause a session (freezing the state) and
   resume it later.
5. **Rematch** — after a game ends, the owner can start a new play-through in the same
   session with the same players.

### C.4 Bot Players

In the lobby, any role can be assigned to a **bot** instead of a human player. The
portal supports several bot policies (random-move, first-applicable, etc.). Bots are
useful for:
- Testing a new game without needing multiple browser tabs
- Setting up educational demonstrations
- Filling roles when a player does not show up

### C.5 Visualization

When a game provides a `_WSZ6_VIS.py` file, the portal displays a graphical view of
each state in the game area. Features:

- **Interactive vis** — clicking SVG/HTML elements that carry `data-op-index` applies
  an operator directly, without using the numbered operator list.
- **Full-screen mode** — the visualization can be expanded to fill the browser window.
- **Previous-state toggle** — a button shows the state before the last move, so players
  can see what changed.
- **Role-specific views** — in parallel-choice games (e.g., Prisoner's Dilemma), each
  player sees only the information appropriate to their role. The other player's choices
  are hidden until the reveal phase.

If no vis file is provided, the portal falls back to showing the state's `__str__()`
output as monospace text.

### C.6 Researcher Panel

The Researcher Panel (available to `ADMIN_RESEARCH` accounts) provides:

- **Session browser** — search and filter sessions by game, date, and status
- **Log viewer** — inspect the `log.jsonl` append-only log for any play-through
- **Artifact viewer** — view any files produced during a session
- **Export** — download session data in JSON or CSV format
- **Annotations** — attach notes to sessions or individual moves
- **REST API** — programmatic access to session data for offline analysis

Every operator application is recorded with a timestamp, player identity, operator
name, arguments, and the resulting state. The log is append-only and tamper-evident.

---

## D. Installing Text\_SOLUZION6

Text\_SOLUZION6 is the terminal-based runner. It requires no Django, no server, and
no browser — just Python. It is the fastest way to test a new game formulation.

### D.1 Prerequisites

- **Python 3.11 or later**

  ```bash
  python3.11 --version   # must show 3.11.x or higher
  ```

  No other packages are required for the runner itself.

### D.2 Get the files

Copy or clone the `Textual_SZ6/` directory from the SZ6\_Dev repository. You need:

| File | Purpose |
|---|---|
| `Textual_SOLUZION6-v01.py` | The runner |
| `soluzion6_02.py` | The SZ6 base class library |
| `sz_sessions6_02.py` | Session tracking used by the runner |
| `Your_Game_SZ6.py` | Your game formulation |

All these files should be in the same directory (or `soluzion6_02.py` must be on
`PYTHONPATH`).

### D.3 Running a game

```bash
cd Textual_SZ6
python3.11 Textual_SOLUZION6-v01.py Tic_Tac_Toe_SZ6
```

Note: the argument is the **module name without the `.py` extension**.

The runner will:
1. Load the formulation
2. Ask you to confirm role assignments (for multi-player games)
3. Show the initial state
4. Let you apply operators by number, undo moves (`B`), or quit (`Q`)

### D.4 Multi-player games at one keyboard

For multi-player games, the runner implements **player cueing**: before each turn, it
prints a handover message and waits for the incoming player to press Enter, giving the
previous player time to look away. This allows two players to share one keyboard for
testing.

For parallel-input games (where both players choose simultaneously), the runner
serializes the inputs and uses `text_view_for_role()` to hide each player's choice
from the other until both have submitted.

### D.5 Commands during play

| Command | Action |
|---|---|
| `0`, `1`, `2`, … | Apply the operator with that number |
| `B` | Undo the last move (go back one state) |
| `H` | Show the help/instructions |
| `Q` | Quit the session |

---

## E. Installing WSZ6-Portal

> The full installation guide is `Claudes-plan-2/WSZ6-portal-installation-guide-v01.md`.
> This section is a condensed student-friendly version.

### E.1 Prerequisites

- **Python 3.11** (`python3.11 --version`)
- **git** (`git --version`)
- **pip** (bundled with Python 3.11)

For single-developer use on a laptop, no other dependencies are needed (the portal
uses SQLite and an in-memory channel layer). For a shared course server with concurrent
students, you will additionally need PostgreSQL 14+ and Redis 6+.

### E.2 Step-by-step setup

**1. Clone the repository**

```bash
git clone <repo-url> SZ6_Dev
cd SZ6_Dev/WSP6-portal/Claudes-plan-2
```

**2. Run the setup script**

```bash
cd wsz6_portal
bash setup_dev.sh
```

This script creates the Python virtual environment at `.venv/`, installs all
dependencies, copies the dev environment file, and runs initial database migrations.

**3. Activate the virtual environment**

```bash
source .venv/bin/activate
```

You must do this every time you open a new shell before running any Django command.
Your prompt should show `(.venv)` when the venv is active.

**4. Migrate both databases**

The portal uses two databases: the main application database and a separate game-data
management (GDM) database for session logs.

```bash
python manage.py migrate
python manage.py migrate --database=gdm
```

**5. Create dev user accounts**

```bash
python manage.py create_dev_users
```

This creates: `admin`, `owner1`, `owner2`, `player1`, `player2` — all with
password `pass1234`.

**6. Install the test game**

```bash
python manage.py install_test_game
```

This installs Tic-Tac-Toe (and any other games defined in `GAME_DEFS` in the
management command) from `game_sources/` into the portal's games repository.

**7. Start the server**

```bash
bash start_server.sh
```

Open `http://127.0.0.1:8000` in your browser.

### E.3 Quick verification

- Log in as `admin` / `pass1234`
- Navigate to the Games page — you should see Tic-Tac-Toe listed
- Create a session, join with a second browser tab as `player1`

---

## F. Running WSZ6-Portal

> The full user manual is `Claudes-plan-2/WSZ6_Portal_User_Manual.md`.

### F.1 Starting and stopping the server

```bash
# From the wsz6_portal/ directory, with .venv active:
bash start_server.sh
```

To stop: press `Ctrl-C` in the terminal running the server.

### F.2 Creating a session (as SESSION\_OWNER or ADMIN)

1. Log in and navigate to **Sessions → New Session**
2. Select a game from the dropdown
3. Give the session a name
4. Click **Create** — you are taken to the lobby

### F.3 The lobby

The lobby is where players gather before the game starts. From the lobby:

- **Assign roles** — drag players to roles, or click a role and select a player
- **Add bots** — assign a bot policy to any unfilled role
- **Share the invite link** — copy and send to other players
- **Start the game** — click "Start Game" once all required roles are filled

Guest players (no account) can join using the invite link; they pick a display name
at the lobby page.

### F.4 Playing a game

Once the game starts:

- The **current state** is shown (text or graphical visualization)
- **Applicable operators** for the current player are listed below the state
- Click an operator to apply it, or click directly on the visualization if it
  is interactive
- After each move, the state updates in real time for all connected players

### F.5 Pausing, resuming, and rematches

- **Pause** — the session owner can pause the game from the session menu; the state
  is frozen and players see a "paused" notice
- **Resume** — the owner resumes; play continues from where it left off
- **Rematch** — after a game ends, the owner can start a new play-through in the
  same session; roles are re-assigned in a new lobby

### F.6 Automated live session setup (GSL)

To open a pre-configured session quickly (useful during development):

```bash
bash gsl_live.sh Setup_MyGame_Live.gsl
```

This runs a GSL script in browser mode, opens Chromium windows with players already
assigned and the game started, and leaves everything open for interactive play.

```bash
bash gsl_stop.sh   # close windows and clean up when done
```

---

## G. Creating Games for SOLUZION6

> **Using an LLM coding assistant?** The file
> `Claudes-plan-2/Making-Game-Implementation-Go-Smoothly.md` was written specifically
> to be given to an LLM (Claude, GPT-4, etc.) as context for implementing a new game.
> Hand that document to your assistant at the start of any game-creation session.

### G.1 The Five SZ6 Classes

Every SOLUZION6 game defines five classes, all in one `.py` file:

| Class | Base class | Purpose |
|---|---|---|
| `<Game>_Metadata` | `SZ_Metadata` | Name, description, version, author, player counts |
| `<Game>_State` | `SZ_State` | A snapshot of the game world |
| `<Game>_Operator_Set` | `SZ_Operator_Set` | All legal moves, each as an `SZ_Operator` |
| `<Game>_Roles_Spec` | `SZ_Roles_Spec` | Player roles and how many are needed |
| `<Game>_Formulation` | `SZ_Formulation` | Top-level object; `initialize_problem()` returns the first state |

At the bottom of the file, create a module-level singleton:

```python
PFF = MyGame_Formulation()
```

The runner finds this object automatically.

**Minimal skeleton:**

```python
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import soluzion6_02 as sz

class MyGame_Metadata(sz.SZ_Metadata):
    def __init__(self):
        self.name            = "My Game"
        self.problem_version = "1.0"
        self.brief_desc      = "One sentence description."
        self.min_players     = 1
        self.max_players     = 2

class MyGame_State(sz.SZ_State):
    def __init__(self, old=None):
        if old is None:
            self.current_role_num = 0
            self.phase = 'playing'
            # ... your game state attributes
        else:
            self.current_role_num = old.current_role_num
            self.phase = old.phase
            # ... deep-copy all attributes

    def __str__(self):
        return f"Phase: {self.phase}"

    def is_goal(self):
        return self.phase == 'game_over'

class MyGame_Operator_Set(sz.SZ_Operator_Set):
    def __init__(self):
        self.operators = [
            sz.SZ_Operator(
                name="My_Move",
                precond_func=lambda s: s.phase == 'playing',
                state_xition_func=lambda s: make_move(s),
                role=None,   # None = any role
            ),
        ]

class MyGame_Roles_Spec(sz.SZ_Roles_Spec):
    def __init__(self):
        self.roles = [
            sz.SZ_Role(name="Player A", description="First player"),
            sz.SZ_Role(name="Player B", description="Second player"),
        ]
        self.min_players_to_start = 2

class MyGame_Formulation(sz.SZ_Formulation):
    def __init__(self):
        self.metadata   = MyGame_Metadata()
        self.operators  = MyGame_Operator_Set()
        self.roles_spec = MyGame_Roles_Spec()

    def initialize_problem(self):
        self.instance_data = sz.SZ_Problem_Instance_Data(d={})
        return MyGame_State()

PFF = MyGame_Formulation()
```

### G.2 Key State Attributes

These attributes have special meaning to the runners and portal:

| Attribute | Type | When required |
|---|---|---|
| `current_role_num` | int | Always — tells the runner whose turn it is |
| `active_roles` | list[int] | Needed for GSL assertions (`Assert_role_count`, `Assert_view_exists`) |
| `parallel` | bool | Parallel-choice phases; set `True` when multiple roles choose simultaneously |
| `jit_transition` | str or None | Message displayed after this state is reached; cleared by the runner after display |

**Example from Prisoner's Dilemma** (parallel choosing phase):

```python
# In the 'choosing' phase, both players pick simultaneously.
self.parallel = True
self.current_role_num = PA   # the runner will cue PA first in Textual mode
self.active_roles = [PA, PB]
```

**Example from Tic-Tac-Toe** (serial turns):

```python
# In TTT_State.__init__ (initial state):
self.current_role_num = X    # X goes first
# No parallel or active_roles needed for serial games
```

### G.3 Writing Operators

Each operator is an `SZ_Operator` instance with:

| Field | Type | Purpose |
|---|---|---|
| `name` | str (or callable) | Display name; also used by GSL `Op` command |
| `description` | str | Longer description |
| `precond_func` | `lambda state: bool` | Returns `True` when the operator is applicable |
| `state_xition_func` | `lambda state: new_state` | Returns the new state after applying |
| `role` | int or None | Which role can use this operator; `None` = any role |
| `params` | list of dicts | Parameter specifications for parameterized operators |

**Non-parameterized operator (Tic-Tac-Toe):**

```python
def place_mark(row, col):
    def precond(s):
        return s.board[row][col] == EMPTY and not s.is_goal()
    def xition(s):
        ns = TTT_State(old=s)
        ns.board[row][col] = s.whose_turn
        ns.check_for_win()
        if not ns.is_goal():
            ns.whose_turn = O if s.whose_turn == X else X
            ns.current_role_num = ns.whose_turn
        return ns
    return sz.SZ_Operator(
        name=f"Place_{NAMES[X] if i < 5 else NAMES[O]}_at_{row}_{col}",
        precond_func=precond,
        state_xition_func=xition,
        role=X if i < 5 else O,
    )
```

**Parameterized operator:**

```python
sz.SZ_Operator(
    name="Place_Mark",
    params=[
        {'name': 'row', 'type': 'int', 'min': 0, 'max': 2},
        {'name': 'col', 'type': 'int', 'min': 0, 'max': 2},
    ],
    precond_func=lambda s: not s.is_goal(),
    state_xition_func=lambda s, args: place(s, args[0], args[1]),
)
```

The runner prompts the player for each parameter automatically.

**Important:** operator `name` strings are used by GSL's `Op` command. Choose names
that are stable identifiers — no spaces, no punctuation other than underscores.

### G.4 Parallel Phases and Role-Hiding

For games where players choose simultaneously (Prisoner's Dilemma, Rock-Paper-Scissors),
use the parallel-phase pattern:

1. Set `state.parallel = True` in the choosing phase.
2. Give each player their own operator (filtered by `role`):

   ```python
   sz.SZ_Operator(
       name="Cooperate",
       precond_func=lambda s: s.phase == 'choosing',
       state_xition_func=lambda s: record_choice(s, PA, COOPERATE),
       role=PA,    # only Prisoner A can use this
   ),
   sz.SZ_Operator(
       name="Defect",
       precond_func=lambda s: s.phase == 'choosing',
       state_xition_func=lambda s: record_choice(s, PA, DEFECT),
       role=PA,
   ),
   # ... same operators for PB
   ```

3. Implement `text_view_for_role(role_num)` on the state to hide information from
   the wrong player in the Textual runner:

   ```python
   def text_view_for_role(self, role_num):
       if self.phase == 'choosing':
           my_choice = self.choices[role_num]
           if my_choice is None:
               return f"You ({ROLE_NAMES[role_num]}): not yet chosen."
           else:
               return f"You ({ROLE_NAMES[role_num]}): {CHOICE_NAMES[my_choice]}. Waiting for opponent."
       return str(self)
   ```

4. The portal hides operator buttons for roles other than the current player's role —
   no extra work is needed in the VIS module; the engine handles it.

### G.5 Testing in the Text Runner

Before touching the portal, always test your game in the Textual runner:

```bash
cd game_sources/my_game
PYTHONPATH=/path/to/Textual_SZ6 python3.11 My_Game_SZ6.py
```

Or from the `Textual_SZ6/` directory:

```bash
python3.11 Textual_SOLUZION6-v01.py My_Game_SZ6
```

Also add a `__main__` block to your PFF that exercises the full game sequence
programmatically (no interactive input). This is the fastest regression test:

```python
if __name__ == '__main__':
    pff = MyGame_Formulation()
    state = pff.initialize_problem()
    op = pff.operators.operators[0]
    state = op.state_xition_func(state)
    assert state.phase == 'choosing', f"Expected 'choosing', got '{state.phase}'"
    print("Self-test passed.")
```

Run this self-test before every portal integration attempt.

### G.6 Writing a VIS Module for the Portal

A VIS module is a separate file named `<Title_Snake_Case>_WSZ6_VIS.py`. It must
define a `render_state()` function that returns an HTML or SVG string.

**Basic signature:**

```python
def render_state(state, role_num=0, base_url='') -> str:
    ...
```

The engine calls this after each state update and injects the result into the
`#vis-display` element on the game page.

**With per-instance data** (for games with randomized setup, hidden information):

```python
def render_state(state, role_num=0, base_url='', instance_data=None) -> str:
    secret = instance_data.secret_value if instance_data else None
    ...
```

The engine auto-detects the `instance_data` parameter via `inspect.signature`
and passes it automatically. **Never import the PFF module from a VIS file** — the
PFF is loaded under a unique UUID-based module name and a plain import will load a
stale, uninitialized copy.

**Interactive vis (Tier 1 — SVG/HTML with `data-*` attributes):**

```python
def render_state(state, role_num=0, base_url='') -> str:
    cells = []
    for i, row in enumerate(state.board):
        for j, cell in enumerate(row):
            op_idx = state.op_index_for_cell(i, j)  # None if cell is taken
            attrs  = f'data-op-index="{op_idx}"' if op_idx is not None else ''
            info   = f'data-info="({i},{j})"'
            x, y   = 10 + j * 60, 10 + i * 60
            cells.append(
                f'<rect x="{x}" y="{y}" width="58" height="58" '
                f'fill="white" stroke="#333" {attrs} {info}/>'
            )
    return f'<svg width="190" height="190">{"".join(cells)}</svg>'
```

Clicking a cell with `data-op-index` calls `applyOp(N)` in the browser without
any JavaScript in your VIS file — the portal's game page handles this automatically.

**Image assets:** reference images via `base_url`:

```python
img_url = f'{base_url}/static/my_game/board.png'
return f'<img src="{img_url}" .../>'
```

**Role-aware views:** check `role_num` and return different HTML for each role:

```python
def render_state(state, role_num=0, base_url='') -> str:
    if state.phase == 'choosing' and state.choices[role_num] is None:
        return render_choose_screen(state, role_num)
    elif state.phase == 'choosing':
        return '<p>Waiting for your opponent to choose...</p>'
    else:
        return render_reveal_screen(state)
```

### G.7 Registering the Game with the Portal

Open `wsz6_portal/wsz6_admin/games_catalog/management/commands/install_test_game.py`
and add an entry to `GAME_DEFS`:

```python
{
    'slug':          'my-game',           # kebab-case; used in URLs and GSL Select_Game
    'name':          'My Game',
    'source_subdir': 'my_game',           # snake_case; directory under game_sources/
    'pff_file':      'My_Game_SZ6.py',
    'vis_file':      'My_Game_WSZ6_VIS.py',   # or None if no VIS
    'brief_desc':    'One-sentence description for the games list.',
    'min_players':   1,
    'max_players':   2,
},
```

Then deploy:

```bash
cd wsz6_portal
source .venv/bin/activate
python manage.py install_test_game
```

The output should say `OK  'My Game' created`. If it says `SKIP`, the game was
already installed with the same content. If it says `WARN`, check the output
for what is wrong.

### G.8 Naming Conventions Cheat Sheet

This table is a perpetual source of confusion — bookmark it.

| Thing | Convention | Example |
|---|---|---|
| Portal slug (URLs, database, `Select_Game` in GSL) | **kebab-case** (hyphens) | `prisoners-dilemma` |
| `source_subdir` in `install_test_game.py` | **snake\_case** (underscores) | `prisoners_dilemma` |
| PFF filename | **Title\_Snake\_Case** + `_SZ6.py` | `Prisoners_Dilemma_SZ6.py` |
| VIS filename | **Title\_Snake\_Case** + `_WSZ6_VIS.py` | `Prisoners_Dilemma_WSZ6_VIS.py` |
| Python class prefix | **Title case, no separators** | `PD_State`, `TTT_Formulation` |

### G.9 Recommended Step-by-Step Workflow

The following order catches problems as early as possible:

1. **Design on paper** — draw the phase/state machine; list state attributes,
   operators, and roles; identify the existing game in `game_sources/` that is
   closest to yours
2. **Read that reference game top to bottom** before writing any code
3. **Implement the PFF** — follow the class structure; write a `__main__` self-test
4. **Run the self-test** — fix all issues before touching the portal
5. **Implement the VIS module** — test by calling `render_state()` from a Python REPL
6. **Register the game** — add to `GAME_DEFS`, run `install_test_game`
7. **Write and run the GSL test** — trace expected state values by hand first
8. **Live session smoke test** — `bash gsl_live.sh Setup_MyGame_Live.gsl`
9. **Commit** — all files, clear commit message

---

## H. Writing GSL Test Scripts

> The complete GSL specification is `Claudes-plan-2/Game-Setup-Language-Spec.md`.
> This section covers the subset you need for normal game testing.

### H.1 What GSL Is For

GSL (Game Setup Language) is a small scripting language for automating game session
setup and verifying game logic. Its two main uses are:

- **Regression testing** — assert that a known move sequence produces the expected
  state, so future changes can be validated quickly
- **Developer shortcut** — reach a specific mid-game state in one command instead of
  clicking through the browser repeatedly

Every new game should have two GSL scripts:

| Script | Purpose |
|---|---|
| `Test_<GameName>.gsl` | Regression test — runs in api mode, no browser |
| `Setup_<GameName>_Live.gsl` | Live session setup — opens browser windows for interactive play |

### H.2 Core Commands

**Session setup (must appear in this order):**

```gsl
Login mock display:"Alice"            # create a temporary owner account
Select_Game my-game                   # kebab-case slug
Create_Session name:"My test session"
Add_Player mock display:"Bob"         # add a second player (also a temp account)
Assign_role Alice  "Role A"
Assign_role Bob    "Role B"
Start_game
```

**Applying operators:**

```gsl
Op Alice  Operator_Name              # simple operator
Op Alice  Place_Mark  0  0           # operator with arguments
Op Bob    "My Operator"  "some arg"  # quoted names and string args
```

Operators are always identified by **name**, never by number. The name must exactly
match the `name` field in the `SZ_Operator` definition.

**Asserting state:**

```gsl
Assert_phase playing                  # session is in the play phase
Assert_phase ended                    # session has finished
Assert_active_role X                  # it is X's turn
Assert_state winner  X                # state.winner == "X"
Assert_state winner  none             # state.winner is None
Assert_state board.0.0  X            # state.board[0][0] == "X"
Assert_state scores.0   12           # state.scores[0] == 12
Assert_state active_roles.length  2  # len(state.active_roles) == 2
Assert_player_count 2                 # two players connected
Assert_role_count   2                 # two active roles
```

**Flow control:**

```gsl
Repeat 3
  Op Alice AutoMove
  Op Bob   AutoMove
End_repeat

Include fixtures/two-player-ready.gsl   # share common setup preamble
```

**Error handling:**

```gsl
On_error continue   # log failures but keep running (default: stop on first error)
```

### H.3 Running GSL Scripts

**API mode (fast, no browser — use for regression tests):**

```bash
cd wsz6_portal
source .venv/bin/activate
python manage.py run_gsl ../Test_MyGame.gsl
```

Exit code 0 = all assertions passed. Exit code 1 = something failed.

**Browser mode (Playwright, visual — use for live sessions):**

```bash
python manage.py run_gsl ../Setup_MyGame_Live.gsl --mode browser --headed --stay-open
```

Or use the wrapper scripts:

```bash
bash gsl_live.sh Setup_MyGame_Live.gsl    # opens windows and waits
bash gsl_stop.sh                          # closes windows when done
```

**At server startup (pre-loads a session):**

```bash
bash start_server.sh -g Setup_MyGame_Live.gsl --gsl-mode browser
```

### H.4 Credentials and Security

| Syntax | Meaning |
|---|---|
| `Login mock display:"Alice"` | Creates a temporary `gsl_mock_*` account; deleted on script exit |
| `Add_Player mock display:"Bob"` | Same — a temp account for a second player |
| `Login admin $ADMIN_PASS` | Reads password from environment variable `ADMIN_PASS` |
| `Login admin pass1234` | Plaintext — allowed in api mode with a warning; **blocked** in browser mode |

**Best practice:** use `mock` for all accounts in test scripts. No real passwords
appear in source code, and mock accounts are cleaned up automatically.

### H.5 Best Practices and Common Pitfalls

**Verify expected values before writing `Assert_state`.**
Trace the arithmetic (or state logic) for your planned move sequence by hand.
Write the GSL only after you know the correct expected values. Guessing and
correcting is slow and error-prone.

**Use `Login mock` in test scripts.**
Never put real passwords in GSL files. `mock` accounts require no password and
are automatically deleted.

**Write the self-test (`__main__`) before the GSL.**
If the game logic is wrong, you want to find that in Python — not after fighting
GSL parsing errors. The self-test is the first and cheapest regression check.

**Match the slug exactly.**
The `Select_Game` argument must use the **kebab-case slug** (`prisoners-dilemma`,
not `prisoners_dilemma`). This is the most common source of "game not found" errors.

**Activate the venv before every Django command.**
`source .venv/bin/activate` is required. Running without it produces
`ModuleNotFoundError: No module named 'django'`.

**Understand `Assert_state` key notation:**
- `Assert_state scores.0 3` checks `state.scores[0] == 3`
- `Assert_state board.1.2 X` checks `state.board[1][2] == "X"`
- `Assert_state active_roles.length 2` checks `len(state.active_roles) == 2`
- `Assert_state winner none` checks `state.winner is None`

**Complete example — Tic-Tac-Toe regression test:**

```gsl
# Test_TicTacToe.gsl
# X wins on the main diagonal.

Login mock display:"Alice"
Select_Game tic-tac-toe
Create_Session name:"X diagonal win"
Add_Player mock display:"Bob"
Assign_role Alice  X
Assign_role Bob    O
Start_game

Assert_phase playing
Assert_active_role X

Op Alice  Place_Mark  0  0    # X at top-left
Op Bob    Place_Mark  0  1    # O
Op Alice  Place_Mark  1  1    # X at center
Op Bob    Place_Mark  0  2    # O
Op Alice  Place_Mark  2  2    # X wins (diagonal)

Assert_phase ended
Assert_state winner  X
```

**Complete example — Live session setup:**

```gsl
# Setup_TicTacToe_Live.gsl
Login admin $ADMIN_PASS display:"Alice"
Select_Game tic-tac-toe
Create_Session name:"Live dev session"
Add_Player mock display:"Bob"
Assign_role Alice  X
Assign_role Bob    O
Start_game
Assert_phase playing
```

Run with:

```bash
bash gsl_live.sh Setup_TicTacToe_Live.gsl
```

---

*End of handbook draft v0.1 — 2026-03-30*

*For corrections or additions, see the handoff document:*
*`WSP6-portal/Handbook-Writing-Handoff-March-30-2026.md`*
