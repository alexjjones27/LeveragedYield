"""Aave v3 official API: exact risk parameters, E-mode categories, rate history."""

from __future__ import annotations

from datetime import datetime, timezone

from .http import post_graphql

AAVE_API = "https://api.v3.aave.com/graphql"

# DefiLlama chain name -> EVM chain id (also used for Morpho).
CHAIN_IDS = {
    "Ethereum": 1, "Arbitrum": 42161, "Avalanche": 43114, "Base": 8453, "BSC": 56,
    "Celo": 42220, "Gnosis": 100, "Linea": 59144, "Metis": 1088, "OP Mainnet": 10,
    "Polygon": 137, "Scroll": 534352, "Soneium": 1868, "Sonic": 146, "zkSync Era": 324,
    "Plasma": 9745, "Ink": 57073, "Mantle": 5000, "MegaETH": 4326, "Xlayer": 196,
    "Monad": 143, "Unichain": 130, "Katana": 747474, "Hyperliquid L1": 999,
    "World Chain": 480, "Corn": 21000000, "Hemi": 43111, "Lisk": 1135, "Fraxtal": 252,
}
CHAIN_NAMES = {v: k for k, v in CHAIN_IDS.items()}

_MARKETS_QUERY = """
{ markets(request: {chainIds: [%s]}) {
    name address chain { chainId name }
    eModeCategories { id label maxLTV { value } liquidationThreshold { value }
      liquidationPenalty { value }
      reserves { underlyingToken { symbol address } canBeCollateral canBeBorrowed hasLtvZero } }
    reserves { underlyingToken { symbol address } isFrozen isPaused
      size { usd }
      supplyInfo { apy { value } maxLTV { value } liquidationThreshold { value }
        liquidationBonus { value } canBeCollateral supplyCapReached }
      borrowInfo { apy { value } borrowingState borrowCapReached availableLiquidity { usd } } }
} }
"""

_HISTORY_QUERY = """
{ %s(request: {market: "%s", underlyingToken: "%s", window: %s, chainId: %d}) {
    avgRate { value } date } }
"""


def fetch_markets(chain_ids: list[int] | None = None) -> list[dict]:
    ids = chain_ids or sorted(set(CHAIN_IDS.values()))
    markets: list[dict] = []
    # Ask in small batches: unknown chain ids make the whole request fail.
    for cid in ids:
        try:
            data = post_graphql(AAVE_API, _MARKETS_QUERY % cid)
        except RuntimeError:
            continue
        markets.extend(data.get("markets") or [])
    return markets


def fetch_rate_history(kind: str, market: str, token: str, chain_id: int,
                       days: int = 180) -> dict[str, float]:
    """Daily average borrow/supply APY (%) keyed by ISO date. kind: borrow|supply."""
    window = "LAST_SIX_MONTHS" if days <= 180 else "LAST_YEAR"
    field = "borrowAPYHistory" if kind == "borrow" else "supplyAPYHistory"
    data = post_graphql(AAVE_API, _HISTORY_QUERY % (field, market, token, window, chain_id),
                        max_age_s=6 * 3600)
    out: dict[str, float] = {}
    for row in data.get(field) or []:
        date = datetime.fromisoformat(row["date"]).astimezone(timezone.utc).date().isoformat()
        out[date] = float(row["avgRate"]["value"]) * 100.0
    return out
