"""Tunable assumptions for the optimizer.

Every number that is a judgement call (gas, swap costs, volatilities, protocol
failure rates, risk aversion) lives here so it can be inspected and overridden
from the CLI or in code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Approximate USD gas cost of one loop step (borrow + convert + supply) per chain.
GAS_USD_PER_STEP = {
    "Ethereum": 1.50,
    "BSC": 0.08,
    "Avalanche": 0.08,
    "Polygon": 0.02,
    "Solana": 0.01,
    "Gnosis": 0.01,
}
DEFAULT_GAS_USD_PER_STEP = 0.05  # L2s / alt-L1s

# One-way swap cost (bps) when the borrowed token must be swapped into the
# venue's deposit token within the same price family (e.g. USDC -> USDe).
SWAP_COST_BPS = {"USD": 3.0, "ETH": 5.0, "BTC": 10.0, "SOL": 5.0, "EUR": 10.0}
DEFAULT_SWAP_COST_BPS = 15.0

# Exit cost (bps) for leaving a venue, by DefiLlama protocol category. Liquid
# staking tokens are normally exited through a DEX (or a slow withdrawal queue).
EXIT_COST_BPS = {
    "Liquid Staking": 5.0,
    "Liquid Restaking": 10.0,
    "Basis Trading": 10.0,
    "Restaked BTC": 15.0,
    "RWA": 5.0,
}

# Annualised price volatility of each price family against USD.
ASSET_VOL = {"USD": 0.0, "ETH": 0.65, "BTC": 0.50, "SOL": 0.85, "EUR": 0.08}
DEFAULT_ASSET_VOL = 1.00
ASSET_CORR = {
    frozenset(("ETH", "BTC")): 0.80,
    frozenset(("ETH", "SOL")): 0.75,
    frozenset(("BTC", "SOL")): 0.70,
}
DEFAULT_ASSET_CORR = 0.50

# Annualised volatility of a token against the debt token *within* the same
# family (depeg risk). Yield-bearing / wrapped tokens use the family number,
# two plain stablecoins use PLAIN_STABLE_DEPEG_VOL.
DEPEG_VOL = {"ETH": 0.04, "USD": 0.03, "BTC": 0.03, "SOL": 0.04, "EUR": 0.03}
DEFAULT_DEPEG_VOL = 0.05
PLAIN_STABLE_DEPEG_VOL = 0.015

# Uncertainty (percentage points, 1 sigma) of the average carry spread
# (venue yield minus borrow rate) over the holding period, by venue category.
SPREAD_VOL_PP = {
    "Liquid Staking": 0.75,
    "Liquid Restaking": 1.0,
    "CDP": 1.0,
    "RWA": 1.0,
    "Lending": 1.5,
    "Yield": 1.5,
    "Yield Aggregator": 1.5,
    "Risk Curators": 1.5,
    "Vault": 1.5,
    "Onchain Capital Allocator": 2.0,
    "Uncollateralized Lending": 2.0,
    "Basis Trading": 3.0,
}
DEFAULT_SPREAD_VOL_PP = 2.0
# Thin markets reprice fast: below this much borrow liquidity / venue TVL the
# spread volatility is scaled by sqrt(THIN_MARKET_USD / liquidity).
THIN_MARKET_USD = 50e6

# Base annual probability of a loss event (hack, insolvency, depeg, bad debt)
# by protocol category, before TVL / age adjustments.
PROTOCOL_BASE_PFAIL = {
    "Lending": 0.010,
    "Liquid Staking": 0.008,
    "CDP": 0.008,
    "Liquid Restaking": 0.015,
    "Yield": 0.015,
    "RWA": 0.015,
    "Risk Curators": 0.020,
    "Vault": 0.020,  # curated vault: curator, oracle and collateral choices on top of the lender
    "Restaked BTC": 0.020,
    "Basis Trading": 0.020,
    "Yield Aggregator": 0.020,
    "Onchain Capital Allocator": 0.025,
    "Uncollateralized Lending": 0.050,
}
DEFAULT_PROTOCOL_BASE_PFAIL = 0.030

# (minimum TVL in USD, multiplier) - first match wins.
TVL_RISK_MULTIPLIER = (
    (5e9, 0.4),
    (1e9, 0.6),
    (250e6, 0.8),
    (50e6, 1.0),
    (10e6, 1.5),
    (0.0, 2.5),
)

DEFAULT_COLLATERALS = ("USDC", "USDT", "WETH", "WSTETH", "WBTC", "CBBTC", "SOL")

# Where borrowed tokens may be put to work: lending, staking and savings
# products. RWA funds, aggregators, capital allocators, uncollateralised credit,
# DEX LPs etc. are excluded by default (override with --venue-categories).
VENUE_CATEGORIES = (
    "Lending", "Vault", "Risk Curators", "Liquid Staking", "Liquid Restaking", "CDP",
    "Basis Trading", "Yield", "Restaked BTC",
)
# Fixed-maturity principal tokens cannot be exited at par before maturity.
DEFAULT_EXCLUDED_PROTOCOLS = ("pendle-v2", "pendle", "spectra-v2")


@dataclass
class Settings:
    capital_usd: float = 10_000.0
    holding_years: float = 1.0
    collaterals: tuple[str, ...] = DEFAULT_COLLATERALS
    chains: tuple[str, ...] | None = None

    # "spot" = current APY, "mean30d" = 30-day mean, "min" = the lower of the
    # two (conservative: do not chase temporary spikes). Borrow rates are spot.
    yield_basis: str = "min"

    # Fraction of the maximum LTV used on every borrow (1.0 = "borrow the full
    # 80%" as in the manual process) and the loop cap.
    utilization_grid: tuple[float, ...] = (
        0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.88, 0.9, 0.92, 0.94, 0.96, 0.98, 1.0)
    max_loops: int = 50
    dust_usd: float = 10.0  # stop looping when the next borrow is smaller

    # Incentive (reward token) APYs are volatile and often paid in illiquid
    # tokens: only (1 - haircut) of them is counted, on supply and borrow side.
    reward_haircut: float = 0.5

    # Universe filters
    min_venue_tvl_usd: float = 10e6
    min_market_supply_usd: float = 5e6
    min_borrow_liquidity_usd: float = 1e6
    max_apy: float = 40.0
    venue_categories: tuple[str, ...] = VENUE_CATEGORIES
    # Only use protocols (lenders and venues) with at least this much TVL.
    min_protocol_tvl_usd: float = 250e6
    exclude_categories: tuple[str, ...] = ()
    exclude_protocols: tuple[str, ...] = DEFAULT_EXCLUDED_PROTOCOLS

    # Hard constraint on the optimised position (the "literal" max-loop
    # comparison ignores it). Non-Aave liquidation thresholds are estimates,
    # so running closer to 1.0 than this is not trusted.
    min_health_factor: float = 1.10
    # The manual process passes through a weaker state after each borrow and
    # before the new tranche is re-posted; it must never touch liquidation.
    min_step_health_factor: float = 1.02

    # Risk model
    horizon_years: float = 1.0  # window for liquidation (barrier) probability
    lgd: float = 0.5  # share of exposure lost if a protocol fails
    risk_aversion: float = 2.0  # mean-variance penalty on spread volatility
    stress_spread_pp: float = 2.0  # spread compression used for "stress APY"
    default_liq_penalty: float = 0.05
    default_lt_buffer: float = 0.03  # LT = LTV + buffer when a source omits LT

    # Reporting
    top_n: int = 25
    backtest_top: int = 25
    backtest_days: int = 180

    gas_usd_per_step: dict[str, float] = field(default_factory=lambda: dict(GAS_USD_PER_STEP))

    def gas_for(self, chain: str) -> float:
        return self.gas_usd_per_step.get(chain, DEFAULT_GAS_USD_PER_STEP)
