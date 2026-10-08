"""Build borrow and lend "legs" with a year of daily rates across CEXs and DEXs.

A *borrow leg* is one way to borrow an asset: venue, debt token, the collateral
you post, its LTV / liquidation threshold, the daily borrow APR and the daily
yield the posted collateral earns. A *lend leg* is one place to deposit a token
and its daily APR (net of venue fees). Every series is ``{ISO date: APR %}``.
"""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..assets import family, normalize_symbol
from ..backtest import borrow_history
from ..config import Settings
from ..sources import aave, defillama
from ..sources import snapshot as market_snapshot
from ..sources.http import post_graphql
from ..universe import Universe, build_universe, morpho_liq_penalty
from . import sources

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "carry" / "rates_snapshot.json.gz"

DEFI_CHAINS = ("Ethereum", "Arbitrum", "Base")
DEBT_TOKENS = ("USDC", "USDT", "WETH", "WBTC", "CBBTC", "SOL")
COLLATERAL_TOKENS = ("USDC", "USDT", "WSTETH", "WETH", "WBTC", "CBBTC", "SOL", "JITOSOL", "BTC")

# Annual probability of losing funds held at a centralised venue (insolvency,
# hack, freeze). Judgement calls, like the DeFi ones in config.py.
CEX_PFAIL = {"okx": 0.010, "bitfinex": 0.015, "gate": 0.020}

# OKX multi-currency margin, approximated: max borrow LTV and liquidation LTV.
# Borrowed funds can be withdrawn (OKX reports them in maxWdEx).
OKX_STABLE_COLLATERAL = (0.75, 0.90)
OKX_CRYPTO_COLLATERAL = (0.70, 0.85)
OKX_ASSETS = {"USDT": "USDT", "USDC": "USDC", "ETH": "WETH", "BTC": "BTC", "SOL": "SOL"}
BITFINEX_ASSETS = {"UST": "USDT", "USD": "USD", "ETH": "WETH", "BTC": "BTC", "SOL": "SOL"}
GATE_ASSETS = {"USDT": "USDT", "USDC": "USDC", "ETH": "WETH", "BTC": "BTC", "SOL": "SOL"}

KAMINO_MAIN = "7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF"
MORPHO_API = "https://blue-api.morpho.org/graphql"
MORPHO_CHAINS = {1: "Ethereum", 8453: "Base", 42161: "Arbitrum"}
MORPHO_QUERY = """{ markets(first: 200, orderBy: BorrowAssetsUsd, orderDirection: Desc,
  where: {chainId_in: [1, 8453, 42161], listed: true, borrowAssetsUsd_gte: %d}) {
  items { marketId lltv chain { id } loanAsset { symbol address } collateralAsset { symbol address }
    state { borrowAssetsUsd liquidityAssetsUsd netBorrowApy } } } }"""


@dataclass
class Leg:
    id: str
    side: str  # borrow | lend
    venue: str  # display name
    protocol: str  # risk bucket, e.g. okx, aave-v3, lido
    venue_type: str  # CEX | DEX
    location: str  # CEX name, or chain for DEX legs
    asset: str  # token borrowed / deposited
    rates: dict[str, float]
    p_fail: float
    category: str = ""
    collateral: str | None = None
    ltv: float = 0.0
    lt: float = 0.0
    liq_penalty: float = 0.05
    collateral_rates: dict[str, float] = field(default_factory=dict)

    @property
    def family(self) -> str:
        return family(self.asset)

    @property
    def collateral_family(self) -> str | None:
        return family(self.collateral) if self.collateral else None


@dataclass
class CarryData:
    legs: list[Leg]
    prices: dict[str, dict[str, float]]  # family -> {date: USD}
    fetched_at: str
    days: int

    def borrow_legs(self) -> list[Leg]:
        return [x for x in self.legs if x.side == "borrow"]

    def lend_legs(self) -> list[Leg]:
        return [x for x in self.legs if x.side == "lend"]


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _add(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    if not b:
        return dict(a)
    if not a:
        return dict(b)
    keys = sorted(set(a) | set(b))
    out, la, lb = {}, None, None
    for k in keys:
        la = a.get(k, la)
        lb = b.get(k, lb)
        out[k] = (la or 0.0) + (lb or 0.0)
    return out


def _native(uni: Universe, token: str, haircut: float) -> dict[str, float]:
    n = uni.natives.get(token)
    if not n:
        return {}
    try:
        return defillama.fetch_pool_history(n.pool_id, haircut)
    except RuntimeError:
        return {}


# --------------------------------------------------------------------------- CEX

def cex_legs(days: int) -> list[Leg]:
    legs: list[Leg] = []
    okx_borrow: dict[str, dict[str, float]] = {}
    for ccy, sym in OKX_ASSETS.items():
        _log(f"  OKX {ccy}")
        borrow, lend = sources.okx_rates(ccy, days)
        okx_borrow[sym] = borrow
        legs.append(Leg(f"okx-lend-{sym}", "lend", "OKX Simple Earn", "okx", "CEX", "OKX", sym,
                        lend, CEX_PFAIL["okx"], "CEX lending"))
    for debt, series in okx_borrow.items():
        for coll in OKX_ASSETS.values():
            if coll == debt:
                continue  # posting and borrowing the same coin on OKX just nets out
            ltv, lt = OKX_STABLE_COLLATERAL if family(coll) == "USD" else OKX_CRYPTO_COLLATERAL
            legs.append(Leg(f"okx-borrow-{debt}-vs-{coll}", "borrow", "OKX margin", "okx", "CEX",
                            "OKX", debt, series, CEX_PFAIL["okx"], "CEX margin", collateral=coll,
                            ltv=ltv, lt=lt, liq_penalty=0.03))
    for sym, token in BITFINEX_ASSETS.items():
        _log(f"  Bitfinex {sym}")
        legs.append(Leg(f"bitfinex-lend-{token}", "lend", "Bitfinex funding", "bitfinex", "CEX",
                        "Bitfinex", token, sources.bitfinex_lend(sym, days),
                        CEX_PFAIL["bitfinex"], "CEX lending"))
    for asset, token in GATE_ASSETS.items():
        _log(f"  Gate {asset}")
        legs.append(Leg(f"gate-lend-{token}", "lend", "Gate Uni lending", "gate", "CEX", "Gate",
                        token, sources.gate_lend(asset, days), CEX_PFAIL["gate"], "CEX lending"))
    return legs


# --------------------------------------------------------------------------- DeFi borrow

def aave_borrow_legs(uni: Universe, days: int, haircut: float) -> list[Leg]:
    legs: list[Leg] = []
    supply_cache: dict[tuple, dict[str, float]] = {}
    for r in uni.routes:
        if r.protocol != "aave-v3" or r.emode is not None or r.chain not in DEFI_CHAINS:
            continue
        if r.market_label != f"Aave v3 {r.chain}":  # main market only
            continue
        if r.collateral not in COLLATERAL_TOKENS or r.debt not in DEBT_TOKENS:
            continue
        _log(f"  Aave {r.chain} {r.collateral}->{r.debt}")
        borrow = borrow_history(r, days)
        if not borrow:
            continue
        key = (r.meta_get("market_address"), r.meta_get("collateral_address"), r.chain)
        if key not in supply_cache:
            try:
                supply_cache[key] = aave.fetch_rate_history(
                    "supply", key[0], key[1], r.meta_get("chain_id"), days)
            except RuntimeError:
                supply_cache[key] = {}
        coll = _add(supply_cache[key], _native(uni, r.collateral, haircut))
        legs.append(Leg(f"aave-{r.chain}-{r.collateral}-{r.debt}", "borrow", f"Aave v3 {r.chain}",
                        "aave-v3", "DEX", r.chain, r.debt, borrow, r.p_fail, "Lending",
                        collateral=r.collateral, ltv=r.ltv, lt=r.lt, liq_penalty=r.liq_penalty,
                        collateral_rates=coll))
    return legs


def morpho_borrow_legs(uni: Universe, days: int, min_borrow_usd: float = 20e6) -> list[Leg]:
    from ..sources.morpho import fetch_borrow_history

    data = post_graphql(MORPHO_API, MORPHO_QUERY % int(min_borrow_usd))
    pfail = {r.chain: r.p_fail for r in uni.routes if r.protocol == "morpho-blue"}
    legs: list[Leg] = []
    for m in data["markets"]["items"]:
        chain = MORPHO_CHAINS.get(m["chain"]["id"])
        if not chain or not m.get("collateralAsset"):
            continue
        coll = normalize_symbol(m["collateralAsset"]["symbol"])
        debt = normalize_symbol(m["loanAsset"]["symbol"])
        if coll not in COLLATERAL_TOKENS + ("WEETH",) or debt not in DEBT_TOKENS:
            continue
        if (m["state"].get("liquidityAssetsUsd") or 0) < 1e6:
            continue
        lltv = int(m["lltv"]) / 1e18
        _log(f"  Morpho {chain} {coll}->{debt} {lltv:.3f}")
        try:
            borrow = fetch_borrow_history(m["marketId"], m["chain"]["id"], days)
        except RuntimeError:
            continue
        if not borrow:
            continue
        legs.append(Leg(f"morpho-{chain}-{m['marketId'][:10]}", "borrow",
                        f"Morpho {coll}/{debt} {lltv:.1%} ({chain})", "morpho-blue", "DEX", chain,
                        debt, borrow, pfail.get(chain, 0.006), "Lending", collateral=coll,
                        ltv=lltv, lt=lltv, liq_penalty=morpho_liq_penalty(lltv),
                        collateral_rates=_native(uni, coll, 0.5)))
    return legs


def kamino_legs(uni: Universe, days: int, haircut: float) -> list[Leg]:
    """Kamino main market (Solana): supply legs plus borrow legs for each collateral."""
    wanted = {"USDC", "USDT", "SOL", "JITOSOL"}
    reserves = {}
    for r in sources.kamino_reserves(KAMINO_MAIN):
        sym = normalize_symbol(r["liquidityToken"])
        if sym in wanted and float(r.get("totalSupplyUsd") or 0) > 5e6:
            cur = reserves.get(sym)
            if cur is None or float(r["totalSupplyUsd"]) > float(cur["totalSupplyUsd"]):
                reserves[sym] = r
    hist = {}
    for sym, r in reserves.items():
        _log(f"  Kamino {sym}")
        rows = sources.kamino_history(KAMINO_MAIN, r["reserve"], days)
        if not rows:
            continue
        borrow, supply = {}, {}
        for row in rows:
            m = row["metrics"]
            day = row["timestamp"][:10]
            borrow[day] = (float(m["borrowInterestAPY"]) - float(m.get("borrowRewardsApy") or 0)
                           * (1 - haircut)) * 100
            supply[day] = (float(m["supplyInterestAPY"]) + float(m.get("supplyRewardsApy") or 0)
                           * (1 - haircut)) * 100
        last = rows[-1]["metrics"]
        hist[sym] = dict(borrow=borrow, supply=supply, ltv=float(last["loanToValue"]),
                         lt=float(last["liquidationThreshold"]),
                         borrow_factor=float(last.get("borrowFactor") or 100) / 100,
                         penalty=(float(last["minLiquidationBonus"])
                                  + float(last["maxLiquidationBonus"])) / 2)
    pfail = next((v.p_fail for v in uni.venues if v.protocol == "kamino-lend"), 0.008)
    legs: list[Leg] = []
    for sym, h in hist.items():
        legs.append(Leg(f"kamino-lend-{sym}", "lend", "Kamino (Solana)", "kamino-lend", "DEX",
                        "Solana", sym, _add(h["supply"], _native(uni, sym, haircut)), pfail,
                        "Lending"))
    for debt in ("USDC", "USDT", "SOL"):
        if debt not in hist:
            continue
        for coll, c in hist.items():
            if coll == debt or c["ltv"] <= 0:
                continue
            bf = hist[debt]["borrow_factor"]
            legs.append(Leg(f"kamino-{coll}-{debt}", "borrow", "Kamino (Solana)", "kamino-lend",
                            "DEX", "Solana", debt, hist[debt]["borrow"], pfail, "Lending",
                            collateral=coll, ltv=c["ltv"] / bf, lt=c["lt"] / bf,
                            liq_penalty=c["penalty"],
                            collateral_rates=_add(c["supply"], _native(uni, coll, haircut))))
    return legs


# --------------------------------------------------------------------------- DeFi lend

def defi_lend_legs(uni: Universe, haircut: float, min_tvl: float) -> list[Leg]:
    legs: list[Leg] = []
    for v in uni.venues:
        if v.chain not in DEFI_CHAINS or v.protocol == "kamino-lend":
            continue
        if v.kind not in ("lend", "vault", "stake") or v.tvl_usd < min_tvl or not v.pool_id:
            continue
        if family(v.deposit) not in ("USD", "ETH", "BTC", "SOL"):
            continue
        _log(f"  DefiLlama {v.label} [{v.chain}]")
        try:
            series = defillama.fetch_pool_history(v.pool_id, haircut)
        except RuntimeError:
            continue
        if v.kind in ("lend", "vault"):
            series = _add(series, _native(uni, v.deposit, haircut))
        legs.append(Leg(f"defi-{v.pool_id}", "lend", v.label, v.protocol, "DEX", v.chain,
                        v.deposit, series, v.p_fail, v.category))
    return legs


# --------------------------------------------------------------------------- entry points

def fetch(days: int = 365, min_lend_tvl: float = 100e6) -> CarryData:
    settings = Settings()
    raw = market_snapshot.load() if market_snapshot.exists() else market_snapshot.fetch_live()
    uni = build_universe(raw, settings)
    h = settings.reward_haircut
    _log("Fetching CEX rate history (OKX, Bitfinex, Gate)...")
    legs = cex_legs(days)
    _log("Fetching DeFi rate history (Aave, Morpho, Kamino, DefiLlama)...")
    legs += aave_borrow_legs(uni, days, h)
    legs += morpho_borrow_legs(uni, days)
    legs += kamino_legs(uni, days, h)
    legs += defi_lend_legs(uni, h, min_lend_tvl)
    px = sources.prices(["ethereum", "bitcoin", "solana"], days)
    prices = {"ETH": px["ethereum"], "BTC": px["bitcoin"], "SOL": px["solana"]}
    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return CarryData([x for x in legs if x.rates], prices, fetched, days)


def save(data: CarryData, path: Path = SNAPSHOT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": data.fetched_at, "days": data.days, "prices": data.prices,
               "legs": [asdict(x) for x in data.legs]}
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), sort_keys=True)
    return path


def load(path: Path = SNAPSHOT) -> CarryData:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    return CarryData([Leg(**x) for x in payload["legs"]], payload["prices"],
                     payload["fetched_at"], payload["days"])
