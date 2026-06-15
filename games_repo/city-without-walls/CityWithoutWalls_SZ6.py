"""CityWithoutWalls_SZ6.py

SOLUZION6 multi-stakeholder simulation: urban homelessness policy.
Built for SZ6 (fresh formulation; not a SZ5 port).

See module __main__ for standalone smoke test.
"""

from __future__ import annotations

SOLUZION_VERSION = 6

import math
import random
from dataclasses import dataclass

import soluzion6_02 as sz


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CONFIG:
    baseline_population: float = 10700.0
    goal_reduction: float = 0.70
    max_rounds: int = 20
    crisis_homeless: int = 15000
    crisis_support: float = 15.0
    shock_probability: float = 0.12
    tax_inflow_rate: float = 0.20
    synergy_bonus: float = 1.25
    construction_delay: int = 2
    base_inflow_rate: float = 643.0  # tuned: ~2%/round at economy_index=100
    policy_fatigue_decay: float = 0.05


CFG = CONFIG()

# Initial subpopulations (scaled to baseline sum)
_RAW_SUM = 2800 + 1800 + 3600 + 1500
_SCALE = CFG.baseline_population / _RAW_SUM

ROLE_NEIGHBORHOODS = 0
ROLE_BUSINESS = 1
ROLE_MEDICAL = 2
ROLE_SHELTERS = 3
ROLE_UNIVERSITY = 4
ROLE_OBSERVER = 5
TURN_OPERATOR_OFFER_SIZE = 5


# ---------------------------------------------------------------------------
# METADATA
# ---------------------------------------------------------------------------


class CityWithoutWalls_Metadata(sz.SZ_Metadata):
    def __init__(self):
        self.name = 'City Without Walls'
        self.soluzion_version = SOLUZION_VERSION
        self.problem_version = '1.0'
        self.authors = ['SZ6 Implementation']
        self.creation_date = '2026-May'
        self.brief_desc = (
            'A multi-stakeholder simulation of urban homelessness policy in a midsized '
            'American city. Each action includes a short policy note and link to real-world '
            'evidence so players learn while negotiating trade-offs.'
        )


# ---------------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------------


class CityWithoutWalls_State(sz.SZ_State):
    """Full game state — all instance data here (no module-level globals)."""

    def __init__(self, old: CityWithoutWalls_State | None = None, config: dict | None = None):
        cfg = config or {}
        if old is None:
            ar = sorted(set(cfg.get('active_roles', [0, 1, 2, 3, 4])))
            if not ar:
                ar = [0, 1, 2, 3, 4]
            self.phase = 'intro'
            self.parallel = False
            self.jit_transition: str | None = None
            self.active_roles = list(ar)
            self.play_order = _compute_play_order(self.active_roles)
            self.current_role_num = self.play_order[0]
            self.game_round = 1
            self.move_seq = 0

            self.pop_families = 2800.0 * _SCALE
            self.pop_youth = 1800.0 * _SCALE
            self.pop_chronic = 3600.0 * _SCALE
            self.pop_veterans = 1500.0 * _SCALE

            self.shelter_capacity = 1400.0
            self.transitional_units = 600.0
            self.permanent_units = 2200.0
            self.construction_pipeline: list[dict] = []

            self.social_workers = 120.0
            self.outreach_teams = 8.0
            self.medical_vans = 3.0

            self.shelter_budget = 800.0
            self.neighborhood_budget = 900.0
            self.business_budget = 750.0
            self.medical_budget = 900.0
            self.university_budget = 450.0

            self.public_support = 52.0
            self.economy_index = 100.0
            self.legal_pressure = 10.0
            self.policy_momentum = 0.0
            self.debt = 0.0
            self.policy_fatigue = 0.0
            self.displaced = 0.0

            self.operating_obligations = 250.0

            self.round_actors: list[int] = []
            self.turn_operator_names: list[str] = []
            self.chronic_reduce_med = 0.0
            self.chronic_reduce_shel = 0.0
            self.observer_report_used = False
            # Last move — surfaced in VIS as “Policy context” (learning snippets).
            self.learn_move_title: str | None = None
            self.learn_fact: str | None = None
            self.learn_source_url: str | None = None
            # Frozen display thresholds (for intro / VIS; logic uses CFG in code paths).
            self.win_homeless_at_or_below = int(CFG.baseline_population * CFG.goal_reduction)
            self.win_public_support_at_or_above = 50.0
            self.win_legal_pressure_below = 20.0
            self.lose_after_round = CFG.max_rounds
            self.lose_homeless_above = float(CFG.crisis_homeless)
            self.lose_public_support_below = CFG.crisis_support
        else:
            self.phase = old.phase
            self.parallel = old.parallel
            self.jit_transition = old.jit_transition
            self.active_roles = old.active_roles[:]
            self.play_order = old.play_order[:]
            self.current_role_num = old.current_role_num
            self.game_round = old.game_round
            self.move_seq = old.move_seq

            self.pop_families = old.pop_families
            self.pop_youth = old.pop_youth
            self.pop_chronic = old.pop_chronic
            self.pop_veterans = old.pop_veterans

            self.shelter_capacity = old.shelter_capacity
            self.transitional_units = old.transitional_units
            self.permanent_units = old.permanent_units
            self.construction_pipeline = [dict(x) for x in old.construction_pipeline]

            self.social_workers = old.social_workers
            self.outreach_teams = old.outreach_teams
            self.medical_vans = old.medical_vans

            self.shelter_budget = old.shelter_budget
            self.neighborhood_budget = old.neighborhood_budget
            self.business_budget = old.business_budget
            self.medical_budget = old.medical_budget
            self.university_budget = old.university_budget

            self.public_support = old.public_support
            self.economy_index = old.economy_index
            self.legal_pressure = old.legal_pressure
            self.policy_momentum = old.policy_momentum
            self.debt = old.debt
            self.policy_fatigue = old.policy_fatigue
            self.displaced = old.displaced

            self.operating_obligations = old.operating_obligations

            self.round_actors = old.round_actors[:]
            self.turn_operator_names = list(getattr(old, 'turn_operator_names', []))
            self.chronic_reduce_med = old.chronic_reduce_med
            self.chronic_reduce_shel = old.chronic_reduce_shel
            self.observer_report_used = old.observer_report_used
            self.learn_move_title = old.learn_move_title
            self.learn_fact = old.learn_fact
            self.learn_source_url = old.learn_source_url
            self.win_homeless_at_or_below = old.win_homeless_at_or_below
            self.win_public_support_at_or_above = old.win_public_support_at_or_above
            self.win_legal_pressure_below = old.win_legal_pressure_below
            self.lose_after_round = old.lose_after_round
            self.lose_homeless_above = old.lose_homeless_above
            self.lose_public_support_below = old.lose_public_support_below

    @property
    def homeless_population(self) -> int:
        return int(round(
            self.pop_families + self.pop_youth + self.pop_chronic + self.pop_veterans
        ))

    def goal_homeless_cap(self) -> int:
        return int(CFG.baseline_population * CFG.goal_reduction)

    def is_goal(self) -> bool:
        # Portal runner only consults is_goal() — treat terminal loss like goal.
        return self.phase in ('won', 'lost')

    def is_loss(self) -> bool:
        return self.phase == 'lost'

    def goal_message(self) -> str:
        if self.phase == 'won':
            return (
                'Goal achieved: homelessness reduced to the target band with '
                'sustainable public support and manageable legal pressure.'
            )
        if self.phase == 'lost':
            return (
                f'Game ended: round={self.game_round}, '
                f'homeless={self.homeless_population}, '
                f'support={self.public_support:.1f}'
            )
        return ''

    def __str__(self) -> str:
        if self.phase == 'intro':
            return _intro_text_view(self)
        return (
            f"City Without Walls | round {self.game_round} | "
            f"role {self.current_role_num} | homeless {self.homeless_population} | "
            f"support {self.public_support:.1f} | legal {self.legal_pressure:.1f}"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CityWithoutWalls_State):
            return False
        return vars(self) == vars(other)

    def __hash__(self) -> int:
        return hash((
            self.phase, self.game_round, self.current_role_num,
            self.homeless_population, round(self.public_support, 2),
        ))


def _compute_play_order(active_roles: list[int]) -> list[int]:
    core = [r for r in (0, 1, 2, 3, 4) if r in active_roles]
    if ROLE_OBSERVER in active_roles:
        core = core + [ROLE_OBSERVER]
    return core


def _intro_rules_body(st: CityWithoutWalls_State) -> str:
    """Plain-text win / lose summary (shared by intro view and operator card)."""
    pct = int(round(100 * CFG.goal_reduction))
    base = int(round(CFG.baseline_population))
    return (
        'HOW TO WIN (all must be true together after a move or macro update):\n'
        f'  • Homeless population ≤ {st.win_homeless_at_or_below:,} '
        f'({pct}% of the {base:,} starting total)\n'
        f'  • Public support ≥ {st.win_public_support_at_or_above:.0f} (0–100 scale)\n'
        f'  • Legal pressure < {st.win_legal_pressure_below:.0f}\n'
        '\n'
        'HOW YOU CAN LOSE (any one ends the simulation):\n'
        f'  • The city completes more than {st.lose_after_round} full policy cycles '
        '(each cycle ends after every stakeholder has acted; the cycle counter rises '
        'at the macro step).\n'
        f'  • Homeless population climbs above {int(st.lose_homeless_above):,}.\n'
        f'  • Public support falls below {st.lose_public_support_below:.0f}.\n'
        '\n'
        'Turn order each cycle: Neighborhoods → Business → Medical → Shelters → '
        'University (then Observer if assigned). After the last role, macro economics '
        'and population pressures update before the next cycle begins.\n'
        '\n'
        'When everyone is ready, the Neighborhoods player (first in turn order) should use '
        '"Review goals & begin simulation" so the round can start.'
    )


def _intro_text_view(st: CityWithoutWalls_State) -> str:
    return 'City Without Walls — briefing\n\n' + _intro_rules_body(st)


def _begin_simulation(state: CityWithoutWalls_State) -> CityWithoutWalls_State:
    if state.phase != 'intro':
        return CityWithoutWalls_State(old=state)
    ns = CityWithoutWalls_State(old=state)
    ns.phase = 'playing'
    ns.current_role_num = ns.play_order[0]
    _assign_turn_operator_offer(ns, _macro_operator_list())
    ns.jit_transition = (
        'Simulation underway.\n'
        f'Opening turn: role {ns.current_role_num}. '
        'Win if homelessness, public support, and legal pressure all stay in the safe band; '
        'see the briefing for exact numbers.'
    )
    return ns


# ---------------------------------------------------------------------------
# CORE MECHANICS
# ---------------------------------------------------------------------------


def schedule_construction(st: CityWithoutWalls_State, kind: str, units: int) -> None:
    delay = max(1, int(round(units / 100.0 * CFG.construction_delay)))
    st.construction_pipeline.append({'kind': kind, 'units': units, 'rounds': delay})


def _tick_construction(st: CityWithoutWalls_State) -> None:
    remaining: list[dict] = []
    for item in st.construction_pipeline:
        item = dict(item)
        item['rounds'] -= 1
        if item['rounds'] <= 0:
            k = item['kind']
            u = item['units']
            if k == 'shelter':
                st.shelter_capacity += u
            elif k == 'trans':
                st.transitional_units += u
            elif k == 'perm':
                st.permanent_units += u
        else:
            remaining.append(item)
    st.construction_pipeline = remaining


def _logistic_p_success(st: CityWithoutWalls_State, difficulty: float) -> float:
    momentum_factor = st.policy_momentum * 0.15
    support_factor = (st.public_support - 50.0) * 0.04
    x = momentum_factor + support_factor - difficulty
    p = 1.0 / (1.0 + math.exp(-x))
    return max(0.05, min(0.98, p))


def _average_operator_cost_by_role(operators: list) -> dict[int, float]:
    totals: dict[int, list[float]] = {i: [] for i in range(6)}
    for op in operators:
        r = getattr(op, 'role', None)
        if r is None or r not in totals:
            continue
        cdict = getattr(op, '_costs', {}) or {}
        totals[r].append(float(sum(cdict.values())))
    return {r: (sum(v) / len(v) if v else 0.0) for r, v in totals.items()}


def _run_macro_cycle(st: CityWithoutWalls_State, operator_list: list) -> None:
    st.jit_transition = None
    _tick_construction(st)

    # Synergy: extra chronic reduction this cycle
    if st.chronic_reduce_med > 0 and st.chronic_reduce_shel > 0:
        bonus = (st.chronic_reduce_med + st.chronic_reduce_shel) * (CFG.synergy_bonus - 1.0)
        st.pop_chronic = max(0.0, st.pop_chronic - bonus)

    st.round_actors = []
    st.chronic_reduce_med = 0.0
    st.chronic_reduce_shel = 0.0

    avgs = _average_operator_cost_by_role(operator_list)
    for role, attr in [
        (ROLE_NEIGHBORHOODS, 'neighborhood_budget'),
        (ROLE_BUSINESS, 'business_budget'),
        (ROLE_MEDICAL, 'medical_budget'),
        (ROLE_SHELTERS, 'shelter_budget'),
        (ROLE_UNIVERSITY, 'university_budget'),
    ]:
        inc = avgs.get(role, 0.0) * CFG.tax_inflow_rate
        setattr(st, attr, getattr(st, attr) + inc)

    if st.policy_momentum > 5.0 and random.random() < 0.25:
        st.shelter_budget += 300.0

    if random.random() < CFG.shock_probability:
        shock = random.choice(('recession', 'boom', 'inflation'))
        if shock == 'recession':
            st.economy_index -= random.uniform(6, 15)
            st.public_support -= random.uniform(1, 4)
        elif shock == 'boom':
            st.economy_index += random.uniform(5, 20)
            st.public_support += random.uniform(0.5, 3)
        else:
            st.operating_obligations *= 1.08

    st.policy_fatigue = max(0.0, st.policy_fatigue - CFG.policy_fatigue_decay)

    inflow = (1.0 - st.economy_index / 150.0) * CFG.base_inflow_rate
    inflow = max(0.0, inflow)
    denom = st.pop_families + st.pop_youth
    if denom <= 0:
        split_f, split_y = 0.5, 0.5
    else:
        split_f = st.pop_families / denom
        split_y = st.pop_youth / denom
    st.pop_families += inflow * split_f
    st.pop_youth += inflow * split_y

    total_budget = (
        st.shelter_budget + st.neighborhood_budget + st.business_budget
        + st.medical_budget + st.university_budget
    )
    if total_budget < st.operating_obligations:
        short = st.operating_obligations - total_budget
        degrade = min(0.05, (short / max(1e-6, st.operating_obligations)) * 0.05)
        st.shelter_capacity *= (1.0 - degrade)

    cap = st.shelter_capacity + st.transitional_units + st.permanent_units
    ur = st.homeless_population / max(1.0, cap)
    if ur > 1.0:
        st.legal_pressure += 1.5
        st.public_support -= 1.0

    st.game_round += 1

    if (
        st.game_round > CFG.max_rounds
        or st.homeless_population > CFG.crisis_homeless
        or st.public_support < CFG.crisis_support
    ):
        st.phase = 'lost'
    elif (
        st.homeless_population <= st.goal_homeless_cap()
        and st.public_support >= 50.0
        and st.legal_pressure < 20.0
    ):
        st.phase = 'won'

    _snap_metrics(st)


def _snap_metrics(st: CityWithoutWalls_State) -> None:
    """Round volatile floats for stable portal/GSL equality checks."""
    st.public_support = round(st.public_support, 2)
    st.legal_pressure = round(st.legal_pressure, 2)
    st.policy_momentum = round(st.policy_momentum, 2)
    st.economy_index = round(st.economy_index, 2)
    st.policy_fatigue = round(st.policy_fatigue, 2)
    st.debt = round(st.debt, 2)
    st.operating_obligations = round(st.operating_obligations, 2)


def _check_immediate_terminal(st: CityWithoutWalls_State) -> None:
    if st.phase != 'playing':
        return
    if (
        st.homeless_population > CFG.crisis_homeless
        or st.public_support < CFG.crisis_support
    ):
        st.phase = 'lost'


def _assign_turn_operator_offer(st: CityWithoutWalls_State, operator_list: list) -> None:
    """Sample the action menu for the current stakeholder turn."""
    if st.phase != 'playing':
        st.turn_operator_names = []
        return

    candidates = [
        op.name
        for op in operator_list
        if getattr(op, '_random_offer', False)
        and getattr(op, 'role', None) == st.current_role_num
        and _can_pay(st, getattr(op, '_costs', {}) or {})
    ]
    if len(candidates) <= TURN_OPERATOR_OFFER_SIZE:
        st.turn_operator_names = candidates
    else:
        st.turn_operator_names = random.sample(candidates, TURN_OPERATOR_OFFER_SIZE)


def _is_turn_operator_offered(st: CityWithoutWalls_State, name: str) -> bool:
    offered = getattr(st, 'turn_operator_names', [])
    return name in offered


def _can_pay(st: CityWithoutWalls_State, costs: dict[str, float]) -> bool:
    for k, v in costs.items():
        if getattr(st, k) < v - 1e-9:
            return False
    return True


_EFFECT_LABELS = {
    'shelter_budget': 'shelter budget',
    'neighborhood_budget': 'neighborhood budget',
    'business_budget': 'business budget',
    'medical_budget': 'medical budget',
    'university_budget': 'university budget',
    'shelter_capacity': 'shelter capacity',
    'transitional_units': 'transitional units',
    'permanent_units': 'permanent units',
    'social_workers': 'social workers',
    'outreach_teams': 'outreach teams',
    'medical_vans': 'medical vans',
    'public_support': 'public support',
    'economy_index': 'economy index',
    'legal_pressure': 'legal pressure',
    'policy_momentum': 'policy momentum',
    'pop_families': 'families',
    'pop_youth': 'youth',
    'pop_chronic': 'chronic homelessness',
    'pop_veterans': 'veterans',
}

_SCHEDULE_LABELS = {
    'shelter': 'shelter capacity',
    'trans': 'transitional units',
    'perm': 'permanent units',
}


def _fmt_number(value: float) -> str:
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f'{rounded:.2f}'.rstrip('0').rstrip('.')


def _fmt_signed(value: float) -> str:
    return ('+' if value > 0 else '') + _fmt_number(value)


def _fmt_percent(value: float) -> str:
    return _fmt_signed(value * 100.0) + '%'


def _base_operator_label(name: str) -> str:
    """Move final parenthetical text into a colon subtitle."""
    if name.endswith(')') and '(' in name:
        prefix, suffix = name.rsplit('(', 1)
        detail = suffix[:-1].strip()
        if detail:
            return f'{prefix.rstrip()}: {detail}'
    return name


def _format_effect(effect: tuple) -> str:
    kind = effect[0]
    if kind == 'add':
        _, attr, delta = effect
        return f'{_EFFECT_LABELS.get(attr, attr.replace("_", " "))} {_fmt_signed(delta)}'
    if kind == 'mulp':
        _, attr, frac = effect
        return f'{_EFFECT_LABELS.get(attr, attr.replace("_", " "))} {_fmt_percent(frac)}'
    if kind == 'sched':
        _, item, units = effect
        return f'{_SCHEDULE_LABELS.get(item, item)} +{_fmt_number(units)} scheduled'
    if kind == 'displace':
        _, frac = effect
        return f'displacement {_fmt_percent(frac)}'
    return ' '.join(str(x) for x in effect)


def _format_effects(effects: list) -> str:
    return ', '.join(_format_effect(effect) for effect in effects)


def _format_operator_name(name: str, effects: list) -> str:
    label = _base_operator_label(name)
    effect_text = _format_effects(effects)
    return f'{label} [{effect_text}]' if effect_text else label


def _pay(st: CityWithoutWalls_State, costs: dict[str, float]) -> None:
    for k, v in costs.items():
        setattr(st, k, getattr(st, k) - v)


def _track_chronic(st: CityWithoutWalls_State, role: int, before: float, after: float) -> None:
    red = max(0.0, before - after)
    if role == ROLE_MEDICAL:
        st.chronic_reduce_med += red
    elif role == ROLE_SHELTERS:
        st.chronic_reduce_shel += red


def _apply_effects(
    st: CityWithoutWalls_State,
    role: int,
    effects: list,
    mult: float,
    base_homeless: float,
) -> None:
    for eff in effects:
        kind = eff[0]
        if kind == 'add':
            _, attr, delta = eff
            setattr(st, attr, getattr(st, attr) + delta * mult)
        elif kind == 'mulp':
            # multiplicative change to subpopulation (negative fraction)
            _, attr, frac = eff
            cur = getattr(st, attr)
            before_chronic = st.pop_chronic if attr == 'pop_chronic' else None
            setattr(st, attr, max(0.0, cur * (1.0 + frac * mult)))
            if attr == 'pop_chronic' and before_chronic is not None:
                _track_chronic(st, role, before_chronic, st.pop_chronic)
        elif kind == 'sched':
            _, skind, units = eff
            schedule_construction(st, skind, max(0, int(round(units * mult))))
        elif kind == 'displace':
            _, frac = eff
            st.displaced += base_homeless * frac * mult


def _advance_turn(st: CityWithoutWalls_State, operator_list: list) -> None:
    if st.phase != 'playing':
        return
    order = st.play_order
    idx = order.index(st.current_role_num)
    if idx < len(order) - 1:
        st.current_role_num = order[idx + 1]
        _assign_turn_operator_offer(st, operator_list)
    else:
        _run_macro_cycle(st, operator_list)
        if st.phase == 'playing':
            st.current_role_num = order[0]
            _assign_turn_operator_offer(st, operator_list)


def _make_transition(
    name: str,
    role: int,
    costs: dict,
    difficulty: float,
    effects: list,
    url: str,
    learn_fact: str,
):
    def _xf(state: CityWithoutWalls_State):
        if state.phase != 'playing':
            return CityWithoutWalls_State(old=state)
        if state.current_role_num != role:
            return CityWithoutWalls_State(old=state)
        ns = CityWithoutWalls_State(old=state)
        ns.jit_transition = None
        ns.move_seq += 1
        if costs:
            _pay(ns, costs)
        p = _logistic_p_success(ns, difficulty)
        success = random.random() < p
        mult = 1.0 if success else (0.25 + 0.5 * random.random())
        h0 = float(ns.homeless_population)
        _apply_effects(ns, role, effects, mult, h0)
        # Any mulp on chronic already tracked inside _apply_effects
        if not success:
            # partial chronic already scaled via mult in mulp
            pass
        ns.round_actors.append(role)
        fact = learn_fact or (
            'Housing and homelessness policy draws on federal data, local pilots, and '
            'program evaluations—use the source below to go deeper.'
        )
        ns.learn_move_title = name
        ns.learn_fact = fact
        ns.learn_source_url = url
        summary = (
            f'{name}\n'
            f'Outcome: {"SUCCESS" if success else "PARTIAL"} (scale {mult:.2f})\n'
            f'Homeless≈{ns.homeless_population}  support={ns.public_support:.1f}  '
            f'legal={ns.legal_pressure:.1f}\n'
            f'---\n'
            f'Policy note: {fact}'
        )
        ns.jit_transition = summary
        _snap_metrics(ns)
        _check_immediate_terminal(ns)
        if ns.phase == 'playing':
            _advance_turn(ns, _macro_operator_list())
        return ns

    return _xf


_MACRO_OPS: list | None = None


def _macro_operator_list() -> list:
    global _MACRO_OPS
    if _MACRO_OPS is None:
        raise RuntimeError('CityWithoutWalls operators not initialized')
    return _MACRO_OPS


class CityWithoutWalls_Operator_Set(sz.SZ_Operator_Set):
    """Operators built from SPEC table."""

    def __init__(self):
        global _MACRO_OPS
        # Briefing state (same thresholds as a live session) for the intro operator text.
        _brief = CityWithoutWalls_State(config={})
        _intro_header = (
            'Read the win and lose conditions, then press this once to start the simulation '
            '(the Neighborhoods player goes first in turn order and clicks this to begin).\n\n'
        )
        begin_op = sz.SZ_Operator(
            name='Review goals & begin simulation',
            description=_intro_header + _intro_rules_body(_brief),
            precond_func=lambda s: s.phase == 'intro',
            state_xition_func=_begin_simulation,
            role=None,
        )
        setattr(begin_op, '_costs', {})

        specs = _OPERATOR_SPEC()
        ops: list = [begin_op]
        for sp in specs:
            base_name, role, costs, diff, effs, url = sp
            name = _format_operator_name(base_name, effs)
            learn = _LEARN_SNIPPETS.get(base_name, '')
            xf = _make_transition(name, role, costs, diff, effs, url, learn)

            def _pre(s, r=role, c=costs, n=name):
                if s.phase != 'playing':
                    return False
                if s.current_role_num != r:
                    return False
                return _can_pay(s, c) and _is_turn_operator_offered(s, n)

            desc_body = learn or (
                'Evidence brief: open the source link for program background and findings.'
            )
            op = sz.SZ_Operator(
                name=name,
                description=f'{name}\n\n{desc_body}\n\nSource: {url}',
                precond_func=_pre,
                state_xition_func=xf,
                role=role,
            )
            op._costs = dict(costs)
            op._random_offer = True
            ops.append(op)

        # Observer — publish (once)
        _pub_effects = [('add', 'public_support', 5.0), ('add', 'policy_momentum', 2.0)]
        _pub_name = _format_operator_name('Publish Independent Report', _pub_effects)

        def _pub_pre(s):
            if s.phase != 'playing':
                return False
            if s.current_role_num != ROLE_OBSERVER:
                return False
            return not s.observer_report_used

        def _pub_xf(s):
            ns = CityWithoutWalls_State(old=s)
            ns.jit_transition = None
            ns.move_seq += 1
            ns.public_support += 5.0
            ns.policy_momentum += 2.0
            ns.observer_report_used = True
            _pub_fact = (
                'Independent reporting and peer-reviewed syntheses help communities separate '
                'myth from evidence on encampments, health harms, and what actually reduces '
                'unsheltered homelessness over time.'
            )
            _pub_url = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC8352395/'
            ns.learn_move_title = _pub_name
            ns.learn_fact = _pub_fact
            ns.learn_source_url = _pub_url
            ns.jit_transition = (
                f'{_pub_name}\n'
                '+5 public support, +2 policy momentum\n'
                '---\n'
                f'Policy note: {_pub_fact}'
            )
            ns.round_actors.append(ROLE_OBSERVER)
            _snap_metrics(ns)
            _check_immediate_terminal(ns)
            if ns.phase == 'playing':
                _advance_turn(ns, _macro_operator_list())
            return ns

        _obs_pub_desc = (
            'Once per game; boosts public support and policy momentum.\n\n'
            'Independent reporting and peer-reviewed syntheses help separate advocacy claims '
            'from evidence on encampments, health, and effective housing responses.\n\n'
            'Source: https://pmc.ncbi.nlm.nih.gov/articles/PMC8352395/'
        )
        ops.append(sz.SZ_Operator(
            name=_pub_name,
            description=_obs_pub_desc,
            precond_func=_pub_pre,
            state_xition_func=_pub_xf,
            role=ROLE_OBSERVER,
        ))
        setattr(ops[-1], '_costs', {})

        # Observer pass — always available on observer turn (e.g. skip Publish)
        def _pass_pre(s):
            if s.phase != 'playing':
                return False
            return s.current_role_num == ROLE_OBSERVER

        def _pass_xf(s):
            ns = CityWithoutWalls_State(old=s)
            ns.jit_transition = 'Observer pass (no effect).'
            ns.move_seq += 1
            ns.round_actors.append(ROLE_OBSERVER)
            _snap_metrics(ns)
            if ns.phase == 'playing':
                _advance_turn(ns, _macro_operator_list())
            return ns

        ops.append(sz.SZ_Operator(
            name='Observer: pass',
            description='Skip observer action this cycle.',
            precond_func=_pass_pre,
            state_xition_func=_pass_xf,
            role=ROLE_OBSERVER,
        ))

        self.operators = ops
        _MACRO_OPS = ops


# ---------------------------------------------------------------------------
# OPERATOR TABLE  (costs in k$, fractions as mulp frac e.g. -0.10 = -10%)
# ---------------------------------------------------------------------------

# Short teaching lines aligned with linked sources (HUD, USICH, NLIHC, SAMHSA, etc.).
# Wording summarizes themes common to those resources—not verbatim quotations.
_LEARN_SNIPPETS: dict[str, str] = {
    'Emergency Expansion (beds +300)': (
        'Federal AHAR-style counts track how many people use shelters versus sleep unsheltered, '
        'so cities can size bed capacity and target prevention—not just react to visible camps.'
    ),
    'Community Partnership (volunteers & caseworkers)': (
        'Evaluations of homelessness programs often highlight that stable staffing and '
        'volunteer coordination improve follow-through on housing and benefits—not just intake.'
    ),
    'Housing First Pilot (perm +150)': (
        'Permanent supportive housing evaluations typically show that housing with voluntary '
        'services can improve health and reduce long shelter stays for people with complex needs.'
    ),
    'Volunteer Training (social workers +3)': (
        'Workforce capacity matters: trained caseworkers help people navigate benefits, IDs, '
        'and housing queues—common bottlenecks in system-level evaluations.'
    ),
    'Rent Assistance Fund (prevention)': (
        'HUD describes rapid re-housing as short-term rent help plus services—often used to '
        'exit shelter quickly or prevent the loss of a current home after a shock.'
    ),
    'Defer Maintenance (gain budget, lose beds)': (
        'Deferred capital spending can free cash short term but often raises safety risks and '
        'public criticism when shelter quality declines—HUD tracks capital needs across programs.'
    ),
    'Rapid Rehousing Boost': (
        'NLIHC’s “Gap” reports underline the mismatch between wages and rents; time-limited '
        'rent help is one tool, but it works best when affordable units exist to move into.'
    ),
    'Add Outreach Vans': (
        'Medical respite and mobile outreach case studies show that meeting people where they '
        'are can stabilize crises and create pathways into housing for those avoiding clinics.'
    ),
    'Intensify Case Management': (
        'High-touch case management is repeatedly cited in program evaluations as key to '
        'keeping people housed after they leave shelter or transitional programs.'
    ),
    'Sanction Encampment (sanctioned services)': (
        'Research on sanctioned encampments notes trade-offs: services can improve access, '
        'but sites must protect dignity, health, and routes to permanent housing.'
    ),
    'Partner: Medical Support (onsite clinics)': (
        'Onsite clinics at shelters can reduce ER cycling and treat conditions that otherwise '
        'block housing placements—Commonwealth Fund case studies emphasize care continuity.'
    ),
    'Evaluation & Data Sharing (with Univ)': (
        'USICH and federal partners stress transparent metrics—shared data helps agencies see '
        'whether reductions come from housing gains or from people leaving the jurisdiction.'
    ),
    'Media Campaign (reframe homelessness)': (
        'Urban planning and policy journals find that how media frame homelessness shapes '
        'whether the public blames individuals or supports systemic housing investments.'
    ),
    'Block New Low-Income Development (NIMBY action)': (
        'Legal clinics document how business improvement districts and local rules can '
        'increase displacement pressure—often without adding housing that ends homelessness.'
    ),
    'Local Voucher Matching Fund': (
        'Housing Choice Vouchers help very low-income households afford private-market units, '
        'but success depends on landlord participation and local payment standards.'
    ),
    'Civic Forum (reduce tensions)': (
        'Deliberative forums in cities can lower conflict when residents distrust how encampments '
        'or shelters are sited—process legitimacy matters as much as the policy text.'
    ),
    'Fund Private Security (pushout)': (
        'Berkeley Law’s clinic reporting shows private security and “clean zones” can move '
        'people without housing them—shifting visibility rather than solving shelter gaps.'
    ),
    'Infrastructure Grants (convert trans->perm)': (
        'Literature reviews find permanent housing investments change neighborhood outcomes '
        'more durably than rotating people through short-term beds alone.'
    ),
    'Community Food & Outreach Sponsorship': (
        'Peer-reviewed work on food and mutual aid at encampments notes survival supports '
        'are vital but should pair with housing access, not replace it.'
    ),
    'Neighborhood Rapid Response to Eviction Spikes': (
        'NLIHC tracks eviction risk as a major pipeline into homelessness—early legal aid and '
        'rent relief often cost less than rehousing someone after months unsheltered.'
    ),
    'Public Space Design (reduce congregation)': (
        'Urban design studies show hostile architecture and bench removal disperse people yet '
        'rarely reduce underlying homelessness; inclusive design plus services works differently.'
    ),
    'Property Value Assistance (tax incentive)': (
        'National shelter reports remind readers that affordable supply and inclusionary policy '
        'affect whether incentives actually add units people can afford.'
    ),
    'Neighborhood-led Transitional Housing Project': (
        'HUD transitional housing guidance emphasizes time limits and clear exits—bridges '
        'work when they connect to permanent subsidies or supportive housing.'
    ),
    'Neighborhood Monitoring & Data': (
        'Better local data can reduce rumor-driven fear, but ethics matter: counts should '
        'protect privacy and not fuel surveillance that criminalizes poverty.'
    ),
    'Tax Incentives for Affordable Housing': (
        'National homelessness summaries tie reductions in unsheltered homelessness to '
        'housing supply, rental assistance, and prevention—not enforcement alone.'
    ),
    'Fund Job Readiness Programs': (
        'Employment supports help some households stabilize rent, but without affordable '
        'housing, wages at the bottom of the labor market often still fail the rent test.'
    ),
    'Clean & Sweep (sanitation)': (
        'Advocacy groups cite evidence that sweeps without housing offers disrupt care, '
        'lose documents, and worsen health—while doing little to lower overall homelessness.'
    ),
    'Public-Private Transitional Housing': (
        'Peer-reviewed reviews of transitional models show strongest results when programs '
        'pair time-limited shelter with rapid paths to permanent subsidies.'
    ),
    'Lobby for Restrictive Ordinances': (
        'Clinic investigations show anti-camping and sit-lie laws can raise legal challenges '
        'and move people into neighboring jurisdictions—a regional, not local, problem.'
    ),
    'Volunteer Street Ambassadors': (
        'Street ambassador programs can build trust and guide people to services, but '
        'evaluation depends on whether outreach is paired with real bed and housing capacity.'
    ),
    'Clean Streets + Social Service Coupling': (
        'Health-policy reviews find sanitation plus voluntary services works better than '
        'punitive clearing when the goal is lasting exits to housing.'
    ),
    'Small Business Microgrants to Hire': (
        'Local hiring incentives can modestly boost economic activity, but researchers tie '
        'large homelessness reductions to housing investments more than to growth alone.'
    ),
    'Sponsor Transitional Unit Conversions': (
        'Converting hotels or offices can add beds quickly after disasters or spikes—success '
        'hinges on operations funding and connections to permanent housing finance.'
    ),
    'Support Low-Barrier Shelters': (
        'Low-barrier shelters reduce rules that exclude couples, pets, or sobriety lapses, '
        'often improving trust and engagement with people who avoid traditional shelters.'
    ),
    'Coalition with Shelters for Employer Placement': (
        'Job-placement partnerships work best when employers offer predictable schedules and '
        'wages that match local housing costs—otherwise turnover remains high.'
    ),
    'Sponsor University Pilot (housing innovation)': (
        'Evaluations of supportive housing pilots emphasize rigorous measurement: track housing '
        'stability, health utilization, and cost offsets—not only bed nights served.'
    ),
    'Deploy Mobile Clinics': (
        'Mobile clinics and respite programs address acute needs while outreach builds trust; '
        'case studies show they shorten crises when housing navigators are embedded.'
    ),
    'Medicaid & Benefits Enrollment Drive': (
        'SAMHSA highlights that benefits enrollment unlocks health care and sometimes '
        'housing-linked services—many people remain unhoused due to paperwork barriers, not choice.'
    ),
    'Substance Use Treatment Expansion': (
        'Treatment expansion can save lives, but evaluations note housing instability undermines '
        'recovery—integrated housing and health models outperform clinic-only approaches.'
    ),
    'Medical Respite & Recovery Beds': (
        'Medical respite gives people a safe place to heal after hospitalization; without it, '
        'patients often return to streets and bounce back to the ER.'
    ),
    'Behavioral Health Outreach Teams': (
        'Outreach teams for behavioral health reduce crises when they can offer ongoing contact, '
        'not one-off encounters, and when housing options exist at the end of the path.'
    ),
    'Hospital Discharge Coordination': (
        'Discharge planning without housing frequently leads to “patient dumping” scandals; '
        'coordinated shelter or respite beds are a documented equity fix.'
    ),
    'Expand Telehealth for Unhoused': (
        'Telehealth pilots show promise for follow-up when people have phones or clinic partners, '
        'but cannot replace shelter during extreme weather or acute withdrawal.'
    ),
    'Create Medical-Legal Partnerships': (
        'Medical-legal partnerships help fight wrongful evictions and benefits denials—legal '
        'wins that stabilize income are upstream homelessness prevention.'
    ),
    'Partner with Shelters for Onsite Clinics': (
        'Co-locating care in shelters raises screening rates for conditions that otherwise '
        'block housing placements, such as unmanaged infections or wounds.'
    ),
    'Performance-based Funding for Treatment Outcomes': (
        'Pay-for-performance can steer funds toward results, but poorly designed metrics may '
        'exclude the hardest-to-serve unless guardrails reward equitable access.'
    ),
    'Veterans Health Focus': (
        'VA homeless programs pair housing with health care; national campaigns showed '
        'coordinated outreach can drive sustained reductions among veterans.'
    ),
    'Evaluation of Health Interventions (data)': (
        'Rigorous evaluation distinguishes programs that truly reduce mortality and hospital '
        'use from those that only reshuffle visibility on the street.'
    ),
    'Research & Program Evaluation': (
        'Peer-reviewed implementation science shows cities learn faster when they publish '
        'methods, not just success stories—failure analysis improves the next pilot.'
    ),
    'Service-Learning & Workforce Integration': (
        'USICH evidence briefs emphasize career pathways into human services because staffing '
        'shortages limit how quickly systems can scale housing-first responses.'
    ),
    'Housing Innovation Lab (modular units)': (
        'Factory-built and modular units can cut construction time; evaluations still focus on '
        'whether operating subsidies and land access match the speed of factory output.'
    ),
    'Reputation Management (PR)': (
        'Universities balance community partnerships with reputational risk; transparent data '
        'sharing often builds more durable trust than glossy one-off announcements.'
    ),
    'Open Data & Dashboard (public transparency)': (
        'Federal interagency guidance encourages public dashboards so residents can see whether '
        'funding converts into housing placements versus administrative overhead.'
    ),
    'Student Outreach & Volunteer Corps': (
        'Volunteer corps can expand street outreach hours if trained and supervised; USICH '
        'briefs caution that volunteers should not replace professional housing navigators.'
    ),
    'Policy Incubator with City (pilot)': (
        'University–city pilots work when they include community stakeholders and clear '
        'off-ramps—scaling requires mainstream funding, not only research grants.'
    ),
    'Deploy Evaluation Fellows to Shelters': (
        'Embedding analysts in shelters surfaces operational bottlenecks—wait times, denial '
        'reasons, and data gaps—that central offices often miss.'
    ),
    'Community-engaged Research on Displacement': (
        'Participatory research with displaced residents improves validity and reduces harm: '
        'communities co-design questions and own how findings are used.'
    ),
    'Leverage Philanthropy for PSH': (
        'Philanthropy can seed permanent supportive housing, but sustained operation typically '
        'needs Medicaid, housing vouchers, or local public subsidies.'
    ),
    'Student-led Rapid Rehousing Pilot': (
        'Housing First evidence reviews emphasize that rapid re-housing works fastest when '
        'landlord incentives and flexible assistance dollars accompany short-term help.'
    ),
    'Academic Advocacy Campaign': (
        'Policy change often follows coalitions that pair lived experience with researchers—'
        'facts alone rarely overcome organized opposition to new housing sites.'
    ),
}


def _OPERATOR_SPEC():
    U = 'https://www.hudexchange.info/programs/hdx/ahar/'
    return [
        # --- SHELTERS (3) ---
        ('Emergency Expansion (beds +300)', ROLE_SHELTERS, {'shelter_budget': 360.0}, 0.20,
         [('sched', 'shelter', 300), ('mulp', 'pop_families', -0.10), ('mulp', 'pop_veterans', -0.12)], U),
        ('Community Partnership (volunteers & caseworkers)', ROLE_SHELTERS, {'shelter_budget': 100.0}, 0.05,
         [('add', 'social_workers', 6.0), ('mulp', 'pop_chronic', -0.015), ('add', 'policy_momentum', 0.6)],
         'https://www.hsri.org/projects/evaluating-samhsa-four-homelessness-programs-and-resources'),
        ('Housing First Pilot (perm +150)', ROLE_SHELTERS, {'shelter_budget': 520.0}, 0.18,
         [('sched', 'perm', 150), ('mulp', 'pop_chronic', -0.08), ('add', 'public_support', 2.5),
          ('add', 'economy_index', -1.5)],
         'https://www.hiltonfoundation.org/learning/evaluation-of-housing-for-health-permanent-supportive-housing-program/'),
        ('Volunteer Training (social workers +3)', ROLE_SHELTERS, {'shelter_budget': 40.0}, 0.02,
         [('add', 'social_workers', 3.0), ('add', 'public_support', 1.0)],
         'https://www.hsri.org/projects/evaluating-samhsa-four-homelessness-programs-and-resources'),
        ('Rent Assistance Fund (prevention)', ROLE_SHELTERS, {'shelter_budget': 260.0}, 0.07,
         [('mulp', 'pop_families', -0.06), ('mulp', 'pop_youth', -0.04), ('add', 'policy_momentum', 1.0),
          ('add', 'public_support', 1.8)],
         'https://www.hudexchange.info/resource/3891/rapid-re-housing-brief/'),
        ('Defer Maintenance (gain budget, lose beds)', ROLE_SHELTERS, {}, 0.01,
         [('add', 'shelter_budget', 60.0), ('add', 'shelter_capacity', -40.0), ('add', 'public_support', -2.5),
          ('add', 'legal_pressure', 2.0)],
         'https://www.hud.gov'),
        ('Rapid Rehousing Boost', ROLE_SHELTERS, {'shelter_budget': 260.0}, 0.09,
         [('add', 'transitional_units', 60.0), ('mulp', 'pop_families', -0.09), ('add', 'policy_momentum', 1.2)],
         'https://nlihc.org/gap'),
        ('Add Outreach Vans', ROLE_SHELTERS, {'shelter_budget': 110.0}, 0.04,
         [('add', 'outreach_teams', 2.0), ('mulp', 'pop_youth', -0.06)],
         'https://www.commonwealthfund.org/publications/case-study/2021/aug/how-medical-respite-care-program-offers-pathway-health-housing'),
        ('Intensify Case Management', ROLE_SHELTERS, {'shelter_budget': 140.0}, 0.06,
         [('add', 'social_workers', 5.0), ('add', 'policy_momentum', 0.9), ('mulp', 'pop_chronic', -0.05)],
         'https://www.hsri.org/projects/evaluating-samhsa-four-homelessness-programs-and-resources'),
        ('Sanction Encampment (sanctioned services)', ROLE_SHELTERS, {'shelter_budget': 180.0}, 0.12,
         [('add', 'shelter_capacity', 80.0), ('add', 'public_support', -1.0), ('add', 'legal_pressure', -2.5)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC8427990'),
        ('Partner: Medical Support (onsite clinics)', ROLE_SHELTERS,
         {'shelter_budget': 160.0, 'medical_budget': 80.0}, 0.08,
         [('add', 'medical_vans', 1.0), ('mulp', 'pop_chronic', -0.07)],
         'https://www.commonwealthfund.org/publications/case-study/2021/aug/how-medical-respite-care-program-offers-pathway-health-housing'),
        ('Evaluation & Data Sharing (with Univ)', ROLE_SHELTERS,
         {'shelter_budget': 80.0, 'university_budget': 70.0}, 0.03,
         [('add', 'policy_momentum', 1.6), ('add', 'public_support', 0.8)],
         'https://www.usich.gov/'),

        # --- NEIGHBORHOODS (0) ---
        ('Media Campaign (reframe homelessness)', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 140.0}, 0.06,
         [('add', 'public_support', 6.0), ('add', 'legal_pressure', -3.0)],
         'https://journals.sagepub.com/doi/10.1177/0739456X241265499'),
        ('Block New Low-Income Development (NIMBY action)', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 60.0}, 0.04,
         [('add', 'permanent_units', -50.0), ('add', 'public_support', 2.0), ('add', 'legal_pressure', 4.0)],
         'https://www.law.berkeley.edu/article/clinic-study-details-how-business-districts-target-homeless-people/'),
        ('Local Voucher Matching Fund', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 200.0}, 0.08,
         [('mulp', 'pop_families', -0.07), ('add', 'permanent_units', 20.0), ('add', 'policy_momentum', 0.8),
          ('add', 'public_support', 3.0)],
         'https://www.hud.gov/program_offices/public_indian_housing/programs/hcv'),
        ('Civic Forum (reduce tensions)', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 30.0}, 0.02,
         [('add', 'legal_pressure', -2.0), ('add', 'public_support', 1.0)],
         'https://journals.sagepub.com/doi/10.1177/10986111241289390'),
        ('Fund Private Security (pushout)', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 120.0}, 0.10,
         [('add', 'public_support', 3.0), ('displace', 0.006), ('add', 'legal_pressure', 2.0)],
         'https://www.law.berkeley.edu/article/clinic-study-details-how-business-districts-target-homeless-people/'),
        ('Infrastructure Grants (convert trans->perm)', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 300.0}, 0.14,
         [('add', 'transitional_units', -80.0), ('add', 'permanent_units', 72.0), ('mulp', 'pop_families', -0.01),
          ('add', 'policy_momentum', 1.5)],
         'https://www.rti.org/publication/a-review-of-the-literature-on-neighborhood-impacts-of-permanent-s'),
        ('Community Food & Outreach Sponsorship', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 80.0}, 0.03,
         [('add', 'outreach_teams', 1.0), ('add', 'public_support', 1.2), ('mulp', 'pop_youth', -0.03)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC8427990/'),
        ('Neighborhood Rapid Response to Eviction Spikes', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 240.0}, 0.09,
         [('mulp', 'pop_families', -0.10), ('add', 'policy_momentum', 1.0)],
         'https://nlihc.org/'),
        ('Public Space Design (reduce congregation)', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 160.0}, 0.05,
         [('add', 'public_support', 1.6), ('add', 'legal_pressure', -1.2)],
         'https://www.tandfonline.com/doi/full/10.1080/10439463.2024.2362730'),
        ('Property Value Assistance (tax incentive)', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 220.0}, 0.08,
         [('add', 'permanent_units', 30.0), ('add', 'public_support', 0.9)],
         'https://housing-infrastructure.canada.ca/homelessness-sans-abri/reports-rapports/shelter-cap-hebergement-2024-eng.html'),
        ('Neighborhood-led Transitional Housing Project', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 300.0}, 0.12,
         [('add', 'transitional_units', 90.0), ('mulp', 'pop_families', -0.06), ('add', 'policy_momentum', 1.2)],
         'https://www.huduser.gov/portal/publications/pdf/lifeaftertransition.pdf'),
        ('Neighborhood Monitoring & Data', ROLE_NEIGHBORHOODS, {'neighborhood_budget': 40.0}, 0.02,
         [('add', 'legal_pressure', -0.8), ('add', 'public_support', 0.4)],
         'https://journals.sagepub.com/doi/10.1177/0739456X241265499'),

        # --- BUSINESS (1) ---
        ('Tax Incentives for Affordable Housing', ROLE_BUSINESS, {'business_budget': 260.0}, 0.12,
         [('sched', 'perm', 120), ('add', 'economy_index', 1.8), ('add', 'public_support', 1.2)],
         'https://endhomelessness.org/state-of-homelessness/'),
        ('Fund Job Readiness Programs', ROLE_BUSINESS, {'business_budget': 180.0}, 0.06,
         [('mulp', 'pop_families', -0.05), ('mulp', 'pop_youth', -0.12), ('add', 'public_support', 2.2)],
         'https://endhomelessness.org/'),
        ('Clean & Sweep (sanitation)', ROLE_BUSINESS, {'business_budget': 80.0}, 0.09,
         [('add', 'public_support', 2.5), ('displace', 0.004), ('add', 'legal_pressure', 1.5)],
         'https://endhomelessness.org/blog/punitive-policies-will-never-solve-homelessness-the-evidence-is-clear/'),
        ('Public-Private Transitional Housing', ROLE_BUSINESS, {'business_budget': 360.0}, 0.11,
         [('add', 'transitional_units', 90.0), ('mulp', 'pop_families', -0.04), ('add', 'public_support', 1.8)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC8899911'),
        ('Lobby for Restrictive Ordinances', ROLE_BUSINESS, {'business_budget': 140.0}, 0.16,
         [('add', 'legal_pressure', 5.0), ('add', 'economy_index', 0.8), ('displace', 0.007)],
         'https://www.law.berkeley.edu/article/clinic-study-details-how-business-districts-target-homeless-people/'),
        ('Volunteer Street Ambassadors', ROLE_BUSINESS, {'business_budget': 100.0}, 0.03,
         [('add', 'outreach_teams', 2.0), ('add', 'public_support', 1.5), ('mulp', 'pop_youth', -0.05)],
         'https://www.tandfonline.com/doi/full/10.1080/10439463.2024.2362730'),
        ('Clean Streets + Social Service Coupling', ROLE_BUSINESS, {'business_budget': 220.0}, 0.07,
         [('add', 'public_support', 2.8), ('mulp', 'pop_chronic', -0.02)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC8356292/'),
        ('Small Business Microgrants to Hire', ROLE_BUSINESS, {'business_budget': 140.0}, 0.02,
         [('add', 'economy_index', 1.2), ('add', 'public_support', 1.0)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC8356292/'),
        ('Sponsor Transitional Unit Conversions', ROLE_BUSINESS, {'business_budget': 280.0}, 0.08,
         [('add', 'transitional_units', 70.0), ('add', 'policy_momentum', 0.9)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC8899911'),
        ('Support Low-Barrier Shelters', ROLE_BUSINESS, {'business_budget': 180.0}, 0.05,
         [('add', 'shelter_capacity', 120.0), ('mulp', 'pop_chronic', -0.03), ('add', 'public_support', 0.6)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC7983925/'),
        ('Coalition with Shelters for Employer Placement', ROLE_BUSINESS, {'business_budget': 160.0}, 0.04,
         [('mulp', 'pop_families', -0.03), ('add', 'policy_momentum', 0.5)],
         'https://www.hsri.org/projects/evaluating-samhsa-four-homelessness-programs-and-resources'),
        ('Sponsor University Pilot (housing innovation)', ROLE_BUSINESS,
         {'business_budget': 240.0, 'university_budget': 50.0}, 0.07,
         [('add', 'transitional_units', 40.0), ('add', 'policy_momentum', 1.0)],
         'https://www.hiltonfoundation.org/learning/evaluation-of-housing-for-health-permanent-supportive-housing-program'),

        # --- MEDICAL (2) ---
        ('Deploy Mobile Clinics', ROLE_MEDICAL, {'medical_budget': 200.0}, 0.06,
         [('add', 'medical_vans', 2.0), ('mulp', 'pop_chronic', -0.06), ('add', 'public_support', 2.8)],
         'https://www.commonwealthfund.org/publications/case-study/2021/aug/how-medical-respite-care-program-offers-pathway-health-housing'),
        ('Medicaid & Benefits Enrollment Drive', ROLE_MEDICAL, {'medical_budget': 160.0}, 0.05,
         [('mulp', 'pop_chronic', -0.07), ('add', 'policy_momentum', 1.2)],
         'https://www.samhsa.gov/'),
        ('Substance Use Treatment Expansion', ROLE_MEDICAL, {'medical_budget': 320.0}, 0.18,
         [('mulp', 'pop_chronic', -0.12), ('add', 'public_support', -1.0), ('add', 'policy_momentum', 2.8)],
         'https://www.hsri.org/projects/evaluating-samhsa-four-homelessness-programs-and-resources'),
        ('Medical Respite & Recovery Beds', ROLE_MEDICAL, {'medical_budget': 260.0}, 0.10,
         [('add', 'shelter_capacity', 80.0), ('mulp', 'pop_chronic', -0.05)],
         'https://www.commonwealthfund.org/publications/case-study/2021/aug/how-medical-respite-care-program-offers-pathway-health-housing'),
        ('Behavioral Health Outreach Teams', ROLE_MEDICAL, {'medical_budget': 220.0}, 0.09,
         [('add', 'outreach_teams', 2.0), ('mulp', 'pop_youth', -0.08), ('add', 'policy_momentum', 1.3)],
         'https://www.samhsa.gov/'),
        ('Hospital Discharge Coordination', ROLE_MEDICAL, {'medical_budget': 120.0}, 0.04,
         [('mulp', 'pop_chronic', -0.03), ('add', 'public_support', 0.7)],
         'https://www.commonwealthfund.org/publications/case-study/2021/aug/how-medical-respite-care-program-offers-pathway-health-housing'),
        ('Expand Telehealth for Unhoused', ROLE_MEDICAL, {'medical_budget': 90.0}, 0.03,
         [('add', 'policy_momentum', 0.6), ('add', 'public_support', 0.5)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC6153151'),
        ('Create Medical-Legal Partnerships', ROLE_MEDICAL, {'medical_budget': 100.0}, 0.04,
         [('add', 'legal_pressure', -1.5), ('add', 'policy_momentum', 0.7)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC8356292'),
        ('Partner with Shelters for Onsite Clinics', ROLE_MEDICAL, {'medical_budget': 140.0}, 0.05,
         [('add', 'medical_vans', 1.0), ('mulp', 'pop_chronic', -0.04)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC8356292'),
        ('Performance-based Funding for Treatment Outcomes', ROLE_MEDICAL, {'medical_budget': 240.0}, 0.12,
         [('add', 'policy_momentum', 1.8), ('add', 'public_support', -0.8)],
         'https://www.hsri.org/projects/evaluating-samhsa-four-homelessness-programs-and-resources'),
        ('Veterans Health Focus', ROLE_MEDICAL, {'medical_budget': 160.0}, 0.06,
         [('mulp', 'pop_veterans', -0.10), ('add', 'policy_momentum', 1.0)],
         'https://www.va.gov/homeless/'),
        ('Evaluation of Health Interventions (data)', ROLE_MEDICAL,
         {'medical_budget': 80.0, 'university_budget': 60.0}, 0.03,
         [('add', 'policy_momentum', 1.4), ('add', 'public_support', 0.6)],
         'https://www.hsri.org/projects/evaluating-samhsa-four-homelessness-programs-and-resources'),

        # --- UNIVERSITY (4) ---
        ('Research & Program Evaluation', ROLE_UNIVERSITY, {'university_budget': 100.0}, 0.03,
         [('add', 'policy_momentum', 1.5)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC1525292/'),
        ('Service-Learning & Workforce Integration', ROLE_UNIVERSITY, {'university_budget': 110.0}, 0.04,
         [('add', 'social_workers', 5.0), ('mulp', 'pop_youth', -0.10), ('add', 'public_support', 1.2)],
         'https://www.usich.gov/sites/default/files/document/Evidence-Behind-Approaches-That-End-Homelessness-Brief-2019.pdf'),
        ('Housing Innovation Lab (modular units)', ROLE_UNIVERSITY, {'university_budget': 260.0}, 0.10,
         [('sched', 'trans', 70), ('mulp', 'pop_chronic', -0.03), ('add', 'policy_momentum', 2.0)],
         'https://www.hiltonfoundation.org/learning/evaluation-of-housing-for-health-permanent-supportive-housing-program'),
        ('Reputation Management (PR)', ROLE_UNIVERSITY, {'university_budget': 80.0}, 0.02,
         [('add', 'public_support', 0.6), ('add', 'policy_momentum', -0.4)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC1525292/'),
        ('Open Data & Dashboard (public transparency)', ROLE_UNIVERSITY, {'university_budget': 70.0}, 0.02,
         [('add', 'policy_momentum', 0.8), ('add', 'public_support', 0.5)],
         'https://www.usich.gov/'),
        ('Student Outreach & Volunteer Corps', ROLE_UNIVERSITY, {'university_budget': 90.0}, 0.03,
         [('add', 'outreach_teams', 2.0), ('mulp', 'pop_youth', -0.06), ('add', 'public_support', 1.0)],
         'https://www.usich.gov/sites/default/files/document/Evidence-Behind-Approaches-That-End-Homelessness-Brief-2019.pdf'),
        ('Policy Incubator with City (pilot)', ROLE_UNIVERSITY,
         {'university_budget': 220.0, 'neighborhood_budget': 60.0}, 0.08,
         [('add', 'permanent_units', 30.0), ('add', 'policy_momentum', 1.6)],
         'https://www.usich.gov/sites/default/files/document/Evidence-Behind-Approaches-That-End-Homelessness-Brief-2019.pdf'),
        ('Deploy Evaluation Fellows to Shelters', ROLE_UNIVERSITY, {'university_budget': 110.0}, 0.03,
         [('add', 'social_workers', 2.0), ('add', 'policy_momentum', 1.0)],
         'https://www.hsri.org/projects/evaluating-samhsa-four-homelessness-programs-and-resources'),
        ('Community-engaged Research on Displacement', ROLE_UNIVERSITY, {'university_budget': 140.0}, 0.05,
         [('add', 'policy_momentum', 1.8), ('add', 'public_support', 0.5)],
         'https://pmc.ncbi.nlm.nih.gov/articles/PMC1525292/'),
        ('Leverage Philanthropy for PSH', ROLE_UNIVERSITY, {'university_budget': 260.0}, 0.09,
         [('sched', 'perm', 50), ('add', 'policy_momentum', 1.2)],
         'https://www.hiltonfoundation.org/learning/evaluation-of-housing-for-health-permanent-supportive-housing-program'),
        ('Student-led Rapid Rehousing Pilot', ROLE_UNIVERSITY, {'university_budget': 120.0}, 0.06,
         [('add', 'transitional_units', 40.0), ('mulp', 'pop_youth', -0.08)],
         'https://nlihc.org/sites/default/files/Housing-First-Evidence.pdf'),
        ('Academic Advocacy Campaign', ROLE_UNIVERSITY, {'university_budget': 80.0}, 0.03,
         [('add', 'public_support', 0.9), ('add', 'policy_momentum', 0.6)],
         'https://nlihc.org/'),
    ]


# Fix: Housing Innovation Lab URL duplicate — use same as other Hilton links
# (left as-is in table)

# ---------------------------------------------------------------------------
# ROLES & FORMULATION
# ---------------------------------------------------------------------------


class CityWithoutWalls_Roles_Spec(sz.SZ_Roles_Spec):
    def __init__(self):
        self.roles = [
            sz.SZ_Role(
                name='Neighborhoods',
                description='Residents seeking visible relief without sacrificing neighborhood stability.',
                max_players=25,
            ),
            sz.SZ_Role(
                name='Business',
                description='Downtown and corridor stakeholders focused on clean, safe streets.',
                max_players=25,
            ),
            sz.SZ_Role(
                name='Medical',
                description='Hospitals and clinics balancing care missions with capacity.',
                max_players=25,
            ),
            sz.SZ_Role(
                name='Shelters',
                description='Emergency housing providers stretching thin budgets.',
                max_players=25,
            ),
            sz.SZ_Role(
                name='University',
                description='Research and teaching mission with reputational exposure.',
                max_players=25,
            ),
            sz.SZ_Role(
                name='Observer',
                description='Independent oversight; one special report per game.',
                max_players=25,
            ),
        ]
        self.min_players_to_start = 5
        self.max_players = 26


class CityWithoutWalls_Formulation(sz.SZ_Formulation):
    def __init__(self):
        self.metadata = CityWithoutWalls_Metadata()
        self.operators = CityWithoutWalls_Operator_Set()
        self.roles_spec = CityWithoutWalls_Roles_Spec()
        self.common_data = sz.SZ_Common_Data()

    def initialize_problem(self, config=None):
        cfg = dict(config or {})
        s = CityWithoutWalls_State(config=cfg)
        self.instance_data = sz.SZ_Problem_Instance_Data(d={'initial_state': s})
        return s


CityWithoutWalls = CityWithoutWalls_Formulation()


# ---------------------------------------------------------------------------
# __main__ smoke test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    random.seed(42)

    F = CityWithoutWalls  # module singleton (macro op list must match transitions)
    ops = F.operators.operators

    s = F.initialize_problem({'active_roles': [0, 1, 2, 3, 4]})
    begin = next(op for op in ops if op.name == 'Review goals & begin simulation')
    assert begin.precond_func(s)
    s = begin.state_xition_func(s)
    assert s.phase == 'playing'
    print('=== City Without Walls SZ6 smoke test ===\n')
    for rnd in range(3):
        print(f'--- Round cycle {rnd + 1} (game_round before ops={s.game_round}) ---')
        for _ in range(len(s.play_order)):
            if s.phase != 'playing':
                break
            applicable = [op for op in ops if op.precond_func(s)]
            assert applicable, f'no offered operators for role {s.current_role_num}'
            op = applicable[0]
            s = op.state_xition_func(s)
        cpy = CityWithoutWalls_State(old=s)
        assert cpy.construction_pipeline is not s.construction_pipeline
        assert cpy is not s
        print(str(s))
        if hasattr(s, 'jit_transition') and s.jit_transition:
            print(s.jit_transition.split('\n')[0])
        print()

    assert id(cpy.construction_pipeline) != id(s.construction_pipeline)
    assert cpy.round_actors is not s.round_actors
    print('Copy fidelity: independent lists OK')
    print('Done. phase=', s.phase, 'game_round=', s.game_round, 'homeless=', s.homeless_population)
