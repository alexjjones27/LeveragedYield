"""Day-by-day simulation of carry trades and plain-lending baselines.

A carry trade for a holder of asset H:
  1. post H (or its yield-bearing form) as collateral on borrow venue A,
  2. borrow token X there at ``u`` x max LTV,
  3. move X to lend venue B (paying withdrawal / bridge / gas / swap costs) and lend it.
The position is delta-neutral in X (you owe X and hold X), so profit is the
spread ``lend APR - borrow APR`` on the borrowed amount, plus whatever the
collateral itself earns at A. Prices only matter for the health factor: a
weekly rebalance re-targets the debt to ``u`` x LTV of the collateral value,
an emergency rebalance runs when the health factor drops below 1.25, and a
liquidation (50% close factor + penalty) happens if it closes a day below 1.

The baseline is the same capital simply lent / staked at one venue.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..assets import family
from .data import CarryData, Leg

HOLDER_HOME = {"USD": "USDC", "ETH": "WETH", "BTC": "BTC", "SOL": "SOL"}

GAS_USD = {"Ethereum": 1.5, "Solana": 0.01}
DEFAULT_GAS_USD = 0.05
CEX_WITHDRAW_USD = {"USD": 1.0, "ETH": 1.5, "BTC": 5.0, "SOL": 0.1}
BRIDGE_USD, BRIDGE_BPS = 1.0, 3.0
SWAP_BPS = {"USD": 3.0, "ETH": 5.0, "BTC": 10.0, "SOL": 5.0}
FIAT_USD_BPS = 10.0  # USDT <-> USD on Bitfinex


@dataclass
class SimConfig:
    capital_usd: float = 10_000.0
    u_same_family: float = 0.8  # share of max LTV when collateral and debt move together
    u_cross_family: float = 0.5  # ... when they do not (price moves hit the health factor)
    rebalance_days: int = 7
    rebalance_band: float = 0.15  # only re-size the debt if it is >15% off target
    hf_floor: float = 1.25  # emergency deleverage below this health factor
    close_factor: float = 0.5
    rotation_lookback: int = 14
    rotation_min_gain_pp: float = 0.5  # switch venue only if trailing APR is this much better
    lgd: float = 0.5  # loss given a venue failure
    min_coverage: float = 0.9
    # Annual failure / depeg probability of yield-bearing tokens' issuers
    # (wstETH -> Lido, ...), applied to whatever you hold of that token.
    issuer_pfail: dict[str, float] = field(default_factory=dict)
    managed: bool = True  # False = set-and-forget: never rebalance, ride out liquidations


@dataclass(frozen=True)
class Plan:
    holder: str
    borrow: Leg | None  # None -> lend-only baseline
    lend: Leg | None  # starting lend leg
    pool: tuple[Leg, ...] = ()  # rotation candidates (empty = static)
    u: float = 0.0

    @property
    def is_carry(self) -> bool:
        return self.borrow is not None

    @property
    def rotating(self) -> bool:
        return bool(self.pool)

    @property
    def key(self) -> str:
        lend = "rotating" if self.rotating else (self.lend.id if self.lend else "hold")
        return f"{self.holder}|{self.borrow.id if self.borrow else 'none'}|{lend}"


@dataclass
class SimResult:
    plan: Plan
    start: str
    end: str
    days: int
    apy: float  # net income / average capital, annualised (simple), after all costs
    expected_loss_apy: float
    profit_usd: float  # net income over the window
    profit_units: float  # ... in units of the held asset (income converted on the day earned)
    avg_capital_usd: float
    avg_borrow: float
    avg_lend: float
    avg_collateral_yield: float
    pct_days_positive_spread: float
    worst_30d_spread: float
    worst_30d_apy: float  # worst 30-day stretch of carry income (excl. entry/exit costs)
    max_drawdown: float  # deepest fall of cumulative carry income, % of capital
    min_hf: float
    rebalances: int
    liquidations: int
    liquidation_loss_usd: float
    switches: int
    costs_usd: float  # gas, transfers, swaps, liquidation penalties
    lend_history: list[str] = field(default_factory=list)

    @property
    def risk_adj_apy(self) -> float:
        return self.apy - self.expected_loss_apy

    @property
    def avg_spread(self) -> float:
        return self.avg_lend - self.avg_borrow


# --------------------------------------------------------------------------- helpers

def gas(leg: Leg) -> float:
    return 0.0 if leg.venue_type == "CEX" else GAS_USD.get(leg.location, DEFAULT_GAS_USD)


def transfer_cost(src: Leg | None, dst: Leg, amount_usd: float) -> float:
    """Cost of moving funds from where ``src`` holds them to ``dst``'s venue."""
    if src is None or (src.venue_type, src.location) == (dst.venue_type, dst.location):
        return 0.0
    fam = family(dst.asset)
    if src.venue_type == "CEX":
        return CEX_WITHDRAW_USD.get(fam, 2.0)
    if dst.venue_type == "CEX":
        return gas(src)
    return BRIDGE_USD + BRIDGE_BPS / 1e4 * amount_usd + gas(src)


def swap_cost(a: str, b: str, amount_usd: float) -> float:
    if a == b:
        return 0.0
    if "USD" in (a, b):  # Bitfinex fiat USD
        return FIAT_USD_BPS / 1e4 * amount_usd
    return SWAP_BPS.get(family(a), 15.0) / 1e4 * amount_usd


def series_on(rates: dict[str, float], dates: list[str], max_gap: int = 7) -> list[float] | None:
    """Rates aligned to ``dates`` with forward fill; None if coverage is poor."""
    if not rates:
        return None
    keys = sorted(rates)
    out, j, last, last_seen = [], 0, None, -10**9
    for i, d in enumerate(dates):
        while j < len(keys) and keys[j] <= d:
            last, last_seen = rates[keys[j]], i
            j += 1
        if last is None:
            out.append(None)
        else:
            out.append(last if i - last_seen <= max_gap else None)
    first = next((i for i, v in enumerate(out) if v is not None), None)
    if first is None or first > max_gap:
        return None
    out = [out[first]] * first + out[first:]
    missing = sum(v is None for v in out)
    if missing / len(dates) > 0.1:
        return None
    filled, prev = [], out[0]
    for v in out:
        prev = v if v is not None else prev
        filled.append(prev)
    return filled


class Market:
    """Aligned daily rates and prices for one backtest window."""

    def __init__(self, data: CarryData, dates: list[str]):
        self.dates = dates
        self._rates: dict[tuple[str, str], list[float] | None] = {}
        self._data = data
        self.prices = {"USD": [1.0] * len(dates)}
        for fam, series in data.prices.items():
            self.prices[fam] = series_on(series, dates, max_gap=10) or [math.nan] * len(dates)

    def rates(self, leg: Leg, which: str = "rates") -> list[float] | None:
        key = (leg.id, which)
        if key not in self._rates:
            src = getattr(leg, which)
            self._rates[key] = (series_on(src, self.dates) if src else [0.0] * len(self.dates))
        return self._rates[key]

    def price(self, token: str) -> list[float]:
        return self.prices.get(family(token), self.prices["USD"])

    def usable(self, leg: Leg) -> bool:
        return self.rates(leg) is not None and (
            leg.side == "lend" or self.rates(leg, "collateral_rates") is not None)


# --------------------------------------------------------------------------- simulation

def simulate(plan: Plan, mkt: Market, cfg: SimConfig) -> SimResult | None:
    """Run one plan over ``mkt.dates``. Income is booked in USD on the day it is
    earned, so the result measures the carry, not the price of the held coin."""
    dates, n = mkt.dates, len(mkt.dates)
    home = HOLDER_HOME[plan.holder]
    p_h = mkt.price(home)
    E = cfg.capital_usd
    lend = plan.lend
    lend_r = mkt.rates(lend) if lend else [0.0] * n
    if lend_r is None:
        return None
    pool_r = {x.id: mkt.rates(x) for x in plan.pool}
    pool_r = {k: v for k, v in pool_r.items() if v is not None}

    carry = plan.is_carry
    b = plan.borrow
    if carry:
        b_r, c_r = mkt.rates(b), mkt.rates(b, "collateral_rates")
        if b_r is None or c_r is None:
            return None
        p_c, p_x = mkt.price(b.collateral), mkt.price(b.asset)
        if any(math.isnan(x) for x in p_c + p_x):
            return None
        q_c = E / p_c[0]
        debt = plan.u * b.ltv * E / p_x[0]
        lent = debt
        entry = (swap_cost(home, b.collateral, E) + 2 * gas(b)
                 + transfer_cost(b, lend, debt * p_x[0])
                 + swap_cost(b.asset, lend.asset, debt * p_x[0]) + gas(lend))
        target_hf = b.lt / (plan.u * b.ltv)
        floor = min(cfg.hf_floor, 1 + (target_hf - 1) / 2)
    else:
        q = E / p_h[0]
        entry = (swap_cost(home, lend.asset, E) + gas(lend)) if lend else 0.0

    costs = liq_loss = exposure_loss = one_off_total = 0.0
    rebalances = liquidations = switches = 0
    spreads, borrows, lends, coll_yields, hfs = [], [], [], [], []
    carry_net, capital = [], []
    profit_units = 0.0
    history = [lend.venue if lend else "hold"]

    for i in range(n):
        one_off = entry if i == 0 else 0.0
        recurring = 0.0
        if plan.rotating and i >= cfg.rotation_lookback and i % cfg.rebalance_days == 0:
            lo = i - cfg.rotation_lookback
            trail = {k: sum(v[lo:i]) / cfg.rotation_lookback for k, v in pool_r.items()}
            best = max(trail, key=trail.get)
            cur = sum(lend_r[lo:i]) / cfg.rotation_lookback
            if best != lend.id and trail[best] - cur >= cfg.rotation_min_gain_pp:
                new = next(x for x in plan.pool if x.id == best)
                amount = lent * p_x[i] if carry else q * p_h[i]
                recurring += (gas(lend) + transfer_cost(lend, new, amount)
                              + swap_cost(lend.asset, new.asset, amount) + gas(new))
                lend, lend_r = new, pool_r[best]
                switches += 1
                history.append(new.venue)
        l = lend_r[i]
        lends.append(l)

        if not carry:
            value = q * p_h[i]
            income = value * l / 36500
            q *= 1 + l / 36500
            cap = value
            if lend:
                exposure_loss += (lend.p_fail + cfg.issuer_pfail.get(lend.asset, 0.0)) * cfg.lgd
        else:
            y_c, rate = c_r[i], b_r[i]
            borrows.append(rate)
            coll_yields.append(y_c)
            spreads.append(l - rate)
            income = (q_c * p_c[i] * y_c + (lent * l - debt * rate) * p_x[i]) / 36500
            q_c *= 1 + y_c / 36500
            debt *= 1 + rate / 36500
            lent *= 1 + l / 36500
            coll_usd, debt_usd = q_c * p_c[i], debt * p_x[i]
            hf = coll_usd * b.lt / debt_usd if debt_usd > 1e-9 else math.inf
            if hf < 1.0:
                # Liquidators repay half the debt (all of it below HF 0.95) and seize
                # collateral worth the repaid amount plus the liquidation bonus.
                repay = debt * (cfg.close_factor if hf >= 0.95 else 1.0)
                seize = repay * p_x[i] * (1 + b.liq_penalty)
                if seize > coll_usd:
                    seize = coll_usd
                    repay = coll_usd / (p_x[i] * (1 + b.liq_penalty))
                q_c -= seize / p_c[i]
                debt -= repay
                penalty = repay * p_x[i] * b.liq_penalty
                recurring += penalty
                liq_loss += penalty
                liquidations += 1
                coll_usd, debt_usd = q_c * p_c[i], debt * p_x[i]
                hf = coll_usd * b.lt / debt_usd if debt_usd > 1e-9 else math.inf
            if cfg.managed and coll_usd > 0:
                scheduled = i % cfg.rebalance_days == 0
                if hf < floor or scheduled:
                    target = plan.u * b.ltv * coll_usd / p_x[i]
                    excess = debt - target
                    if excess > 0 and (hf < floor or excess > cfg.rebalance_band * target):
                        paid = min(excess, lent)
                        if paid > 0:
                            lent -= paid
                            debt -= paid
                            recurring += gas(lend) + transfer_cost(lend, b, paid * p_x[i]) + gas(b)
                            rebalances += 1
                    elif scheduled and -excess > cfg.rebalance_band * target:
                        debt -= excess
                        lent -= excess
                        recurring += gas(b) + transfer_cost(b, lend, -excess * p_x[i]) + gas(lend)
                        rebalances += 1
                hf = q_c * p_c[i] * b.lt / (debt * p_x[i]) if debt > 1e-12 else math.inf
            hfs.append(hf)
            cap = q_c * p_c[i] + (lent - debt) * p_x[i]
            if cap > 0:
                at_a = max(0.0, q_c * p_c[i] - debt * p_x[i]) * b.p_fail
                at_b = lent * p_x[i] * (lend.p_fail + cfg.issuer_pfail.get(lend.asset, 0.0))
                issuer = q_c * p_c[i] * cfg.issuer_pfail.get(b.collateral, 0.0)
                exposure_loss += cfg.lgd * (at_a + at_b + issuer) / cap

        if i == n - 1:  # unwind
            if carry:
                amount = lent * p_x[i]
                one_off += (gas(lend) + transfer_cost(lend, b, amount)
                            + swap_cost(lend.asset, b.asset, amount) + 2 * gas(b)
                            + swap_cost(b.collateral, home, q_c * p_c[i]))
            elif lend:
                one_off += gas(lend) + swap_cost(lend.asset, home, q * p_h[i])
        costs += one_off + recurring
        one_off_total += one_off
        carry_net.append(income - recurring)
        capital.append(cap)
        profit_units += (income - recurring - one_off) / p_h[i]

    avg = (lambda xs: sum(xs) / len(xs) if xs else 0.0)
    avg_cap = avg(capital)
    total_profit = sum(carry_net) - one_off_total
    apy = total_profit / avg_cap * 365 / n * 100 if avg_cap > 0 else -100.0

    def worst_window(xs: list[float], caps: list[float], w: int = 30) -> float:
        if len(xs) < w:
            return 0.0
        run_x, run_c = sum(xs[:w]), sum(caps[:w])
        worst = run_x / run_c * w
        for k in range(w, len(xs)):
            run_x += xs[k] - xs[k - w]
            run_c += caps[k] - caps[k - w]
            if run_c > 0:
                worst = min(worst, run_x / run_c * w)
        return worst / w * 365 * 100

    cum, peak, mdd = 0.0, 0.0, 0.0
    for x in carry_net:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return SimResult(
        plan=plan, start=dates[0], end=dates[-1], days=n, apy=apy,
        expected_loss_apy=exposure_loss / n * 100, profit_usd=total_profit,
        profit_units=profit_units, avg_capital_usd=avg_cap, avg_borrow=avg(borrows),
        avg_lend=avg(lends), avg_collateral_yield=avg(coll_yields),
        pct_days_positive_spread=(sum(s > 0 for s in spreads) / len(spreads) * 100) if spreads else 100.0,
        worst_30d_spread=(min(sum(spreads[k:k + 30]) / 30 for k in range(len(spreads) - 29))
                          if len(spreads) >= 30 else 0.0),
        worst_30d_apy=worst_window(carry_net, capital), max_drawdown=mdd / avg_cap * 100 if avg_cap else 0.0,
        min_hf=min(hfs) if hfs else math.inf, rebalances=rebalances, liquidations=liquidations,
        liquidation_loss_usd=liq_loss, switches=switches, costs_usd=costs, lend_history=history,
    )
