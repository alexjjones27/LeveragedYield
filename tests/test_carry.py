"""Carry-trade simulator tests on synthetic venues with known rates."""

from datetime import date, timedelta

import pytest

from leveraged_yield.carry.data import CarryData, Leg
from leveraged_yield.carry.run import plans_for, run
from leveraged_yield.carry.sim import Market, Plan, SimConfig, series_on, simulate

DAYS = 120
END = date(2026, 1, 31)
DATES = [(END - timedelta(days=k)).isoformat() for k in range(DAYS - 1, -1, -1)]


def flat(apr: float) -> dict[str, float]:
    return {d: apr for d in DATES}


def lend(id_, venue, asset, apr, location="OKX", venue_type="CEX", p_fail=0.0):
    rates = apr if isinstance(apr, dict) else flat(apr)
    return Leg(id_, "lend", venue, venue.lower(), venue_type, location, asset, rates, p_fail)


def borrow(id_, venue, asset, apr, collateral, ltv, lt, coll_apr=0.0, location="OKX",
           venue_type="CEX", penalty=0.05):
    return Leg(id_, "borrow", venue, venue.lower(), venue_type, location, asset, flat(apr), 0.0,
               collateral=collateral, ltv=ltv, lt=lt, liq_penalty=penalty,
               collateral_rates=flat(coll_apr))


def market(prices=None, legs=()):
    data = CarryData(list(legs), prices or {"ETH": {d: 2000.0 for d in DATES}},
                     (END + timedelta(days=1)).isoformat() + "T00:00:00Z", DAYS)
    return Market(data, DATES), data


CFG = SimConfig(issuer_pfail={})


def test_series_on_fills_and_rejects_sparse_data():
    filled = series_on({DATES[0]: 1.0, DATES[5]: 2.0}, DATES[:8])
    assert filled == [1.0] * 5 + [2.0] * 3
    assert series_on({DATES[-1]: 1.0}, DATES) is None  # starts too late
    assert series_on({}, DATES) is None


def test_plain_lending_earns_its_rate():
    mkt, _ = market()
    r = simulate(Plan("USD", None, lend("l", "Bitfinex", "USDC", 5.0)), mkt, CFG)
    assert r.apy == pytest.approx(5.0, abs=0.05)
    assert r.liquidations == 0


def test_carry_earns_collateral_yield_plus_levered_spread():
    # Collateral earns 4%, borrow at 3%, lend at 5%: 4% + 0.8 * 0.75 * 2% = 5.2%.
    b = borrow("b", "Aave", "USDT", 3.0, "USDC", 0.75, 0.78, coll_apr=4.0)
    l = lend("l", "Bitfinex", "USDT", 5.0, location="Bitfinex")
    mkt, _ = market(legs=[b, l])
    r = simulate(Plan("USD", b, l, (), 0.8), mkt, CFG)
    assert r.apy == pytest.approx(5.2, abs=0.1)
    assert r.avg_lend - r.avg_borrow == pytest.approx(2.0)
    assert r.pct_days_positive_spread == 100.0
    assert r.costs_usd > 0  # withdrawal between venues is charged


def test_negative_spread_loses_against_lending():
    b = borrow("b", "Aave", "USDT", 6.0, "USDC", 0.75, 0.78, coll_apr=0.0)
    l = lend("l", "Bitfinex", "USDT", 5.0, location="Bitfinex")
    mkt, _ = market(legs=[b, l])
    assert simulate(Plan("USD", b, l, (), 0.8), mkt, CFG).apy < 0


def crash_prices(drop: float, days: int = 10):
    """ETH flat, then falls by ``drop`` over ``days`` days, then flat."""
    px, start = {}, 40
    for i, d in enumerate(DATES):
        k = min(max(i - start, 0), days) / days
        px[d] = 2000.0 * (1 - drop * k)
    return {"ETH": px}


def test_set_and_forget_gets_liquidated_in_a_crash_but_managed_does_not():
    b = borrow("b", "Aave", "USDC", 3.0, "WETH", 0.80, 0.83)
    l = lend("l", "Bitfinex", "USDC", 6.0, location="Bitfinex")
    mkt, _ = market(crash_prices(0.6), [b, l])
    plan = Plan("ETH", b, l, (), 0.8)
    managed = simulate(plan, mkt, CFG)
    forgotten = simulate(plan, mkt, SimConfig(issuer_pfail={}, managed=False))
    assert forgotten.liquidations >= 1
    assert forgotten.liquidation_loss_usd > 0
    assert managed.liquidations == 0
    assert managed.rebalances > 0
    assert managed.apy > forgotten.apy


def test_rotation_moves_to_the_better_venue_and_pays_for_it():
    low = lend("low", "OKX", "USDC", 2.0)
    late = {d: (2.0 if i < 30 else 8.0) for i, d in enumerate(DATES)}
    high = lend("high", "Bitfinex", "USDC", late, location="Bitfinex")
    mkt, _ = market(legs=[low, high])
    static = simulate(Plan("USD", None, low), mkt, CFG)
    rotating = simulate(Plan("USD", None, low, (low, high)), mkt, CFG)
    assert rotating.switches == 1
    assert rotating.lend_history[-1] == "Bitfinex"
    assert rotating.apy > static.apy


def test_same_venue_same_coin_is_not_a_carry():
    b = borrow("b", "OKX", "USDT", 3.0, "USDC", 0.75, 0.9)
    same = lend("okx-usdt", "OKX", "USDT", 2.5)
    other = lend("bfx-usdt", "Bitfinex", "USDT", 5.0, location="Bitfinex")
    mkt, data = market(legs=[b, same, other])
    carry, base = plans_for("USD", data, mkt, CFG)
    assert [p.lend.id for p in carry] == ["bfx-usdt"]
    assert {p.lend.id for p in base} == {"okx-usdt", "bfx-usdt"}


def test_walk_forward_picks_on_first_half_only():
    # Venue A pays more in the first half, venue B in the second: the walk-forward
    # pick must be A (chosen without seeing the second half) and lose to hindsight.
    half = DAYS // 2
    a = lend("a", "OKX", "USDC", {d: (6.0 if i < half else 1.0) for i, d in enumerate(DATES)})
    b = lend("b", "Bitfinex", "USDC", {d: (3.0 if i < half else 7.0) for i, d in enumerate(DATES)},
             location="Bitfinex")
    _, data = market(legs=[a, b])
    res = run(data, CFG).holders["USD"]
    assert res.is_base.plan.lend.id == "a"
    assert res.oos["picked_base"].apy < res.oos["hindsight_base"].apy
    assert res.oos["hindsight_base"].plan.lend.id == "b"
