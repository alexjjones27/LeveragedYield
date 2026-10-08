import math

import pytest

from leveraged_yield.config import Settings
from leveraged_yield.model import (
    Spec, account_risk, barrier_hit_probability, evaluate, step_health_factor, tranche_schedule,
)
from leveraged_yield.universe import Route, Venue


def route(ltv=0.8, lt=0.85, rate=3.0, account="acct", collateral="WSTETH", debt="WETH",
          penalty=0.05):
    return Route(id=f"{account}|{collateral}", protocol="lender", chain="Ethereum", market="m",
                 market_label="Lender", account=account, collateral=collateral, debt=debt, ltv=ltv,
                 lt=lt, liq_penalty=penalty, borrow_apy=rate, collateral_apy=0.0,
                 borrow_liquidity_usd=1e9, p_fail=0.0)


def venue(apy=5.0, receipt="WSTETH"):
    return Venue(id="v", protocol="staker", category="Liquid Staking", chain="Ethereum",
                 label="stake", deposit="WETH", receipt=receipt, receipt_market=None, apy=apy,
                 tvl_usd=1e9, entry_bps=0, exit_bps=0, pool_id=None, kind="stake", p_fail=0.0,
                 spread_vol_pp=0.0)


def spec(r1=None, r2="same", y_c=0.0, y_v=5.0, cost=3.0, capital=10_000.0, gas=0.0):
    r1 = r1 or route(rate=cost)
    if r2 == "same":
        r2 = r1
    return Spec(capital=capital, collateral="WSTETH", r1=r1, venue=venue(y_v), r2=r2,
                y_collateral=y_c, y_venue=y_v, borrow_cost1=cost, borrow_cost2=cost,
                entry_cost=0.0, exit_cost=0.0, gas_step_usd=gas, spread_vol_pp=0.0)


@pytest.fixture
def settings():
    return Settings(max_loops=500, dust_usd=1e-6, risk_aversion=0.0)


def test_infinite_loop_converges_to_geometric_limit(settings):
    sp = spec()
    tranches = tranche_schedule(sp, 1.0, settings)
    # Borrowing 80% of each new deposit forever: total debt = E * 0.8 / (1 - 0.8) = 4E.
    assert sum(tranches) == pytest.approx(4 * sp.capital, rel=1e-6)
    assert tranches[1] / tranches[0] == pytest.approx(0.8)


def test_carry_without_loop_route_borrows_once(settings):
    sp = spec(r2=None)
    assert tranche_schedule(sp, 0.5, settings) == [pytest.approx(0.5 * 0.8 * sp.capital)]


def test_net_apy_matches_hand_calculation(settings):
    sp = spec()
    sched = tranche_schedule(sp, 1.0, settings)
    res = evaluate(sp, 1.0, 3, sched, settings)
    # Tranches 8000 + 6400 + 5120 = 19520 earn 5% and cost 3%.
    assert res.debt == pytest.approx(19_520)
    assert res.net_apy == pytest.approx(19_520 * 2.0 / 10_000)
    assert res.leverage == pytest.approx(1 + 1.952)
    # Same account: HF = 0.85 * (E + deployed) / debt.
    assert res.min_health_factor == pytest.approx(0.85 * 29_520 / 19_520)


def test_gas_stops_unprofitable_loops():
    s = Settings(max_loops=500, dust_usd=10.0)
    sp = spec(y_v=3.1, cost=3.0, gas=5.0)  # 0.1% spread: a tranche must exceed $10k to pay $10 gas
    assert len(tranche_schedule(sp, 1.0, s)) == 1


def test_dust_stops_loops():
    s = Settings(max_loops=500, dust_usd=100.0)
    sched = tranche_schedule(spec(), 1.0, s)
    assert min(sched) >= 100.0
    assert 0.8 * sched[-1] < 100.0


def test_directional_buffer_for_stable_collateral_and_eth_debt(settings):
    a = account_risk("x", [("USDC", 10_000, 0.8)], "WETH", 4_000, 0.05, settings)
    assert a.health_factor == pytest.approx(2.0)
    assert a.directional_buffer == pytest.approx(0.5)  # USDC/ETH must fall 50%
    assert a.depeg_buffer is None
    assert 0 < a.p_liquidation < 1


def test_depeg_buffer_for_correlated_loop(settings):
    a = account_risk("x", [("WSTETH", 10_000, 0.95)], "WETH", 9_000, 0.01, settings)
    assert a.directional_buffer is None
    assert a.depeg_buffer == pytest.approx(1 - 9_000 / 9_500)


def test_identical_token_has_no_price_risk(settings):
    a = account_risk("x", [("USDC", 10_000, 0.8)], "USDC", 7_000, 0.05, settings)
    assert a.directional_buffer is None and a.depeg_buffer is None
    assert a.p_liquidation == 0.0


def test_barrier_probability_edges_and_monotonicity():
    assert barrier_hit_probability(None, 0.5, 1) == 0.0
    assert barrier_hit_probability(0.0, 0.5, 1) == 1.0
    assert barrier_hit_probability(1.0, 0.5, 1) == 0.0
    near = barrier_hit_probability(0.1, 0.5, 1)
    far = barrier_hit_probability(0.5, 0.5, 1)
    assert 1 >= near > far > 0
    assert barrier_hit_probability(0.1, 0.0, 1) == 0.0


def test_full_ltv_on_morpho_style_market_is_liquidatable_mid_process(settings):
    r = route(ltv=0.945, lt=0.945)  # Morpho: LTV == LLTV
    sp = spec(r1=r)
    sched = tranche_schedule(sp, 1.0, settings)
    assert step_health_factor(sp, sched[:5]) == pytest.approx(1.0)
    assert step_health_factor(sp, tranche_schedule(sp, 0.9, settings)[:5]) > 1.1


def test_separate_accounts_are_risked_separately(settings):
    r1 = route(ltv=0.75, lt=0.78, account="a1", collateral="USDC", debt="WETH")
    r2 = route(ltv=0.93, lt=0.95, account="a2")
    sp = Spec(capital=10_000, collateral="USDC", r1=r1, venue=venue(), r2=r2, y_collateral=0.0,
              y_venue=5.0, borrow_cost1=3.0, borrow_cost2=3.0, entry_cost=0.0, exit_cost=0.0,
              gas_step_usd=0.0)
    res = evaluate(sp, 0.8, 4, tranche_schedule(sp, 0.8, settings), settings)
    assert len(res.accounts) == 2
    first = res.accounts[0]
    assert first.health_factor == pytest.approx(0.78 / (0.8 * 0.75))
    assert first.directional_buffer is not None  # USDC collateral vs ETH debt
    assert res.accounts[1].depeg_buffer is not None  # wstETH vs WETH


def test_risk_adjusted_is_below_net(settings):
    s = Settings(risk_aversion=2.0)
    sp = spec()
    r1 = sp.r1
    sp = Spec(**{**sp.__dict__, "r1": Route(**{**r1.__dict__, "p_fail": 0.01}), "spread_vol_pp": 1.0})
    res = evaluate(sp, 0.9, 5, tranche_schedule(sp, 0.9, s), s)
    assert res.risk_adjusted_apy < res.net_apy
    assert res.stress_apy == pytest.approx(res.net_apy - res.debt / sp.capital * s.stress_spread_pp)
    assert math.isfinite(res.p5_apy)
