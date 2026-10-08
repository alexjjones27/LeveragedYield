"""Raw market data bundle: fetch live, or save/load a trimmed, reproducible snapshot."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import aave, defillama

SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "data" / "snapshot"


@dataclass
class RawData:
    pools: list[dict]
    lend_borrow: list[dict]
    protocols: dict[str, dict]
    aave_markets: list[dict]
    fetched_at: str


def fetch_live() -> RawData:
    pools = defillama.fetch_pools()
    lend_borrow = defillama.fetch_lend_borrow()
    protocols = defillama.fetch_protocols()
    aave_markets = aave.fetch_markets()
    return RawData(pools, lend_borrow, protocols, aave_markets,
                   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def trim(raw: RawData, min_pool_tvl: float = 1e6) -> RawData:
    """Keep only what the optimizer reads, so the snapshot is small enough to commit."""
    lending_ids = {x["pool"] for x in raw.lend_borrow}
    pools = [
        {k: p.get(k) for k in defillama.POOL_FIELDS}
        for p in raw.pools
        if p["pool"] in lending_ids
        or (p.get("exposure") == "single" and (p.get("tvlUsd") or 0) >= min_pool_tvl)
    ]
    kept = {p["pool"] for p in pools}
    lend_borrow = [{k: x.get(k) for k in defillama.LEND_FIELDS}
                   for x in raw.lend_borrow if x["pool"] in kept]
    projects = {p["project"] for p in pools}
    protocols = {k: v for k, v in raw.protocols.items() if k in projects}
    return RawData(pools, lend_borrow, protocols, raw.aave_markets, raw.fetched_at)


def save(raw: RawData, directory: Path = SNAPSHOT_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "market_snapshot.json.gz"
    payload = {
        "fetched_at": raw.fetched_at,
        "pools": raw.pools,
        "lend_borrow": raw.lend_borrow,
        "protocols": raw.protocols,
        "aave_markets": raw.aave_markets,
    }
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), sort_keys=True)
    return path


def load(directory: Path = SNAPSHOT_DIR) -> RawData:
    path = directory / "market_snapshot.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    return RawData(payload["pools"], payload["lend_borrow"], payload["protocols"],
                   payload["aave_markets"], payload["fetched_at"])


def exists(directory: Path = SNAPSHOT_DIR) -> bool:
    return (directory / "market_snapshot.json.gz").exists()
