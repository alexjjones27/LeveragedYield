"""Morpho Blue API: used only to fetch borrow-rate history for backtests."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from ..assets import normalize_symbol
from .http import post_graphql

MORPHO_API = "https://blue-api.morpho.org/graphql"

_FIND_QUERY = """
{ markets(first: 50, where: {chainId_in: [%d], collateralAssetAddress_in: ["%s"], listed: true}) {
    items { marketId lltv loanAsset { symbol address } state { borrowAssetsUsd netBorrowApy } } } }
"""

_HISTORY_QUERY = """
{ marketById(marketId: "%s", chainId: %d) {
    historicalState { dailyNetBorrowApy(options: {startTimestamp: %d, endTimestamp: %d,
      interval: DAY}) { x y } } } }
"""


def find_market(chain_id: int, collateral_address: str, loan_symbol: str, lltv: float,
                borrow_apy_pct: float | None = None) -> str | None:
    data = post_graphql(MORPHO_API, _FIND_QUERY % (chain_id, collateral_address))
    best, best_key = None, None
    for m in data["markets"]["items"]:
        if normalize_symbol(m["loanAsset"]["symbol"]) != normalize_symbol(loan_symbol):
            continue
        if abs(int(m["lltv"]) / 1e18 - lltv) > 1e-6:
            continue
        state = m.get("state") or {}
        # Prefer the market whose current rate matches DefiLlama, then the largest.
        rate_gap = 0.0
        if borrow_apy_pct is not None and state.get("netBorrowApy") is not None:
            rate_gap = abs(state["netBorrowApy"] * 100 - borrow_apy_pct)
        key = (round(rate_gap, 2), -(state.get("borrowAssetsUsd") or 0.0))
        if best_key is None or key < best_key:
            best, best_key = m["marketId"], key
    return best


def fetch_borrow_history(market_id: str, chain_id: int, days: int = 180) -> dict[str, float]:
    end = int(time.time())
    start = end - days * 86400
    data = post_graphql(MORPHO_API, _HISTORY_QUERY % (market_id, chain_id, start, end),
                        max_age_s=6 * 3600)
    out: dict[str, float] = {}
    for pt in data["marketById"]["historicalState"]["dailyNetBorrowApy"]:
        if pt["y"] is None:
            continue
        date = datetime.fromtimestamp(pt["x"], tz=timezone.utc).date().isoformat()
        out[date] = float(pt["y"]) * 100.0
    return out
