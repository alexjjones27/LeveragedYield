"""CARRY_RESULTS.md and CSV output for the carry backtest."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from ..report import money, pct
from .run import HOLDERS, CarryRun
from .sim import SimResult

HOLDER_LABEL = {"USD": "Stablecoins (USDC)", "ETH": "ETH", "BTC": "BTC", "SOL": "SOL"}


def _table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows]
    return "\n".join(out)


def hf(x: float) -> str:
    return "n/a" if math.isinf(x) else f"{x:.2f}"


def leg_text(leg) -> str:
    where = "" if leg.venue_type == "CEX" or leg.location in leg.venue else f" [{leg.location}]"
    return f"{leg.venue}{where}"


def lend_text(leg) -> str:
    if leg is None:
        return "hold"
    label = leg_text(leg)
    return label if leg.asset in label.upper() else f"{label} {leg.asset}"


def borrow_text(r: SimResult) -> str:
    b = r.plan.borrow
    return f"{b.collateral} on {leg_text(b)}, borrow {b.asset}"


def strategy_row(r: SimResult, base: SimResult | None) -> list:
    p = r.plan
    lift = f"{r.apy - base.apy:+.2f} pp" if base else ""
    if p.is_carry:
        what, lev = borrow_text(r), f"{p.u:.0%} of {p.borrow.ltv:.0%}"
        rates = f"{r.avg_collateral_yield:.2f}% / {r.avg_borrow:.2f}% / {r.avg_lend:.2f}%"
    else:
        what, lev, rates = "no borrowing (baseline)", "-", f"- / - / {r.avg_lend:.2f}%"
    return [what, lend_text(p.lend), lev, rates, pct(r.apy), money(r.profit_usd), lift,
            pct(r.risk_adj_apy), pct(r.worst_30d_apy), hf(r.min_hf), r.rebalances,
            r.liquidations]


def build_markdown(run: CarryRun) -> str:
    cfg, data = run.cfg, run.data
    E = cfg.capital_usd
    L: list[str] = []
    add = L.append
    cex = sorted({x.venue for x in data.legs if x.venue_type == "CEX"})
    dex = sorted({x.protocol for x in data.legs if x.venue_type == "DEX"})
    add("# Crypto carry trade backtest: borrow cheap, lend rich, across CEXs and DEXs\n")
    add(f"Window **{run.dates[0]} to {run.dates[-1]}** ({len(run.dates)} days of daily rates; "
        f"data pulled {data.fetched_at}). Walk-forward split: choose on {run.dates[0]} to "
        f"{run.dates[run.split - 1]}, test on {run.dates[run.split]} to {run.dates[-1]}. "
        f"Portfolio size {money(E)}.\n")
    add(f"Venues: CEX {', '.join(cex)}; DeFi {', '.join(dex)} "
        f"({len(data.borrow_legs())} borrow and {len(data.lend_legs())} lend rate series). "
        "Over the window ETH fell ~47%, BTC ~35% and SOL ~54%, so collateral management "
        "was tested hard.\n")

    # ------------------------------------------------------------- 1. headline
    add("## 1. Headline: does the carry beat simply lending your coins?\n")
    rows = []
    for h in HOLDERS:
        rep = run.holders[h]
        if not rep.full_base:
            continue
        base = rep.full_base[0]
        best = rep.full_carry[0] if rep.full_carry else None
        oc, ob = rep.oos.get("picked_carry"), rep.oos.get("picked_base")
        rows.append([
            HOLDER_LABEL[h], f"{lend_text(base.plan.lend)}: {pct(base.apy)}",
            (f"{borrow_text(best)} -> {lend_text(best.plan.lend)}: {pct(best.apy)}"
             if best else "-"),
            f"{best.apy - base.apy:+.2f} pp" if best else "-",
            pct(oc.apy) if oc else "n/a", pct(ob.apy) if ob else "n/a",
            ("**carry**" if oc and ob and oc.risk_adj_apy > ob.risk_adj_apy else "lend only")])
    add(_table(["You hold", "Best plain lend / stake (full year)", "Best carry trade (full year)",
                "Carry lift", "Carry, out-of-sample", "Lend, out-of-sample",
                "Winner out-of-sample (risk-adjusted)"], rows))
    add("\nFull-year columns are picked with hindsight; the out-of-sample columns pick on the "
        "first half and are scored only on the second half, which is what you could actually "
        "have earned.\n")

    # ------------------------------------------------------------- 2. pure spreads
    add(f"## 2. The spreads themselves: borrow here, lend there (per {money(E)} borrowed)\n")
    add("Spread = lend APR - borrow APR on the same coin (or a 1:1 stablecoin swap). This is the "
        "carry on the *borrowed* money only, before the cost of the collateral you must post. "
        "One row per borrow venue / lend venue, best five per asset.\n")
    rows = []
    for fam in ("USD", "ETH", "BTC", "SOL"):
        seen = set()
        for p in [x for x in run.pairs if x["family"] == fam]:
            key = (p["borrow"], p["lend"])
            if key in seen:
                continue
            seen.add(key)
            rows.append([fam, p["borrow"], pct(p["avg_borrow"]), p["lend"], pct(p["avg_lend"]),
                         f"**{p['avg_spread']:+.2f} pp**", f"{p['pct_positive']:.0f}%",
                         f"{p['worst_30d']:+.2f} pp", f"{p['is_spread']:+.2f} / {p['oos_spread']:+.2f}",
                         money(p["avg_spread"] / 100 * E)])
            if len(seen) == 5:
                break
    add(_table(["Asset", "Borrow at", "Avg borrow", "Lend at", "Avg lend", "Avg spread",
                "Days positive", "Worst 30 days", "1st half / 2nd half",
                f"$/yr per {money(E)} borrowed"], rows))
    add("")

    # ------------------------------------------------------------- 3. holders
    add(f"## 3. Running it with {money(E)}: best five carry trades per starting coin (full year)\n")
    add("The borrowed amount is limited by your collateral: `LTV used` is the share of the max "
        "LTV borrowed (50% when collateral and debt are different coins, 80% when they move "
        "together), re-sized weekly and cut early if the health factor drops. APY = net income / "
        "average capital, after gas, withdrawal, bridge and swap costs and liquidation penalties. "
        "Rates column: collateral yield / borrow / lend.\n")
    headers = ["Collateral & borrow", "Lend at", "LTV used", "Rates (avg)", "Net APY",
               f"Profit on {money(E)}", "vs best plain lend", "Risk-adj. APY",
               "Worst 30 days", "Min HF", "Rebalances", "Liquidations"]
    for h in HOLDERS:
        rep = run.holders[h]
        if not rep.full_base:
            continue
        base = rep.full_base[0]
        add(f"### {HOLDER_LABEL[h]}\n")
        rows = [strategy_row(base, None)]
        seen = set()
        for r in rep.full_carry:
            key = (r.plan.borrow.venue, r.plan.borrow.asset, r.plan.lend.venue, r.plan.lend.location)
            if key in seen:
                continue
            seen.add(key)
            rows.append(strategy_row(r, base))
            if len(seen) == 5:
                break
        add(_table(headers, rows))
        idle = [r for r in rep.full_carry if r.plan.borrow.venue_type == "CEX"]
        if idle:
            r = idle[0]
            add(f"\nCollateral already sitting idle on OKX (e.g. trading margin): the best "
                f"overlay is {borrow_text(r)} -> {lend_text(r.plan.lend)}: "
                f"**{pct(r.apy)}** ({money(r.profit_usd)} on {money(E)}) instead of 0%.")
        add("")

    # ------------------------------------------------------------- 4. walk-forward
    add("## 4. Walk-forward test (no hindsight)\n")
    add(f"Strategies are chosen on the first half ({run.dates[0]} to {run.dates[run.split - 1]}) "
        f"and run on the second half only. *Rotating* re-checks every {cfg.rebalance_days} days "
        f"and moves the lent funds to whichever venue paid the most over the previous "
        f"{cfg.rotation_lookback} days (if it is {cfg.rotation_min_gain_pp} pp better), paying "
        "the transfer costs. *Hindsight* is the best possible pick, for reference only.\n")
    labels = [("picked_base", "Plain lend, picked on 1st half"),
              ("rotating_base", "Plain lend, rotating"),
              ("picked_carry", "Carry, picked on 1st half"),
              ("rotating_carry", "Carry, rotating lend venue"),
              ("hindsight_base", "Plain lend, hindsight best"),
              ("hindsight_carry", "Carry, hindsight best")]
    rows = []
    for h in HOLDERS:
        rep = run.holders[h]
        for key, label in labels:
            r = rep.oos.get(key)
            if r is None:
                continue
            what = (f"{borrow_text(r)} -> " if r.plan.is_carry else "") + (
                "rotating: " + " -> ".join(dict.fromkeys(r.lend_history)) if r.plan.rotating
                else lend_text(r.plan.lend))
            rows.append([HOLDER_LABEL[h], label, what, pct(r.apy), money(r.profit_usd),
                         pct(r.risk_adj_apy), r.switches, r.liquidations])
    add(_table(["You hold", "Strategy", "Positions", "Net APY", "Profit (half year)",
                "Risk-adj. APY", "Venue switches", "Liquidations"], rows))
    add("")

    # ------------------------------------------------------------- 5. leverage
    add("## 5. Leverage and babysitting: managed vs set-and-forget\n")
    add("The best full-year carry for each coin, at different shares of max LTV. *Managed* = "
        "weekly re-sizing plus an emergency deleverage if the health factor falls halfway to 1. "
        "*Set-and-forget* = never touch it after opening.\n")
    rows = []
    for h in HOLDERS:
        rep = run.holders[h]
        for u, (m, s) in rep.sensitivity.items():
            if m is None or s is None:
                continue
            rows.append([HOLDER_LABEL[h], f"{u:.0%}", pct(m.apy), hf(m.min_hf), m.liquidations,
                         pct(s.apy), hf(s.min_hf), s.liquidations, money(s.liquidation_loss_usd)])
    add(_table(["You hold", "LTV used", "Managed APY", "Managed min HF", "Managed liquidations",
                "Set-and-forget APY", "Set-and-forget min HF", "Set-and-forget liquidations",
                "Liquidation penalties paid"], rows))
    add("")

    # ------------------------------------------------------------- 6. venue rates
    add("## 6. Average rates by venue over the year\n")
    for fam in ("USD", "ETH", "BTC", "SOL"):
        rows = []
        for side in ("borrow", "lend"):
            vs = sorted([v for v in run.venue_rates if v["family"] == fam and v["side"] == side],
                        key=lambda v: v["avg"], reverse=(side == "lend"))
            for v in vs[:6]:
                where = v["location"] if v["type"] == "DEX" else "CEX"
                rows.append([side, v["venue"], v["asset"], where, pct(v["avg"]),
                             pct(v["last_30d"]), f"{v['min']:.2f}% to {v['max']:.2f}%"])
        add(f"**{fam}** (cheapest six borrow venues, richest six lend venues)\n")
        add(_table(["Side", "Venue", "Coin", "Where", "1-year avg", "Last 30 days", "Daily range"],
                   rows))
        add("")

    # ------------------------------------------------------------- method
    add("## How this works and what it assumes\n")
    add("\n".join([
        "- **Data.** OKX: public Simple Earn lending history (`rate` = what margin borrowers "
        "pay, which matches OKX's published VIP0 borrow rate; `lendingRate` = what lenders "
        "receive). Bitfinex: daily funding candles (2-30 day offers), midpoint of open/close, "
        "minus Bitfinex's 15% lender fee. Gate: Uni lending APR. Aave v3 (Ethereum, Arbitrum, "
        "Base) and Morpho: official APIs. Kamino: its public API. Other DeFi lend venues "
        "(Maple, Sky, Ethena, Spark, Fluid, Morpho vaults, liquid staking): DefiLlama daily "
        "history, reward tokens counted at 50%. Prices: DefiLlama.",
        "- **Not covered:** Binance and Bybit block API access from this environment; KuCoin "
        "only publishes 7 days; Compound's API was unreachable. Bitfinex and Gate are lend-only "
        "here (Bitfinex margin loans cannot be withdrawn).",
        "- **Mechanics.** Collateral earns what the borrow venue pays on it (Aave supply APY, "
        "Kamino supply APY) plus its own staking yield (wstETH, JitoSOL); collateral on OKX and "
        "Morpho earns nothing. OKX margin is approximated as 75% max LTV / 90% liquidation LTV "
        "for stablecoin collateral and 70% / 85% for BTC, ETH and SOL. Liquidation repays 50% "
        "of the debt (100% below HF 0.95) and charges the venue's penalty.",
        "- **Costs.** Gas $1.50 per action on Ethereum, $0.05 on L2s, $0.01 on Solana; CEX "
        "withdrawal $1 (stablecoins), $1.50 (ETH), $5 (BTC), $0.10 (SOL); bridges $1 + 3 bps; "
        "swaps 3 bps (stables), 5 bps (ETH, SOL), 10 bps (BTC), 10 bps USDT->fiat USD on "
        "Bitfinex.",
        f"- **Risk-adj. APY** subtracts expected losses from venue failures: annual failure "
        f"probability (OKX 1%, Bitfinex 1.5%, Gate 2%; DeFi from the protocol risk model) x "
        f"{cfg.lgd:.0%} loss x the money sitting there, plus issuer risk on staked tokens.",
        "- **Caveats.** Venue list is today's large venues (survivorship bias). CEX rates are "
        "the advertised market rate; your fill may differ. Borrow caps, withdrawal limits and "
        "KYC are not modelled. Past spreads are not future spreads. Not financial advice.",
    ]))
    add("")
    return "\n".join(L)


def write_csvs(run: CarryRun, directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pairs_path = directory / "carry_pairs.csv"
    with pairs_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["asset", "borrow", "lend", "avg_borrow_apr", "avg_lend_apr", "avg_spread_pp",
                    "pct_days_positive", "worst_30d_spread_pp", "last_30d_spread_pp",
                    "first_half_spread_pp", "second_half_spread_pp"])
        for p in run.pairs:
            w.writerow([p["family"], p["borrow"], p["lend"], round(p["avg_borrow"], 3),
                        round(p["avg_lend"], 3), round(p["avg_spread"], 3),
                        round(p["pct_positive"], 1), round(p["worst_30d"], 3),
                        round(p["last_30d"], 3),
                        None if p["is_spread"] is None else round(p["is_spread"], 3),
                        None if p["oos_spread"] is None else round(p["oos_spread"], 3)])
    strat_path = directory / "carry_strategies.csv"
    with strat_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["holder", "collateral", "borrow_venue", "borrow_location", "borrow_asset",
                    "ltv_used", "lend_venue", "lend_location", "lend_asset", "net_apy",
                    "risk_adj_apy", "profit_usd", "avg_collateral_yield", "avg_borrow",
                    "avg_lend", "pct_days_positive_spread", "worst_30d_apy", "min_hf",
                    "rebalances", "liquidations", "costs_usd"])
        for h in HOLDERS:
            rep = run.holders[h]
            for r in rep.full_base + rep.full_carry:
                b, lend = r.plan.borrow, r.plan.lend
                w.writerow([h, b.collateral if b else "", b.venue if b else "",
                            b.location if b else "", b.asset if b else "",
                            round(r.plan.u * b.ltv, 3) if b else 0,
                            lend.venue if lend else "hold", lend.location if lend else "",
                            lend.asset if lend else "", round(r.apy, 3),
                            round(r.risk_adj_apy, 3), round(r.profit_usd, 2),
                            round(r.avg_collateral_yield, 3), round(r.avg_borrow, 3),
                            round(r.avg_lend, 3), round(r.pct_days_positive_spread, 1),
                            round(r.worst_30d_apy, 3),
                            "" if math.isinf(r.min_hf) else round(r.min_hf, 3),
                            r.rebalances, r.liquidations, round(r.costs_usd, 2)])
    return [pairs_path, strat_path]
