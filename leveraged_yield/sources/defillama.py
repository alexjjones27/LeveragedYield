"""DefiLlama yields + protocol metadata (free endpoints)."""

from __future__ import annotations

from .http import get_json

YIELDS = "https://yields.llama.fi"
PROTOCOLS = "https://api.llama.fi/protocols"

POOL_FIELDS = (
    "chain", "project", "symbol", "tvlUsd", "apyBase", "apyReward", "apy", "apyMean30d",
    "pool", "poolMeta", "underlyingTokens", "stablecoin", "exposure", "outlier", "ilRisk",
)
NON_CHAIN_TVL_KEYS = {"borrowed", "staking", "pool2", "vesting", "offers", "treasury"}
# Pool chain names that differ from the protocol endpoint's chainTvls keys.
PROTOCOL_CHAIN_NAMES = {"OP Mainnet": "Optimism", "BSC": "Binance", "Gnosis": "xDai",
                        "Xlayer": "X Layer"}
LEND_FIELDS = (
    "pool", "apyBaseBorrow", "apyRewardBorrow", "totalSupplyUsd", "totalBorrowUsd",
    "debtCeilingUsd", "ltv", "borrowable", "mintedCoin", "underlyingTokens",
)


def fetch_pools() -> list[dict]:
    return get_json(f"{YIELDS}/pools")["data"]


def fetch_lend_borrow() -> list[dict]:
    return get_json(f"{YIELDS}/lendBorrow")


def fetch_protocols() -> dict[str, dict]:
    out = {}
    for p in get_json(PROTOCOLS):
        slug = p.get("slug")
        if not slug:
            continue
        chain_tvls = {k: v for k, v in (p.get("chainTvls") or {}).items()
                      if "-" not in k and k not in NON_CHAIN_TVL_KEYS and v}
        out[slug] = {
            "name": p.get("name"),
            "category": p.get("category"),
            "tvl": p.get("tvl") or 0.0,
            "chainTvls": chain_tvls,
            "listedAt": p.get("listedAt"),
            "audits": p.get("audits"),
        }
    return out


def fetch_pool_history(pool_id: str, reward_haircut: float = 0.0) -> dict[str, float]:
    """Daily supply APY (%) keyed by ISO date, with incentives haircut."""
    data = get_json(f"{YIELDS}/chart/{pool_id}", max_age_s=6 * 3600)["data"]
    out: dict[str, float] = {}
    for row in data:
        base, reward = row.get("apyBase"), row.get("apyReward")
        if base is None and reward is None:
            if row.get("apy") is None:
                continue
            base, reward = row["apy"], 0.0
        out[row["timestamp"][:10]] = (base or 0.0) + max(reward or 0.0, 0.0) * (1 - reward_haircut)
    return out
