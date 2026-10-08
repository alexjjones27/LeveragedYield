"""Markdown and CSV output."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from .assets import family
from .backtest import BacktestResult
from .model import Result
from .optimizer import OptimizationResult, Outcome, baseline_candidates, dedupe


def pct(x: float | None, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x:.{digits}f}%"


def money(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.0f}"


def hf(x: float) -> str:
    return "∞" if math.isinf(x) else f"{x:.2f}"


def chain_short(chain: str) -> str:
    return {"OP Mainnet": "Optimism", "Hyperliquid L1": "HyperEVM"}.get(chain, chain)


def loop_text(r: Result) -> str:
    if r.spec.r2 is None:
        return f"{r.leverage:.2f}x, single borrow @ {r.utilization:.0%} of max LTV"
    return f"{r.leverage:.2f}x, {r.loops} loops @ {r.utilization:.0%} of max LTV"


def loop_market(r: Result) -> str:
    s = r.spec
    if s.r2 is None:
        return "not re-posted (single borrow)"
    if s.same_account:
        return "same account"
    return f"{s.r2.market_label} ({s.r2.debt} {s.r2.borrow_apy:.2f}%)"


def buffer_text(r: Result) -> str:
    parts = []
    for a in r.accounts:
        if a.debt <= 0:
            continue
        if a.directional_buffer is not None and a.directional_buffer < 1:
            parts.append(f"{a.directional_buffer:.0%} price")
        if a.depeg_buffer is not None and a.depeg_buffer < 1:
            parts.append(f"{a.depeg_buffer:.1%} depeg")
    return ", ".join(parts) if parts else "none (same token)"


def strategy_text(r: Result) -> str:
    s = r.spec
    text = (f"Post {s.collateral} on {s.r1.market_label} ({chain_short(s.r1.chain)}), "
            f"borrow {s.r1.debt}, {s.venue.label}")
    if s.r2 is not None:
        text += (", re-post and loop" if s.same_account
                 else f", loop on {s.r2.market_label}")
    return text


def short_label(r: Result) -> str:
    s = r.spec
    lender = s.r1.market_label.split(" [E-mode")[0].split(" (")[0]
    return f"{s.collateral} on {lender} ({chain_short(s.r1.chain)}) / {s.r1.debt} / {s.venue.protocol}"


def row(o: Outcome) -> dict:
    r, s = o.best, o.best.spec
    lit = o.literal
    return {
        "collateral": s.collateral,
        "chain": s.r1.chain,
        "borrow_market": s.r1.market_label,
        "borrow_asset": s.r1.debt,
        "borrow_apy": round(s.r1.borrow_apy, 3),
        "borrow_cost_apy": round(s.borrow_cost1, 3),
        "collateral_yield_apy": round(s.y_collateral, 3),
        "venue": s.venue.label,
        "venue_protocol": s.venue.protocol,
        "venue_category": s.venue.category,
        "venue_yield_apy": round(s.y_venue, 3),
        "loop_market": loop_market(r),
        "loop_borrow_cost_apy": round(s.borrow_cost2, 3) if s.r2 else "",
        "utilization_of_max_ltv": round(r.utilization, 2),
        "loops": r.loops,
        "leverage": round(r.leverage, 3),
        "debt_usd": round(r.debt, 2),
        "net_apy": round(r.net_apy, 3),
        "annual_profit_usd": round(r.annual_profit_usd(), 2),
        "baseline": o.baseline.label,
        "baseline_apy": round(o.baseline.net_apy, 3),
        "excess_vs_baseline_pp": round(r.net_apy - o.baseline.net_apy, 3),
        "risk_adjusted_apy": round(r.risk_adjusted_apy, 3),
        "baseline_risk_adjusted_apy": round(o.baseline.risk_adjusted_apy, 3),
        "stress_apy_spread_minus_2pp": round(r.stress_apy, 3),
        "p5_apy": round(r.p5_apy, 3),
        "health_factor": round(r.min_health_factor, 3) if not math.isinf(r.min_health_factor) else "",
        "step_health_factor": round(r.step_health_factor, 3),
        "liquidation_buffer": buffer_text(r),
        "p_liquidation_1y": round(r.p_liquidation, 4),
        "liq_loss_apy": round(r.liq_loss_apy, 3),
        "protocol_loss_apy": round(r.protocol_loss_apy, 3),
        "spread_risk_apy": round(r.spread_risk_apy, 3),
        "cost_apy": round(r.cost_apy, 3),
        "manual_loops": lit.loops,
        "manual_leverage": round(lit.leverage, 3),
        "manual_health_factor": round(lit.min_health_factor, 3) if not math.isinf(lit.min_health_factor) else "",
        "manual_net_apy": round(lit.net_apy, 3),
        "manual_risk_adjusted_apy": round(lit.risk_adjusted_apy, 3),
    }


def write_csv(outcomes: list[Outcome], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [row(o) for o in outcomes]
    with path.open("w", newline="") as fh:
        if not rows:
            fh.write("")
            return
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def diverse_top(res: OptimizationResult, n: int) -> list[Outcome]:
    """Top-n winners, keeping the best one per (collateral, lender market, borrowed-asset
    family, venue category) so the table is not twenty near-identical rows."""
    key = (lambda o: (o.best.spec.collateral, o.best.spec.r1.chain,
                      o.best.spec.r1.market_label.split(" [E-mode")[0],
                      family(o.best.spec.r1.debt), o.best.spec.venue.category))
    return dedupe(res.winners(), key)[:n]


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows]
    return "\n".join(out)


def build_markdown(res: OptimizationResult, backtests: dict[int, BacktestResult | None],
                   top: list[Outcome]) -> str:
    s, uni = res.settings, res.universe
    E = s.capital_usd
    lines: list[str] = []
    add = lines.append
    add(f"# Leveraged yield optimizer: results for a {money(E)} portfolio\n")
    add(f"Market data snapshot: **{uni.fetched_at}** (DefiLlama yields + lend/borrow, Aave v3 API "
        f"for exact LTV / liquidation thresholds / E-mode). Universe after quality filters: "
        f"{len(uni.routes):,} borrow routes and {len(uni.venues):,} lend/stake venues; "
        f"{res.evaluations:,} position sizes evaluated.\n")
    add(f"Yields use the lower of spot and 30-day average APY; reward-token incentives count at "
        f"{1 - s.reward_haircut:.0%}. Borrow costs include the staking yield of the borrowed "
        f"token when it is yield-bearing. Every optimised position keeps a health factor of at "
        f"least {s.min_health_factor:.2f} (and {s.min_step_health_factor:.2f} between loops).\n")

    # ---------------------------------------------------------------- summary
    winners = res.winners()
    add("## 1. Best combination per starting collateral\n")
    rows = []
    for c in s.collaterals:
        base = res.baselines[c]
        mine = [o for o in winners if o.best.spec.collateral == c]
        if mine:
            o = mine[0]
            r = o.best
            rows.append([c, base.label, pct(base.net_apy), strategy_text(r), loop_text(r),
                         pct(r.net_apy), pct(r.risk_adjusted_apy),
                         money(r.annual_profit_usd()), money(base.net_apy / 100 * E),
                         f"+{r.net_apy - base.net_apy:.2f} pp"])
        else:
            rows.append([c, base.label, pct(base.net_apy),
                         "None beats the baseline after risk: stay unlevered", "-", "-", "-", "-",
                         money(base.net_apy / 100 * E), "-"])
    add(_table(["Collateral", "Best unlevered option (baseline)", "Baseline APY",
                "Best levered combination", "Leverage", "Net APY", "Risk-adj. APY",
                f"Profit/yr on {money(E)}", "Baseline profit/yr", "Lift"], rows))
    add("")

    # ---------------------------------------------------------------- top list
    add(f"## 2. Top {len(top)} combinations (all beat their unlevered baseline)\n")
    add("Ranked by risk-adjusted APY. One row per collateral / lender / borrowed-asset type / "
        "venue type (the best variant of each); every variant is in `results/strategies.csv`.\n")
    add("### 2a. What to do\n")
    rows = []
    for i, o in enumerate(top, 1):
        r, sp = o.best, o.best.spec
        rows.append([i, sp.collateral, chain_short(sp.r1.chain), sp.r1.market_label,
                     f"{sp.r1.debt} ({sp.borrow_cost1:.2f}%)", f"{sp.venue.label} ({sp.y_venue:.2f}%)",
                     loop_market(r), f"{r.utilization:.0%}", r.loops, f"{r.leverage:.2f}x"])
    add(_table(["#", "Collateral", "Chain", "Borrow on", "Borrow (cost)", "Stake / lend on (yield)",
                "Loop collateral on", "LTV used", "Loops", "Leverage"], rows))
    add("\n### 2b. Returns and downside\n")
    rows = []
    for i, o in enumerate(top, 1):
        r = o.best
        rows.append([i, pct(r.net_apy), money(r.annual_profit_usd()), pct(o.baseline.net_apy),
                     f"+{r.net_apy - o.baseline.net_apy:.2f} pp", pct(r.risk_adjusted_apy),
                     pct(r.stress_apy), pct(r.p5_apy), hf(r.min_health_factor), buffer_text(r),
                     f"{r.p_liquidation:.1%}"])
    add(_table(["#", "Net APY", f"Profit/yr on {money(E)}", "Baseline APY", "Lift",
                "Risk-adj. APY", "Stress APY (spread -2pp)", "Bad-year APY (5th pct)",
                "Health factor", "Move to liquidation", "P(liquidation, 1y)"], rows))
    add("")

    # ---------------------------------------------------------------- literal
    add("## 3. Your manual process vs the optimised version\n")
    add("\"Manual\" = borrow the full max LTV every time and keep looping until the next borrow "
        "is dust or no longer covers its gas. \"Optimised\" = the LTV share and loop count the "
        "optimiser picked for the best risk-adjusted return.\n")
    rows = []
    for i, o in enumerate(top[:10], 1):
        lit, r = o.literal, o.best
        rows.append([i, short_label(r), lit.loops, f"{lit.leverage:.2f}x", hf(lit.min_health_factor),
                     pct(lit.net_apy), pct(lit.risk_adjusted_apy),
                     f"{r.utilization:.0%}", r.loops, f"{r.leverage:.2f}x",
                     hf(r.min_health_factor), pct(r.net_apy), pct(r.risk_adjusted_apy)])
    add(_table(["#", "Collateral on lender / borrow / venue", "Manual loops", "Manual leverage", "Manual HF",
                "Manual net APY", "Manual risk-adj.", "Opt. LTV used", "Opt. loops",
                "Opt. leverage", "Opt. HF", "Opt. net APY", "Opt. risk-adj."], rows))
    add("")

    # ---------------------------------------------------------------- backtest
    add(f"## 4. Backtest: last {s.backtest_days} days of real daily rates\n")
    add("Each position is held at the tranche sizes above while borrow and supply rates follow "
        "their actual daily history (Aave v3 and Morpho borrow history; DefiLlama supply / "
        "staking history). Rows that borrow on other lenders show n/a (no free borrow history).\n")
    rows = []
    for i, o in enumerate(top, 1):
        bt = backtests.get(id(o))
        if i > s.backtest_top:
            break
        label = short_label(o.best)
        if bt is None:
            rows.append([i, label, "n/a (no free borrow-rate history for this lender)",
                         "", "", "", "", "", "", ""])
            continue
        rows.append([i, label, f"{bt.start} to {bt.end}", pct(bt.realized_apy), pct(bt.baseline_apy),
                     "yes" if bt.realized_apy > bt.baseline_apy else "**no**",
                     pct(bt.worst_30d_apy), f"{bt.pct_days_below_baseline:.0f}%",
                     money(bt.final_value), money(bt.baseline_final_value)])
    add(_table(["#", "Collateral on lender / borrow / venue", "Window", "Realised APY", "Baseline realised",
                "Beat baseline?", "Worst 30-day APY", "Days below baseline", f"{money(E)} became",
                "Baseline became"], rows))
    done = [b for b in backtests.values() if b is not None]
    if done:
        wins = sum(b.realized_apy > b.baseline_apy for b in done)
        add(f"\n{wins} of {len(done)} backtested combinations beat their baseline over the "
            "window. Forward-looking APYs assume today's rates persist; the backtest shows how "
            "often they did not.")
    add("")

    # ---------------------------------------------------------------- raw max
    add("## 5. Highest raw net APY, ignoring risk (for contrast)\n")
    raw = sorted(dedupe([o for o in res.outcomes if o.beats_baseline]),
                 key=lambda o: o.best.net_apy, reverse=True)[:10]
    rows = []
    for i, o in enumerate(raw, 1):
        r = o.best
        rows.append([i, strategy_text(r), loop_text(r), pct(r.net_apy), pct(r.risk_adjusted_apy),
                     pct(o.baseline.risk_adjusted_apy), hf(r.min_health_factor),
                     "yes" if o.beats_baseline_risk_adjusted else "no"])
    add(_table(["#", "Combination", "Leverage", "Net APY", "Risk-adj. APY",
                "Baseline risk-adj.", "HF", "Still wins after risk?"], rows))
    add("")

    # ---------------------------------------------------------------- unlevered
    add("## 6. Unlevered options per collateral (top 3 by risk-adjusted APY)\n")
    rows = []
    for c in s.collaterals:
        cands = sorted(baseline_candidates(uni, c), key=lambda b: b.risk_adjusted_apy, reverse=True)
        for b in cands[:3]:
            rows.append([c, b.label, pct(b.net_apy), pct(b.risk_adjusted_apy)])
    add(_table(["Collateral", "Option", "Net APY", "Risk-adj. APY"], rows))
    add("")
    add(assumptions_section(res))
    return "\n".join(lines)


def assumptions_section(res: OptimizationResult) -> str:
    s = res.settings
    return "\n".join([
        "## How to read this / key assumptions\n",
        "- **Net APY** = yield on your collateral + yield on everything you borrowed and deployed "
        "- borrow cost - swap, exit and gas costs (amortised over "
        f"{s.holding_years:g} year), as a % of your {money(s.capital_usd)}.",
        "- **Baseline** = the best way to just lend / stake the same collateral with no borrowing "
        "(best risk-adjusted option from the same venue universe, same chain as the token).",
        "- **Risk-adj. APY** = net APY minus expected annual losses from (a) liquidation: the "
        f"chance a price or depeg move hits your liquidation level within {s.horizon_years:g} "
        "year times the liquidation penalty, (b) protocol failure of every protocol in the stack "
        f"(base rate by category, scaled by TVL and age, {s.lgd:.0%} loss given failure), and "
        f"(c) a mean-variance charge (risk aversion {s.risk_aversion:g}) for the borrow/yield "
        "spread moving against you, which grows with leverage and in thin markets.",
        f"- **Stress APY** = net APY if the carry spread compresses by {s.stress_spread_pp:g} "
        "percentage points (e.g. ETH borrow rates spike). **Bad-year APY** = 5th percentile of "
        "that spread distribution.",
        "- **Move to liquidation**: *price* = how far your collateral must fall against the "
        "borrowed asset (different assets, e.g. ETH vs USD); *depeg* = how far a same-family "
        "token (wstETH vs ETH, USDC vs AUSD) must slip.",
        f"- Positions are capped at health factor {s.min_health_factor:.2f} after looping and "
        f"{s.min_step_health_factor:.2f} at any moment while looping. Non-Aave liquidation "
        "thresholds are estimated (LTV + 3pp; Morpho LLTV exact).",
        f"- Universe: protocols with TVL >= {money(s.min_protocol_tvl_usd)}, venues with TVL >= "
        f"{money(s.min_venue_tvl_usd)} in categories {', '.join(s.venue_categories)}; "
        f"excluded: {', '.join(s.exclude_protocols)}. Everything stays on one chain (no bridging).",
        "- Rates move. These are a snapshot; rerun `python -m leveraged_yield --refresh` before "
        "acting, and size positions so a few bad weeks of negative carry are survivable.",
        "",
    ])
