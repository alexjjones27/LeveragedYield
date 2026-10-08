# Leveraged Yield Optimizer

Finds the best way to run a **recursive borrow-and-deploy loop** in DeFi and checks that it
actually beats simply lending or staking your collateral.

The strategy being optimised:

1. Post your starting capital (e.g. $10,000 of USDC, ETH or wstETH) as collateral on a lending
   market.
2. Borrow a token against it, up to the market's max LTV (typically 75-95%).
3. Put the borrowed token to work on a lending / staking platform (Lido, ether.fi, Aave supply,
   a Morpho vault, sUSDe, ...).
4. If what you receive (wstETH, weETH, an Aave supply position ...) is itself accepted as
   collateral, post it and borrow again. Repeat until the next borrow is dust or no longer
   pays for its gas.

For every combination of **collateral × lending market × borrowed asset × yield venue ×
loop market** the optimiser picks how much of the max LTV to use and how many loops to run,
then ranks combinations by net APY *and* by a risk-adjusted APY.

**Latest results for a $10,000 portfolio: [RESULTS.md](RESULTS.md)** (every winning
combination: [`results/strategies.csv`](results/strategies.csv)).

### Second tool: cross-venue carry trade backtest

`python -m leveraged_yield.carry` backtests the simpler **borrow cheap here, lend rich there**
trade across centralised exchanges (OKX, Bitfinex, Gate) and DeFi (Aave, Morpho, Kamino,
Maple, Sky, Ethena, Spark, Fluid, liquid staking) on a year of daily rates:

* the raw spreads for every borrow venue / lend venue pair (USD, ETH, BTC, SOL),
* what a $10,000 holder of USDC, ETH, BTC or SOL actually earns once the collateral needed
  to borrow is accounted for, versus simply lending or staking the same coins,
* a walk-forward test (choose on the first six months, score on the last six), weekly
  venue rotation, and managed vs set-and-forget positions through real price crashes.

**Results: [CARRY_RESULTS.md](CARRY_RESULTS.md)** (CSV: `results/carry_pairs.csv`,
`results/carry_strategies.csv`). Code: `leveraged_yield/carry/`. `--refresh` re-downloads the
history (a few minutes); otherwise the committed snapshot in `data/carry/` is used.

## Quick start

```bash
pip install -r requirements.txt
python -m leveraged_yield                     # uses the committed data snapshot
python -m leveraged_yield --refresh           # pull live rates first (DefiLlama + Aave API)
python -m leveraged_yield --collateral USDC --capital 25000 --chains Ethereum,Base
python -m pytest                              # offline unit tests
```

Useful options: `--min-health-factor 1.25` (more conservative), `--risk-aversion 0` (rank on
expected value only), `--yield-basis spot` (use current APYs instead of min(spot, 30-day mean)),
`--venue-categories ...` / `--min-protocol-tvl ...` (widen or narrow the universe),
`--no-backtest`. Every assumption lives in [`leveraged_yield/config.py`](leveraged_yield/config.py).

## How it works

### Loop maths

With capital `E`, first-leg LTV `L1`, loop-leg LTV `L2` and utilisation `u` (share of the max
LTV used on each borrow; `u = 1` is "borrow the full 80%"):

```
b1      = u * L1 * E                    first borrow
b(k+1)  = u * L2 * b(k)                 each re-posted tranche supports the next borrow
D       = sum(b)  ->  u*L1*E / (1 - u*L2) as loops -> infinity
NetAPY  = [E*y_collateral + D*y_venue - b1*c1 - (D - b1)*c2] / E  -  costs
HF      = sum(collateral_i * LiqThreshold_i) / debt
```

`y_venue` includes the native yield of the receipt token (wstETH's staking yield) and any supply
APY paid on it when re-posted. `c1, c2` are borrow APYs **plus the native yield of the borrowed
token** (borrowing JitoSOL means owing an asset that appreciates against SOL). Costs are DEX
swaps, LST exit spreads and per-loop gas, amortised over the holding period.

### Risk model (the "downside" half of the objective)

`Risk-adjusted APY = Net APY - liquidation loss - protocol loss - spread-risk charge`

* **Liquidation loss**: for each account, the price move that triggers liquidation (collateral
  vs debt across asset families, e.g. ETH vs USD) and the depeg that triggers it (wstETH vs
  WETH, USDC vs AUSD). The probability of touching that level within a year uses a barrier
  model with family volatilities; the loss is that probability × liquidation penalty × debt.
* **Protocol loss**: every protocol in the stack (lender, venue, collateral token issuer) has
  an annual failure rate from its DefiLlama category, scaled by the TVL of that specific chain
  deployment and its age; loss = 50% of the exposure, capped at your equity.
* **Spread risk**: a mean-variance charge on the carry spread (venue yield − borrow cost)
  moving against you. It scales with leverage and is larger for thin markets.
* **Hard constraints**: health factor ≥ 1.10 after looping and ≥ 1.02 at every step while
  looping (the moment after a borrow and before re-posting).

Reported alongside: stress APY (spread −2pp), 5th-percentile APY, health factor, distance to
liquidation, and a comparison with the literal "100% LTV until dust" process.

### Baseline

For each collateral the baseline is the best risk-adjusted way to *just* lend or stake it
(same venue universe, same chain as the token, no borrowing). A combination is only reported
as a winner if it beats that baseline on **both** net APY and risk-adjusted APY.

### Backtest

The top combinations are replayed over the last 180 days of real daily rates: borrow history
from the Aave v3 API and the Morpho Blue API, supply/staking history from DefiLlama. Lenders
without free borrow history (Spark, Compound, Dolomite, Kamino, ...) are marked n/a. This tests
the carry only, not price paths.

### Data

| Source | Used for |
|---|---|
| DefiLlama `yields.llama.fi/pools`, `/lendBorrow` | supply, staking and borrow APYs, LTVs, liquidity for ~all lenders |
| DefiLlama `api.llama.fi/protocols` | protocol category, TVL per chain, listing date |
| Aave v3 API `api.v3.aave.com/graphql` | exact LTV, liquidation threshold, penalty and **E-mode** categories; rate history |
| Morpho Blue API `blue-api.morpho.org/graphql` | borrow-rate history for backtests |

A trimmed snapshot (`data/snapshot/market_snapshot.json.gz`) is committed so results are
reproducible; `--refresh` replaces it.

## Layout

```
leveraged_yield/
  config.py      all tunable assumptions
  assets.py      symbol normalisation, price families
  universe.py    raw data -> borrow routes (incl. Aave E-mode), venues, native yields
  model.py       loop schedule, P&L, health factor, liquidation / protocol / spread risk
  optimizer.py   enumerate combinations, choose utilisation + loops, baselines
  backtest.py    replay positions over historical rates
  report.py      RESULTS.md and CSV
  sources/       DefiLlama, Aave and Morpho clients; snapshot store
tests/           synthetic-market unit tests
```

## Limitations

* Rates are a snapshot and move quickly, especially in small markets. Rerun with `--refresh`
  before acting.
* Liquidation thresholds outside Aave and Morpho are estimated as LTV + 3pp, and Spark /
  Kamino E-modes are not modelled (their loops may be slightly better than shown).
* The manual loop is modelled step by step; flash-loan "one-click" looping reaches the same
  end state with less gas and no intermediate health-factor dip.
* Protocol failure rates and volatilities are judgement calls; they are explicit in
  `config.py` so you can change them.
* Nothing here is financial advice.
