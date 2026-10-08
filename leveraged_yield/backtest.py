"""Replay a chosen position over the last N days of real daily rates.

Borrow-rate history comes from the Aave v3 API and the Morpho Blue API (the
two largest lenders); DefiLlama's borrow history is paywalled, so strategies
that borrow elsewhere are reported as "n/a". Supply / staking yields come from
DefiLlama pool charts. The position keeps the optimiser's tranche sizes for
the whole window (no price path, so this tests the carry, not liquidations).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from .optimizer import Baseline, Outcome
from .sources import aave, defillama, morpho
from .universe import Route, Universe


@dataclass
class BacktestResult:
    days: int
    start: str
    end: str
    realized_apy: float  # annualised, after one-off costs
    baseline_apy: float
    worst_30d_apy: float  # worst rolling 30-day average net APY
    pct_days_below_baseline: float
    final_value: float
    baseline_final_value: float
    avg_borrow_apy: float
    avg_venue_apy: float


def _series_on(series: dict[str, float], days: list[str]) -> list[float] | None:
    """Values on each day, carrying the last known value forward."""
    if not series:
        return None
    keys = sorted(series)
    out, j, last = [], 0, series[keys[0]]
    for d in days:
        while j < len(keys) and keys[j] <= d:
            last = series[keys[j]]
            j += 1
        out.append(last)
    return out


def _const(x: float, n: int) -> list[float]:
    return [x] * n


def borrow_history(route: Route, days: int) -> dict[str, float] | None:
    source = route.meta_get("source")
    try:
        if source == "aave":
            return aave.fetch_rate_history("borrow", route.meta_get("market_address"),
                                           route.meta_get("debt_address"),
                                           route.meta_get("chain_id"), days)
        if source == "morpho-blue" and route.meta_get("chain_id"):
            market_id = morpho.find_market(route.meta_get("chain_id"),
                                           route.meta_get("collateral_address"), route.debt,
                                           route.ltv, route.borrow_apy)
            if market_id:
                return morpho.fetch_borrow_history(market_id, route.meta_get("chain_id"), days)
    except RuntimeError:
        return None
    return None


def _pool_series(pool_id: str | None, haircut: float) -> dict[str, float]:
    if not pool_id:
        return {}
    try:
        return defillama.fetch_pool_history(pool_id, haircut)
    except RuntimeError:
        return {}


def _sum_series(parts: list[list[float] | None], n: int, fallback: float) -> list[float]:
    parts = [p for p in parts if p is not None]
    if not parts:
        return _const(fallback, n)
    return [sum(p[i] for p in parts) for i in range(n)]


def baseline_series(base: Baseline, days: list[str], haircut: float) -> list[float]:
    parts = [_series_on(_pool_series(pid, haircut), days) for pid in base.pool_ids]
    return _sum_series(parts, len(days), base.net_apy)


def run_backtest(outcome: Outcome, uni: Universe) -> BacktestResult | None:
    s = uni.settings
    res = outcome.best
    spec = res.spec
    r1, r2, v = spec.r1, spec.r2, spec.venue
    h = s.reward_haircut

    b1_hist = borrow_history(r1, s.backtest_days)
    if not b1_hist:
        return None
    b2_hist = None
    if r2 is not None and len(res.tranches) > 1:
        b2_hist = b1_hist if r2.id == r1.id else borrow_history(r2, s.backtest_days)
        if not b2_hist:
            return None

    end = date.fromisoformat(max(b1_hist))
    days = [(end - timedelta(days=i)).isoformat() for i in range(s.backtest_days - 1, -1, -1)]
    days = [d for d in days if d >= min(b1_hist)]
    n = len(days)
    if n < 30:
        return None

    def native_series(token: str) -> list[float] | None:
        nat = uni.natives.get(token)
        return _series_on(_pool_series(nat.pool_id, h), days) if nat else None

    # Collateral: supply APY on the borrow market + its own native yield.
    coll_pool = r1.meta_get("collateral_pool_id")
    coll_supply = (_series_on(_pool_series(coll_pool, h), days) if coll_pool
                   else _const(r1.collateral_apy, n))
    y_coll = _sum_series([coll_supply, native_series(spec.collateral)], n, spec.y_collateral)

    # Venue yield (+ native yield of a lent yield-bearing token, + supply APY paid
    # on the receipt token when it is re-posted as collateral).
    venue_parts = [_series_on(_pool_series(v.pool_id, h), days)]
    if v.kind == "lend":
        venue_parts.append(native_series(v.deposit))
    if r2 is not None and v.receipt_market is None:
        r2_pool = r2.meta_get("collateral_pool_id")
        venue_parts.append(_series_on(_pool_series(r2_pool, h), days) if r2_pool
                           else _const(r2.collateral_apy, n))
    y_venue = _sum_series(venue_parts, n, spec.y_venue)

    debt_native = native_series(r1.debt) or _const(0.0, n)
    c1 = [x + y for x, y in zip(_series_on(b1_hist, days), debt_native)]
    c2 = ([x + y for x, y in zip(_series_on(b2_hist, days), debt_native)]
          if b2_hist else _const(0.0, n))

    E = spec.capital
    d1, d2 = res.tranches[0], sum(res.tranches[1:])
    deployed = sum(res.tranches)
    one_off = deployed * (spec.entry_cost + spec.exit_cost) + spec.gas_step_usd * (2 + 2 * len(res.tranches))

    base_y = baseline_series(outcome.baseline, days, h)
    # Entry/exit costs are amortised over the holding period, as in the forward model.
    equity = E - one_off * min(1.0, n / 365 / s.holding_years)
    base_equity = E
    daily, below = [], 0
    for i in range(n):
        net = (E * y_coll[i] + deployed * y_venue[i] - d1 * c1[i] - d2 * c2[i]) / E
        daily.append(net)
        below += net < base_y[i]
        equity *= 1 + net / 100 / 365
        base_equity *= 1 + base_y[i] / 100 / 365

    window = min(30, n)
    worst = min(sum(daily[i:i + window]) / window for i in range(n - window + 1))
    years = n / 365
    return BacktestResult(
        days=n, start=days[0], end=days[-1],
        realized_apy=((equity / E) ** (1 / years) - 1) * 100,
        baseline_apy=((base_equity / E) ** (1 / years) - 1) * 100,
        worst_30d_apy=worst, pct_days_below_baseline=below / n * 100,
        final_value=equity, baseline_final_value=base_equity,
        avg_borrow_apy=sum(c1) / n, avg_venue_apy=sum(y_venue) / n,
    )


def safe_backtest(outcome: Outcome, uni: Universe) -> BacktestResult | None:
    try:
        result = run_backtest(outcome, uni)
    except (RuntimeError, KeyError, ValueError, ZeroDivisionError):
        return None
    if result is None or math.isnan(result.realized_apy):
        return None
    return result
