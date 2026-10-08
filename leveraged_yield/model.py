"""Loop mechanics, P&L and risk for a single leveraged-yield combination.

The process being modelled (the manual "recursive borrow" strategy):

1. Post the starting capital E of token C as collateral on lending route r1.
2. Borrow b1 = u * LTV1 * E of token B (u = share of the max LTV you use;
   u = 1 is "borrow the full 80%").
3. Put b1 to work in venue V (lend / stake / vault). If V's receipt token R is
   accepted as collateral (route r2: R -> B), post it and borrow again:
   b_{k+1} = u * LTV2 * b_k. Repeat until the next borrow is dust or no longer
   pays for its gas. Without such a route the strategy stops after b1 (carry).

All APYs are in percent per year; money is in USD.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from . import config
from .assets import family, is_plain_stable
from .config import Settings
from .universe import Route, Venue

Z_95 = 1.6448536269514722


@dataclass(frozen=True)
class Spec:
    """Everything needed to evaluate one (collateral, r1, venue, r2) combination."""
    capital: float
    collateral: str
    r1: Route
    venue: Venue
    r2: Route | None
    y_collateral: float  # yield on the posted collateral (market supply APY + native yield)
    y_venue: float  # yield on every deployed tranche
    # Effective cost of each borrow leg: borrow APY plus the native yield of the
    # debt token (borrowing JitoSOL means owing an asset that appreciates vs SOL).
    borrow_cost1: float
    borrow_cost2: float
    entry_cost: float  # fraction of each tranche lost converting B -> venue deposit
    exit_cost: float  # fraction lost converting back to repay
    gas_step_usd: float
    collateral_issuer: str | None = None  # protocol behind a yield-bearing collateral token
    collateral_issuer_pfail: float = 0.0
    spread_vol_pp: float = 1.5  # 1-sigma uncertainty of the carry spread over the holding period

    @property
    def same_account(self) -> bool:
        return self.r2 is not None and self.r2.account == self.r1.account


@dataclass
class AccountRisk:
    label: str
    health_factor: float
    directional_buffer: float | None  # adverse move of collateral vs debt to liquidation
    depeg_buffer: float | None  # depeg of same-family collateral vs debt to liquidation
    p_liquidation: float
    debt: float
    liq_penalty: float


@dataclass
class Result:
    spec: Spec
    utilization: float
    loops: int
    tranches: list[float]
    debt: float
    deployed: float
    leverage: float  # total assets / equity
    net_apy: float
    gross_carry_apy: float
    cost_apy: float
    liq_loss_apy: float
    protocol_loss_apy: float
    spread_risk_apy: float
    risk_adjusted_apy: float
    stress_apy: float
    p5_apy: float
    accounts: list[AccountRisk] = field(default_factory=list)
    exposures: dict[str, float] = field(default_factory=dict)
    step_health_factor: float = math.inf  # weakest state while building the loop

    @property
    def min_health_factor(self) -> float:
        return min((a.health_factor for a in self.accounts if a.debt > 0), default=math.inf)

    @property
    def liquidation_buffer(self) -> float | None:
        """Smallest adverse price move (any kind) that triggers a liquidation."""
        vals = [b for a in self.accounts if a.debt > 0
                for b in (a.directional_buffer, a.depeg_buffer) if b is not None]
        return min(vals) if vals else None

    @property
    def p_liquidation(self) -> float:
        p_ok = 1.0
        for a in self.accounts:
            p_ok *= 1.0 - a.p_liquidation
        return 1.0 - p_ok

    @property
    def spread_leverage(self) -> float:
        return self.debt / self.spec.capital

    def annual_profit_usd(self) -> float:
        return self.net_apy / 100.0 * self.spec.capital


# --------------------------------------------------------------------------- math helpers

def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def barrier_hit_probability(buffer: float | None, sigma: float, years: float) -> float:
    """P(a driftless log-price path falls by ``buffer`` at least once within ``years``)."""
    if buffer is None or buffer >= 1.0:
        return 0.0
    if buffer <= 0.0:
        return 1.0
    if sigma <= 0.0 or years <= 0.0:
        return 0.0
    distance = -math.log(1.0 - buffer)
    return min(1.0, 2.0 * norm_cdf(-distance / (sigma * math.sqrt(years))))


def pair_vol(fam_a: str, fam_b: str) -> float:
    va = config.ASSET_VOL.get(fam_a, config.DEFAULT_ASSET_VOL)
    vb = config.ASSET_VOL.get(fam_b, config.DEFAULT_ASSET_VOL)
    rho = config.ASSET_CORR.get(frozenset((fam_a, fam_b)), config.DEFAULT_ASSET_CORR)
    return math.sqrt(max(va * va + vb * vb - 2 * rho * va * vb, 0.0))


def depeg_vol(token: str, debt: str) -> float:
    if is_plain_stable(token) and is_plain_stable(debt):
        return config.PLAIN_STABLE_DEPEG_VOL
    return config.DEPEG_VOL.get(family(debt), config.DEFAULT_DEPEG_VOL)


def account_risk(label: str, collateral: list[tuple[str, float, float]], debt_token: str,
                 debt: float, liq_penalty: float, settings: Settings) -> AccountRisk:
    """collateral: list of (token, value_usd, liquidation_threshold)."""
    if debt <= 0:
        return AccountRisk(label, math.inf, None, None, 0.0, 0.0, liq_penalty)
    fam = family(debt_token)
    s_ident = sum(v * lt for t, v, lt in collateral if t == debt_token)
    peg = [(t, v, lt) for t, v, lt in collateral if t != debt_token and family(t) == fam]
    dirc = [(t, v, lt) for t, v, lt in collateral if family(t) != fam]
    s_peg = sum(v * lt for _, v, lt in peg)
    s_dir = sum(v * lt for _, v, lt in dirc)
    hf = (s_ident + s_peg + s_dir) / debt

    def buffer(moving: float, fixed: float) -> float | None:
        if moving <= 0:
            return None
        if debt <= fixed:
            return 1.0  # cannot be liquidated by this move alone
        return max(0.0, 1.0 - (debt - fixed) / moving)

    dir_buf = buffer(s_dir, s_ident + s_peg)
    peg_buf = buffer(s_peg, s_ident + s_dir)
    years = settings.horizon_years
    p_dir = 0.0
    if dir_buf is not None:
        sig = max(pair_vol(family(t), fam) for t, _, _ in dirc)
        p_dir = barrier_hit_probability(dir_buf, sig, years)
    p_peg = 0.0
    if peg_buf is not None:
        sig = max(depeg_vol(t, debt_token) for t, _, _ in peg)
        p_peg = barrier_hit_probability(peg_buf, sig, years)
    p = 1.0 - (1.0 - p_dir) * (1.0 - p_peg)
    if hf <= 1.0:
        p = 1.0
    return AccountRisk(label, hf, dir_buf, peg_buf, p, debt, liq_penalty)


# --------------------------------------------------------------------------- loop mechanics

def tranche_schedule(spec: Spec, u: float, settings: Settings) -> list[float]:
    """Borrow sizes for each loop until the next one is dust or does not pay for gas."""
    tranches = [u * spec.r1.ltv * spec.capital]
    if spec.r2 is None:
        return tranches
    margin = (spec.y_venue - spec.borrow_cost2) / 100.0 * settings.holding_years
    while len(tranches) < settings.max_loops:
        nxt = u * spec.r2.ltv * tranches[-1]
        if nxt < settings.dust_usd:
            break
        gain = nxt * (margin - spec.entry_cost - spec.exit_cost)
        if gain < 2 * spec.gas_step_usd:  # enter + unwind this loop
            break
        tranches.append(nxt)
    return tranches


def step_health_factor(spec: Spec, b: list[float]) -> float:
    """Lowest health factor reached mid-process: right after a borrow, before the
    borrowed tranche has been converted and re-posted as collateral.

    Each step's ratio is a blend of the first and the last step, so checking
    those two is enough.
    """
    E, r1, r2 = spec.capital, spec.r1, spec.r2
    worst = r1.lt * E / b[0]
    if r2 is None or len(b) < 2:
        return worst
    if spec.same_account:
        worst = min(worst, (r1.lt * E + r2.lt * sum(b[:-1])) / sum(b))
    else:
        worst = min(worst, r2.lt * b[0] / b[1], r2.lt * sum(b[:-1]) / sum(b[1:]))
    return worst


def evaluate(spec: Spec, u: float, loops: int, schedule: list[float],
             settings: Settings) -> Result:
    E = spec.capital
    b = schedule[:loops]
    d1, d2 = b[0], sum(b[1:])
    debt = d1 + d2
    deployed = sum(b)
    r1, r2, v = spec.r1, spec.r2, spec.venue

    carry = (E * spec.y_collateral + deployed * spec.y_venue
             - d1 * spec.borrow_cost1 - d2 * spec.borrow_cost2)
    one_off = deployed * (spec.entry_cost + spec.exit_cost) + spec.gas_step_usd * (2 + 2 * len(b))
    cost_apy = one_off / settings.holding_years / E * 100.0
    gross = carry / E
    net = gross - cost_apy

    # --- liquidation risk per account
    c, B = spec.collateral, r1.debt
    accounts: list[AccountRisk] = []
    if r2 is None:
        accounts.append(account_risk(r1.market_label, [(c, E, r1.lt)], B, d1, r1.liq_penalty,
                                     settings))
    elif spec.same_account:
        accounts.append(account_risk(r1.market_label, [(c, E, r1.lt), (v.receipt, deployed, r2.lt)],
                                     B, debt, max(r1.liq_penalty, r2.liq_penalty), settings))
    else:
        accounts.append(account_risk(r1.market_label, [(c, E, r1.lt)], B, d1, r1.liq_penalty,
                                     settings))
        accounts.append(account_risk(r2.market_label, [(v.receipt, deployed, r2.lt)], B, d2,
                                     r2.liq_penalty, settings))
    liq_loss = sum(a.p_liquidation * a.liq_penalty * a.debt for a in accounts) / E * 100.0

    # --- protocol (smart-contract / insolvency / depeg) risk
    exposure: dict[str, float] = defaultdict(float)
    pfail: dict[str, float] = {}

    def add(protocol: str, amount: float, p: float) -> None:
        exposure[protocol] += amount
        pfail[protocol] = max(pfail.get(protocol, 0.0), p)

    add(r1.protocol, E + (deployed if spec.same_account else 0.0), r1.p_fail)
    if r2 is not None and not spec.same_account:
        add(r2.protocol, deployed, r2.p_fail)
    add(v.protocol, deployed, v.p_fail)
    if spec.collateral_issuer:
        add(spec.collateral_issuer, E, spec.collateral_issuer_pfail)
    proto_loss = sum(pfail[p] * min(1.0, settings.lgd * x / E) for p, x in exposure.items()) * 100

    # --- carry-spread uncertainty (rates move after you enter)
    lev_s = debt / E
    sigma = lev_s * spec.spread_vol_pp
    spread_risk = 0.5 * settings.risk_aversion * sigma * sigma / 100.0

    return Result(
        spec=spec, utilization=u, loops=len(b), tranches=b, debt=debt, deployed=deployed,
        leverage=(E + deployed) / E, net_apy=net, gross_carry_apy=gross, cost_apy=cost_apy,
        liq_loss_apy=liq_loss, protocol_loss_apy=proto_loss, spread_risk_apy=spread_risk,
        risk_adjusted_apy=net - liq_loss - proto_loss - spread_risk,
        stress_apy=net - lev_s * settings.stress_spread_pp, p5_apy=net - Z_95 * sigma,
        accounts=accounts, exposures=dict(exposure), step_health_factor=step_health_factor(spec, b),
    )


def loop_counts(n_max: int) -> list[int]:
    """Candidate loop counts to try (all small counts, then a sparse grid, then the max)."""
    base = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50]
    return sorted({n for n in base if n <= n_max} | {n_max})
