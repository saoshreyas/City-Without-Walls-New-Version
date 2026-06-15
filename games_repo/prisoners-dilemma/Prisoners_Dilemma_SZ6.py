"""Prisoners_Dilemma_SZ6.py

The Iterated Prisoner's Dilemma for SOLUZION6.
Two players, DEFAULT_ROUNDS rounds (configurable via initialize_problem config).

Each round both players simultaneously and secretly choose:
  Cooperate (stay silent)  — or —  Defect (betray your partner)

Payoff matrix (points earned this round):
                  B Cooperates    B Defects
  A Cooperates      (3, 3)          (0, 5)
  A Defects         (5, 0)          (1, 1)

The simultaneous-choice mechanic uses state.parallel = True during the
choosing phase.  In the web portal both players submit independently over
WebSocket; Textual_SOLUZION6 serialises the choices via player cueing, with
text_view_for_role masking actual choices until both are in.

Phases:
  'intro'    -- initial state; rules are displayed; "Start the Game" advances
  'choosing' -- both players secretly choose; state.parallel = True
  'reveal'   -- both choices shown; jit_transition gives outcome explanation
  'game_over'-- after the final round's reveal + "Continue" click

Status: Initial SZ6 implementation, March 2026.
"""

SOLUZION_VERSION = 6

import soluzion6_02 as sz

# ---------------------------------------------------------------------------
# GLOBAL CONSTANTS
# ---------------------------------------------------------------------------

COOPERATE = 0
DEFECT    = 1

PA = 0   # Prisoner A  (role index)
PB = 1   # Prisoner B  (role index)

CHOICE_NAMES  = {COOPERATE: "Cooperate", DEFECT: "Defect"}
CHOICE_ICONS  = {COOPERATE: "[C]",       DEFECT: "[D]"}

# Payoff matrix: PAYOFFS[(ca, cb)] = (score_a, score_b)
PAYOFFS = {
    (COOPERATE, COOPERATE): (3, 3),
    (COOPERATE, DEFECT):    (0, 5),
    (DEFECT,    COOPERATE): (5, 0),
    (DEFECT,    DEFECT):    (1, 1),
}

OUTCOME_LABELS = {
    (COOPERATE, COOPERATE): "Mutual Cooperation",
    (COOPERATE, DEFECT):    "Betrayal (A cooperated, B defected)",
    (DEFECT,    COOPERATE): "Betrayal (A defected, B cooperated)",
    (DEFECT,    DEFECT):    "Mutual Defection",
}

DEFAULT_ROUNDS = 5

# ---------------------------------------------------------------------------
# METADATA
# ---------------------------------------------------------------------------

class PD_Metadata(sz.SZ_Metadata):
    def __init__(self):
        self.name             = "Prisoner's Dilemma"
        self.soluzion_version = SOLUZION_VERSION
        self.problem_version  = "1.0"
        self.authors          = ['S. Tanimoto', 'Claude']
        self.creation_date    = "2026-Mar"
        self.brief_desc = (
            "An iterated Prisoner's Dilemma for two players. "
            "Each round both players secretly choose to Cooperate or Defect. "
            "Mutual cooperation earns +3 each; mutual defection earns +1 each. "
            "Betraying a cooperator earns +5 (betrayer) / +0 (betrayed). "
            f"The game lasts {DEFAULT_ROUNDS} rounds by default."
        )

# ---------------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------------

class PD_State(sz.SZ_State):
    """One moment in an Iterated Prisoner's Dilemma match.

    Phases:
      'intro'    -- before play begins; rules displayed.
      'choosing' -- both players are choosing; parallel = True.
      'reveal'   -- both choices are in; round result visible; parallel = False.
      'game_over'-- after the final round's "Continue"; is_goal() returns True.
    """

    def __init__(self, old=None, max_rounds=DEFAULT_ROUNDS):
        if old is None:
            self.max_rounds       = max_rounds
            self.round_num        = 1
            self.scores           = [0, 0]        # [PA_total, PB_total]
            self.phase            = 'intro'
            self.choices          = [None, None]  # current round; None = not yet chosen
            self.history          = []            # list of {'choices':(ca,cb), 'scores':(sa,sb)}
            self.parallel         = False
            self.current_role_num = PA
            self.active_roles     = [PA, PB]
        else:
            self.max_rounds       = old.max_rounds
            self.round_num        = old.round_num
            self.scores           = old.scores[:]
            self.phase            = old.phase
            self.choices          = old.choices[:]
            self.history          = [h.copy() for h in old.history]
            self.parallel         = old.parallel
            self.current_role_num = old.current_role_num
            self.active_roles     = old.active_roles[:]

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __str__(self):
        return self.text_view_for_role(self.current_role_num)

    def text_view_for_role(self, role_num):
        if self.phase == 'intro':
            return _build_intro(self.max_rounds)

        role_label = "Prisoner A" if role_num == PA else "Prisoner B"
        lines = []
        lines.append(f"=== Prisoner's Dilemma — Round {self.round_num} of {self.max_rounds} ===")
        lines.append(f"You are: {role_label}")
        lines.append(f"Scores:  A = {self.scores[PA]},  B = {self.scores[PB]}")
        lines.append("")
        lines.append(_PAYOFF_TABLE)
        lines.append("")

        if self.phase == 'choosing':
            my_choice    = self.choices[role_num]
            their_choice = self.choices[1 - role_num]
            my_str    = CHOICE_ICONS[my_choice] if my_choice is not None else "(pending...)"
            their_str = "LOCKED IN"              if their_choice is not None else "(deciding...)"
            lines.append(f"Your choice this round:      {my_str}")
            lines.append(f"Opponent's choice this round: {their_str}")

        elif self.phase in ('reveal', 'game_over'):
            ca, cb = self.choices
            lines.append(f"A chose: {CHOICE_NAMES[ca]}   B chose: {CHOICE_NAMES[cb]}")
            lines.append(f"Outcome: {OUTCOME_LABELS[(ca, cb)]}")
            if self.phase == 'game_over':
                lines.append("")
                lines.append("--- GAME OVER ---")

        if self.history:
            lines.append("")
            lines.append("Round history:")
            for i, h in enumerate(self.history, 1):
                ca, cb = h['choices']
                sa, sb = h['scores']
                lines.append(
                    f"  Rd {i}: A={CHOICE_ICONS[ca]} B={CHOICE_ICONS[cb]}"
                    f"  → A:{sa:+d}  B:{sb:+d}"
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Equality / hashing (required for state stack / undo)
    # ------------------------------------------------------------------

    def __eq__(self, s):
        return (self.round_num  == s.round_num  and
                self.scores     == s.scores     and
                self.phase      == s.phase      and
                self.choices    == s.choices    and
                len(self.history) == len(s.history))

    def __hash__(self):
        return hash((self.round_num, tuple(self.scores), self.phase,
                     tuple(self.choices)))

    # ------------------------------------------------------------------
    # Move application
    # ------------------------------------------------------------------

    def apply_choice(self, player, choice):
        """Return new state after `player` submits `choice`.

        If both choices are now in, resolves the round and builds
        jit_transition.  Otherwise just records the choice and flips
        current_role_num so the serial engine cues the other player.
        """
        news = PD_State(old=self)
        news.choices[player] = choice

        if news.choices[PA] is not None and news.choices[PB] is not None:
            _resolve_round(news)
        else:
            # One player down; cue the other.
            news.current_role_num = PB if player == PA else PA

        return news

    # ------------------------------------------------------------------
    # Goal
    # ------------------------------------------------------------------

    def is_goal(self):
        return self.phase == 'game_over'

    def goal_message(self):
        sa, sb = self.scores[PA], self.scores[PB]

        if sa > sb:
            winner_line = f"Prisoner A wins the match!  (A={sa}, B={sb})"
        elif sb > sa:
            winner_line = f"Prisoner B wins the match!  (A={sa}, B={sb})"
        else:
            winner_line = f"The match is a draw!  (A={sa}, B={sb})"

        # Tally outcomes
        cc = dd = ad = da = 0
        for h in self.history:
            ca, cb = h['choices']
            if   (ca, cb) == (COOPERATE, COOPERATE): cc += 1
            elif (ca, cb) == (DEFECT,    DEFECT):    dd += 1
            elif (ca, cb) == (COOPERATE, DEFECT):    ad += 1
            else:                                     da += 1

        tally = (
            f"  Mutual Cooperation (C,C): {cc} rounds\n"
            f"  Mutual Defection   (D,D): {dd} rounds\n"
            f"  A betrayed B       (D,C): {da} rounds\n"
            f"  B betrayed A       (C,D): {ad} rounds"
        )

        # Strategy commentary
        if cc == self.max_rounds:
            commentary = (
                "Both players cooperated every round — the best possible\n"
                "collective outcome.  This requires mutual trust, which is\n"
                "rational in iterated play when both parties expect to meet again."
            )
        elif dd == self.max_rounds:
            commentary = (
                "Both players defected every round — the Nash Equilibrium.\n"
                "Each individual choice was 'rational', yet together you\n"
                "scored far less than mutual cooperation would have yielded.\n"
                "This is the Tragedy of the Commons."
            )
        elif cc > dd:
            commentary = (
                "Cooperation dominated this match.  In Robert Axelrod's famous\n"
                "computer tournaments, strategies that started with cooperation\n"
                "and reciprocated (Tit-for-Tat) consistently outperformed\n"
                "always-defect strategies over repeated interactions."
            )
        else:
            commentary = (
                "Defection dominated this match.  Once trust breaks down,\n"
                "retaliation cycles can trap both players in mutual defection.\n"
                "Real-world parallels: arms races, price wars, overfishing,\n"
                "climate inaction — all share this same payoff structure."
            )

        return (
            f"{winner_line}\n\n"
            f"Outcome breakdown:\n{tally}\n\n"
            f"What does this mean?\n{commentary}"
        )


# ---------------------------------------------------------------------------
# STATIC TEXT
# ---------------------------------------------------------------------------

def _build_intro(max_rounds: int) -> str:
    """Build the intro screen, padding the round-count line to fit the box."""
    prefix  = f"  This game lasts {max_rounds} rounds.  After each round"
    # Box inner width = 62 chars; pad to fill
    line    = f"║{prefix.ljust(62)}║"
    return _INTRO_TEMPLATE.replace("__ROUNDS_LINE__", line)


_INTRO_TEMPLATE = """\
╔══════════════════════════════════════════════════════════════╗
║              THE PRISONER'S DILEMMA                         ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  You and your partner have been arrested.  The police        ║
║  have separated you.  Each of you must independently         ║
║  decide — without knowing the other's choice:                ║
║                                                              ║
║  • COOPERATE (stay silent)                                   ║
║  • DEFECT    (betray your partner)                           ║
║                                                              ║
║  The consequences:                                           ║
║                                                              ║
║    Both Cooperate   → you both earn  +3 points each          ║
║    You Defect,                                               ║
║      partner Cooperates → you earn +5, partner earns +0      ║
║    You Cooperate,                                            ║
║      partner Defects → you earn +0, partner earns +5         ║
║    Both Defect       → you both earn  +1 point each          ║
║                                                              ║
__ROUNDS_LINE__
║  you will see choices revealed and learn what they mean.     ║
║                                                              ║
║  The question: can rational self-interest coexist with       ║
║  mutual benefit?  Play to find out.                          ║
║                                                              ║
║  Press "Start the Game" when both players are ready.         ║
╚══════════════════════════════════════════════════════════════╝"""

_PAYOFF_TABLE = """\
  Payoff matrix (your points, opponent's points):
  ┌──────────────┬────────────────┬──────────────┐
  │              │  B Cooperates  │  B Defects   │
  ├──────────────┼────────────────┼──────────────┤
  │ A Cooperates │   A:+3, B:+3   │  A:+0, B:+5  │
  │ A Defects    │   A:+5, B:+0   │  A:+1, B:+1  │
  └──────────────┴────────────────┴──────────────┘"""


# ---------------------------------------------------------------------------
# ROUND-RESOLUTION HELPER
# ---------------------------------------------------------------------------

def _resolve_round(state):
    """Mutate state to reflect a completed round (both choices are set).

    Updates cumulative scores, appends history entry, sets jit_transition,
    and advances the phase to 'reveal' (or 'game_over' on the last round
    — but the "Continue" operator handles that transition; here we go to
    'reveal' in all cases so the player always sees the round result).
    """
    ca, cb     = state.choices
    sa, sb     = PAYOFFS[(ca, cb)]
    state.scores[PA] += sa
    state.scores[PB] += sb

    state.history.append({'choices': (ca, cb), 'scores': (sa, sb)})

    outcome_label = OUTCOME_LABELS[(ca, cb)]
    commentary    = _outcome_commentary(ca, cb, state.round_num, state.max_rounds)

    state.jit_transition = (
        f"--- Round {state.round_num} Result ---\n"
        f"A chose {CHOICE_NAMES[ca]}.  B chose {CHOICE_NAMES[cb]}.\n"
        f"Outcome: {outcome_label}\n"
        f"Points this round:  A: {sa:+d},  B: {sb:+d}\n"
        f"Cumulative scores:  A = {state.scores[PA]},  B = {state.scores[PB]}\n"
        f"\n{commentary}"
    )

    state.parallel         = False
    state.current_role_num = PA   # PA triggers "Continue" (or either player can)
    state.phase            = 'reveal'


def _outcome_commentary(ca, cb, round_num, max_rounds):
    """Return an educational paragraph for the outcome of one round."""
    rounds_left = max_rounds - round_num

    if (ca, cb) == (COOPERATE, COOPERATE):
        base = (
            "Both players cooperated — the best collective outcome (+3 each).\n"
            "This is 'Pareto optimal': neither player could do better without\n"
            "making the other worse off.  Notice, however, that either player\n"
            "could have earned +5 by defecting here — the temptation is real."
        )
        if rounds_left == 0:
            return base + "\nYou ended on mutual trust.  Well played."
        return base

    elif (ca, cb) == (DEFECT, DEFECT):
        return (
            "Both players defected — the Nash Equilibrium (+1 each).\n"
            "Each choice was individually 'rational': whatever your partner did,\n"
            "you could not have improved your score by switching.  Yet you both\n"
            "earned less than mutual cooperation would have given you.\n"
            "This is the Tragedy of the Commons: individual rationality,\n"
            "collective irrationality."
        )

    elif (ca, cb) == (DEFECT, COOPERATE):
        extra = ""
        if rounds_left > 0:
            extra = (
                "\nIf B adopts Tit-for-Tat — mirroring your last move —\n"
                "they will defect next round in retaliation."
            )
        return (
            "A defected while B cooperated.  A earns the 'Temptation Payoff' (+5);\n"
            "B suffers the 'Sucker's Payoff' (+0).\n"
            "In a single-round game, defecting is always the dominant strategy.\n"
            "In iterated play, exploitation risks triggering a retaliation cycle."
            + extra
        )

    else:  # (COOPERATE, DEFECT)
        extra = ""
        if rounds_left > 0:
            extra = (
                "\nIf A adopts Tit-for-Tat — mirroring your last move —\n"
                "they will defect next round in retaliation."
            )
        return (
            "B defected while A cooperated.  B earns the 'Temptation Payoff' (+5);\n"
            "A suffers the 'Sucker's Payoff' (+0).\n"
            "In a single-round game, defecting is always the dominant strategy.\n"
            "In iterated play, exploitation risks triggering a retaliation cycle."
            + extra
        )


# ---------------------------------------------------------------------------
# TRANSITION HELPERS
# ---------------------------------------------------------------------------

def _start_game(s):
    """Operator transition: intro → first choosing phase."""
    news               = PD_State(old=s)
    news.phase         = 'choosing'
    news.choices       = [None, None]
    news.parallel      = True
    news.current_role_num = PA
    return news


def _continue_round(s):
    """Operator transition: reveal → next choosing phase (or game_over)."""
    news = PD_State(old=s)
    if news.round_num >= news.max_rounds:
        news.phase    = 'game_over'
        news.parallel = False
    else:
        news.round_num       += 1
        news.phase            = 'choosing'
        news.choices          = [None, None]
        news.parallel         = True
        news.current_role_num = PA
    return news


# ---------------------------------------------------------------------------
# OPERATORS
# ---------------------------------------------------------------------------

class PD_Operator_Set(sz.SZ_Operator_Set):
    """
    Operators for the Prisoner's Dilemma:

      0. Start the Game          (role=None, intro phase only)
      1. Cooperate (Stay Silent) (role=PA,   choosing phase, PA not yet chosen)
      2. Defect (Betray Partner) (role=PA,   choosing phase, PA not yet chosen)
      3. Cooperate (Stay Silent) (role=PB,   choosing phase, PB not yet chosen)
      4. Defect (Betray Partner) (role=PB,   choosing phase, PB not yet chosen)
      5. Continue                (role=None, reveal phase)

    Choice operators carry op.role = PA or PB so that Textual_SOLUZION6's
    applicability filter shows each player only their own choices during the
    serialised choosing phase, and so the web portal routes correctly.
    """

    def __init__(self):
        start_op = sz.SZ_Operator(
            name="Start the Game",
            description=(
                "Begin the first round.  Both players must be ready before "
                "clicking this."
            ),
            precond_func=lambda s: s.phase == 'intro',
            state_xition_func=_start_game,
            role=None,
        )

        pa_coop = sz.SZ_Operator(
            name="Cooperate (Stay Silent)",
            description=(
                "Stay silent.  If your partner also cooperates you both earn +3. "
                "If your partner defects, you earn +0 and they earn +5."
            ),
            precond_func=lambda s: s.phase == 'choosing' and s.choices[PA] is None,
            state_xition_func=lambda s: s.apply_choice(PA, COOPERATE),
            role=PA,
        )

        pa_defe = sz.SZ_Operator(
            name="Defect (Betray Partner)",
            description=(
                "Betray your partner.  If they cooperate, you earn +5 and they "
                "earn +0.  If they also defect, you both earn only +1."
            ),
            precond_func=lambda s: s.phase == 'choosing' and s.choices[PA] is None,
            state_xition_func=lambda s: s.apply_choice(PA, DEFECT),
            role=PA,
        )

        pb_coop = sz.SZ_Operator(
            name="Cooperate (Stay Silent)",
            description=(
                "Stay silent.  If your partner also cooperates you both earn +3. "
                "If your partner defects, you earn +0 and they earn +5."
            ),
            precond_func=lambda s: s.phase == 'choosing' and s.choices[PB] is None,
            state_xition_func=lambda s: s.apply_choice(PB, COOPERATE),
            role=PB,
        )

        pb_defe = sz.SZ_Operator(
            name="Defect (Betray Partner)",
            description=(
                "Betray your partner.  If they cooperate, you earn +5 and they "
                "earn +0.  If they also defect, you both earn only +1."
            ),
            precond_func=lambda s: s.phase == 'choosing' and s.choices[PB] is None,
            state_xition_func=lambda s: s.apply_choice(PB, DEFECT),
            role=PB,
        )

        continue_op = sz.SZ_Operator(
            name="Continue",
            description="Advance to the next round (or end the game after the last round).",
            precond_func=lambda s: s.phase == 'reveal',
            state_xition_func=_continue_round,
            role=None,
        )

        self.operators = [
            start_op,
            pa_coop, pa_defe,
            pb_coop, pb_defe,
            continue_op,
        ]


# ---------------------------------------------------------------------------
# ROLES
# ---------------------------------------------------------------------------

class PD_Roles_Spec(sz.SZ_Roles_Spec):
    def __init__(self):
        self.roles = [
            sz.SZ_Role(
                name='Prisoner A',
                description=(
                    "You are Prisoner A.  You are being interrogated in a room "
                    "separate from your partner.  Each round you choose to "
                    "Cooperate (stay silent) or Defect (betray your partner)."
                ),
            ),
            sz.SZ_Role(
                name='Prisoner B',
                description=(
                    "You are Prisoner B.  You are being interrogated in a room "
                    "separate from your partner.  Each round you choose to "
                    "Cooperate (stay silent) or Defect (betray your partner)."
                ),
            ),
        ]
        self.min_players_to_start = 2
        self.max_players          = 2


# ---------------------------------------------------------------------------
# FORMULATION
# ---------------------------------------------------------------------------

class PD_Formulation(sz.SZ_Formulation):
    def __init__(self):
        self.metadata    = PD_Metadata()
        self.operators   = PD_Operator_Set()
        self.roles_spec  = PD_Roles_Spec()
        self.common_data = sz.SZ_Common_Data()

    def initialize_problem(self, config={}):
        max_rounds    = int(config.get('max_rounds', DEFAULT_ROUNDS))
        initial_state = PD_State(max_rounds=max_rounds)
        self.instance_data = sz.SZ_Problem_Instance_Data(
            d={'initial_state': initial_state}
        )
        return initial_state


# ---------------------------------------------------------------------------
# MODULE-LEVEL ENTRY POINT
# ---------------------------------------------------------------------------

PD = PD_Formulation()

# ---------------------------------------------------------------------------
# SELF-TEST  (run with: python3 Prisoners_Dilemma_SZ6.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Prisoner's Dilemma SZ6 self-test ===\n")

    s = PD.initialize_problem()
    ops = PD.operators.operators
    # ops[0] = Start the Game
    # ops[1] = PA Cooperate,  ops[2] = PA Defect
    # ops[3] = PB Cooperate,  ops[4] = PB Defect
    # ops[5] = Continue

    print(f"Initial state (intro):\n{s}\n")

    # Start the game
    s = ops[0].state_xition_func(s)
    print(f"After Start (PA view):\n{s.text_view_for_role(PA)}\n")

    # --- Round 1: Both cooperate (C, C) ---
    s = ops[1].state_xition_func(s)   # PA cooperates
    print(f"PA has chosen (PB view):\n{s.text_view_for_role(PB)}\n")
    s = ops[3].state_xition_func(s)   # PB cooperates
    print(f"Round 1 reveal — transition:\n{s.jit_transition}\n")
    print(f"Reveal state:\n{s}\n")

    # Continue to round 2
    s = ops[5].state_xition_func(s)

    # --- Round 2: PA defects, PB cooperates (D, C) ---
    s = ops[2].state_xition_func(s)   # PA defects
    s = ops[3].state_xition_func(s)   # PB cooperates
    print(f"Round 2 reveal — transition:\n{s.jit_transition}\n")

    # Continue through rounds 3–5 (both defect each time)
    for r in range(3, 6):
        s = ops[5].state_xition_func(s)
        s = ops[2].state_xition_func(s)   # PA defects
        s = ops[4].state_xition_func(s)   # PB defects
        print(f"Round {r} (D,D) transition:\n{s.jit_transition}\n")

    # Last Continue → game_over
    s = ops[5].state_xition_func(s)
    print(f"Final state:\n{s}\n")
    print(f"is_goal: {s.is_goal()}")
    print(f"\ngoal_message:\n{s.goal_message()}")
