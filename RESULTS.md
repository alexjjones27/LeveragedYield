# Leveraged yield optimizer: results for a $10,000 portfolio

Market data snapshot: **2026-10-08T11:19:48Z** (DefiLlama yields + lend/borrow, Aave v3 API for exact LTV / liquidation thresholds / E-mode). Universe after quality filters: 1,724 borrow routes and 203 lend/stake venues; 247,310 position sizes evaluated.

Yields use the lower of spot and 30-day average APY; reward-token incentives count at 50%. Borrow costs include the staking yield of the borrowed token when it is yield-bearing. Every optimised position keeps a health factor of at least 1.10 (and 1.02 between loops).

## 1. Best combination per starting collateral

| Collateral | Best unlevered option (baseline) | Baseline APY | Best levered combination | Leverage | Net APY | Risk-adj. APY | Profit/yr on $10,000 | Baseline profit/yr | Lift |
|---|---|---|---|---|---|---|---|---|---|
| USDC | morpho-blue ROXCUSDC vault [Ethereum] | 8.36% | Post USDC on Aave v3 Monad (Monad), borrow AUSD, Lend USDC on aave-v3, re-post and loop | 3.39x, 8 loops @ 96% of max LTV | 9.48% | 7.95% | $948 | $836 | +1.12 pp |
| USDT | morpho-blue ROXCUSDC vault [Ethereum] | 8.30% | None beats the baseline after risk: stay unlevered | - | - | - | - | $830 | - |
| WETH | Stake WETH -> WEETH (ether.fi-stake) [Ethereum] | 2.24% | Post WETH on Aave v3 Monad (Monad), borrow AUSD, Lend USDC on aave-v3, re-post and loop | 2.03x, 2 loops @ 80% of max LTV | 4.61% | 3.33% | $461 | $224 | +2.36 pp |
| WSTETH | Hold WSTETH (lido yield) | 2.25% | Post WSTETH on Aave v3 Ethereum [E-mode: ETH correlated] (Ethereum), borrow WETH, Stake WETH -> WEETH (ether.fi-stake), re-post and loop | 6.85x, 8 loops @ 100% of max LTV | 3.78% | 2.66% | $378 | $225 | +1.53 pp |
| WBTC | Hold WBTC | 0.00% | Post WBTC on morpho-blue WBTC/RLUSD (86.0% LTV) (Ethereum), borrow RLUSD, sentora-curator USDC vault (Sentora USD) | 1.43x, single borrow @ 50% of max LTV | 2.09% | 1.03% | $209 | $0 | +2.09 pp |
| CBBTC | Hold CBBTC | 0.00% | Post CBBTC on Aave v3 Monad (Monad), borrow AUSD, Lend USDC on aave-v3, re-post and loop | 2.24x, 2 loops @ 98% of max LTV | 2.35% | 1.02% | $235 | $0 | +2.35 pp |
| SOL | Stake SOL -> JUPSOL (jupiter-staked-sol) [Solana] | 5.38% | None beats the baseline after risk: stay unlevered | - | - | - | - | $538 | - |

## 2. Top 25 combinations (all beat their unlevered baseline)

Ranked by risk-adjusted APY. One row per collateral / lender / borrowed-asset type / venue type (the best variant of each); every variant is in `results/strategies.csv`.

### 2a. What to do

| # | Collateral | Chain | Borrow on | Borrow (cost) | Stake / lend on (yield) | Loop collateral on | LTV used | Loops | Leverage |
|---|---|---|---|---|---|---|---|---|---|
| 1 | USDC | Monad | Aave v3 Monad | AUSD (3.02%) | Lend USDC on aave-v3 (4.97%) | same account | 96% | 8 | 3.39x |
| 2 | WETH | Monad | Aave v3 Monad | AUSD (3.02%) | Lend USDC on aave-v3 (4.97%) | same account | 80% | 2 | 2.03x |
| 3 | WETH | Monad | Aave v3 Monad | AUSD (3.02%) | morpho-blue HYPERUSDCA vault (6.92%) | not re-posted (single borrow) | 40% | 1 | 1.32x |
| 4 | WSTETH | Ethereum | Aave v3 Ethereum [E-mode: ETH correlated] | WETH (1.97%) | Stake WETH -> WEETH (ether.fi-stake) (2.32%) | same account | 100% | 8 | 6.85x |
| 5 | WSTETH | Ethereum | morpho-blue WSTETH/USDT (86.0% LTV) | USDT (3.17%) | sentora-curator USDC vault (Sentora USD) (7.44%) | not re-posted (single borrow) | 40% | 1 | 1.34x |
| 6 | WSTETH | Ethereum | Compound v3 WETH market | WETH (1.90%) | Stake WETH -> WEETH (ether.fi-stake) (2.32%) | same account | 100% | 8 | 6.13x |
| 7 | WSTETH | Ethereum | sparklend | RLUSD (3.90%) | morpho-blue ROXCUSDC vault (8.39%) | not re-posted (single borrow) | 40% | 1 | 1.33x |
| 8 | WSTETH | Ethereum | Compound v3 USDT market | USDT (3.98%) | morpho-blue ROXCUSDC vault (8.39%) | not re-posted (single borrow) | 40% | 1 | 1.33x |
| 9 | WSTETH | Ethereum | dolomite | WETH (1.68%) | Stake WETH -> WEETH (ether.fi-stake) (2.32%) | same account | 100% | 6 | 4.17x |
| 10 | WSTETH | Ethereum | Aave v3 EthereumLido | GHO (4.17%) | morpho-blue ROXCUSDC vault (8.39%) | not re-posted (single borrow) | 30% | 1 | 1.25x |
| 11 | WSTETH | Ethereum | sparklend | RLUSD (3.90%) | sentora-curator USDC vault (Sentora USD) (7.44%) | not re-posted (single borrow) | 40% | 1 | 1.33x |
| 12 | WSTETH | Ethereum | Aave v3 Ethereum | USDT (4.37%) | morpho-blue ROXCUSDC vault (8.39%) | not re-posted (single borrow) | 30% | 1 | 1.24x |
| 13 | WSTETH | Ethereum | morpho-blue WSTETH/WETH (96.5% LTV) | WETH (1.92%) | Stake WETH -> WSTETH (lido) (2.25%) | same account | 98% | 8 | 7.27x |
| 14 | WSTETH | Polygon | Aave v3 Polygon [E-mode: ETH correlated] | WETH (1.83%) | Buy WSTETH (lido) on Polygon (2.25%) | same account | 98% | 10 | 6.35x |
| 15 | WSTETH | Ethereum | Aave v3 EthereumLido | GHO (4.17%) | sentora-curator USDC vault (Sentora USD) (7.44%) | not re-posted (single borrow) | 30% | 1 | 1.25x |
| 16 | WSTETH | Ethereum | Compound v3 USDT market | USDT (3.98%) | sentora-curator USDC vault (Sentora USD) (7.44%) | not re-posted (single borrow) | 40% | 1 | 1.33x |
| 17 | WSTETH | Ethereum | morpho-blue WSTETH/USDT (86.0% LTV) | USDT (3.17%) | Lend USDC on dolomite (5.30%) | not re-posted (single borrow) | 30% | 1 | 1.26x |
| 18 | WSTETH | Ethereum | Aave v3 Ethereum | USDT (4.37%) | sentora-curator USDC vault (Sentora USD) (7.44%) | not re-posted (single borrow) | 30% | 1 | 1.24x |
| 19 | WSTETH | Ethereum | sparklend | WETH (1.92%) | Stake WETH -> WEETH (ether.fi-stake) (2.32%) | Aave v3 Ethereum [E-mode: ETH correlated] (WETH 1.97%) | 94% | 12 | 5.97x |
| 20 | WSTETH | Ethereum | morpho-blue WSTETH/USDT (86.0% LTV) | USDT (3.17%) | Stake USDS -> STUSDS (sky-lending) (5.07%) | not re-posted (single borrow) | 30% | 1 | 1.26x |
| 21 | WSTETH | Ethereum | morpho-blue WSTETH/USDC (86.0% LTV) | USDC (4.74%) | sentora-curator USDC vault (Sentora USD) (7.44%) | not re-posted (single borrow) | 30% | 1 | 1.26x |
| 22 | WBTC | Ethereum | morpho-blue WBTC/RLUSD (86.0% LTV) | RLUSD (2.37%) | sentora-curator USDC vault (Sentora USD) (7.44%) | not re-posted (single borrow) | 50% | 1 | 1.43x |
| 23 | CBBTC | Monad | Aave v3 Monad | AUSD (3.02%) | Lend USDC on aave-v3 (4.97%) | same account | 98% | 2 | 2.24x |
| 24 | WBTC | Ethereum | morpho-blue WBTC/USDT (86.0% LTV) | USDT (3.17%) | sentora-curator USDC vault (Sentora USD) (7.44%) | not re-posted (single borrow) | 50% | 1 | 1.43x |
| 25 | CBBTC | Ethereum | sparklend | RLUSD (3.90%) | morpho-blue ROXCUSDC vault (8.39%) | not re-posted (single borrow) | 50% | 1 | 1.41x |

### 2b. Returns and downside

| # | Net APY | Profit/yr on $10,000 | Baseline APY | Lift | Risk-adj. APY | Stress APY (spread -2pp) | Bad-year APY (5th pct) | Health factor | Move to liquidation | P(liquidation, 1y) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 9.48% | $948 | 8.36% | +1.12 pp | 7.95% | 4.71% | -4.56% | 1.11 | 9.7% depeg | 0.0% |
| 2 | 4.61% | $461 | 2.24% | +2.36 pp | 3.33% | 2.55% | -1.46% | 1.60 | 73% price, 76.3% depeg | 4.4% |
| 3 | 3.89% | $389 | 2.24% | +1.65 pp | 2.91% | 3.25% | 2.00% | 2.61 | 62% price | 14.0% |
| 4 | 3.78% | $378 | 2.25% | +1.53 pp | 2.66% | -7.92% | -3.44% | 1.11 | 10.1% depeg | 0.8% |
| 5 | 3.64% | $364 | 2.25% | +1.39 pp | 2.62% | 2.95% | 2.59% | 2.50 | 60% price | 15.9% |
| 6 | 3.90% | $390 | 2.25% | +1.64 pp | 2.58% | -6.36% | -3.46% | 1.14 | 11.9% depeg | 0.2% |
| 7 | 3.66% | $366 | 2.25% | +1.41 pp | 2.55% | 3.00% | 1.75% | 2.59 | 61% price | 14.3% |
| 8 | 3.62% | $362 | 2.25% | +1.37 pp | 2.44% | 2.96% | 2.24% | 2.65 | 62% price | 13.3% |
| 9 | 3.91% | $391 | 2.25% | +1.66 pp | 2.42% | -2.43% | -1.85% | 1.12 | 10.6% depeg | 0.5% |
| 10 | 3.25% | $325 | 2.25% | +1.00 pp | 2.42% | 2.76% | 1.67% | 3.37 | 70% price | 6.1% |
| 11 | 3.35% | $335 | 2.25% | +1.09 pp | 2.34% | 2.68% | 1.43% | 2.59 | 61% price | 14.3% |
| 12 | 3.13% | $313 | 2.25% | +0.87 pp | 2.33% | 2.65% | 2.30% | 3.44 | 71% price | 5.7% |
| 13 | 3.73% | $373 | 2.25% | +1.47 pp | 2.31% | -8.82% | -9.64% | 1.12 | 10.6% depeg | 0.5% |
| 14 | 4.00% | $400 | 2.25% | +1.75 pp | 2.30% | -6.69% | -5.14% | 1.10 | 9.4% depeg | 1.3% |
| 15 | 3.02% | $302 | 2.25% | +0.76 pp | 2.26% | 2.52% | 1.44% | 3.37 | 70% price | 6.1% |
| 16 | 3.31% | $331 | 2.25% | +1.05 pp | 2.23% | 2.65% | 1.93% | 2.65 | 62% price | 13.3% |
| 17 | 2.73% | $273 | 2.25% | +0.47 pp | 2.19% | 2.21% | 1.90% | 3.33 | 70% price | 6.4% |
| 18 | 2.90% | $290 | 2.25% | +0.65 pp | 2.18% | 2.43% | 2.32% | 3.44 | 71% price | 5.7% |
| 19 | 3.42% | $342 | 2.25% | +1.17 pp | 2.14% | -6.51% | -2.70% | 1.10 | 9.3% depeg, 11.3% depeg | 1.8% |
| 20 | 2.67% | $267 | 2.25% | +0.41 pp | 2.13% | 2.15% | 2.14% | 3.33 | 70% price | 6.4% |
| 21 | 2.89% | $289 | 2.25% | +0.64 pp | 2.13% | 2.37% | 0.52% | 3.33 | 70% price | 6.4% |
| 22 | 2.09% | $209 | 0.00% | +2.09 pp | 1.03% | 1.23% | -0.75% | 2.00 | 50% price | 16.6% |
| 23 | 2.35% | $235 | 0.00% | +2.35 pp | 1.02% | -0.14% | -4.96% | 1.41 | 65% price, 52.4% depeg | 3.6% |
| 24 | 1.75% | $175 | 0.00% | +1.75 pp | 0.71% | 0.89% | 0.10% | 2.00 | 50% price | 16.6% |
| 25 | 1.73% | $173 | 0.00% | +1.73 pp | 0.61% | 0.92% | -0.60% | 2.07 | 52% price | 14.5% |

## 3. Your manual process vs the optimised version

"Manual" = borrow the full max LTV every time and keep looping until the next borrow is dust or no longer covers its gas. "Optimised" = the LTV share and loop count the optimiser picked for the best risk-adjusted return.

| # | Collateral on lender / borrow / venue | Manual loops | Manual leverage | Manual HF | Manual net APY | Manual risk-adj. | Opt. LTV used | Opt. loops | Opt. leverage | Opt. HF | Opt. net APY | Opt. risk-adj. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | USDC on Aave v3 Monad (Monad) / AUSD / aave-v3 | 24 | 4.00x | 1.04 | 10.62% | 8.48% | 96% | 8 | 3.39x | 1.11 | 9.48% | 7.95% |
| 2 | WETH on Aave v3 Monad (Monad) / AUSD / aave-v3 | 24 | 4.22x | 1.04 | 8.73% | -12.51% | 80% | 2 | 2.03x | 1.60 | 4.61% | 3.33% |
| 3 | WETH on Aave v3 Monad (Monad) / AUSD / morpho-blue | 1 | 1.80x | 1.04 | 5.75% | 0.26% | 40% | 1 | 1.32x | 2.61 | 3.89% | 2.91% |
| 4 | WSTETH on Aave v3 Ethereum (Ethereum) / WETH / ether.fi-stake | 32 | 12.98x | 1.03 | 4.94% | -2.38% | 100% | 8 | 6.85x | 1.11 | 3.78% | 2.66% |
| 5 | WSTETH on morpho-blue WSTETH/USDT (Ethereum) / USDT / sentora-curator | 1 | 1.86x | 1.00 | 5.81% | 0.62% | 40% | 1 | 1.34x | 2.50 | 3.64% | 2.62% |
| 6 | WSTETH on Compound v3 WETH market (Ethereum) / WETH / ether.fi-stake | 23 | 9.20x | 1.07 | 4.59% | -1.55% | 100% | 8 | 6.13x | 1.14 | 3.90% | 2.58% |
| 7 | WSTETH on sparklend (Ethereum) / RLUSD / morpho-blue | 1 | 1.83x | 1.04 | 5.87% | 0.21% | 40% | 1 | 1.33x | 2.59 | 3.66% | 2.55% |
| 8 | WSTETH on Compound v3 USDT market (Ethereum) / USDT / morpho-blue | 1 | 1.82x | 1.06 | 5.76% | 0.22% | 40% | 1 | 1.33x | 2.65 | 3.62% | 2.44% |
| 9 | WSTETH on dolomite (Ethereum) / WETH / ether.fi-stake | 15 | 5.32x | 1.05 | 4.32% | -2.70% | 100% | 6 | 4.17x | 1.12 | 3.91% | 2.42% |
| 10 | WSTETH on Aave v3 EthereumLido (Ethereum) / GHO / morpho-blue | 1 | 1.82x | 1.01 | 5.64% | -0.90% | 30% | 1 | 1.25x | 3.37 | 3.25% | 2.42% |

## 4. Backtest: last 180 days of real daily rates

Each position is held at the tranche sizes above while borrow and supply rates follow their actual daily history (Aave v3 and Morpho borrow history; DefiLlama supply / staking history). Rows that borrow on other lenders show n/a (no free borrow history).

| # | Collateral on lender / borrow / venue | Window | Realised APY | Baseline realised | Beat baseline? | Worst 30-day APY | Days below baseline | $10,000 became | Baseline became |
|---|---|---|---|---|---|---|---|---|---|
| 1 | USDC on Aave v3 Monad (Monad) / AUSD / aave-v3 | 2026-07-03 to 2026-10-08 | 6.22% | 5.80% | yes | 3.76% | 54% | $10,163 | $10,153 |
| 2 | WETH on Aave v3 Monad (Monad) / AUSD / aave-v3 | 2026-07-03 to 2026-10-08 | 2.70% | 2.41% | yes | 1.63% | 51% | $10,072 | $10,064 |
| 3 | WETH on Aave v3 Monad (Monad) / AUSD / morpho-blue | 2026-07-03 to 2026-10-08 | 3.26% | 2.41% | yes | 2.58% | 12% | $10,087 | $10,064 |
| 4 | WSTETH on Aave v3 Ethereum (Ethereum) / WETH / ether.fi-stake | 2026-04-12 to 2026-10-08 | 1.60% | 2.36% | **no** | -7.42% | 21% | $10,078 | $10,116 |
| 5 | WSTETH on morpho-blue WSTETH/USDT (Ethereum) / USDT / sentora-curator | 2026-04-12 to 2026-10-08 | 3.17% | 2.36% | yes | 3.00% | 6% | $10,155 | $10,116 |
| 6 | WSTETH on Compound v3 WETH market (Ethereum) / WETH / ether.fi-stake | n/a (no free borrow-rate history for this lender) |  |  |  |  |  |  |  |
| 7 | WSTETH on sparklend (Ethereum) / RLUSD / morpho-blue | n/a (no free borrow-rate history for this lender) |  |  |  |  |  |  |  |
| 8 | WSTETH on Compound v3 USDT market (Ethereum) / USDT / morpho-blue | n/a (no free borrow-rate history for this lender) |  |  |  |  |  |  |  |
| 9 | WSTETH on dolomite (Ethereum) / WETH / ether.fi-stake | n/a (no free borrow-rate history for this lender) |  |  |  |  |  |  |  |
| 10 | WSTETH on Aave v3 EthereumLido (Ethereum) / GHO / morpho-blue | 2026-04-12 to 2026-10-08 | 2.87% | 2.36% | yes | 2.60% | 1% | $10,141 | $10,116 |
| 11 | WSTETH on sparklend (Ethereum) / RLUSD / sentora-curator | n/a (no free borrow-rate history for this lender) |  |  |  |  |  |  |  |
| 12 | WSTETH on Aave v3 Ethereum (Ethereum) / USDT / morpho-blue | 2026-04-12 to 2026-10-08 | 2.49% | 2.36% | yes | 2.03% | 10% | $10,122 | $10,116 |
| 13 | WSTETH on morpho-blue WSTETH/WETH (Ethereum) / WETH / lido | 2026-04-12 to 2026-10-08 | 3.01% | 2.36% | yes | 0.99% | 13% | $10,147 | $10,116 |
| 14 | WSTETH on Aave v3 Polygon (Polygon) / WETH / lido | 2026-04-12 to 2026-10-08 | 4.92% | 2.36% | yes | 4.08% | 4% | $10,240 | $10,116 |
| 15 | WSTETH on Aave v3 EthereumLido (Ethereum) / GHO / sentora-curator | 2026-04-12 to 2026-10-08 | 3.21% | 2.36% | yes | 3.01% | 0% | $10,157 | $10,116 |
| 16 | WSTETH on Compound v3 USDT market (Ethereum) / USDT / sentora-curator | n/a (no free borrow-rate history for this lender) |  |  |  |  |  |  |  |
| 17 | WSTETH on morpho-blue WSTETH/USDT (Ethereum) / USDT / dolomite | 2026-04-12 to 2026-10-08 | 2.71% | 2.36% | yes | 2.55% | 11% | $10,133 | $10,116 |
| 18 | WSTETH on Aave v3 Ethereum (Ethereum) / USDT / sentora-curator | 2026-04-12 to 2026-10-08 | 2.81% | 2.36% | yes | 2.41% | 7% | $10,138 | $10,116 |
| 19 | WSTETH on sparklend (Ethereum) / WETH / ether.fi-stake | n/a (no free borrow-rate history for this lender) |  |  |  |  |  |  |  |
| 20 | WSTETH on morpho-blue WSTETH/USDT (Ethereum) / USDT / sky-lending | 2026-04-12 to 2026-10-08 | 2.89% | 2.36% | yes | 2.52% | 7% | $10,142 | $10,116 |
| 21 | WSTETH on morpho-blue WSTETH/USDC (Ethereum) / USDC / sentora-curator | 2026-04-12 to 2026-10-08 | 2.89% | 2.36% | yes | 2.72% | 2% | $10,141 | $10,116 |
| 22 | WBTC on morpho-blue WBTC/RLUSD (Ethereum) / RLUSD / sentora-curator | 2026-05-02 to 2026-10-08 | 1.35% | 0.00% | yes | 0.94% | 1% | $10,059 | $10,000 |
| 23 | CBBTC on Aave v3 Monad (Monad) / AUSD / aave-v3 | 2026-07-03 to 2026-10-08 | 0.45% | 0.00% | yes | -0.56% | 44% | $10,012 | $10,000 |
| 24 | WBTC on morpho-blue WBTC/USDT (Ethereum) / USDT / sentora-curator | 2026-04-12 to 2026-10-08 | 0.96% | 0.00% | yes | 0.49% | 7% | $10,047 | $10,000 |
| 25 | CBBTC on sparklend (Ethereum) / RLUSD / morpho-blue | n/a (no free borrow-rate history for this lender) |  |  |  |  |  |  |  |

16 of 17 backtested combinations beat their baseline over the window. Forward-looking APYs assume today's rates persist; the backtest shows how often they did not.

## 5. Highest raw net APY, ignoring risk (for contrast)

| # | Combination | Leverage | Net APY | Risk-adj. APY | Baseline risk-adj. | HF | Still wins after risk? |
|---|---|---|---|---|---|---|---|
| 1 | Post USDC on Aave v3 Monad (Monad), borrow AUSD, Lend USDC on aave-v3, re-post and loop | 3.39x, 8 loops @ 96% of max LTV | 9.48% | 7.95% | 6.82% | 1.11 | yes |
| 2 | Post WETH on Aave v3 Monad (Monad), borrow AUSD, Lend USDC on aave-v3, re-post and loop | 2.03x, 2 loops @ 80% of max LTV | 4.61% | 3.33% | 2.08% | 1.60 | yes |
| 3 | Post WSTETH on morpho-blue WSTETH/USDT (86.0% LTV) (Ethereum), borrow USDT, morpho-blue ROXCUSDC vault | 1.43x, single borrow @ 50% of max LTV | 4.41% | 1.56% | 2.09% | 2.00 | no |
| 4 | Post WSTETH on Compound v3 WETH market (Ethereum), borrow WETH, Stake WETH -> CBETH (coinbase-wrapped-staked-eth), re-post and loop | 6.13x, 8 loops @ 100% of max LTV | 4.04% | 2.40% | 2.09% | 1.14 | yes |
| 5 | Post WSTETH on Aave v3 Polygon [E-mode: ETH correlated] (Polygon), borrow WETH, Buy WSTETH (lido) on Polygon, re-post and loop | 6.35x, 10 loops @ 98% of max LTV | 4.00% | 2.30% | 2.09% | 1.10 | yes |
| 6 | Post WSTETH on Aave v3 Optimism [E-mode: ETH correlated] (Optimism), borrow WETH, Buy WSTETH (lido) on OP Mainnet, re-post and loop | 5.39x, 6 loops @ 98% of max LTV | 3.97% | 1.78% | 2.09% | 1.17 | no |
| 7 | Post WSTETH on Aave v3 Ethereum [E-mode: ETH correlated] (Ethereum), borrow WETH, Stake WETH -> CBETH (coinbase-wrapped-staked-eth), re-post and loop | 6.85x, 8 loops @ 100% of max LTV | 3.94% | 2.51% | 2.09% | 1.11 | yes |
| 8 | Post WSTETH on morpho-blue WSTETH/USDT (86.0% LTV) (Ethereum), borrow USDT, morpho-blue FCUSDT vault | 1.34x, single borrow @ 40% of max LTV | 3.92% | 1.50% | 2.09% | 2.50 | no |
| 9 | Post WSTETH on dolomite (Ethereum), borrow WETH, Stake WETH -> WEETH (ether.fi-stake), re-post and loop | 4.17x, 6 loops @ 100% of max LTV | 3.91% | 2.42% | 2.09% | 1.12 | yes |
| 10 | Post WSTETH on Compound v3 WETH market (Ethereum), borrow WETH, Stake WETH -> WEETH (ether.fi-stake), re-post and loop | 6.13x, 8 loops @ 100% of max LTV | 3.90% | 2.58% | 2.09% | 1.14 | yes |

## 6. Unlevered options per collateral (top 3 by risk-adjusted APY)

| Collateral | Option | Net APY | Risk-adj. APY |
|---|---|---|---|
| USDC | morpho-blue ROXCUSDC vault [Ethereum] | 8.36% | 6.82% |
| USDC | morpho-blue FCUSDT vault [Ethereum] | 8.10% | 6.54% |
| USDC | sentora-curator USDC vault (Sentora USD) [Ethereum] | 7.41% | 6.19% |
| USDT | morpho-blue ROXCUSDC vault [Ethereum] | 8.30% | 6.76% |
| USDT | morpho-blue FCUSDT vault [Ethereum] | 8.16% | 6.60% |
| USDT | sentora-curator USDC vault (Sentora USD) [Ethereum] | 7.35% | 6.13% |
| WETH | Stake WETH -> WEETH (ether.fi-stake) [Ethereum] | 2.24% | 2.08% |
| WETH | Buy WEETH (ether.fi-stake) on Arbitrum [Arbitrum] | 2.22% | 2.06% |
| WETH | Stake WETH -> WSTETH (lido) [Ethereum] | 2.17% | 2.01% |
| WSTETH | Hold WSTETH (lido yield) | 2.25% | 2.09% |
| WSTETH | Stake WETH -> WEETH (ether.fi-stake) [Ethereum] | 2.14% | 1.98% |
| WSTETH | Buy WEETH (ether.fi-stake) on Arbitrum [Arbitrum] | 2.12% | 1.96% |
| WBTC | Hold WBTC | 0.00% | 0.00% |
| WBTC | Lend WBTC on aave-v3 [Ethereum] | -0.03% | -0.25% |
| WBTC | Lend WBTC on aave-v3 [Arbitrum] | 0.02% | -0.41% |
| CBBTC | Hold CBBTC | 0.00% | 0.00% |
| CBBTC | Lend CBBTC on aave-v3 [Ethereum] | -0.03% | -0.25% |
| CBBTC | Lend CBBTC on sparklend [Ethereum] | -0.03% | -0.25% |
| SOL | Stake SOL -> JUPSOL (jupiter-staked-sol) [Solana] | 5.38% | 5.05% |
| SOL | Lend JUPSOL on kamino-lend (SOL/BTC Market) [Solana] | 5.33% | 5.01% |
| SOL | Stake SOL -> MSOL (marinade-liquid-staking) [Solana] | 5.11% | 4.79% |

## How to read this / key assumptions

- **Net APY** = yield on your collateral + yield on everything you borrowed and deployed - borrow cost - swap, exit and gas costs (amortised over 1 year), as a % of your $10,000.
- **Baseline** = the best way to just lend / stake the same collateral with no borrowing (best risk-adjusted option from the same venue universe, same chain as the token).
- **Risk-adj. APY** = net APY minus expected annual losses from (a) liquidation: the chance a price or depeg move hits your liquidation level within 1 year times the liquidation penalty, (b) protocol failure of every protocol in the stack (base rate by category, scaled by TVL and age, 50% loss given failure), and (c) a mean-variance charge (risk aversion 2) for the borrow/yield spread moving against you, which grows with leverage and in thin markets.
- **Stress APY** = net APY if the carry spread compresses by 2 percentage points (e.g. ETH borrow rates spike). **Bad-year APY** = 5th percentile of that spread distribution.
- **Move to liquidation**: *price* = how far your collateral must fall against the borrowed asset (different assets, e.g. ETH vs USD); *depeg* = how far a same-family token (wstETH vs ETH, USDC vs AUSD) must slip.
- Positions are capped at health factor 1.10 after looping and 1.02 at any moment while looping. Non-Aave liquidation thresholds are estimated (LTV + 3pp; Morpho LLTV exact).
- Universe: protocols with TVL >= $250,000,000, venues with TVL >= $10,000,000 in categories Lending, Vault, Risk Curators, Liquid Staking, Liquid Restaking, CDP, Basis Trading, Yield, Restaked BTC; excluded: pendle-v2, pendle, spectra-v2. Everything stays on one chain (no bridging).
- Rates move. These are a snapshot; rerun `python -m leveraged_yield --refresh` before acting, and size positions so a few bad weeks of negative carry are survivable.

