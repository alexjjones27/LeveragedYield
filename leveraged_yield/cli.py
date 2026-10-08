"""Command line entry point: python -m leveraged_yield [options]."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from . import backtest as bt
from .config import Settings
from .optimizer import optimize
from .report import build_markdown, diverse_top, write_csv
from .sources import snapshot
from .universe import build_universe

ROOT = Path(__file__).resolve().parents[1]


def _csv(text: str | None) -> tuple[str, ...] | None:
    if not text:
        return None
    return tuple(x.strip() for x in text.split(",") if x.strip())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    d = Settings()
    p = argparse.ArgumentParser(
        prog="python -m leveraged_yield",
        description="Find the best collateral / borrow market / borrow asset / yield venue "
                    "combination for a recursive leveraged-yield loop.")
    p.add_argument("--capital", type=float, default=d.capital_usd, help="portfolio size in USD")
    p.add_argument("--collateral", help=f"comma list (default {','.join(d.collaterals)})")
    p.add_argument("--chains", help="comma list of DefiLlama chain names (default: all)")
    p.add_argument("--refresh", action="store_true",
                   help="fetch live data and overwrite data/snapshot before optimising")
    p.add_argument("--no-backtest", action="store_true", help="skip the historical backtest")
    p.add_argument("--top", type=int, default=d.top_n, help="rows in the main table")
    p.add_argument("--holding-years", type=float, default=d.holding_years)
    p.add_argument("--yield-basis", choices=["spot", "mean30d", "min"], default=d.yield_basis)
    p.add_argument("--reward-haircut", type=float, default=d.reward_haircut)
    p.add_argument("--risk-aversion", type=float, default=d.risk_aversion)
    p.add_argument("--min-health-factor", type=float, default=d.min_health_factor)
    p.add_argument("--min-protocol-tvl", type=float, default=d.min_protocol_tvl_usd)
    p.add_argument("--min-venue-tvl", type=float, default=d.min_venue_tvl_usd)
    p.add_argument("--venue-categories", help="comma list of DefiLlama categories allowed as venues")
    p.add_argument("--exclude-protocols", help="comma list of DefiLlama project slugs to skip")
    p.add_argument("--output", default=str(ROOT / "RESULTS.md"), help="markdown report path")
    p.add_argument("--csv", default=str(ROOT / "results" / "strategies.csv"))
    return p.parse_args(argv)


def settings_from(args: argparse.Namespace) -> Settings:
    s = Settings()
    return replace(
        s,
        capital_usd=args.capital,
        collaterals=tuple(c.upper() for c in _csv(args.collateral) or s.collaterals),
        chains=_csv(args.chains),
        top_n=args.top,
        holding_years=args.holding_years,
        yield_basis=args.yield_basis,
        reward_haircut=args.reward_haircut,
        risk_aversion=args.risk_aversion,
        min_health_factor=args.min_health_factor,
        min_protocol_tvl_usd=args.min_protocol_tvl,
        min_venue_tvl_usd=args.min_venue_tvl,
        venue_categories=_csv(args.venue_categories) or s.venue_categories,
        exclude_protocols=_csv(args.exclude_protocols) or s.exclude_protocols,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = settings_from(args)

    if args.refresh or not snapshot.exists():
        print("Fetching live market data (DefiLlama + Aave v3 API)...", file=sys.stderr)
        raw = snapshot.trim(snapshot.fetch_live())
        snapshot.save(raw)
    else:
        raw = snapshot.load()

    uni = build_universe(raw, settings)
    res = optimize(uni)
    top = diverse_top(res, settings.top_n)

    backtests = {}
    if not args.no_backtest:
        print(f"Backtesting the top {settings.backtest_top} combinations...", file=sys.stderr)
        for o in top[:settings.backtest_top]:
            backtests[id(o)] = bt.safe_backtest(o, uni)

    md = build_markdown(res, backtests, top)
    Path(args.output).write_text(md + "\n")
    write_csv(res.winners(), Path(args.csv))

    print(md.split("## 2b.")[0])
    print(f"Full report: {args.output}\nAll winning combinations: {args.csv}")
    return 0
