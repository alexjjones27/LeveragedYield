"""Enumerate carry trades per holder, run full-year and walk-forward backtests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from ..assets import family
from .data import CarryData, Leg
from .sim import Market, Plan, SimConfig, SimResult, simulate

HOLDERS = ("USD", "ETH", "BTC", "SOL")


@dataclass
class HolderReport:
    holder: str
    full_carry: list[SimResult] = field(default_factory=list)
    full_base: list[SimResult] = field(default_factory=list)
    # walk-forward: chosen on the in-sample half, measured on the out-of-sample half
    is_carry: SimResult | None = None
    is_base: SimResult | None = None
    oos: dict[str, SimResult | None] = field(default_factory=dict)
    # leverage sensitivity of the best full-year carry: u -> (managed, set-and-forget)
    sensitivity: dict[float, tuple[SimResult | None, SimResult | None]] = field(default_factory=dict)


@dataclass
class CarryRun:
    data: CarryData
    cfg: SimConfig
    dates: list[str]
    split: int
    holders: dict[str, HolderReport]
    pairs: list[dict]
    venue_rates: list[dict]

    @property
    def is_dates(self) -> list[str]:
        return self.dates[: self.split]

    @property
    def oos_dates(self) -> list[str]:
        return self.dates[self.split:]


def window(data: CarryData) -> list[str]:
    end = date.fromisoformat(data.fetched_at[:10]) - timedelta(days=1)
    return [(end - timedelta(days=k)).isoformat() for k in range(data.days - 1, -1, -1)]


def same_place(a: Leg, b: Leg) -> bool:
    return (a.venue_type, a.location, a.protocol) == (b.venue_type, b.location, b.protocol)


def plans_for(holder: str, data: CarryData, mkt: Market, cfg: SimConfig) -> tuple[list[Plan], list[Plan]]:
    lends = [x for x in data.lend_legs() if mkt.usable(x)]
    carry: list[Plan] = []
    for b in data.borrow_legs():
        if b.collateral_family != holder or not mkt.usable(b):
            continue
        u = cfg.u_same_family if family(b.collateral) == b.family else cfg.u_cross_family
        for l in lends:
            if l.family != b.family or (same_place(b, l) and l.asset == b.asset):
                continue  # same venue, same coin: you would pay the spread, not earn it
            carry.append(Plan(holder, b, l, (), u))
    base = [Plan(holder, None, l) for l in lends if l.family == holder]
    if holder != "USD":
        base.append(Plan(holder, None, None))  # just hold the coin
    return carry, base


def run_all(plans: list[Plan], mkt: Market, cfg: SimConfig) -> list[SimResult]:
    out = []
    for p in plans:
        r = simulate(p, mkt, cfg)
        if r is not None:
            out.append(r)
    return sorted(out, key=lambda r: r.risk_adj_apy, reverse=True)


def pair_stats(data: CarryData, full: Market, ins: Market, oos: Market) -> list[dict]:
    """Spread statistics per (borrow venue, lend venue) independent of collateral."""
    seen, rows = set(), []
    for b in data.borrow_legs():
        key_b = (b.venue, b.location, b.asset)
        rb = full.rates(b)
        if rb is None:
            continue
        for l in data.lend_legs():
            if l.family != b.family or (same_place(b, l) and l.asset == b.asset):
                continue
            if (key_b, l.id) in seen:
                continue
            rl = full.rates(l)
            if rl is None:
                continue
            seen.add((key_b, l.id))
            s = [x - y for x, y in zip(rl, rb)]
            n = len(s)
            w = 30
            worst = min(sum(s[k:k + w]) / w for k in range(n - w + 1))
            ib, il, ob, ol = ins.rates(b), ins.rates(l), oos.rates(b), oos.rates(l)
            rows.append({
                "family": b.family, "borrow": f"{b.venue} {b.asset}", "borrow_leg": b,
                "lend": f"{l.venue} {l.asset}" + (f" [{l.location}]" if l.venue_type == "DEX" else ""),
                "lend_leg": l, "avg_borrow": sum(rb) / n, "avg_lend": sum(rl) / n,
                "avg_spread": sum(s) / n, "pct_positive": sum(x > 0 for x in s) / n * 100,
                "worst_30d": worst, "last_30d": sum(s[-30:]) / 30,
                "is_spread": (sum(il) - sum(ib)) / len(ib) if ib and il else None,
                "oos_spread": (sum(ol) - sum(ob)) / len(ob) if ob and ol else None,
            })
    return sorted(rows, key=lambda r: r["avg_spread"], reverse=True)


def venue_rates(data: CarryData, full: Market) -> list[dict]:
    rows, seen = [], set()
    for leg in data.legs:
        key = (leg.side, leg.venue, leg.location, leg.asset)
        if key in seen:
            continue
        r = full.rates(leg)
        if r is None:
            continue
        seen.add(key)
        rows.append({"side": leg.side, "venue": leg.venue, "type": leg.venue_type,
                     "location": leg.location, "asset": leg.asset, "family": leg.family,
                     "avg": sum(r) / len(r), "last_30d": sum(r[-30:]) / 30,
                     "min": min(r), "max": max(r)})
    return rows


SENSITIVITY_U = (0.3, 0.5, 0.7, 0.9)


def issuer_pfail() -> dict[str, float]:
    """Failure / depeg probabilities of yield-bearing token issuers, from the market snapshot."""
    from ..config import Settings
    from ..sources import snapshot
    from ..universe import build_universe

    if not snapshot.exists():
        return {}
    uni = build_universe(snapshot.load(), Settings())
    return {sym: n.p_fail for sym, n in uni.natives.items()}


def run(data: CarryData, cfg: SimConfig | None = None) -> CarryRun:
    cfg = cfg or SimConfig(issuer_pfail=issuer_pfail())
    dates = window(data)
    split = len(dates) // 2
    full, ins, oos = Market(data, dates), Market(data, dates[:split]), Market(data, dates[split:])
    holders: dict[str, HolderReport] = {}
    for h in HOLDERS:
        rep = HolderReport(h)
        carry, base = plans_for(h, data, full, cfg)
        rep.full_carry = run_all(carry, full, cfg)
        rep.full_base = run_all(base, full, cfg)

        # Walk-forward: pick on the first half using only first-half data.
        carry_is, base_is = plans_for(h, data, ins, cfg)
        is_carry = run_all(carry_is, ins, cfg)
        is_base = run_all(base_is, ins, cfg)
        rep.is_carry = is_carry[0] if is_carry else None
        rep.is_base = is_base[0] if is_base else None
        carry_oos, base_oos = plans_for(h, data, oos, cfg)
        oos_carry = run_all(carry_oos, oos, cfg)
        oos_base = run_all(base_oos, oos, cfg)
        o = rep.oos
        o["picked_carry"] = simulate(rep.is_carry.plan, oos, cfg) if rep.is_carry else None
        o["picked_base"] = simulate(rep.is_base.plan, oos, cfg) if rep.is_base else None
        if rep.is_carry:
            b, start = rep.is_carry.plan.borrow, rep.is_carry.plan.lend
            pool = tuple(x for x in data.lend_legs()
                         if x.family == b.family and oos.usable(x)
                         and not (same_place(b, x) and x.asset == b.asset))
            o["rotating_carry"] = simulate(Plan(h, b, start, pool, rep.is_carry.plan.u), oos, cfg)
        if rep.is_base and rep.is_base.plan.lend:
            pool = tuple(x for x in data.lend_legs() if x.family == h and oos.usable(x))
            o["rotating_base"] = simulate(Plan(h, None, rep.is_base.plan.lend, pool), oos, cfg)
        o["hindsight_carry"] = oos_carry[0] if oos_carry else None
        o["hindsight_base"] = oos_base[0] if oos_base else None
        if rep.full_carry:
            top = rep.full_carry[0].plan
            passive = replace(cfg, managed=False)
            for u in SENSITIVITY_U:
                p = replace(top, u=u)
                rep.sensitivity[u] = (simulate(p, full, cfg), simulate(p, full, passive))
        holders[h] = rep
    return CarryRun(data, cfg, dates, split, holders, pair_stats(data, full, ins, oos),
                    venue_rates(data, full))
