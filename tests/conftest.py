"""A tiny synthetic market so the optimizer can be tested offline and deterministically."""

from __future__ import annotations

import pytest

from leveraged_yield.sources.snapshot import RawData

WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
WSTETH = "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
NATIVE = "0x0000000000000000000000000000000000000000"
AAVE_MARKET = "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"


def pool(pid, project, symbol, apy, underlying, tvl=500e6, meta=None, reward=None):
    return {
        "chain": "Ethereum", "project": project, "symbol": symbol, "tvlUsd": tvl,
        "apyBase": apy, "apyReward": reward, "apy": apy + (reward or 0.0), "apyMean30d": None,
        "pool": pid, "poolMeta": meta, "underlyingTokens": [underlying], "stablecoin": False,
        "exposure": "single", "outlier": False, "ilRisk": "no",
    }


def lend(pid, ltv, borrow_apy=None, borrowable=True, minted=None, supply=1e9, borrow=5e8,
         ceiling=None):
    return {
        "pool": pid, "apyBaseBorrow": borrow_apy, "apyRewardBorrow": None,
        "totalSupplyUsd": supply, "totalBorrowUsd": borrow, "debtCeilingUsd": ceiling,
        "ltv": ltv, "borrowable": borrowable, "mintedCoin": minted, "underlyingTokens": [],
    }


def pct(x):
    return {"value": str(x)}


def reserve(symbol, address, ltv, lt, bonus, supply_apy, borrow_apy=None):
    borrow = None
    if borrow_apy is not None:
        borrow = {"apy": pct(borrow_apy), "borrowingState": "ENABLED", "borrowCapReached": False,
                  "availableLiquidity": {"usd": "500000000"}}
    return {
        "underlyingToken": {"symbol": symbol, "address": address},
        "isFrozen": False, "isPaused": False, "size": {"usd": "1000000000"},
        "supplyInfo": {"apy": pct(supply_apy), "maxLTV": pct(ltv), "liquidationThreshold": pct(lt),
                       "liquidationBonus": pct(bonus), "canBeCollateral": ltv > 0,
                       "supplyCapReached": False},
        "borrowInfo": borrow,
    }


def make_raw(weth_borrow_apy: float = 2.0, lido_apy: float = 3.0) -> RawData:
    pools = [
        pool("aave-weth", "aave-v3", "WETH", 1.3, WETH),
        pool("aave-wsteth", "aave-v3", "WSTETH", 0.0, WSTETH),
        pool("aave-usdc", "aave-v3", "USDC", 3.9, USDC),
        pool("lido", "lido", "STETH", lido_apy, NATIVE, tvl=20e9),
        pool("morpho-wsteth-weth", "morpho-blue", "WSTETH", 0.0, WSTETH),
        pool("steak-usdc", "morpho-blue", "STEAKUSDC", 5.0, USDC, tvl=100e6),
    ]
    lend_borrow = [
        lend("aave-weth", 0.805, weth_borrow_apy),
        lend("aave-wsteth", 0.785, None, borrowable=False),
        lend("aave-usdc", 0.75, 4.6),
        lend("morpho-wsteth-weth", 0.945, weth_borrow_apy - 0.2, minted="WETH", ceiling=50e6),
    ]
    protocols = {
        "aave-v3": {"category": "Lending", "tvl": 20e9, "chainTvls": {"Ethereum": 15e9},
                    "listedAt": 1_600_000_000},
        "lido": {"category": "Liquid Staking", "tvl": 25e9, "chainTvls": {"Ethereum": 25e9},
                 "listedAt": None},
        "morpho-blue": {"category": "Lending", "tvl": 10e9, "chainTvls": {"Ethereum": 5e9},
                        "listedAt": 1_700_000_000},
    }
    emode = {
        "id": 1, "label": "ETH correlated", "maxLTV": pct(0.93), "liquidationThreshold": pct(0.95),
        "liquidationPenalty": pct(0.01), "isolated": False,
        "reserves": [
            {"underlyingToken": {"symbol": "WETH", "address": WETH}, "canBeCollateral": True,
             "canBeBorrowed": True, "hasLtvZero": False},
            {"underlyingToken": {"symbol": "wstETH", "address": WSTETH}, "canBeCollateral": True,
             "canBeBorrowed": False, "hasLtvZero": False},
        ],
    }
    aave_markets = [{
        "name": "AaveV3Ethereum", "address": AAVE_MARKET, "chain": {"chainId": 1, "name": "Ethereum"},
        "eModeCategories": [emode],
        "reserves": [
            reserve("WETH", WETH, 0.805, 0.83, 0.05, 0.013, 0.02),
            reserve("wstETH", WSTETH, 0.785, 0.81, 0.06, 0.0),
            reserve("USDC", USDC, 0.75, 0.78, 0.045, 0.039, 0.046),
        ],
    }]
    return RawData(pools, lend_borrow, protocols, aave_markets, "2026-10-08T00:00:00Z")


@pytest.fixture
def raw():
    return make_raw()
