"""Turn raw market data into borrow routes, yield venues and native token yields.

Vocabulary
----------
Route   one way to borrow: post COLLATERAL on a lending market, borrow DEBT.
        Routes that share an ``account`` share one health factor (same Aave
        E-mode account, same Morpho market, ...).
Venue   one place to put a borrowed token to work: lend it, stake it into a
        yield-bearing token (stETH, sUSDe, JitoSOL ...) or deposit it in a
        vault. If the venue's receipt token is itself accepted as collateral
        the position can be looped.
Native  the intrinsic yield of a yield-bearing token (e.g. wstETH accrues
        Lido staking yield wherever it sits).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import config
from .assets import NATIVE_EVM, NATIVE_SOL, family, native_symbol, normalize_symbol
from .config import Settings
from .sources.aave import CHAIN_IDS, CHAIN_NAMES
from .sources.defillama import PROTOCOL_CHAIN_NAMES
from .sources.snapshot import RawData

# DefiLlama projects whose borrow pools are (collateral, poolMeta "COLL/DEBT") vault pairs.
VAULT_PAIR_PROJECTS = {"jupiter-lend"}
# Isolated pair markets where the reported LTV is already the liquidation LTV.
LT_EQUALS_LTV_PROJECTS = {"morpho-blue", "curve-llamalend", "crvusd", "liquity-v1", "liquity-v2",
                          "sky-lending", "lista-cdp", "felix-cdp", "frankencoin", "fraxlend",
                          "inverse-finance-firm", "resupply", "asymmetry-usdaf", "kava-mint"}
# Categories whose tokens can be bought on other chains and still earn the native yield.
TOKEN_YIELD_CATEGORIES = {"Liquid Staking", "Liquid Restaking", "Basis Trading", "CDP", "Yield",
                          "RWA", "Restaked BTC"}
CLEAN_SYMBOL = re.compile(r"^[A-Z0-9.+]+$")


@dataclass(frozen=True)
class Route:
    id: str
    protocol: str
    chain: str
    market: str
    market_label: str
    account: str
    collateral: str
    debt: str
    ltv: float
    lt: float
    liq_penalty: float
    borrow_apy: float
    collateral_apy: float
    borrow_liquidity_usd: float
    p_fail: float
    emode: str | None = None
    meta: tuple = ()

    def meta_get(self, key, default=None):
        return dict(self.meta).get(key, default)


@dataclass(frozen=True)
class NativeYield:
    symbol: str
    apy: float
    protocol: str
    category: str
    pool_id: str
    tvl_usd: float
    underlying: str
    chain: str
    p_fail: float


@dataclass(frozen=True)
class Venue:
    id: str
    protocol: str
    category: str
    chain: str
    label: str
    deposit: str
    receipt: str
    receipt_market: str | None
    apy: float
    tvl_usd: float
    entry_bps: float
    exit_bps: float
    pool_id: str | None
    kind: str  # lend | stake | token | vault
    p_fail: float
    spread_vol_pp: float


@dataclass
class Universe:
    routes: list[Route]
    venues: list[Venue]
    natives: dict[str, NativeYield]
    protocols: dict[str, dict]
    fetched_at: str
    settings: Settings
    routes_by_collateral: dict = field(default_factory=dict)
    routes_by_coll_debt: dict = field(default_factory=dict)
    venues_by_chain: dict = field(default_factory=dict)

    def index(self) -> "Universe":
        self.routes_by_collateral = defaultdict(list)
        self.routes_by_coll_debt = defaultdict(list)
        self.venues_by_chain = defaultdict(list)
        for r in self.routes:
            self.routes_by_collateral[(r.chain, r.collateral)].append(r)
            self.routes_by_coll_debt[(r.chain, r.collateral, r.debt)].append(r)
        for v in self.venues:
            self.venues_by_chain[v.chain].append(v)
        return self

    def native_apy(self, symbol: str) -> float:
        n = self.natives.get(symbol)
        return n.apy if n else 0.0


# --------------------------------------------------------------------------- helpers

def pool_apy(pool: dict, basis: str, reward_haircut: float = 0.0) -> float | None:
    """Supply APY (%) of a DefiLlama pool on the chosen basis, haircutting incentives."""
    base, reward = pool.get("apyBase"), pool.get("apyReward")
    if base is None and reward is None:
        if pool.get("apy") is None:
            return None
        base, reward = pool["apy"], 0.0
    reward = max(reward or 0.0, 0.0)
    cut = reward * reward_haircut
    spot = (base or 0.0) + reward - cut
    mean = pool.get("apyMean30d")
    if basis == "spot" or mean is None:
        return float(spot)
    mean = float(mean) - cut  # assume the incentive was similar over the window
    if basis == "mean30d":
        return mean
    return float(min(spot, mean))


def borrow_apy(lb: dict, reward_haircut: float = 0.0) -> float | None:
    """Borrow APY (%) net of (haircut) borrower incentives."""
    if lb.get("apyBaseBorrow") is None:
        return None
    reward = max(lb.get("apyRewardBorrow") or 0.0, 0.0)
    return lb["apyBaseBorrow"] - reward * (1.0 - reward_haircut)


def tvl_multiplier(tvl: float) -> float:
    for threshold, mult in config.TVL_RISK_MULTIPLIER:
        if tvl >= threshold:
            return mult
    return config.TVL_RISK_MULTIPLIER[-1][1]


def age_multiplier(listed_at: float | None, now: float) -> float:
    if not listed_at:
        return 1.0  # DefiLlama omits the listing date for its oldest protocols
    years = (now - float(listed_at)) / (365.25 * 86400)
    if years < 1:
        return 1.5
    if years < 2:
        return 1.2
    return 1.0


def morpho_liq_penalty(lltv: float) -> float:
    # Morpho Blue liquidation incentive factor: min(1.15, 1 / (0.3 * LLTV + 0.7)).
    return min(1.15, 1.0 / (0.3 * lltv + 0.7)) - 1.0


class _Ctx:
    """Shared lookups while building the universe."""

    def __init__(self, raw: RawData, settings: Settings):
        self.raw = raw
        self.settings = settings
        self.now = datetime.strptime(raw.fetched_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
        self.pools = {p["pool"]: p for p in raw.pools}
        self.lend = {x["pool"]: x for x in raw.lend_borrow if x["pool"] in self.pools}
        self.registry, self.registry_any = self._token_registry()

    def _token_registry(self):
        per_chain: dict[tuple, Counter] = defaultdict(Counter)
        anywhere: dict[str, Counter] = defaultdict(Counter)
        for pid in self.lend:
            p = self.pools[pid]
            und = p.get("underlyingTokens") or []
            sym = normalize_symbol(p["symbol"])
            if len(und) == 1 and und[0] and CLEAN_SYMBOL.match(sym):
                addr = und[0].lower()
                per_chain[(p["chain"], addr)][sym] += 1
                anywhere[addr][sym] += 1
        reg = {k: c.most_common(1)[0][0] for k, c in per_chain.items()}
        reg_any = {k: c.most_common(1)[0][0] for k, c in anywhere.items()}
        reg_any[NATIVE_SOL] = "SOL"
        return reg, reg_any

    def token_symbol(self, chain: str, address: str | None) -> str | None:
        if not address:
            return None
        a = address.lower()
        if a == NATIVE_EVM:
            return native_symbol(chain)
        return self.registry.get((chain, a)) or self.registry_any.get(a)

    def category(self, project: str) -> str:
        return (self.raw.protocols.get(project) or {}).get("category") or "Unknown"

    def protocol_pfail(self, project: str, category: str | None = None,
                       tvl: float | None = None, chain: str | None = None) -> float:
        """Annual loss-event probability. With ``chain`` the size of that chain's
        deployment is used (a small Aave deployment on a new chain is riskier than
        Aave on Ethereum); otherwise ``tvl`` or the protocol's total TVL."""
        meta = self.raw.protocols.get(project) or {}
        cat = category or meta.get("category") or "Unknown"
        base = config.PROTOCOL_BASE_PFAIL.get(cat, config.DEFAULT_PROTOCOL_BASE_PFAIL)
        t = tvl if tvl is not None else (meta.get("tvl") or 0.0)
        if tvl is None and chain is not None:
            chain_tvls = meta.get("chainTvls") or {}
            key = PROTOCOL_CHAIN_NAMES.get(chain, chain)
            if key in chain_tvls:
                t = chain_tvls[key]
        return base * tvl_multiplier(t) * age_multiplier(meta.get("listedAt"), self.now)

    def excluded(self, project: str) -> bool:
        s = self.settings
        tvl = (self.raw.protocols.get(project) or {}).get("tvl") or 0.0
        return (project in s.exclude_protocols or self.category(project) in s.exclude_categories
                or tvl < s.min_protocol_tvl_usd)

    def chain_ok(self, chain: str) -> bool:
        return not self.settings.chains or chain in self.settings.chains


# --------------------------------------------------------------------------- natives

def _receipt_symbol(p: dict) -> str:
    meta = (p.get("poolMeta") or "").upper()
    if p["project"] == "maple" and meta.startswith("SYRUP "):
        return normalize_symbol("SYRUP" + meta.split(" ", 1)[1].replace(" ", ""))
    return normalize_symbol(p["symbol"])


def _deposit_symbol(ctx: _Ctx, p: dict) -> str | None:
    syms = [ctx.token_symbol(p["chain"], a) for a in (p.get("underlyingTokens") or [])]
    syms = [s for s in syms if s]
    if not syms:
        return None
    for preferred in ("WETH", "SOL"):
        if preferred in syms:
            return preferred
    return syms[0]


def build_natives(ctx: _Ctx) -> dict[str, NativeYield]:
    out: dict[str, NativeYield] = {}
    for p in ctx.raw.pools:
        if p["pool"] in ctx.lend or p.get("exposure") != "single" or p.get("outlier"):
            continue
        if (p.get("tvlUsd") or 0) < 20e6:
            continue
        cat = ctx.category(p["project"])
        if cat not in TOKEN_YIELD_CATEGORIES and p["project"] != "maple":
            continue
        receipt, deposit = _receipt_symbol(p), _deposit_symbol(ctx, p)
        if not deposit or not CLEAN_SYMBOL.match(receipt) or receipt == deposit:
            continue
        if family(receipt) != family(deposit):
            continue
        apy = pool_apy(p, ctx.settings.yield_basis, ctx.settings.reward_haircut)
        if apy is None or apy <= 0 or apy > ctx.settings.max_apy:
            continue
        cur = out.get(receipt)
        if cur is None or p["tvlUsd"] > cur.tvl_usd:
            out[receipt] = NativeYield(
                symbol=receipt, apy=apy, protocol=p["project"], category=cat, pool_id=p["pool"],
                tvl_usd=p["tvlUsd"], underlying=deposit, chain=p["chain"],
                p_fail=ctx.protocol_pfail(p["project"], tvl=p["tvlUsd"]))
    return out


# --------------------------------------------------------------------------- Aave

def _aave_market_for(chain: str, pool_meta: str | None, markets: list[dict]) -> dict | None:
    if not markets:
        return None
    meta = (pool_meta or "").lower()
    if "prime" in meta or "lido" in meta:
        key = "lido"
    elif "horizon" in meta:
        key = "horizon"
    elif "etherfi" in meta or "ether.fi" in meta:
        key = "etherfi"
    else:
        key = None
    if key:
        for m in markets:
            if key in m["name"].lower():
                return m
        return None
    plain = [m for m in markets if not any(k in m["name"].lower()
                                           for k in ("lido", "horizon", "etherfi"))]
    return max(plain or markets, key=lambda m: len(m["reserves"]))


def _f(x) -> float:
    return float(x["value"]) if isinstance(x, dict) else float(x)


def build_aave_routes(ctx: _Ctx) -> tuple[list[Route], set[str], dict[str, str]]:
    """Routes for every Aave v3 market from the official API (exact LTV/LT/E-mode).

    Returns routes, the set of chains covered, and DefiLlama pool id -> market key.
    """
    s = ctx.settings
    routes: list[Route] = []
    by_chain: dict[str, list[dict]] = defaultdict(list)
    for m in ctx.raw.aave_markets:
        chain = CHAIN_NAMES.get(m["chain"]["chainId"])
        if chain:
            by_chain[chain].append(m)

    # DefiLlama rates (include incentives) keyed by (market name, token address).
    dl_rates: dict[tuple, tuple[dict, dict]] = {}
    pool_market: dict[str, str] = {}
    for pid, lb in ctx.lend.items():
        p = ctx.pools[pid]
        if p["project"] != "aave-v3" or p["chain"] not in by_chain:
            continue
        m = _aave_market_for(p["chain"], p.get("poolMeta"), by_chain[p["chain"]])
        und = p.get("underlyingTokens") or []
        if m is None or len(und) != 1:
            continue
        dl_rates[(m["name"], und[0].lower())] = (p, lb)
        pool_market[pid] = f"aave-v3|{p['chain']}|{m['name']}"

    for chain, markets in by_chain.items():
        if not ctx.chain_ok(chain) or ctx.excluded("aave-v3"):
            continue
        pfail = ctx.protocol_pfail("aave-v3", chain=chain)
        for m in markets:
            market_key = f"aave-v3|{chain}|{m['name']}"
            reserves = {}
            for r in m["reserves"]:
                addr = r["underlyingToken"]["address"].lower()
                sym = normalize_symbol(r["underlyingToken"]["symbol"])
                dl = dl_rates.get((m["name"], addr))
                sup, bor = r["supplyInfo"], r.get("borrowInfo")
                if dl:
                    p, lb = dl
                    supply_apy = pool_apy(p, s.yield_basis, s.reward_haircut) or 0.0
                    b_apy = borrow_apy(lb, s.reward_haircut)
                    liquidity = p.get("tvlUsd") or 0.0
                    supply_usd = lb.get("totalSupplyUsd") or 0.0
                else:
                    supply_apy = _f(sup["apy"]) * 100
                    b_apy = _f(bor["apy"]) * 100 if bor else None
                    liquidity = float(bor["availableLiquidity"]["usd"]) if bor else 0.0
                    supply_usd = float((r.get("size") or {}).get("usd") or 0.0)
                active = not r["isFrozen"] and not r["isPaused"]
                bonus = _f(sup["liquidationBonus"])
                reserves[addr] = dict(
                    sym=sym, addr=addr, supply_apy=supply_apy, borrow_apy=b_apy,
                    liquidity=liquidity, supply_usd=supply_usd,
                    ltv=_f(sup["maxLTV"]), lt=_f(sup["liquidationThreshold"]),
                    penalty=bonus - 1.0 if bonus > 1 else bonus,
                    collateral_ok=active and sup["canBeCollateral"] and not sup["supplyCapReached"],
                    borrow_ok=active and bor is not None and bor["borrowingState"] == "ENABLED"
                    and not bor["borrowCapReached"] and b_apy is not None,
                    pool_id=dl[0]["pool"] if dl else None,
                )

            modes = [(0, None, None)]
            for e in m.get("eModeCategories") or []:
                modes.append((e["id"], e["label"], e))
            for eid, label, e in modes:
                coll_params, borrowable = {}, set()
                if e is None:
                    for a, rv in reserves.items():
                        if rv["collateral_ok"] and rv["ltv"] > 0:
                            coll_params[a] = (rv["ltv"], rv["lt"], rv["penalty"])
                        if rv["borrow_ok"]:
                            borrowable.add(a)
                else:
                    in_cat = {x["underlyingToken"]["address"].lower(): x for x in e["reserves"]}
                    for a, rv in reserves.items():
                        x = in_cat.get(a)
                        if rv["collateral_ok"]:
                            if x and x["canBeCollateral"] and not x["hasLtvZero"]:
                                pen = _f(e["liquidationPenalty"])
                                coll_params[a] = (_f(e["maxLTV"]), _f(e["liquidationThreshold"]),
                                                  pen - 1.0 if pen > 1 else pen)
                            elif not (x and x["hasLtvZero"]) and rv["ltv"] > 0:
                                coll_params[a] = (rv["ltv"], rv["lt"], rv["penalty"])
                        if x and x["canBeBorrowed"] and rv["borrow_ok"]:
                            borrowable.add(a)
                    # E-mode accounts only matter if some collateral gets boosted params.
                    if not any(a in in_cat and in_cat[a]["canBeCollateral"] for a in coll_params):
                        continue
                account = f"{market_key}|e{eid}"
                for ca, (ltv, lt, pen) in coll_params.items():
                    c = reserves[ca]
                    for ba in borrowable:
                        b = reserves[ba]
                        if b["liquidity"] < s.min_borrow_liquidity_usd:
                            continue
                        if b["supply_usd"] < s.min_market_supply_usd:
                            continue
                        name = m["name"].replace("AaveV3", "")
                        routes.append(Route(
                            id=f"{account}|{c['sym']}->{b['sym']}",
                            protocol="aave-v3", chain=chain, market=market_key,
                            market_label=f"Aave v3 {name}" + (f" [E-mode: {label}]" if label else ""),
                            account=account, collateral=c["sym"], debt=b["sym"],
                            ltv=ltv, lt=max(lt, ltv), liq_penalty=pen or s.default_liq_penalty,
                            borrow_apy=b["borrow_apy"], collateral_apy=c["supply_apy"],
                            borrow_liquidity_usd=b["liquidity"], p_fail=pfail, emode=label,
                            meta=(("source", "aave"), ("market_address", m["address"]),
                                  ("chain_id", CHAIN_IDS.get(chain)), ("debt_address", ba),
                                  ("collateral_address", ca),
                                  ("collateral_pool_id", c["pool_id"]),
                                  ("borrow_pool_id", b["pool_id"])),
                        ))
    return routes, set(by_chain), pool_market


# --------------------------------------------------------------------------- other lenders

def _generic_market_key(p: dict) -> str:
    return f"{p['project']}|{p['chain']}|{p.get('poolMeta') or 'main'}"


def build_defillama_routes(ctx: _Ctx, aave_chains: set[str]) -> tuple[list[Route], dict[str, str]]:
    s = ctx.settings
    routes: list[Route] = []
    pool_market: dict[str, str] = {}
    pooled: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    compound_base: dict[tuple, tuple[dict, dict]] = {}
    compound_coll: list[tuple[dict, dict]] = []

    def borrow_rate(lb):
        return borrow_apy(lb, s.reward_haircut)

    def rate_ok(r):
        return r is not None and -5.0 < r < 100.0

    for pid, lb in ctx.lend.items():
        p = ctx.pools[pid]
        proj, chain = p["project"], p["chain"]
        if not ctx.chain_ok(chain) or ctx.excluded(proj):
            continue
        if proj == "aave-v3" and chain in aave_chains:
            continue
        sym = normalize_symbol(p["symbol"])
        if not CLEAN_SYMBOL.match(sym):
            continue
        ltv = lb.get("ltv") or 0.0
        rate = borrow_rate(lb)
        meta_str = p.get("poolMeta") or ""

        pair_debt = None
        if lb.get("mintedCoin") and proj != "aave-v3":
            pair_debt = normalize_symbol(lb["mintedCoin"])
        elif proj in VAULT_PAIR_PROJECTS and "/" in meta_str:
            pair_debt = normalize_symbol(meta_str.split("/", 1)[1].split(" ")[0])

        if pair_debt is not None:
            if ltv <= 0 or not lb.get("borrowable") or not rate_ok(rate):
                continue
            liquidity = lb.get("debtCeilingUsd")
            if liquidity is None:
                liquidity = max((lb.get("totalSupplyUsd") or 0) - (lb.get("totalBorrowUsd") or 0), 0)
            if liquidity < s.min_borrow_liquidity_usd:
                continue
            if (lb.get("totalBorrowUsd") or 0) + liquidity < s.min_market_supply_usd:
                continue
            if proj in LT_EQUALS_LTV_PROJECTS:
                lt = ltv
            elif proj == "fluid-lending":
                lt = min(ltv + 0.02, 0.99)
            else:
                lt = min(ltv + s.default_lt_buffer, 0.99)
            penalty = morpho_liq_penalty(ltv) if proj == "morpho-blue" else s.default_liq_penalty
            routes.append(Route(
                id=f"{proj}|{chain}|{pid}", protocol=proj, chain=chain,
                market=f"{proj}|{chain}|{pid}",
                market_label=f"{proj} {sym}/{pair_debt} ({ltv:.1%} LTV)",
                account=f"{proj}|{chain}|{pid}", collateral=sym, debt=pair_debt,
                ltv=ltv, lt=lt, liq_penalty=penalty, borrow_apy=rate,
                collateral_apy=max(pool_apy(p, s.yield_basis, s.reward_haircut) or 0.0, 0.0),
                borrow_liquidity_usd=liquidity, p_fail=ctx.protocol_pfail(proj, chain=chain),
                meta=(("source", proj), ("chain_id", CHAIN_IDS.get(chain)),
                      ("collateral_address", (p.get("underlyingTokens") or [None])[0]),
                      ("collateral_pool_id", None), ("borrow_pool_id", None)),
            ))
            continue

        if proj == "compound-v3":
            if meta_str.endswith("-pool") and ltv > 0:
                compound_coll.append((p, lb))
            elif lb.get("borrowable") and rate_ok(rate):
                compound_base[(chain, sym)] = (p, lb)
            continue

        pooled[_generic_market_key(p)].append((p, lb))

    # Compound v3: one market per base asset; only the base is borrowable.
    for p, lb in compound_coll:
        base_sym = normalize_symbol(p["poolMeta"][: -len("-pool")])
        base = compound_base.get((p["chain"], base_sym))
        if base is None:
            continue
        bp, blb = base
        liquidity = bp.get("tvlUsd") or 0.0
        if liquidity < s.min_borrow_liquidity_usd or (blb.get("totalSupplyUsd") or 0) < s.min_market_supply_usd:
            continue
        key = f"compound-v3|{p['chain']}|{base_sym}"
        pool_market[bp["pool"]] = key
        ltv = lb["ltv"]
        routes.append(Route(
            id=f"{key}|{normalize_symbol(p['symbol'])}", protocol="compound-v3", chain=p["chain"],
            market=key, market_label=f"Compound v3 {base_sym} market", account=key,
            collateral=normalize_symbol(p["symbol"]), debt=base_sym, ltv=ltv,
            lt=min(ltv + 0.05, 0.99), liq_penalty=s.default_liq_penalty,
            borrow_apy=borrow_rate(blb), collateral_apy=0.0, borrow_liquidity_usd=liquidity,
            p_fail=ctx.protocol_pfail("compound-v3", chain=p["chain"]),
            meta=(("source", "compound-v3"), ("collateral_pool_id", None),
                  ("borrow_pool_id", bp["pool"])),
        ))

    # Generic pooled markets (Spark, Venus, Kamino, Dolomite, ...).
    for key, entries in pooled.items():
        colls = [(p, lb) for p, lb in entries if (lb.get("ltv") or 0) > 0]
        borrows = [(p, lb) for p, lb in entries
                   if lb.get("borrowable") and rate_ok(borrow_rate(lb))
                   and (p.get("tvlUsd") or 0) >= s.min_borrow_liquidity_usd
                   and (lb.get("totalSupplyUsd") or 0) >= s.min_market_supply_usd]
        for p, _ in entries:
            pool_market[p["pool"]] = key
        if not colls or not borrows:
            continue
        proj, chain = entries[0][0]["project"], entries[0][0]["chain"]
        label_meta = entries[0][0].get("poolMeta")
        pfail = ctx.protocol_pfail(proj, chain=chain)
        for cp, clb in colls:
            csym = normalize_symbol(cp["symbol"])
            if not CLEAN_SYMBOL.match(csym):
                continue
            for bp, blb in borrows:
                bsym = normalize_symbol(bp["symbol"])
                if not CLEAN_SYMBOL.match(bsym):
                    continue
                ltv = clb["ltv"]
                routes.append(Route(
                    id=f"{key}|{csym}->{bsym}", protocol=proj, chain=chain, market=key,
                    market_label=f"{proj}" + (f" ({label_meta})" if label_meta else ""),
                    account=key, collateral=csym, debt=bsym, ltv=ltv,
                    lt=min(ltv + s.default_lt_buffer, 0.99), liq_penalty=s.default_liq_penalty,
                    borrow_apy=borrow_rate(blb),
                    collateral_apy=max(pool_apy(cp, s.yield_basis, s.reward_haircut) or 0.0, 0.0),
                    borrow_liquidity_usd=bp.get("tvlUsd") or 0.0, p_fail=pfail,
                    meta=(("source", proj), ("collateral_pool_id", cp["pool"]),
                          ("borrow_pool_id", bp["pool"])),
                ))
    return routes, pool_market


# --------------------------------------------------------------------------- venues

def build_venues(ctx: _Ctx, natives: dict[str, NativeYield], routes: list[Route],
                 pool_market: dict[str, str]) -> list[Venue]:
    s = ctx.settings
    venues: list[Venue] = []
    seen_receipts: set[tuple[str, str]] = set()
    for p in ctx.raw.pools:
        chain, proj = p["chain"], p["project"]
        if not ctx.chain_ok(chain) or ctx.excluded(proj):
            continue
        if p.get("exposure") != "single" or p.get("outlier") or p.get("ilRisk") == "yes":
            continue
        tvl = p.get("tvlUsd") or 0.0
        if tvl < s.min_venue_tvl_usd:
            continue
        apy = pool_apy(p, s.yield_basis, s.reward_haircut)
        if apy is None or apy <= 0 or apy > s.max_apy:
            continue
        category = ctx.category(proj)
        lb = ctx.lend.get(p["pool"])
        if lb is not None:
            # Supply side of a pooled lending market (pair markets list collateral here).
            if lb.get("mintedCoin") or not lb.get("borrowable"):
                continue
            if proj in VAULT_PAIR_PROJECTS and "/" in (p.get("poolMeta") or ""):
                continue
            deposit = normalize_symbol(p["symbol"])
            if not CLEAN_SYMBOL.match(deposit):
                continue
            receipt, receipt_market, kind = deposit, pool_market.get(p["pool"]), "lend"
            if receipt_market is None:
                # The supplied position lives inside a market we cannot pair, so it
                # cannot be re-posted as collateral: give it a unique receipt.
                receipt = f"{proj}:{deposit}:{p['pool'][:8]}"
            label = f"Lend {deposit} on {proj}" + (f" ({p['poolMeta']})" if p.get("poolMeta") else "")
            risk_tvl = None  # protocol-level TVL
            apy += ctx_native(natives, deposit)
        else:
            deposit = _deposit_symbol(ctx, p)
            if not deposit:
                continue
            receipt = _receipt_symbol(p)
            if receipt != deposit and CLEAN_SYMBOL.match(receipt) and receipt in natives \
                    and family(receipt) == family(deposit):
                kind = "stake"
                label = f"Stake {deposit} -> {receipt} ({proj})"
            else:
                kind, receipt = "vault", f"{proj}:{p['symbol']}:{p['pool'][:8]}"
                label = f"{proj} {p['symbol']} vault" + (f" ({p['poolMeta']})" if p.get("poolMeta") else "")
                if category == "Lending":
                    category = "Vault"
            receipt_market, risk_tvl = None, tvl
        if category not in s.venue_categories:
            continue
        exit_bps = 0.0 if kind == "lend" else config.EXIT_COST_BPS.get(category, 0.0)
        venues.append(Venue(
            id=p["pool"], protocol=proj, category=category, chain=chain, label=label,
            deposit=deposit, receipt=receipt, receipt_market=receipt_market, apy=apy,
            tvl_usd=tvl, entry_bps=0.0, exit_bps=exit_bps, pool_id=p["pool"], kind=kind,
            p_fail=ctx.protocol_pfail(proj, category=category, tvl=risk_tvl, chain=chain),
            spread_vol_pp=config.SPREAD_VOL_PP.get(category, config.DEFAULT_SPREAD_VOL_PP),
        ))
        if kind == "stake":
            seen_receipts.add((chain, receipt))

    # Yield tokens bought with a swap on chains where they are accepted as collateral.
    collateral_on = {(r.chain, r.collateral) for r in routes}
    for (chain, sym) in sorted(collateral_on):
        n = natives.get(sym)
        if n is None or (chain, sym) in seen_receipts or n.category not in TOKEN_YIELD_CATEGORIES:
            continue
        if not ctx.chain_ok(chain) or ctx.excluded(n.protocol):
            continue
        if n.category not in s.venue_categories:
            continue
        swap = config.SWAP_COST_BPS.get(family(sym), config.DEFAULT_SWAP_COST_BPS)
        venues.append(Venue(
            id=f"token|{chain}|{sym}", protocol=n.protocol, category=n.category, chain=chain,
            label=f"Buy {sym} ({n.protocol}) on {chain}", deposit=n.underlying, receipt=sym,
            receipt_market=None, apy=n.apy, tvl_usd=n.tvl_usd, entry_bps=swap,
            exit_bps=max(swap, config.EXIT_COST_BPS.get(n.category, 0.0)), pool_id=n.pool_id,
            kind="token", p_fail=n.p_fail,
            spread_vol_pp=config.SPREAD_VOL_PP.get(n.category, config.DEFAULT_SPREAD_VOL_PP),
        ))
    return venues


def ctx_native(natives: dict[str, NativeYield], symbol: str) -> float:
    n = natives.get(symbol)
    return n.apy if n else 0.0


# --------------------------------------------------------------------------- entry point

def build_universe(raw: RawData, settings: Settings) -> Universe:
    ctx = _Ctx(raw, settings)
    natives = build_natives(ctx)
    aave_routes, aave_chains, aave_pool_market = build_aave_routes(ctx)
    other_routes, other_pool_market = build_defillama_routes(ctx, aave_chains)
    routes = [r for r in aave_routes + other_routes if r.ltv > 0 and r.borrow_apy is not None]
    venues = build_venues(ctx, natives, routes, {**other_pool_market, **aave_pool_market})
    return Universe(routes=routes, venues=venues, natives=natives, protocols=raw.protocols,
                    fetched_at=raw.fetched_at, settings=settings).index()
