"""
Prisoners_Dilemma_WSZ6_VIS.py

WSZ6 Portal visualization module for the Prisoner's Dilemma.
Companion to Prisoners_Dilemma_SZ6.py.

Convention: the vis file has the same filename prefix as the PFF, with the
suffix _WSZ6_VIS replacing _SZ6.

Public API (called by the game runner):
    render_state(state, role_num=0, base_url='') -> str
        Return an HTML string for the current game state.
        role_num determines which player's perspective is shown.

State attributes used (duck-typed; no import from the PFF):
    state.phase           -- 'intro' | 'choosing' | 'reveal' | 'game_over'
    state.round_num       -- int, current round (1-based)
    state.max_rounds      -- int
    state.scores          -- [int, int]  cumulative scores
    state.choices         -- [int|None, int|None]  this round's choices
    state.history         -- list of {'choices':(ca,cb), 'scores':(sa,sb)}
    state.current_role_num -- int
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants  (mirrors PFF values; never import from PFF)
# ---------------------------------------------------------------------------

_COOPERATE = 0
_DEFECT    = 1
_PA        = 0
_PB        = 1

_CHOICE_LABEL  = {_COOPERATE: "Cooperate", _DEFECT: "Defect"}
_CHOICE_ICON   = {_COOPERATE: "🤝", _DEFECT: "⚔️"}
_CHOICE_COLOR  = {_COOPERATE: "#2e7d32", _DEFECT: "#c62828"}  # dark-green / dark-red

_OUTCOME_LABEL = {
    (_COOPERATE, _COOPERATE): "Mutual Cooperation",
    (_COOPERATE, _DEFECT):    "Betrayal — B defected",
    (_DEFECT,    _COOPERATE): "Betrayal — A defected",
    (_DEFECT,    _DEFECT):    "Mutual Defection (Nash Equilibrium)",
}

# Highlight colours for the payoff matrix cells
_CELL_HIGHLIGHT = {
    (_COOPERATE, _COOPERATE): "#a5d6a7",   # green
    (_COOPERATE, _DEFECT):    "#ffcc80",   # orange
    (_DEFECT,    _COOPERATE): "#ffcc80",   # orange
    (_DEFECT,    _DEFECT):    "#ef9a9a",   # red
}
_CELL_DEFAULT = "#f5f5f5"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_state(state, role_num: int = 0, base_url: str = '') -> str:
    """Return HTML visualising *state* from the perspective of *role_num*.

    base_url is injected by the game runner but unused (no external assets).
    """
    phase = getattr(state, 'phase', 'intro')

    if phase == 'intro':
        return _render_intro(state)
    elif phase == 'choosing':
        return _render_choosing(state, role_num)
    elif phase == 'reveal':
        return _render_reveal(state)
    elif phase == 'game_over':
        return _render_game_over(state)
    else:
        return f'<p>Unknown phase: {_esc(str(phase))}</p>'


# ---------------------------------------------------------------------------
# Phase renderers
# ---------------------------------------------------------------------------

def _render_intro(state) -> str:
    max_r = getattr(state, 'max_rounds', 5)
    return f'''
<div style="{_CONTAINER_STYLE}">
  <div style="{_TITLE_STYLE}">The Prisoner&#8217;s Dilemma</div>

  <div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:8px;
              padding:18px 22px;margin-bottom:18px;font-size:15px;line-height:1.7;">
    <p style="margin:0 0 10px 0;">
      You and your partner have been arrested and placed in separate rooms.
      Each round you must independently decide:
    </p>
    <ul style="margin:0 0 10px 20px;padding:0;">
      <li><strong>Cooperate</strong> — stay silent, trust your partner</li>
      <li><strong>Defect</strong> — betray your partner to the authorities</li>
    </ul>
    <p style="margin:0;">
      You cannot see your partner&#8217;s choice until <em>both</em> of you
      have decided.  The game lasts <strong>{max_r} rounds</strong>.
    </p>
  </div>

  {_payoff_matrix_html()}

  <div style="text-align:center;margin-top:18px;font-size:14px;color:#555;">
    The central question of game theory:<br>
    <em>Can rational self-interest coexist with mutual benefit?</em>
  </div>
</div>'''


def _render_choosing(state, role_num: int) -> str:
    my_choice    = state.choices[role_num]
    their_choice = state.choices[1 - role_num]
    role_name    = "Prisoner A" if role_num == _PA else "Prisoner B"

    my_status    = (_choice_badge(my_choice)
                    if my_choice is not None
                    else '<span style="color:#888;font-style:italic;">Deciding…</span>')
    their_status = ('<span style="color:#1565c0;font-weight:600;">Locked in ✓</span>'
                    if their_choice is not None
                    else '<span style="color:#888;font-style:italic;">Deciding…</span>')

    return f'''
<div style="{_CONTAINER_STYLE}">
  {_header_bar(state)}

  <div style="display:flex;gap:14px;margin-bottom:16px;">
    {_player_card("Prisoner A", state.scores[_PA],
                  state.choices[_PA], is_me=(role_num == _PA))}
    {_player_card("Prisoner B", state.scores[_PB],
                  state.choices[_PB], is_me=(role_num == _PB))}
  </div>

  <div style="background:#fff3e0;border:1px solid #ffcc80;border-radius:8px;
              padding:14px 18px;margin-bottom:16px;">
    <div style="font-weight:600;margin-bottom:6px;">Your turn — {_esc(role_name)}</div>
    <div>Your choice: {my_status}</div>
    <div>Partner&#8217;s choice: {their_status}</div>
  </div>

  {_payoff_matrix_html()}
  {_history_strip(state.history)}
</div>'''


def _render_reveal(state) -> str:
    ca, cb = state.choices
    highlight = (ca, cb)

    outcome  = _OUTCOME_LABEL.get(highlight, "Unknown")
    sa, sb   = _payoff(ca, cb)
    bg_color = _CELL_HIGHLIGHT.get(highlight, "#fff9c4")

    return f'''
<div style="{_CONTAINER_STYLE}">
  {_header_bar(state)}

  <div style="display:flex;gap:14px;margin-bottom:16px;">
    {_player_card("Prisoner A", state.scores[_PA], ca, is_me=False, reveal=True)}
    {_player_card("Prisoner B", state.scores[_PB], cb, is_me=False, reveal=True)}
  </div>

  <div style="background:{bg_color};border-radius:8px;padding:16px 20px;
              margin-bottom:16px;text-align:center;">
    <div style="font-size:22px;margin-bottom:8px;">
      {_CHOICE_ICON.get(ca,"?")} &nbsp;vs&nbsp; {_CHOICE_ICON.get(cb,"?")}
    </div>
    <div style="font-weight:700;font-size:16px;margin-bottom:6px;">
      {_esc(outcome)}
    </div>
    <div style="font-size:14px;color:#333;">
      Points this round:&nbsp;&nbsp;
      A: <strong>{sa:+d}</strong>&nbsp;&nbsp;
      B: <strong>{sb:+d}</strong>
    </div>
  </div>

  {_payoff_matrix_html(highlight)}
  {_history_strip(state.history)}
</div>'''


def _render_game_over(state) -> str:
    sa, sb = state.scores[_PA], state.scores[_PB]

    if sa > sb:
        winner_text = "Prisoner A wins!"
        winner_color = "#1565c0"
    elif sb > sa:
        winner_text = "Prisoner B wins!"
        winner_color = "#6a1b9a"
    else:
        winner_text = "It&#8217;s a draw!"
        winner_color = "#4e342e"

    # Outcome tally
    cc = dd = ad = da = 0
    for h in state.history:
        ca, cb = h['choices']
        if   (ca, cb) == (_COOPERATE, _COOPERATE): cc += 1
        elif (ca, cb) == (_DEFECT,    _DEFECT):    dd += 1
        elif (ca, cb) == (_COOPERATE, _DEFECT):    ad += 1
        else:                                       da += 1

    tally_html = f'''
    <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:12px;">
      <tr style="background:#e8eaf6;">
        <th style="padding:6px 10px;text-align:left;">Outcome</th>
        <th style="padding:6px 10px;text-align:center;">Rounds</th>
      </tr>
      <tr style="background:#a5d6a7;">
        <td style="padding:5px 10px;">🤝 Mutual Cooperation (C,C)</td>
        <td style="padding:5px 10px;text-align:center;font-weight:700;">{cc}</td>
      </tr>
      <tr style="background:#ef9a9a;">
        <td style="padding:5px 10px;">⚔️ Mutual Defection (D,D)</td>
        <td style="padding:5px 10px;text-align:center;font-weight:700;">{dd}</td>
      </tr>
      <tr style="background:#ffcc80;">
        <td style="padding:5px 10px;">⚔️ A betrayed B (D,C)</td>
        <td style="padding:5px 10px;text-align:center;font-weight:700;">{da}</td>
      </tr>
      <tr style="background:#ffcc80;">
        <td style="padding:5px 10px;">⚔️ B betrayed A (C,D)</td>
        <td style="padding:5px 10px;text-align:center;font-weight:700;">{ad}</td>
      </tr>
    </table>'''

    commentary = _end_commentary(cc, dd, da, ad, state.max_rounds)

    return f'''
<div style="{_CONTAINER_STYLE}">
  <div style="text-align:center;padding:18px 0 12px;
              font-size:26px;font-weight:700;color:{winner_color};">
    {winner_text}
  </div>
  <div style="text-align:center;font-size:18px;margin-bottom:18px;">
    Final scores: &nbsp;
    <strong style="color:#1565c0;">A = {sa}</strong>
    &nbsp;&nbsp;
    <strong style="color:#6a1b9a;">B = {sb}</strong>
  </div>

  {tally_html}

  {_history_strip(state.history)}

  <div style="background:#e3f2fd;border:1px solid #90caf9;border-radius:8px;
              padding:14px 18px;margin-top:16px;font-size:14px;line-height:1.65;">
    <div style="font-weight:700;margin-bottom:6px;">What does this mean?</div>
    {commentary}
  </div>
</div>'''


# ---------------------------------------------------------------------------
# Shared sub-components
# ---------------------------------------------------------------------------

def _header_bar(state) -> str:
    phase = state.phase
    label = "Choose your action" if phase == 'choosing' else "Round result"
    return (
        f'<div style="display:flex;justify-content:space-between;'
        f'align-items:center;margin-bottom:14px;">'
        f'<div style="font-size:18px;font-weight:700;">{_esc(label)}</div>'
        f'<div style="font-size:14px;color:#666;">'
        f'Round {state.round_num} / {state.max_rounds}</div>'
        f'</div>'
    )


def _player_card(name: str, score: int, choice, is_me: bool,
                  reveal: bool = False) -> str:
    border = "2px solid #1976d2" if is_me else "1px solid #ccc"
    bg     = "#e3f2fd"           if is_me else "#fafafa"

    if choice is None:
        choice_str = '<span style="color:#aaa;font-style:italic;">Deciding…</span>'
    elif reveal:
        color = _CHOICE_COLOR.get(choice, "#333")
        icon  = _CHOICE_ICON.get(choice, "?")
        label = _CHOICE_LABEL.get(choice, "?")
        choice_str = (f'<span style="color:{color};font-weight:700;">'
                      f'{icon} {_esc(label)}</span>')
    else:
        # choosing phase — my own choice is visible, opponent's is masked by caller
        color = _CHOICE_COLOR.get(choice, "#333")
        icon  = _CHOICE_ICON.get(choice, "?")
        label = _CHOICE_LABEL.get(choice, "?")
        choice_str = (f'<span style="color:{color};font-weight:700;">'
                      f'{icon} {_esc(label)} ✓</span>')

    return (
        f'<div style="flex:1;background:{bg};border:{border};border-radius:10px;'
        f'padding:12px 16px;text-align:center;">'
        f'<div style="font-weight:700;margin-bottom:6px;">{_esc(name)}</div>'
        f'<div style="font-size:22px;font-weight:700;color:#333;margin-bottom:6px;">'
        f'{score}</div>'
        f'<div style="font-size:12px;color:#555;">points</div>'
        f'<div style="margin-top:8px;font-size:13px;">{choice_str}</div>'
        f'</div>'
    )


def _choice_badge(choice) -> str:
    color = _CHOICE_COLOR.get(choice, "#333")
    icon  = _CHOICE_ICON.get(choice, "?")
    label = _CHOICE_LABEL.get(choice, "?")
    return (f'<span style="background:{color};color:#fff;padding:2px 10px;'
            f'border-radius:12px;font-size:13px;font-weight:600;">'
            f'{icon} {_esc(label)}</span>')


def _payoff_matrix_html(highlight: tuple | None = None) -> str:
    """Render the 2×2 payoff matrix as an HTML table.

    highlight: (ca, cb) tuple — that cell will be highlighted.
    """
    cells = {}
    payoffs_data = {
        (_COOPERATE, _COOPERATE): ("A:+3, B:+3", "Mutual Benefit"),
        (_COOPERATE, _DEFECT):    ("A:+0, B:+5", "Sucker's Payoff"),
        (_DEFECT,    _COOPERATE): ("A:+5, B:+0", "Temptation"),
        (_DEFECT,    _DEFECT):    ("A:+1, B:+1", "Nash Equilibrium"),
    }

    rows = ""
    for ca in [_COOPERATE, _DEFECT]:
        row_label = "A: 🤝 Cooperate" if ca == _COOPERATE else "A: ⚔️ Defect"
        row_html  = f'<td style="{_TD_HEADER}">{row_label}</td>'
        for cb in [_COOPERATE, _DEFECT]:
            key    = (ca, cb)
            payoff, sublabel = payoffs_data[key]
            bg     = _CELL_HIGHLIGHT[key] if key == highlight else _CELL_DEFAULT
            border = "2px solid #333"     if key == highlight else "1px solid #ccc"
            fw     = "700"                if key == highlight else "400"
            row_html += (
                f'<td style="padding:8px;text-align:center;background:{bg};'
                f'border:{border};font-weight:{fw};font-size:13px;">'
                f'<div style="font-size:12px;color:#555;">{_esc(sublabel)}</div>'
                f'<div>{_esc(payoff)}</div>'
                f'</td>'
            )
        rows += f'<tr>{row_html}</tr>'

    header = (
        f'<tr>'
        f'<td style="{_TD_HEADER}"></td>'
        f'<td style="{_TD_HEADER}">B: 🤝 Cooperate</td>'
        f'<td style="{_TD_HEADER}">B: ⚔️ Defect</td>'
        f'</tr>'
    )

    return (
        '<div style="margin-bottom:14px;">'
        '<div style="font-size:12px;font-weight:700;color:#555;margin-bottom:4px;">'
        'PAYOFF MATRIX</div>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        f'{header}{rows}'
        '</table></div>'
    )


def _history_strip(history: list) -> str:
    if not history:
        return ''

    badges = []
    for i, h in enumerate(history, 1):
        ca, cb = h['choices']
        sa, sb = h['scores']
        icon_a = _CHOICE_ICON.get(ca, "?")
        icon_b = _CHOICE_ICON.get(cb, "?")
        bg = _CELL_HIGHLIGHT.get((ca, cb), "#fff9c4")
        badges.append(
            f'<div title="Round {i}: A {_CHOICE_LABEL.get(ca,"?")} / '
            f'B {_CHOICE_LABEL.get(cb,"?")}" '
            f'style="background:{bg};border:1px solid #ccc;border-radius:6px;'
            f'padding:4px 8px;font-size:12px;text-align:center;min-width:50px;">'
            f'<div style="font-size:11px;color:#555;">Rd {i}</div>'
            f'<div>{icon_a}{icon_b}</div>'
            f'<div style="color:#333;">{sa:+d}/{sb:+d}</div>'
            f'</div>'
        )

    badges_html = "\n".join(badges)
    return (
        '<div style="margin-top:14px;">'
        '<div style="font-size:12px;font-weight:700;color:#555;margin-bottom:6px;">'
        'ROUND HISTORY</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:6px;">{badges_html}</div>'
        '</div>'
    )


def _end_commentary(cc: int, dd: int, da: int, ad: int, max_rounds: int) -> str:
    betrayals = da + ad
    if cc == max_rounds:
        return (
            "Both players cooperated every round — the best possible "
            "collective outcome. This demonstrates that mutual trust is "
            "achievable in iterated play, and that it pays off more than "
            "mutual defection over time."
        )
    elif dd == max_rounds:
        return (
            "Both players defected every round — the Nash Equilibrium. "
            "Each individual choice was technically 'rational', yet together "
            "you scored far less than mutual cooperation would have given. "
            "This is the <strong>Tragedy of the Commons</strong>: "
            "individually rational decisions producing collectively irrational outcomes."
        )
    elif cc > dd and betrayals == 0:
        return (
            "Cooperation dominated with no betrayals. "
            "Robert Axelrod&#8217;s famous computer tournaments showed that "
            "<em>Tit-for-Tat</em> — start cooperating, mirror your partner&#8217;s "
            "last move — consistently outperforms all other strategies in iterated play."
        )
    elif betrayals > dd:
        return (
            "Betrayal was common in this match. Once trust breaks down, "
            "retaliation cycles can lock players into mutual defection. "
            "Real-world parallels: arms races, price wars, overfishing, "
            "climate negotiations — all share exactly this payoff structure."
        )
    else:
        return (
            "A mixed match. Cooperation and defection both appeared. "
            "The iterated Prisoner&#8217;s Dilemma is the foundation of modern "
            "evolutionary game theory: whether cooperation can emerge from "
            "self-interested actors depends critically on whether they "
            "interact repeatedly and can build reputations."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payoff(ca, cb) -> tuple[int, int]:
    table = {
        (_COOPERATE, _COOPERATE): (3, 3),
        (_COOPERATE, _DEFECT):    (0, 5),
        (_DEFECT,    _COOPERATE): (5, 0),
        (_DEFECT,    _DEFECT):    (1, 1),
    }
    return table.get((ca, cb), (0, 0))


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------

_CONTAINER_STYLE = (
    "font-family:sans-serif;max-width:520px;margin:0 auto;"
    "padding:16px;background:#fff;border-radius:12px;"
)

_TITLE_STYLE = (
    "text-align:center;font-size:22px;font-weight:700;"
    "color:#1a237e;margin-bottom:16px;"
)

_TD_HEADER = (
    "padding:7px 10px;background:#e8eaf6;font-weight:700;"
    "font-size:12px;text-align:center;border:1px solid #ccc;"
)
