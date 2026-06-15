# SOLUZION6 Alpha-Tester Kit — Quick Start

**For full documentation read:** `SOLUZION6-Alpha-Tester-Handbook.md`

---

## What's in this folder

```
Alpha-Install-Kit/
  README-Quick-Start.md               ← you are here
  SOLUZION6-Alpha-Tester-Handbook.md  ← full handbook (read this)
  Making-Game-Implementation-Go-Smoothly.md  ← guide for creating games

  install.sh   ← ONE-TIME setup + server launch  (run this first)
  run.sh       ← start the server on subsequent days

  Textual_SZ6/          ← terminal runner + SZ6 base library + 4 example games
  game_sources/         ← example games for the web portal
  games_repo/           ← (empty — auto-populated by install.sh)
  gdm/                  ← (empty — session logs go here)

  WSP6-portal/          ← web portal source (managed by the scripts above)
```

---

## Part 1 — Text\_SOLUZION6 (terminal, no server needed)

### Prerequisites
- Python 3.11 or later

### Run a game

```bash
cd Alpha-Install-Kit/Textual_SZ6

python3.11 Textual_SOLUZION6-v01.py Tic_Tac_Toe_SZ6
```

Other games to try (same command, different name):

| Module name | Game | Players |
|---|---|---|
| `Tic_Tac_Toe_SZ6` | Tic-Tac-Toe | 2 (share keyboard) |
| `Rock_Paper_Scissors_SZ6` | Rock-Paper-Scissors | 2 (share keyboard) |
| `Missionaries_SZ6` | Missionaries & Cannibals | 1 |
| `Guess_My_Age_SZ6` | Guess My Age | 1 |

**During play:** enter a number to apply an operator, `B` to undo, `Q` to quit.

---

## Part 2 — WSZ6-portal (browser-based multi-player)

### Prerequisite
- Python 3.10 or later — check with `python3 --version`
  - Linux/WSL: `sudo apt update && sudo apt install python3.11 python3.11-venv`
  - macOS: `brew install python@3.11`

### First time only — install and launch

```bash
cd Alpha-Install-Kit
bash install.sh
```

That one command sets up the Python environment, creates the database,
creates all user accounts, installs the example games, and starts the server.
Your browser opens automatically to the login page.

Press **Ctrl-C** to stop the server.

### Every time after that

```bash
cd Alpha-Install-Kit
bash run.sh
```

### User accounts (password for all: `pass1234`)

| Username | Role |
|---|---|
| `admin` | Full admin |
| `owner1`, `owner2` | Can create game sessions |
| `player1`, `player2` | Players |

### Play a game

1. Log in as `owner1` / `pass1234`
2. Go to **Games** and pick a game (e.g., Tic-Tac-Toe)
3. Click **New Session**, give it a name
4. Copy the lobby URL and open it in a second browser tab (log in as `player1`)
5. Assign roles in the lobby → click **Start Game** → play

---

## Installed games

| Game | Players | Notes |
|---|---|---|
| Tic-Tac-Toe | 2 | SVG visualization; interactive click-to-play |
| Rock-Paper-Scissors | 2 | Parallel simultaneous choice |
| Prisoner's Dilemma | 2 | Parallel choice with role-hiding and educational messages |
| OCCLUEdo | 2–6 | Role-based multiplayer mystery with card images |
| Missionaries & Cannibals | 1 | Classic AI puzzle |
| Guess My Age | 1 | Parameterized operator demo |
| Mt. Rainier Views | 1 | SVG image browser |
| Cliquez sur l'image | 1 | French vocabulary click-on-scene game |
| Pixel Values (UW Aerial) | 1 | Raster image region hit-testing demo |

---

## Creating your own game

Read `Making-Game-Implementation-Go-Smoothly.md` and section G of the
handbook. If you are using an LLM assistant to write the game, hand it
that document as context.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `install.sh` says Python not found | Install Python 3.11+ (see prerequisite above) |
| Browser does not open | Navigate manually to `http://localhost:8000` |
| `No operator with number N` | Enter a number from the list shown |
| Game not found in portal | Re-run `bash install.sh` — it is safe to run again |
| Server starts but pages look broken | Press Ctrl-C, then re-run `bash run.sh` |
