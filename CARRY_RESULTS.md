# Crypto carry trade backtest: borrow cheap, lend rich, across CEXs and DEXs

Window **2025-10-08 to 2026-10-07** (365 days of daily rates; data pulled 2026-10-08T15:51:45Z). Walk-forward split: choose on 2025-10-08 to 2026-04-07, test on 2026-04-08 to 2026-10-07. Portfolio size $10,000.

Venues: CEX Bitfinex funding, Gate Uni lending, OKX Simple Earn, OKX margin; DeFi aave-v3, binance-staked-eth, coinbase-wrapped-staked-eth, ethena-usde, ether.fi-stake, fluid-lending, kamino-lend, kelp, lido, liquid-collective, maple, meth-protocol, morpho-blue, rocket-pool, sky-lending, spark-savings, sparklend, stader, stakewise-v3 (93 borrow and 69 lend rate series). Over the window ETH fell ~47%, BTC ~35% and SOL ~54%, so collateral management was tested hard.

## 1. Headline: does the carry beat simply lending your coins?

| You hold | Best plain lend / stake (full year) | Best carry trade (full year) | Carry lift | Carry, out-of-sample | Lend, out-of-sample | Winner out-of-sample (risk-adjusted) |
|---|---|---|---|---|---|---|
| Stablecoins (USDC) | Stake USDC -> SYRUPUSDC (maple) [Ethereum]: 5.21% | USDC on Aave v3 Ethereum, borrow USDT -> Stake USDC -> SYRUPUSDC (maple) [Ethereum]: 4.00% | -1.22 pp | 3.98% | 4.82% | lend only |
| ETH | Stake WETH -> WBETH (binance-staked-eth) [Ethereum]: 2.47% | WSTETH on Morpho WSTETH/USDT 86.0% (Ethereum), borrow USDT -> Stake USDC -> SYRUPUSDC (maple) [Ethereum]: 2.64% | +0.17 pp | 2.10% | 2.19% | lend only |
| BTC | hold: 0.00% | WBTC on Morpho WBTC/USDT 86.0% (Ethereum), borrow USDT -> Stake USDC -> SYRUPUSDC (maple) [Ethereum]: 0.10% | +0.10 pp | -0.48% | 0.00% | lend only |
| SOL | Kamino (Solana) JITOSOL: 5.52% | JITOSOL on Kamino (Solana), borrow USDT -> Bitfinex funding USDT: 5.31% | -0.20 pp | 3.22% | 2.97% | **carry** |

Full-year columns are picked with hindsight; the out-of-sample columns pick on the first half and are scored only on the second half, which is what you could actually have earned.

## 2. The spreads themselves: borrow here, lend there (per $10,000 borrowed)

Spread = lend APR - borrow APR on the same coin (or a 1:1 stablecoin swap). This is the carry on the *borrowed* money only, before the cost of the collateral you must post. One row per borrow venue / lend venue, best five per asset.

| Asset | Borrow at | Avg borrow | Lend at | Avg lend | Avg spread | Days positive | Worst 30 days | 1st half / 2nd half | $/yr per $10,000 borrowed |
|---|---|---|---|---|---|---|---|---|---|
| USD | OKX margin USDT | 2.88% | Stake USDC -> SYRUPUSDC (maple) USDC [Ethereum] | 5.25% | **+2.37 pp** | 100% | +1.47 pp | +2.65 / +2.09 | $237 |
| USD | OKX margin USDC | 2.98% | Stake USDC -> SYRUPUSDC (maple) USDC [Ethereum] | 5.25% | **+2.27 pp** | 99% | +1.43 pp | +2.57 / +1.97 | $227 |
| USD | OKX margin USDT | 2.88% | Bitfinex funding USD | 4.98% | **+2.10 pp** | 94% | +0.88 pp | +2.12 / +2.08 | $210 |
| USD | OKX margin USDT | 2.88% | Bitfinex funding USDT | 4.98% | **+2.10 pp** | 85% | +0.04 pp | +2.04 / +2.15 | $210 |
| USD | OKX margin USDC | 2.98% | Bitfinex funding USD | 4.98% | **+2.00 pp** | 92% | +0.67 pp | +2.03 / +1.97 | $200 |
| ETH | OKX margin WETH | 1.88% | Stake WETH -> CBETH (coinbase-wrapped-staked-eth) WETH [Ethereum] | 2.55% | **+0.67 pp** | 96% | -0.02 pp | +0.33 / +1.01 | $67 |
| ETH | OKX margin WETH | 1.88% | Stake WETH -> LSETH (liquid-collective) WETH [Ethereum] | 2.53% | **+0.65 pp** | 86% | -0.26 pp | +0.49 / +0.82 | $65 |
| ETH | OKX margin WETH | 1.88% | Stake WETH -> WBETH (binance-staked-eth) WETH [Ethereum] | 2.51% | **+0.63 pp** | 97% | -0.15 pp | +0.30 / +0.96 | $63 |
| ETH | OKX margin WETH | 1.88% | Stake WETH -> RSETH (kelp) WETH [Ethereum] | 2.50% | **+0.62 pp** | 82% | -0.61 pp | +0.32 / +0.92 | $62 |
| ETH | OKX margin WETH | 1.88% | Stake WETH -> ETHX (stader) WETH [Ethereum] | 2.46% | **+0.58 pp** | 97% | -0.28 pp | +0.34 / +0.82 | $58 |
| BTC | Aave v3 Ethereum CBBTC | 0.29% | OKX Simple Earn BTC | 0.53% | **+0.24 pp** | 51% | -0.28 pp | +0.73 / -0.24 | $24 |
| BTC | Aave v3 Ethereum WBTC | 0.34% | OKX Simple Earn BTC | 0.53% | **+0.18 pp** | 51% | -0.37 pp | +0.67 / -0.30 | $18 |
| BTC | Aave v3 Ethereum CBBTC | 0.29% | Gate Uni lending BTC | 0.17% | **-0.12 pp** | 22% | -0.29 pp | -0.00 / -0.23 | -$12 |
| BTC | Aave v3 Ethereum WBTC | 0.34% | Gate Uni lending BTC | 0.17% | **-0.17 pp** | 13% | -0.30 pp | -0.06 / -0.28 | -$17 |
| BTC | Aave v3 Ethereum CBBTC | 0.29% | Lend WBTC on aave-v3 WBTC [Arbitrum] | 0.04% | **-0.25 pp** | 0% | -0.33 pp | -0.24 / -0.26 | -$25 |
| SOL | OKX margin SOL | 5.47% | Kamino (Solana) JITOSOL [Solana] | 5.62% | **+0.15 pp** | 92% | -2.92 pp | -0.39 / +0.69 | $15 |
| SOL | OKX margin SOL | 5.47% | Kamino (Solana) SOL [Solana] | 5.12% | **-0.35 pp** | 47% | -4.06 pp | -1.82 / +1.11 | -$35 |
| SOL | OKX margin SOL | 5.47% | Gate Uni lending SOL | 4.27% | **-1.20 pp** | 5% | -4.84 pp | -1.87 / -0.54 | -$120 |
| SOL | Kamino (Solana) SOL | 6.85% | Kamino (Solana) JITOSOL [Solana] | 5.62% | **-1.23 pp** | 31% | -5.16 pp | -0.29 / -2.17 | -$123 |
| SOL | OKX margin SOL | 5.47% | Bitfinex funding SOL | 3.61% | **-1.87 pp** | 4% | -6.43 pp | -1.12 / -2.61 | -$187 |

## 3. Running it with $10,000: best five carry trades per starting coin (full year)

The borrowed amount is limited by your collateral: `LTV used` is the share of the max LTV borrowed (50% when collateral and debt are different coins, 80% when they move together), re-sized weekly and cut early if the health factor drops. APY = net income / average capital, after gas, withdrawal, bridge and swap costs and liquidation penalties. Rates column: collateral yield / borrow / lend.

### Stablecoins (USDC)

| Collateral & borrow | Lend at | LTV used | Rates (avg) | Net APY | Profit on $10,000 | vs best plain lend | Risk-adj. APY | Worst 30 days | Min HF | Rebalances | Liquidations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| no borrowing (baseline) | Stake USDC -> SYRUPUSDC (maple) [Ethereum] | - | - / - / 5.25% | 5.21% | $536 |  | 4.91% | 4.32% | n/a | 0 | 0 |
| USDC on Aave v3 Ethereum, borrow USDT | Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 80% of 75% | 3.58% / 4.36% / 5.25% | 4.00% | $408 | -1.22 pp | 3.74% | 2.71% | 1.29 | 0 | 0 |
| USDC on Aave v3 Ethereum, borrow USDC | Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 80% of 75% | 3.58% / 4.67% / 5.25% | 3.84% | $392 | -1.37 pp | 3.58% | 2.68% | 1.29 | 0 | 0 |
| USDC on Kamino (Solana), borrow USDT | Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 80% of 80% | 3.93% / 5.14% / 5.25% | 3.87% | $394 | -1.35 pp | 3.57% | 2.06% | 1.39 | 0 | 0 |
| USDC on Aave v3 Ethereum, borrow USDT | Stake USDT -> SYRUPUSDT (maple) [Ethereum] | 80% of 75% | 3.58% / 4.36% / 4.75% | 3.73% | $380 | -1.48 pp | 3.41% | 2.51% | 1.29 | 0 | 0 |
| USDC on Aave v3 Ethereum, borrow USDT | Bitfinex funding USDT | 80% of 75% | 3.58% / 4.36% / 4.98% | 3.88% | $395 | -1.34 pp | 3.34% | 1.61% | 1.29 | 0 | 0 |

Collateral already sitting idle on OKX (e.g. trading margin): the best overlay is USDC on OKX margin, borrow USDT -> Stake USDC -> SYRUPUSDC (maple) [Ethereum]: **1.38%** ($139 on $10,000) instead of 0%.

### ETH

| Collateral & borrow | Lend at | LTV used | Rates (avg) | Net APY | Profit on $10,000 | vs best plain lend | Risk-adj. APY | Worst 30 days | Min HF | Rebalances | Liquidations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| no borrowing (baseline) | Stake WETH -> WBETH (binance-staked-eth) [Ethereum] | - | - / - / 2.51% | 2.47% | $140 |  | 2.31% | 2.22% | n/a | 0 | 0 |
| WSTETH on Morpho WSTETH/USDT 86.0% (Ethereum), borrow USDT | Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 50% of 86% | 2.44% / 3.71% / 5.25% | 2.64% | $150 | +0.17 pp | 2.24% | 1.54% | 1.54 | 5 | 0 |
| WSTETH on Morpho WSTETH/WETH 94.5% (Ethereum), borrow WETH | Stake WETH -> WBETH (binance-staked-eth) [Ethereum] | 80% of 94% | 2.44% / 2.09% / 2.51% | 2.51% | $142 | +0.04 pp | 2.18% | 2.16% | 1.25 | 0 | 0 |
| WSTETH on Morpho WSTETH/WETH 94.5% (Ethereum), borrow WETH | Stake WETH -> WEETH (ether.fi-stake) [Ethereum] | 80% of 94% | 2.44% / 2.09% / 2.45% | 2.47% | $140 | -0.00 pp | 2.14% | 2.09% | 1.25 | 0 | 0 |
| WSTETH on Morpho WSTETH/WETH 94.5% (Ethereum), borrow WETH | Stake WETH -> WSTETH (lido) [Ethereum] | 80% of 94% | 2.44% / 2.09% / 2.44% | 2.46% | $140 | -0.01 pp | 2.14% | 2.01% | 1.25 | 0 | 0 |
| WSTETH on Morpho WSTETH/WETH 94.5% (Ethereum), borrow WETH | Stake WETH -> LSETH (liquid-collective) [Ethereum] | 80% of 94% | 2.44% / 2.09% / 2.53% | 2.54% | $144 | +0.07 pp | 2.09% | 1.95% | 1.25 | 0 | 0 |

Collateral already sitting idle on OKX (e.g. trading margin): the best overlay is WETH on OKX margin, borrow USDT -> Stake USDC -> SYRUPUSDC (maple) [Ethereum]: **0.55%** ($31 on $10,000) instead of 0%.

### BTC

| Collateral & borrow | Lend at | LTV used | Rates (avg) | Net APY | Profit on $10,000 | vs best plain lend | Risk-adj. APY | Worst 30 days | Min HF | Rebalances | Liquidations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| no borrowing (baseline) | hold | - | - / - / 0.00% | 0.00% | $0 |  | 0.00% | 0.00% | n/a | 0 | 0 |
| WBTC on Morpho WBTC/USDT 86.0% (Ethereum), borrow USDT | Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 50% of 86% | 0.00% / 3.73% / 5.25% | 0.10% | $6 | +0.10 pp | -0.15% | -0.90% | 1.60 | 5 | 0 |
| CBBTC on Morpho CBBTC/USDC 86.0% (Ethereum), borrow USDC | Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 50% of 86% | 0.00% / 4.19% / 5.25% | -0.10% | -$7 | -0.10 pp | -0.34% | -0.52% | 1.60 | 5 | 0 |
| WBTC on Morpho WBTC/USDC 86.0% (Ethereum), borrow USDC | Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 50% of 86% | 0.00% / 4.22% / 5.25% | -0.12% | -$8 | -0.12 pp | -0.36% | -0.55% | 1.60 | 5 | 0 |
| WBTC on Morpho WBTC/USDT 86.0% (Ethereum), borrow USDT | Stake USDT -> SYRUPUSDT (maple) [Ethereum] | 50% of 86% | 0.00% / 3.73% / 4.75% | -0.09% | -$6 | -0.09 pp | -0.38% | -1.22% | 1.60 | 5 | 0 |
| WBTC on Morpho WBTC/USDT 86.0% (Ethereum), borrow USDT | Bitfinex funding USDT | 50% of 86% | 0.00% / 3.73% / 4.98% | 0.01% | $1 | +0.01 pp | -0.43% | -1.05% | 1.60 | 5 | 0 |

Collateral already sitting idle on OKX (e.g. trading margin): the best overlay is BTC on OKX margin, borrow USDT -> Stake USDC -> SYRUPUSDC (maple) [Ethereum]: **0.58%** ($38 on $10,000) instead of 0%.

### SOL

| Collateral & borrow | Lend at | LTV used | Rates (avg) | Net APY | Profit on $10,000 | vs best plain lend | Risk-adj. APY | Worst 30 days | Min HF | Rebalances | Liquidations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| no borrowing (baseline) | Kamino (Solana) JITOSOL | - | - / - / 5.62% | 5.52% | $271 |  | 4.98% | 4.83% | n/a | 0 | 0 |
| JITOSOL on Kamino (Solana), borrow USDT | Bitfinex funding USDT | 50% of 63% | 5.62% / 5.14% / 4.98% | 5.31% | $261 | -0.20 pp | 4.63% | 4.64% | 1.55 | 9 | 0 |
| JITOSOL on Kamino (Solana), borrow USDC | Bitfinex funding USDT | 50% of 63% | 5.62% / 5.60% / 4.98% | 5.23% | $257 | -0.29 pp | 4.55% | 3.79% | 1.55 | 9 | 0 |
| JITOSOL on Kamino (Solana), borrow USDT | Kamino (Solana) USDC | 50% of 63% | 5.62% / 5.14% / 3.93% | 5.04% | $247 | -0.48 pp | 4.50% | 4.55% | 1.55 | 9 | 0 |
| JITOSOL on Kamino (Solana), borrow USDT | morpho-blue GTUSDCP vault [Base] | 50% of 63% | 5.62% / 5.14% / 4.75% | 5.10% | $251 | -0.42 pp | 4.40% | 3.99% | 1.55 | 9 | 0 |
| JITOSOL on Kamino (Solana), borrow SOL | Kamino (Solana) JITOSOL | 80% of 50% | 5.62% / 6.85% / 5.62% | 5.03% | $247 | -0.49 pp | 4.39% | 3.10% | 1.27 | 0 | 0 |

Collateral already sitting idle on OKX (e.g. trading margin): the best overlay is SOL on OKX margin, borrow USDT -> morpho-blue GTUSDCP vault [Base]: **0.64%** ($31 on $10,000) instead of 0%.

## 4. Walk-forward test (no hindsight)

Strategies are chosen on the first half (2025-10-08 to 2026-04-07) and run on the second half only. *Rotating* re-checks every 7 days and moves the lent funds to whichever venue paid the most over the previous 14 days (if it is 0.5 pp better), paying the transfer costs. *Hindsight* is the best possible pick, for reference only.

| You hold | Strategy | Positions | Net APY | Profit (half year) | Risk-adj. APY | Venue switches | Liquidations |
|---|---|---|---|---|---|---|---|
| Stablecoins (USDC) | Plain lend, picked on 1st half | Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 4.82% | $245 | 4.52% | 0 | 0 |
| Stablecoins (USDC) | Plain lend, rotating | rotating: Stake USDC -> SYRUPUSDC (maple) -> fluid-lending USDT vault -> Lend USDT on aave-v3 -> Lend USDE on aave-v3 -> Kamino (Solana) -> fluid-lending USDC vault -> Bitfinex funding -> Gate Uni lending | 4.03% | $205 | 3.34% | 9 | 0 |
| Stablecoins (USDC) | Carry, picked on 1st half | USDC on Aave v3 Ethereum, borrow USDT -> Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 3.98% | $202 | 3.72% | 0 | 0 |
| Stablecoins (USDC) | Carry, rotating lend venue | USDC on Aave v3 Ethereum, borrow USDT -> rotating: Stake USDC -> SYRUPUSDC (maple) -> fluid-lending USDT vault -> Lend USDE on aave-v3 -> Kamino (Solana) -> fluid-lending USDC vault -> Bitfinex funding -> Gate Uni lending | 3.40% | $172 | 2.90% | 8 | 0 |
| Stablecoins (USDC) | Plain lend, hindsight best | Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 4.82% | $245 | 4.52% | 0 | 0 |
| Stablecoins (USDC) | Carry, hindsight best | USDC on Kamino (Solana), borrow USDT -> Kamino (Solana) USDC | 4.22% | $214 | 3.92% | 0 | 0 |
| ETH | Plain lend, picked on 1st half | Stake WETH -> LSETH (liquid-collective) [Ethereum] | 2.19% | $106 | 1.87% | 0 | 0 |
| ETH | Plain lend, rotating | rotating: Stake WETH -> LSETH (liquid-collective) -> Lend WETH on aave-v3 -> Stake WETH -> CBETH (coinbase-wrapped-staked-eth) -> Stake WETH -> RSETH (kelp) | 2.21% | $107 | 1.81% | 3 | 0 |
| ETH | Carry, picked on 1st half | WSTETH on Morpho WSTETH/USDT 86.0% (Ethereum), borrow USDT -> Stake USDC -> SYRUPUSDC (maple) [Ethereum] | 2.10% | $102 | 1.69% | 0 | 0 |
| ETH | Carry, rotating lend venue | WSTETH on Morpho WSTETH/USDT 86.0% (Ethereum), borrow USDT -> rotating: Stake USDC -> SYRUPUSDC (maple) -> fluid-lending USDT vault -> Lend USDT on aave-v3 -> Lend USDE on aave-v3 -> Kamino (Solana) -> fluid-lending USDC vault -> Bitfinex funding -> Gate Uni lending | 1.46% | $71 | 0.89% | 9 | 0 |
| ETH | Plain lend, hindsight best | Stake WETH -> WBETH (binance-staked-eth) [Ethereum] | 2.34% | $113 | 2.18% | 0 | 0 |
| ETH | Carry, hindsight best | WSTETH on Morpho WSTETH/WETH 94.5% (Ethereum), borrow WETH -> Stake WETH -> WBETH (binance-staked-eth) [Ethereum] | 2.15% | $104 | 1.82% | 0 | 0 |
| BTC | Plain lend, picked on 1st half | hold | 0.00% | $0 | 0.00% | 0 | 0 |
| BTC | Carry, picked on 1st half | WBTC on Morpho WBTC/USDT 86.0% (Ethereum), borrow USDT -> Stake USDC -> SYRUPUSDC (maple) [Ethereum] | -0.48% | -$24 | -0.72% | 0 | 0 |
| BTC | Carry, rotating lend venue | WBTC on Morpho WBTC/USDT 86.0% (Ethereum), borrow USDT -> rotating: Stake USDC -> SYRUPUSDC (maple) -> fluid-lending USDT vault -> Lend USDT on aave-v3 -> Lend USDE on aave-v3 -> Kamino (Solana) -> fluid-lending USDC vault -> Bitfinex funding -> Gate Uni lending | -1.09% | -$55 | -1.49% | 9 | 0 |
| BTC | Plain lend, hindsight best | hold | 0.00% | $0 | 0.00% | 0 | 0 |
| BTC | Carry, hindsight best | WBTC on Aave v3 Arbitrum, borrow USDC -> Kamino (Solana) USDC | -0.24% | -$12 | -0.60% | 0 | 0 |
| SOL | Plain lend, picked on 1st half | OKX Simple Earn SOL | 2.97% | $156 | 2.47% | 0 | 0 |
| SOL | Plain lend, rotating | rotating: OKX Simple Earn -> Kamino (Solana) -> Gate Uni lending | 4.59% | $242 | 4.16% | 7 | 0 |
| SOL | Carry, picked on 1st half | JITOSOL on Kamino (Solana), borrow SOL -> OKX Simple Earn SOL | 3.22% | $169 | 2.60% | 0 | 0 |
| SOL | Carry, rotating lend venue | JITOSOL on Kamino (Solana), borrow SOL -> rotating: OKX Simple Earn -> Kamino (Solana) -> Gate Uni lending | 3.85% | $203 | 3.20% | 3 | 0 |
| SOL | Plain lend, hindsight best | Kamino (Solana) | 5.67% | $300 | 5.37% | 0 | 0 |
| SOL | Carry, hindsight best | SOL on Kamino (Solana), borrow USDT -> Kamino (Solana) USDC | 5.37% | $283 | 5.07% | 0 | 0 |

## 5. Leverage and babysitting: managed vs set-and-forget

The best full-year carry for each coin, at different shares of max LTV. *Managed* = weekly re-sizing plus an emergency deleverage if the health factor falls halfway to 1. *Set-and-forget* = never touch it after opening.

| You hold | LTV used | Managed APY | Managed min HF | Managed liquidations | Set-and-forget APY | Set-and-forget min HF | Set-and-forget liquidations | Liquidation penalties paid |
|---|---|---|---|---|---|---|---|---|
| Stablecoins (USDC) | 30% | 3.68% | 3.44 | 0 | 3.68% | 3.44 | 0 | $0 |
| Stablecoins (USDC) | 50% | 3.81% | 2.06 | 0 | 3.81% | 2.06 | 0 | $0 |
| Stablecoins (USDC) | 70% | 3.93% | 1.47 | 0 | 3.93% | 1.47 | 0 | $0 |
| Stablecoins (USDC) | 90% | 4.06% | 1.15 | 0 | 4.06% | 1.15 | 0 | $0 |
| ETH | 30% | 2.35% | 2.57 | 0 | 2.86% | 1.16 | 0 | $0 |
| ETH | 50% | 2.64% | 1.54 | 0 | 0.73% | 1.03 | 2 | $191 |
| ETH | 70% | 2.57% | 1.21 | 0 | 0.64% | 1.00 | 3 | $266 |
| ETH | 90% | 1.04% | 1.06 | 1 | 0.70% | 1.00 | 5 | $340 |
| BTC | 30% | -0.19% | 2.67 | 0 | 0.21% | 1.55 | 0 | $0 |
| BTC | 50% | 0.10% | 1.60 | 0 | -0.92% | 1.01 | 2 | $145 |
| BTC | 70% | 0.39% | 1.22 | 0 | -0.17% | 1.00 | 6 | $262 |
| BTC | 90% | -0.49% | 1.06 | 1 | 0.37% | 1.00 | 6 | $340 |
| SOL | 30% | 5.34% | 2.59 | 0 | 3.85% | 1.00 | 1 | $78 |
| SOL | 50% | 5.31% | 1.55 | 0 | 0.16% | 1.02 | 1 | $257 |
| SOL | 70% | 5.28% | 1.24 | 0 | -0.99% | 1.02 | 1 | $355 |
| SOL | 90% | 1.14% | 1.08 | 1 | -2.11% | 1.01 | 4 | $457 |

## 6. Average rates by venue over the year

**USD** (cheapest six borrow venues, richest six lend venues)

| Side | Venue | Coin | Where | 1-year avg | Last 30 days | Daily range |
|---|---|---|---|---|---|---|
| borrow | OKX margin | USDT | CEX | 2.88% | 3.52% | 1.00% to 5.00% |
| borrow | OKX margin | USDC | CEX | 2.98% | 3.53% | 1.00% to 7.19% |
| borrow | Morpho WSTETH/USDT 86.0% (Ethereum) | USDT | Ethereum | 3.71% | 4.04% | 1.96% to 10.84% |
| borrow | Morpho WBTC/USDT 86.0% (Ethereum) | USDT | Ethereum | 3.73% | 4.06% | 1.86% to 10.98% |
| borrow | Aave v3 Arbitrum | USDC | Arbitrum | 4.06% | 3.99% | 2.44% to 11.86% |
| borrow | Morpho CBBTC/USDC 86.0% (Ethereum) | USDC | Ethereum | 4.19% | 4.92% | 2.54% to 6.34% |
| lend | Stake USDC -> SYRUPUSDC (maple) | USDC | Ethereum | 5.25% | 5.08% | 4.18% to 7.97% |
| lend | Bitfinex funding | USD | CEX | 4.98% | 5.48% | 2.15% to 10.14% |
| lend | Bitfinex funding | USDT | CEX | 4.98% | 5.39% | 0.37% to 16.11% |
| lend | Stake USDT -> SYRUPUSDT (maple) | USDT | Ethereum | 4.75% | 4.95% | 3.63% to 7.56% |
| lend | morpho-blue GTUSDCP vault | USDC | Base | 4.75% | 4.36% | 2.70% to 7.15% |
| lend | fluid-lending USDC vault | USDC | Ethereum | 4.63% | 4.48% | 2.37% to 22.59% |

**ETH** (cheapest six borrow venues, richest six lend venues)

| Side | Venue | Coin | Where | 1-year avg | Last 30 days | Daily range |
|---|---|---|---|---|---|---|
| borrow | OKX margin | WETH | CEX | 1.88% | 1.00% | 1.00% to 13.65% |
| borrow | Morpho WSTETH/WETH 94.5% (Ethereum) | WETH | Ethereum | 2.09% | 2.08% | 1.16% to 7.86% |
| borrow | Morpho WSTETH/WETH 96.5% (Ethereum) | WETH | Ethereum | 2.21% | 2.16% | 1.23% to 7.77% |
| borrow | Aave v3 Base | WETH | Base | 2.33% | 2.20% | 1.32% to 3.99% |
| borrow | Aave v3 Arbitrum | WETH | Arbitrum | 2.34% | 2.03% | 1.35% to 6.44% |
| borrow | Aave v3 Ethereum | WETH | Ethereum | 2.36% | 2.07% | 1.67% to 7.70% |
| lend | Stake WETH -> CBETH (coinbase-wrapped-staked-eth) | WETH | Ethereum | 2.55% | 2.35% | 0.00% to 12.20% |
| lend | Stake WETH -> LSETH (liquid-collective) | WETH | Ethereum | 2.53% | 2.33% | 1.73% to 5.16% |
| lend | Stake WETH -> WBETH (binance-staked-eth) | WETH | Ethereum | 2.51% | 2.23% | 2.13% to 5.33% |
| lend | Stake WETH -> RSETH (kelp) | WETH | Ethereum | 2.50% | 2.35% | 0.25% to 10.13% |
| lend | Stake WETH -> ETHX (stader) | WETH | Ethereum | 2.46% | 2.26% | 0.00% to 7.47% |
| lend | Stake WETH -> WEETH (ether.fi-stake) | WETH | Ethereum | 2.45% | 2.32% | 0.02% to 4.15% |

**BTC** (cheapest six borrow venues, richest six lend venues)

| Side | Venue | Coin | Where | 1-year avg | Last 30 days | Daily range |
|---|---|---|---|---|---|---|
| borrow | Aave v3 Ethereum | CBBTC | Ethereum | 0.29% | 0.29% | 0.07% to 0.51% |
| borrow | Aave v3 Ethereum | WBTC | Ethereum | 0.34% | 0.32% | 0.13% to 0.57% |
| borrow | OKX margin | BTC | CEX | 0.79% | 0.50% | 0.50% to 1.00% |
| borrow | Aave v3 Base | CBBTC | Base | 0.83% | 0.67% | 0.35% to 1.44% |
| borrow | Aave v3 Arbitrum | WBTC | Arbitrum | 0.86% | 0.80% | 0.19% to 1.23% |
| lend | OKX Simple Earn | BTC | CEX | 0.53% | 0.01% | 0.01% to 1.00% |
| lend | Gate Uni lending | BTC | CEX | 0.17% | 0.07% | 0.05% to 0.40% |
| lend | Lend WBTC on aave-v3 | WBTC | Arbitrum | 0.04% | 0.02% | 0.01% to 0.06% |
| lend | Lend CBBTC on aave-v3 | CBBTC | Base | 0.03% | 0.01% | 0.01% to 0.10% |
| lend | Lend CBBTC on sparklend | CBBTC | Ethereum | 0.01% | 0.00% | 0.00% to 0.05% |
| lend | Lend WBTC on aave-v3 | WBTC | Ethereum | 0.01% | 0.00% | 0.00% to 0.01% |

**SOL** (cheapest six borrow venues, richest six lend venues)

| Side | Venue | Coin | Where | 1-year avg | Last 30 days | Daily range |
|---|---|---|---|---|---|---|
| borrow | OKX margin | SOL | CEX | 5.47% | 4.07% | 4.00% to 54.21% |
| borrow | Kamino (Solana) | SOL | Solana | 6.85% | 6.88% | 4.54% to 27.22% |
| lend | Kamino (Solana) | JITOSOL | Solana | 5.62% | 4.86% | 3.83% to 6.79% |
| lend | Kamino (Solana) | SOL | Solana | 5.12% | 5.25% | 3.09% to 21.96% |
| lend | OKX Simple Earn | SOL | CEX | 4.72% | 2.81% | 1.19% to 54.21% |
| lend | Gate Uni lending | SOL | CEX | 4.27% | 2.27% | 0.95% to 66.54% |
| lend | Bitfinex funding | SOL | CEX | 3.61% | 2.17% | 0.07% to 307.33% |

## How this works and what it assumes

- **Data.** OKX: public Simple Earn lending history (`rate` = what margin borrowers pay, which matches OKX's published VIP0 borrow rate; `lendingRate` = what lenders receive). Bitfinex: daily funding candles (2-30 day offers), midpoint of open/close, minus Bitfinex's 15% lender fee. Gate: Uni lending APR. Aave v3 (Ethereum, Arbitrum, Base) and Morpho: official APIs. Kamino: its public API. Other DeFi lend venues (Maple, Sky, Ethena, Spark, Fluid, Morpho vaults, liquid staking): DefiLlama daily history, reward tokens counted at 50%. Prices: DefiLlama.
- **Not covered:** Binance and Bybit block API access from this environment; KuCoin only publishes 7 days; Compound's API was unreachable. Bitfinex and Gate are lend-only here (Bitfinex margin loans cannot be withdrawn).
- **Mechanics.** Collateral earns what the borrow venue pays on it (Aave supply APY, Kamino supply APY) plus its own staking yield (wstETH, JitoSOL); collateral on OKX and Morpho earns nothing. OKX margin is approximated as 75% max LTV / 90% liquidation LTV for stablecoin collateral and 70% / 85% for BTC, ETH and SOL. Liquidation repays 50% of the debt (100% below HF 0.95) and charges the venue's penalty.
- **Costs.** Gas $1.50 per action on Ethereum, $0.05 on L2s, $0.01 on Solana; CEX withdrawal $1 (stablecoins), $1.50 (ETH), $5 (BTC), $0.10 (SOL); bridges $1 + 3 bps; swaps 3 bps (stables), 5 bps (ETH, SOL), 10 bps (BTC), 10 bps USDT->fiat USD on Bitfinex.
- **Risk-adj. APY** subtracts expected losses from venue failures: annual failure probability (OKX 1%, Bitfinex 1.5%, Gate 2%; DeFi from the protocol risk model) x 50% loss x the money sitting there, plus issuer risk on staked tokens.
- **Caveats.** Venue list is today's large venues (survivorship bias). CEX rates are the advertised market rate; your fill may differ. Borrow caps, withdrawal limits and KYC are not modelled. Past spreads are not future spreads. Not financial advice.

