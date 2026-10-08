"""python -m leveraged_yield.carry [--refresh] [--capital 10000] [--days 365]"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from . import data
from .report import build_markdown, write_csvs
from .run import issuer_pfail, run
from .sim import SimConfig

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m leveraged_yield.carry",
                                description="Backtest borrow-cheap / lend-rich carry trades "
                                            "across CEXs and DEXs.")
    p.add_argument("--refresh", action="store_true", help="re-download a year of rate history")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--u-cross", type=float, default=SimConfig.u_cross_family,
                   help="share of max LTV when collateral and debt are different coins")
    p.add_argument("--u-same", type=float, default=SimConfig.u_same_family,
                   help="share of max LTV when collateral and debt move together")
    p.add_argument("--output", default=str(ROOT / "CARRY_RESULTS.md"))
    args = p.parse_args(argv)

    if args.refresh or not data.SNAPSHOT.exists():
        print("Downloading rate history (a few minutes the first time)...", file=sys.stderr)
        data.save(data.fetch(args.days))
    snap = data.load()
    cfg = replace(SimConfig(issuer_pfail=issuer_pfail()), capital_usd=args.capital,
                  u_cross_family=args.u_cross, u_same_family=args.u_same)
    result = run(snap, cfg)
    md = build_markdown(result)
    Path(args.output).write_text(md + "\n")
    paths = write_csvs(result, ROOT / "results")
    print(md.split("## 3.")[0])
    print(f"Full report: {args.output}\nCSV: {', '.join(str(x) for x in paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
