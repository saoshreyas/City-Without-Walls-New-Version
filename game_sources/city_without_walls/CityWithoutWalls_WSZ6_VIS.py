"""
CityWithoutWalls_WSZ6_VIS.py

Portal visualization for City Without Walls. Do not import the PFF.
"""

from __future__ import annotations


def _render_intro(state) -> str:
    """Opening screen: win / lose conditions before the first move."""
    wh = getattr(state, 'win_homeless_at_or_below', 7490)
    ws = getattr(state, 'win_public_support_at_or_above', 50.0)
    wl = getattr(state, 'win_legal_pressure_below', 20.0)
    lr = getattr(state, 'lose_after_round', 20)
    ch = int(getattr(state, 'lose_homeless_above', 15000))
    cs = getattr(state, 'lose_public_support_below', 15.0)
    h0 = int(getattr(state, 'homeless_population', 10700) or 10700)
    pct = int(round(100.0 * wh / max(1, h0)))

    return f'''\
<article class="cww-vis cww-intro">
<style>
.cww-vis {{ font-family: system-ui, Segoe UI, Roboto, sans-serif; max-width: 720px;
  margin: 0 auto; color: #1a1a1a; }}
.cww-intro h1 {{ font-size: 1.25rem; margin: 0 0 0.75rem; color: #0d47a1; }}
.cww-intro .lead {{ color: #444; line-height: 1.5; margin-bottom: 1rem; font-size: 0.95rem; }}
.cww-intro .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
.cww-intro .card {{ border-radius: 8px; padding: 14px 16px; border: 1px solid #ccc; }}
.cww-intro .win {{ background: #e8f5e9; border-color: #a5d6a7; }}
.cww-intro .lose {{ background: #fff3e0; border-color: #ffcc80; }}
.cww-intro .card h2 {{ margin: 0 0 10px; font-size: 1rem; }}
.cww-intro ul {{ margin: 0; padding-left: 1.15rem; line-height: 1.55; font-size: 0.92rem; }}
.cww-intro .cta {{ margin-top: 1rem; padding: 12px; background: #e3f2fd; border-radius: 8px;
  font-size: 0.9rem; border: 1px solid #90caf9; }}
</style>
<h1>City Without Walls — briefing</h1>
<p class="lead">
  Five stakeholder roles negotiate housing, health, and street conditions while homelessness,
  public opinion, and legal pressure shift each round. Before the first move, confirm how the
  city <strong>wins</strong> or <strong>loses</strong> below.
</p>
<div class="cols">
  <div class="card win">
    <h2>Win (all at once)</h2>
    <ul>
      <li>Homeless population ≤ <strong>{wh:,}</strong> (about <strong>{pct}%</strong> of the starting total)</li>
      <li>Public support ≥ <strong>{ws:.0f}</strong> (0–100)</li>
      <li>Legal pressure &lt; <strong>{wl:.0f}</strong></li>
    </ul>
  </div>
  <div class="card lose">
    <h2>Lose (any one)</h2>
    <ul>
      <li>More than <strong>{lr}</strong> full policy cycles complete (macro step advances the counter)</li>
      <li>Homeless population &gt; <strong>{ch:,}</strong></li>
      <li>Public support &lt; <strong>{cs:.0f}</strong></li>
    </ul>
  </div>
</div>
<p class="cta">
  <strong>Next step:</strong> in the operator list, the <strong>Neighborhoods</strong> player
  (first in the cycle) chooses <strong>Review goals &amp; begin simulation</strong> once
  everyone has read this screen.
</p>
</article>'''


def _esc(s: str) -> str:
    return (
        str(s)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def render_state(state, role_num: int = 0, base_url: str = '') -> str:
    """Return HTML for the current state (role_num selects budget emphasis)."""
    phase = getattr(state, 'phase', 'playing')
    if phase == 'intro':
        return _render_intro(state)
    gr = getattr(state, 'game_round', 0)
    cr = getattr(state, 'current_role_num', 0)
    homeless = getattr(state, 'homeless_population', 0)
    sup = getattr(state, 'public_support', 0.0)
    leg = getattr(state, 'legal_pressure', 0.0)
    mom = getattr(state, 'policy_momentum', 0.0)
    econ = getattr(state, 'economy_index', 0.0)
    disp = getattr(state, 'displaced', 0.0)

    sc = getattr(state, 'shelter_capacity', 0)
    tu = getattr(state, 'transitional_units', 0)
    pu = getattr(state, 'permanent_units', 0)
    cap = sc + tu + pu

    role_labels = (
        'Neighborhoods', 'Business', 'Medical', 'Shelters', 'University', 'Observer'
    )
    rname = role_labels[cr] if 0 <= cr < len(role_labels) else str(cr)

    budget_rows = [
        ('Neighborhood', getattr(state, 'neighborhood_budget', 0)),
        ('Business', getattr(state, 'business_budget', 0)),
        ('Medical', getattr(state, 'medical_budget', 0)),
        ('Shelter', getattr(state, 'shelter_budget', 0)),
        ('University', getattr(state, 'university_budget', 0)),
    ]
    def _row(i: int, label: str, val: float) -> str:
        cls = 'highlight' if i == role_num else ''
        return (
            f'<tr class="{cls}"><td>{_esc(label)}</td>'
            f'<td class="num">{val:,.0f}</td></tr>'
        )

    b_html = ''.join(_row(i, l, v) for i, (l, v) in enumerate(budget_rows))

    pipe = getattr(state, 'construction_pipeline', []) or []
    pipe_rows = ''.join(
        f'<tr><td>{_esc(p.get("kind", ""))}</td>'
        f'<td class="num">{p.get("units", 0)}</td>'
        f'<td class="num">{p.get("rounds", 0)}</td></tr>'
        for p in pipe
    )
    if not pipe_rows:
        pipe_rows = '<tr><td colspan="3" class="muted">No projects in pipeline</td></tr>'

    learn_title = getattr(state, 'learn_move_title', None)
    learn_fact = getattr(state, 'learn_fact', None)
    learn_url = getattr(state, 'learn_source_url', None)
    learn_block = ''
    if learn_fact and learn_url:
        lt = _esc(learn_title) if learn_title else 'Last policy action'
        learn_block = f'''
  <div class="card learn">
    <h2>Policy context</h2>
    <p class="learn-title">{lt}</p>
    <p class="learn-fact">{_esc(learn_fact)}</p>
    <p class="learn-src"><a href="{_esc(learn_url)}" target="_blank" rel="noopener noreferrer">Open source &amp; learn more →</a></p>
  </div>'''

    status_banner = ''
    if phase == 'won':
        status_banner = '<div class="banner win">Goal achieved — sustainable reduction path.</div>'
    elif phase == 'lost':
        status_banner = '<div class="banner loss">Simulation ended — crisis thresholds reached.</div>'

    html = f'''\
<article class="cww-vis">
<style>
.cww-vis {{ font-family: system-ui, Segoe UI, Roboto, sans-serif; max-width: 720px;
  margin: 0 auto; color: #1a1a1a; }}
.cww-vis h1 {{ font-size: 1.15rem; margin: 0 0 0.5rem; }}
.cww-vis .sub {{ color: #555; font-size: 0.9rem; margin-bottom: 1rem; }}
.cww-vis .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.cww-vis .card {{ border: 1px solid #ccc; border-radius: 8px; padding: 12px;
  background: #fafafa; }}
.cww-vis .card h2 {{ font-size: 0.95rem; margin: 0 0 8px; }}
.cww-vis table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
.cww-vis td, .cww-vis th {{ padding: 4px 6px; text-align: left; }}
.cww-vis td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.cww-vis tr.highlight {{ background: #e3f2fd; }}
.cww-vis .muted {{ color: #777; }}
.cww-vis .metric {{ display: flex; justify-content: space-between; margin: 4px 0; }}
.cww-vis .banner {{ padding: 10px; border-radius: 6px; margin-bottom: 12px; font-weight: 600; }}
.cww-vis .banner.win {{ background: #e8f5e9; color: #1b5e20; }}
.cww-vis .banner.loss {{ background: #ffebee; color: #b71c1c; }}
.cww-vis .learn {{ border-left: 4px solid #1565c0; background: #e3f2fd; }}
.cww-vis .learn h2 {{ color: #0d47a1; }}
.cww-vis .learn-title {{ font-weight: 600; margin: 0 0 6px; font-size: 0.92rem; }}
.cww-vis .learn-fact {{ margin: 0 0 10px; line-height: 1.45; font-size: 0.9rem; color: #222; }}
.cww-vis .learn-src {{ margin: 0; font-size: 0.88rem; }}
.cww-vis .learn-src a {{ color: #0d47a1; }}
</style>
{status_banner}
<h1>City Without Walls</h1>
<p class="sub">Round <strong>{gr}</strong> · Active turn: <strong>{_esc(rname)}</strong>
 · Your role index: {role_num}</p>
<div class="grid">
  <div class="card">
    <h2>Population &amp; pressure</h2>
    <div class="metric"><span>Homeless (total)</span><strong>{homeless:,}</strong></div>
    <div class="metric"><span>Public support (0–100)</span><strong>{sup:.1f}</strong></div>
    <div class="metric"><span>Legal pressure</span><strong>{leg:.1f}</strong></div>
    <div class="metric"><span>Policy momentum</span><strong>{mom:.1f}</strong></div>
    <div class="metric"><span>Economy index</span><strong>{econ:.1f}</strong></div>
    <div class="metric"><span>Displaced (cum.)</span><strong>{disp:,.0f}</strong></div>
  </div>
  <div class="card">
    <h2>Housing capacity</h2>
    <div class="metric"><span>Shelter beds</span><strong>{sc:,.0f}</strong></div>
    <div class="metric"><span>Transitional</span><strong>{tu:,.0f}</strong></div>
    <div class="metric"><span>Permanent</span><strong>{pu:,.0f}</strong></div>
    <div class="metric"><span>Total units</span><strong>{cap:,.0f}</strong></div>
    <div class="metric"><span>Utilization</span><strong>{(homeless / max(1, cap)):.2f}</strong></div>
  </div>
</div>
<div class="grid" style="margin-top:12px">
  <div class="card">
    <h2>Budgets (k$)</h2>
    <table><thead><tr><th>Stakeholder</th><th>Balance</th></tr></thead>
    <tbody>{b_html}</tbody></table>
  </div>
  <div class="card">
    <h2>Construction pipeline</h2>
    <table><thead><tr><th>Type</th><th>Units</th><th>Rounds left</th></tr></thead>
    <tbody>{pipe_rows}</tbody></table>
  </div>
</div>
{learn_block}
</article>'''
    return html
