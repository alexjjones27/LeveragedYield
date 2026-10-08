import pytest

from leveraged_yield.config import Settings
from leveraged_yield.optimizer import compute_baselines, optimize
from leveraged_yield.universe import build_universe, pool_apy

from .conftest import make_raw


def routes_for(uni, collateral, debt):
    return [r for r in uni.routes if r.collateral == collateral and r.debt == debt]


def test_aave_emode_parameters_are_applied(raw):
    uni = build_universe(raw, Settings())
    aave = {r.emode: r for r in routes_for(uni, "WSTETH", "WETH") if r.protocol == "aave-v3"}
    assert aave[None].ltv == pytest.approx(0.785) and aave[None].lt == pytest.approx(0.81)
    assert aave["ETH correlated"].ltv == pytest.approx(0.93)
    assert aave["ETH correlated"].lt == pytest.approx(0.95)
    assert aave["ETH correlated"].liq_penalty == pytest.approx(0.01)
    # E-mode only allows borrowing WETH, so no wstETH -> USDC route in E-mode.
    assert all(r.emode is None for r in routes_for(uni, "WSTETH", "USDC"))


def test_morpho_pair_uses_lltv_as_liquidation_threshold(raw):
    uni = build_universe(raw, Settings())
    (m,) = [r for r in routes_for(uni, "WSTETH", "WETH") if r.protocol == "morpho-blue"]
    assert m.ltv == m.lt == pytest.approx(0.945)
    assert 0 < m.liq_penalty < 0.03


def test_staking_venue_and_native_yield(raw):
    uni = build_universe(raw, Settings())
    assert uni.natives["WSTETH"].apy == pytest.approx(3.0)
    (lido,) = [v for v in uni.venues if v.protocol == "lido"]
    assert (lido.deposit, lido.receipt, lido.kind) == ("WETH", "WSTETH", "stake")
    vaults = [v for v in uni.venues if v.kind == "vault"]
    assert vaults and all(":" in v.receipt for v in vaults)  # vault shares cannot be looped


def test_lend_venue_receipt_is_bound_to_its_market(raw):
    uni = build_universe(raw, Settings())
    (weth,) = [v for v in uni.venues if v.kind == "lend" and v.deposit == "WETH"]
    assert weth.receipt_market == "aave-v3|Ethereum|AaveV3Ethereum"


def test_reward_haircut():
    p = {"apyBase": 2.0, "apyReward": 4.0, "apy": 6.0, "apyMean30d": None}
    assert pool_apy(p, "spot", 0.5) == pytest.approx(4.0)
    p["apyMean30d"] = 5.0
    assert pool_apy(p, "min", 0.5) == pytest.approx(3.0)


def test_optimizer_finds_loop_that_beats_holding(raw):
    s = Settings(collaterals=("WSTETH",))
    res = optimize(build_universe(raw, s))
    base = res.baselines["WSTETH"]
    assert base.label.startswith("Hold WSTETH") and base.net_apy == pytest.approx(3.0)
    winners = res.winners()
    assert winners
    best = winners[0].best
    assert best.net_apy > base.net_apy
    assert best.risk_adjusted_apy > base.risk_adjusted_apy
    assert best.spec.venue.protocol == "lido"
    assert best.spec.r2 is not None and best.loops > 1
    assert best.min_health_factor >= s.min_health_factor
    assert best.step_health_factor >= s.min_step_health_factor
    # The manual "100% LTV until dust" version levers harder than the optimised one.
    assert winners[0].literal.leverage > best.leverage


def test_negative_carry_is_never_selected():
    raw = make_raw(weth_borrow_apy=3.5, lido_apy=3.0)  # borrowing ETH costs more than staking pays
    res = optimize(build_universe(raw, Settings(collaterals=("WSTETH",))))
    loops = [o for o in res.outcomes if o.best.spec.r1.debt == "WETH"]
    assert all(o.best.spec.y_venue > min(o.best.spec.borrow_cost1, o.best.spec.borrow_cost2)
               for o in loops)
    assert not [o for o in res.winners() if o.best.spec.venue.protocol == "lido"]


def test_min_health_factor_is_enforced(raw):
    s = Settings(collaterals=("WSTETH",), min_health_factor=1.5)
    res = optimize(build_universe(raw, s))
    assert res.outcomes
    assert all(o.best.min_health_factor >= 1.5 for o in res.outcomes)


def test_baseline_for_usdc_includes_vault(raw):
    uni = build_universe(raw, Settings())
    best, raw_best = compute_baselines(uni, "USDC")
    assert raw_best.net_apy == pytest.approx(5.0, abs=0.05)  # STEAKUSDC vault
    assert best.risk_adjusted_apy <= best.net_apy
