"""Enumerate every (collateral, borrow route, venue, loop route) combination,
pick the best utilisation / loop count for each, and compare with the
unleveraged baseline for the same starting collateral."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import config
from .assets import family
from .config import Settings
from .model import Result, Spec, evaluate, loop_counts, tranche_schedule
from .universe import Route, Universe, Venue


@dataclass
class Baseline:
    collateral: str
    label: str
    chain: str | None
    protocol: str | None
    net_apy: float
    risk_adjusted_apy: float
    # DefiLlama pools whose APYs add up to this baseline's yield (for backtests).
    pool_ids: tuple[str, ...] = ()


@dataclass
class Outcome:
    best: Result  # utilisation / loop count chosen by the optimizer
    literal: Result  # the manual process: borrow 100% of max LTV, loop until dust
    baseline: Baseline

    @property
    def beats_baseline(self) -> bool:
        return self.best.net_apy > self.baseline.net_apy

    @property
    def beats_baseline_risk_adjusted(self) -> bool:
        return self.best.risk_adjusted_apy > self.baseline.risk_adjusted_apy


@dataclass
class OptimizationResult:
    settings: Settings
    universe: Universe
    baselines: dict[str, Baseline]
    max_raw_baselines: dict[str, Baseline]
    outcomes: list[Outcome] = field(default_factory=list)
    evaluations: int = 0

    def winners(self) -> list[Outcome]:
        """Combinations that beat the unleveraged baseline on net AND risk-adjusted APY."""
        ok = [o for o in self.outcomes if o.beats_baseline and o.beats_baseline_risk_adjusted]
        return sorted(ok, key=lambda o: o.best.risk_adjusted_apy, reverse=True)


def conversion_bps(borrowed: str, deposit: str) -> float | None:
    """Swap cost to turn the borrowed token into the venue's deposit token (None = not allowed)."""
    if borrowed == deposit:
        return 0.0
    fam = family(borrowed)
    if fam != family(deposit) or fam not in config.SWAP_COST_BPS:
        return None
    return config.SWAP_COST_BPS[fam]


def venue_yield(venue: Venue, r2: Route | None) -> float:
    y = venue.apy
    if r2 is not None and venue.receipt_market is None:
        y += r2.collateral_apy  # e.g. supply APY paid on wstETH posted to Aave
    return y


def chains_with_token(uni: Universe, token: str) -> set[str]:
    chains = {r.chain for r in uni.routes if token in (r.collateral, r.debt)}
    chains |= {v.chain for v in uni.venues if v.deposit == token}
    return chains


def compute_baselines(uni: Universe, collateral: str) -> tuple[Baseline, Baseline]:
    """Best unleveraged use of the collateral: (best risk-adjusted, best raw APY)."""
    cands = baseline_candidates(uni, collateral)
    return max(cands, key=lambda b: b.risk_adjusted_apy), max(cands, key=lambda b: b.net_apy)


def baseline_candidates(uni: Universe, collateral: str) -> list[Baseline]:
    """Every unleveraged way to stake / lend the collateral (same chain as the token)."""
    s = uni.settings
    E = s.capital_usd
    native = uni.natives.get(collateral)
    hold_apy = native.apy if native else 0.0
    hold_risk = native.p_fail * min(1.0, s.lgd) * 100 if native else 0.0
    hold_sigma = config.SPREAD_VOL_PP.get(native.category, 1.0) if native else 0.0
    cands = [Baseline(
        collateral, f"Hold {collateral}" + (f" ({native.protocol} yield)" if native else ""),
        None, native.protocol if native else None, hold_apy,
        hold_apy - hold_risk - 0.5 * s.risk_aversion * hold_sigma ** 2 / 100,
        (native.pool_id,) if native else ())]
    chains = chains_with_token(uni, collateral)
    for v in uni.venues:
        bps = conversion_bps(collateral, v.deposit)
        if bps is None or v.chain not in chains:
            continue
        keep_native = v.deposit == collateral and v.kind == "vault"
        y = v.apy + (hold_apy if keep_native else 0.0)
        one_off = (2 * bps + v.entry_bps + v.exit_bps) / 1e4 * E + 2 * s.gas_for(v.chain)
        net = y - one_off / s.holding_years / E * 100
        risk = v.p_fail * min(1.0, s.lgd) * 100
        if native and v.deposit == collateral:
            risk += hold_risk
        thin = max(1.0, math.sqrt(config.THIN_MARKET_USD / max(v.tvl_usd, 1.0)))
        ra = net - risk - 0.5 * s.risk_aversion * (v.spread_vol_pp * thin) ** 2 / 100
        pools = tuple(x for x in (v.pool_id, native.pool_id if (keep_native and native) else None)
                      if x)
        cands.append(Baseline(collateral, f"{v.label} [{v.chain}]", v.chain, v.protocol, net, ra,
                              pools))
    return cands


def optimize(uni: Universe) -> OptimizationResult:
    s = uni.settings
    E = s.capital_usd
    res = OptimizationResult(s, uni, {}, {})
    for collateral in s.collaterals:
        base, raw = compute_baselines(uni, collateral)
        res.baselines[collateral], res.max_raw_baselines[collateral] = base, raw
        native = uni.natives.get(collateral)
        r1s = [r for (chain, c), rs in uni.routes_by_collateral.items() if c == collateral
               for r in rs]
        for r1 in r1s:
            if r1.borrow_liquidity_usd < 2 * E:
                continue
            borrowed = r1.debt
            gas = s.gas_for(r1.chain)
            y_coll = r1.collateral_apy + (native.apy if native else 0.0)
            cost1 = r1.borrow_apy + uni.native_apy(borrowed)
            for v in uni.venues_by_chain.get(r1.chain, []):
                bps = conversion_bps(borrowed, v.deposit)
                if bps is None:
                    continue
                entry = (v.entry_bps + bps) / 1e4
                exit_ = (v.exit_bps + bps) / 1e4
                loop_routes: list[Route | None] = [None]
                for r2 in uni.routes_by_coll_debt.get((r1.chain, v.receipt, borrowed), []):
                    if v.receipt_market is not None and r2.market != v.receipt_market:
                        continue
                    loop_routes.append(r2)
                for r2 in loop_routes:
                    y_v = venue_yield(v, r2)
                    cost2 = cost1 if r2 is None else r2.borrow_apy + uni.native_apy(borrowed)
                    if y_v - min(cost1, cost2) - (entry + exit_) * 100 / s.holding_years <= 0:
                        continue  # negative carry: borrowing cannot help
                    liquidity = min(r1.borrow_liquidity_usd, v.tvl_usd,
                                    r2.borrow_liquidity_usd if r2 else float("inf"))
                    thin = max(1.0, math.sqrt(config.THIN_MARKET_USD / max(liquidity, 1.0)))
                    spec = Spec(
                        capital=E, collateral=collateral, r1=r1, venue=v, r2=r2,
                        y_collateral=y_coll, y_venue=y_v, borrow_cost1=cost1,
                        borrow_cost2=cost2, entry_cost=entry, exit_cost=exit_, gas_step_usd=gas,
                        collateral_issuer=native.protocol if native else None,
                        collateral_issuer_pfail=native.p_fail if native else 0.0,
                        spread_vol_pp=v.spread_vol_pp * thin)
                    best = None
                    for u in s.utilization_grid:
                        sched = tranche_schedule(spec, u, s)
                        for n in (loop_counts(len(sched)) if r2 is not None else [1]):
                            r = evaluate(spec, u, n, sched, s)
                            res.evaluations += 1
                            if (r.min_health_factor < s.min_health_factor
                                    or r.step_health_factor < s.min_step_health_factor):
                                continue
                            if best is None or r.risk_adjusted_apy > best.risk_adjusted_apy:
                                best = r
                    if best is None:
                        continue  # cannot be run at the required health factor
                    full = tranche_schedule(spec, 1.0, s)
                    literal = evaluate(spec, 1.0, len(full), full, s)
                    res.outcomes.append(Outcome(best, literal, base))
    return res


def dedupe(outcomes: list[Outcome], key=None) -> list[Outcome]:
    """Keep the best outcome per key (default: collateral, borrow route, venue)."""
    key = key or (lambda o: (o.best.spec.collateral, o.best.spec.r1.id, o.best.spec.venue.id))
    best: dict = {}
    for o in outcomes:
        k = key(o)
        if k not in best or o.best.risk_adjusted_apy > best[k].best.risk_adjusted_apy:
            best[k] = o
    return sorted(best.values(), key=lambda o: o.best.risk_adjusted_apy, reverse=True)
