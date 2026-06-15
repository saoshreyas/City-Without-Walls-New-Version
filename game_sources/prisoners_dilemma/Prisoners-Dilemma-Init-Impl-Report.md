# Prisoner's Dilemma — Initial Implementation Report

**Date:** 2026-03-04
**Author:** Claude (Sonnet 4.6), assisting the SOLUZION6 project
**Working directory:** `/Users/slt/SZ6_Dev/game_sources/prisoners_dilemma/`

---

## Overview

This report documents the initial implementation of the Iterated Prisoner's Dilemma
as a SOLUZION6 game for two players.  Four files were created: the core Problem
Formulation File (PFF), a portal visualization module, a GSL automated test script,
and a GSL live-session setup script.  The self-test in the PFF runs cleanly and all
score arithmetic was verified by a separate Python assertion test.

---

## Files Created

| File | Location |
|------|----------|
| `Prisoners_Dilemma_SZ6.py` | `game_sources/prisoners_dilemma/` |
| `Prisoners_Dilemma_WSZ6_VIS.py` | `game_sources/prisoners_dilemma/` |
| `Test_PrisonersDilemma.gsl` | `WSP6-portal/Claudes-plan-2/` |
| `Setup_PrisonersDilemma_Live.gsl` | `WSP6-portal/Claudes-plan-2/` |
| `Gamifying-the-Prisoners-Dilemma-a-Plan.md` | `WSP6-portal/Claudes-plan-2/` |

---

## 1. Game Design

### Payoff Matrix

Standard symmetric Prisoner's Dilemma payoffs (points per round):

|              | B Cooperates | B Defects |
|--------------|:------------:|:---------:|
| **A Cooperates** | A:+3, B:+3 | A:+0, B:+5 |
| **A Defects**    | A:+5, B:+0 | A:+1, B:+1 |

- **(C,C) Mutual Cooperation** — best collective outcome; Pareto optimal
- **(D,D) Mutual Defection** — Nash equilibrium; individually rational, collectively wasteful
- **(D,C) Temptation Payoff** — exploiter earns +5; exploited earns +0
- **(C,D) Sucker's Payoff** — mirror of the above

### Format

Iterated play over **5 rounds** (configurable via `initialize_problem(config={'max_rounds': N})`).
Multiple rounds allow players to experience strategy emergence: trust-building,
retaliation, Tit-for-Tat, always-defect.

### Roles

| Index | Name | Description |
|-------|------|-------------|
| 0 | Prisoner A | Interrogated separately; chooses Cooperate or Defect each round |
| 1 | Prisoner B | Same as above |

`min_players_to_start = 2`, `max_players = 2`

---

## 2. State Machine

```
INTRO  (phase='intro', parallel=False)
  │  Op: "Start the Game"  (role=None)
  ▼
CHOOSING  (phase='choosing', parallel=True)
  │  Op: "Cooperate (Stay Silent)"  (role=PA or PB)
  │  Op: "Defect (Betray Partner)"  (role=PA or PB)
  │  Both choices in → resolve round → jit_transition set
  ▼
REVEAL  (phase='reveal', parallel=False)
  │  Op: "Continue"  (role=None)
  ├─ round < max_rounds → CHOOSING (round_num += 1)
  └─ round == max_rounds → GAME_OVER
```

The `parallel=True` flag during the choosing phase tells the web portal to collect
both players' inputs simultaneously over WebSocket.  The Textual engine serialises
this via player cueing, with `text_view_for_role()` masking the opponent's choice.

---

## 3. Operators

| Index | Name | Role | Precondition |
|-------|------|------|-------------|
| 0 | `Start the Game` | None | `phase == 'intro'` |
| 1 | `Cooperate (Stay Silent)` | PA | `phase == 'choosing' and choices[PA] is None` |
| 2 | `Defect (Betray Partner)` | PA | `phase == 'choosing' and choices[PA] is None` |
| 3 | `Cooperate (Stay Silent)` | PB | `phase == 'choosing' and choices[PB] is None` |
| 4 | `Defect (Betray Partner)` | PB | `phase == 'choosing' and choices[PB] is None` |
| 5 | `Continue` | None | `phase == 'reveal'` |

Operators 1–4 share names across roles intentionally — the GSL `Op <user> <name>`
command routes correctly because `<user>` determines which role is acting.

---

## 4. State Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `phase` | str | `'intro'`, `'choosing'`, `'reveal'`, `'game_over'` |
| `round_num` | int | Current round (1-based) |
| `max_rounds` | int | Total rounds (default 5) |
| `scores` | [int, int] | Cumulative scores for PA and PB |
| `choices` | [int\|None, int\|None] | Current round choices; None = not yet chosen |
| `history` | list of dict | `{'choices': (ca, cb), 'scores': (sa, sb)}` per completed round |
| `parallel` | bool | True during choosing phase |
| `current_role_num` | int | Whose turn it is (used by Textual engine and assertions) |
| `active_roles` | [int, int] | Always `[0, 1]`; required by `Assert_role_count` GSL assertion |
| `jit_transition` | str\|None | Educational message set after each round is resolved |

---

## 5. Educational Transition Messages

A core design goal was embedding game-theory education directly into the game flow.
Messages appear as `jit_transition` text immediately after each round is resolved —
at the moment of highest player engagement.

### Per-round jit_transition

Each of the four outcome types triggers a distinct message:

**Mutual Cooperation (C,C):**
> Both players cooperated — the best collective outcome (+3 each).  This is
> 'Pareto optimal': neither player could do better without making the other worse off.
> Notice, however, that either player could have earned +5 by defecting here —
> the temptation is real.

**Mutual Defection (D,D):**
> Both players defected — the Nash Equilibrium (+1 each).  Each choice was
> individually 'rational': whatever your partner did, you could not have improved
> your score by switching.  Yet you both earned less than mutual cooperation would
> have given you.  This is the Tragedy of the Commons: individual rationality,
> collective irrationality.

**Temptation/Betrayal (D,C or C,D):**
> [Defector] earns the 'Temptation Payoff' (+5); [cooperator] suffers the 'Sucker's
> Payoff' (+0).  In a single-round game, defecting is always the dominant strategy.
> In iterated play, exploitation risks triggering a retaliation cycle.
> If [the betrayed player] adopts Tit-for-Tat — mirroring your last move —
> they will defect next round in retaliation.

The Tit-for-Tat warning is suppressed on the final round (no future rounds to retaliate in).

### Goal Message

`goal_message()` produces a post-game analysis:
- Final score and winner/tie declaration
- Count of each outcome type across all rounds
- Strategy commentary: detects always-cooperate, always-defect, cooperation-dominated,
  or betrayal-dominated patterns and explains the real-world implications
- References Robert Axelrod's computer tournaments and the Tragedy of the Commons

---

## 6. Role-Aware Information Hiding

During the choosing phase, `text_view_for_role(role_num)` masks the opponent's
choice to preserve simultaneous-choice fairness:

```
Your choice this round:       [C]          ← your actual choice (if made)
Opponent's choice this round: LOCKED IN    ← masked; opponent has chosen
```

```
Your choice this round:       (pending...) ← you haven't chosen yet
Opponent's choice this round: (deciding...)← opponent hasn't chosen yet
```

After both choices are in and the round resolves (`phase='reveal'`), both choices
are displayed openly.

---

## 7. Portal Visualization Module

`Prisoners_Dilemma_WSZ6_VIS.py` provides HTML rendering via `render_state(state, role_num, base_url)`.

### Phase-adaptive rendering

| Phase | What is shown |
|-------|--------------|
| `intro` | Narrative setup, formatted payoff matrix, central question |
| `choosing` | Player score cards (choice hidden/masked), payoff matrix, history strip |
| `reveal` | Both choices shown, outcome highlighted in payoff matrix cell, history strip |
| `game_over` | Final scores, outcome tally table, round history, end commentary |

### Visual elements

- **Payoff matrix** — always visible; the current round's outcome cell is highlighted
  in green (C,C), orange (D,C or C,D), or red (D,D) during the reveal phase
- **Player score cards** — show each player's cumulative score and current choice status
- **Round history strip** — compact badges with 🤝/⚔️ icons and per-round point deltas
- **End-game tally table** — row-per-outcome-type with colour coding
- **Commentary box** — educational paragraph in the game-over view, adapts to what happened

No external image assets are needed.

---

## 8. GSL Test Script

**`Test_PrisonersDilemma.gsl`** — runs in API mode (no browser required):

```
python manage.py run_gsl Test_PrisonersDilemma.gsl
```

### Test sequence (5 rounds)

| Round | A's choice | B's choice | Outcome | Cumulative A | Cumulative B |
|-------|-----------|-----------|---------|:------------:|:------------:|
| 1 | Cooperate | Cooperate | C,C → +3/+3 | 3 | 3 |
| 2 | Defect | Cooperate | D,C → +5/+0 | 8 | 3 |
| 3 | Defect | Defect | D,D → +1/+1 | 9 | 4 |
| 4 | Cooperate | Defect | C,D → +0/+5 | 9 | 9 |
| 5 | Cooperate | Cooperate | C,C → +3/+3 | 12 | 12 |

All 4 outcome types are exercised.  The test covers:
- Session setup, role assignment, game start
- Intro phase and `Start the Game` operator
- Parallel choosing phase (both players submit independently)
- Score accumulation after each round
- `choices.0` and `choices.1` correct after reveal
- `phase` and `round_num` transitions
- Final `Assert_phase ended` after `game_over`

### Key assertions used

```gsl
Assert_state  phase       choosing
Assert_state  round_num   3
Assert_state  scores.0    9
Assert_state  choices.1   0
Assert_phase  ended
```

---

## 9. GSL Live Session Script

**`Setup_PrisonersDilemma_Live.gsl`** — opens a browser-mode session for human play:

```
python manage.py run_gsl Setup_PrisonersDilemma_Live.gsl \
    --mode browser --headed --stay-open
```

Alice (admin) plays Prisoner A in the main browser window.
Bob (mock account) plays Prisoner B in a second tab opened automatically.
The `--stay-open` flag holds the session alive for interactive play.

---

## 10. What Remains Before Portal Deployment

1. **Register the game** — add a `prisoners_dilemma` row to the portal's game database
   (same process used for OCCLUEdo and rock_paper_scissors).  The PFF loader expects
   the directory slug `prisoners_dilemma` and the file `Prisoners_Dilemma_SZ6.py` to
   be present under `GAMES_REPO_ROOT`.

2. **Run the GSL test** — once registered:
   ```
   python manage.py run_gsl Test_PrisonersDilemma.gsl
   ```

3. **Run in browser mode** — for visual confirmation of the visualization module:
   ```
   python manage.py run_gsl Test_PrisonersDilemma.gsl --mode browser
   ```

4. **Live session** — for human testing:
   ```
   python manage.py run_gsl Setup_PrisonersDilemma_Live.gsl \
       --mode browser --headed --stay-open
   ```

5. **Optional enhancements** (from the plan document):
   - Strategy graph (line chart of cumulative scores over rounds) in the game-over view
   - Configurable round count surfaced in the portal's session-creation UI
   - A bot player with a selectable strategy (Always-Cooperate, Always-Defect, Tit-for-Tat)

---

## 11. Verification

The following was confirmed working before this report was written:

```
PYTHONPATH=/Users/slt/SZ6_Dev/Textual_SZ6 \
  python3 Prisoners_Dilemma_SZ6.py
```

Output verified:
- Intro box renders with all 4 payoff outcomes described
- Choosing phase masks opponent choices correctly per role
- All 4 outcome types produce correct scores and distinct educational messages
- Round history accumulates correctly
- `is_goal()` returns True after the final "Continue"
- `goal_message()` produces correct winner, tally, and commentary
- Visualization module imports cleanly

Score arithmetic also confirmed by independent assertion test covering the exact
sequence used in `Test_PrisonersDilemma.gsl`:

```
Round 1 (C,C): [0,0] → [3,3]    ✓
Round 2 (D,C): [3,3] → [8,3]    ✓
Round 3 (D,D): [8,3] → [9,4]    ✓
Round 4 (C,D): [9,4] → [9,9]    ✓
Round 5 (C,C): [9,9] → [12,12]  ✓
```

---

*End of report*
