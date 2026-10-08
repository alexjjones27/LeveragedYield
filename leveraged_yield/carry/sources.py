"""Daily rate histories from centralised exchanges, Kamino and price feeds.

All functions return ``{ISO date: APR in percent}`` (prices: ``{ISO date: USD}``).
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone

from ..sources.http import get_json

OKX = "https://www.okx.com/api/v5/finance/savings/lending-rate-history"
BITFINEX = "https://api-pub.bitfinex.com/v2/candles/trade:1D:f{sym}:a30:p2:p30/hist"
GATE = "https://api.gateio.ws/api/v4/earn/uni/chart"
KAMINO = "https://api.kamino.finance"
COINS = "https://coins.llama.fi/chart"

BITFINEX_LENDER_FEE = 0.15  # Bitfinex keeps 15% of the interest lenders earn


def _day(ts_seconds: float) -> str:
    return datetime.fromtimestamp(ts_seconds, tz=timezone.utc).date().isoformat()


def _daily_mean(points: list[tuple[str, float]]) -> dict[str, float]:
    acc: dict[str, list[float]] = defaultdict(list)
    for day, value in points:
        acc[day].append(value)
    return {d: sum(v) / len(v) for d, v in acc.items()}


def okx_rates(ccy: str, days: int) -> tuple[dict[str, float], dict[str, float]]:
    """(borrow APR, lend APR) from OKX's public Simple Earn lending history.

    ``rate`` is the market rate margin borrowers pay (it matches the VIP0 borrow
    rate in /public/interest-rate-loan-quota); ``lendingRate`` is what lenders
    actually receive after OKX's cut. Hourly points are averaged per day.
    """
    cutoff_ms = (time.time() - days * 86400) * 1000
    borrow, lend = [], []
    after = None
    for _ in range(days * 24 // 100 + 5):
        url = f"{OKX}?ccy={ccy}&limit=100" + (f"&after={after}" if after else "")
        rows = get_json(url, max_age_s=6 * 3600).get("data") or []
        if not rows:
            break
        for r in rows:
            day = _day(int(r["ts"]) / 1000)
            borrow.append((day, float(r["rate"]) * 100))
            lend.append((day, float(r["lendingRate"]) * 100))
        after = rows[-1]["ts"]
        if int(after) < cutoff_ms:
            break
        time.sleep(0.12)  # stay well inside OKX's public rate limit
    return _daily_mean(borrow), _daily_mean(lend)


def bitfinex_lend(sym: str, days: int) -> dict[str, float]:
    """Lender APR on Bitfinex margin funding (all periods 2-30d), net of the 15% fee.

    Uses the midpoint of each day's open and close funding rate.
    """
    start_ms = int((time.time() - (days + 2) * 86400) * 1000)
    rows = get_json(f"{BITFINEX.format(sym=sym)}?limit=1000&sort=1&start={start_ms}",
                    max_age_s=6 * 3600)
    out = {}
    for mts, open_, close, _high, _low, _vol in rows:
        out[_day(mts / 1000)] = (open_ + close) / 2 * 365 * 100 * (1 - BITFINEX_LENDER_FEE)
    return out


def gate_lend(asset: str, days: int) -> dict[str, float]:
    """Hourly Gate.io Uni lending APR (the API serves at most 30 days per call)."""
    now = int(time.time())
    points = []
    end = now
    while end > now - days * 86400:
        start = max(end - 30 * 86400, now - days * 86400)
        rows = get_json(f"{GATE}?asset={asset}&from={start}&to={end}", max_age_s=6 * 3600)
        points += [(_day(r["time"]), float(r["value"])) for r in rows]
        end = start
        time.sleep(0.1)
    return _daily_mean(points)


def kamino_reserves(market: str) -> list[dict]:
    return get_json(f"{KAMINO}/kamino-market/{market}/reserves/metrics?env=mainnet-beta")


def kamino_history(market: str, reserve: str, days: int) -> list[dict]:
    end = datetime.now(timezone.utc)
    start = datetime.fromtimestamp(end.timestamp() - days * 86400, tz=timezone.utc)
    fmt = "%Y-%m-%dT00:00:00.000Z"
    url = (f"{KAMINO}/kamino-market/{market}/reserves/{reserve}/metrics/history"
           f"?env=mainnet-beta&start={start.strftime(fmt)}&end={end.strftime(fmt)}&frequency=day")
    return get_json(url, max_age_s=6 * 3600).get("history") or []


def prices(coingecko_ids: list[str], days: int) -> dict[str, dict[str, float]]:
    """Daily USD prices, one coin and at most 180 days per call (API limits)."""
    out: dict[str, dict[str, float]] = {}
    now = int(time.time())
    for coin in coingecko_ids:
        series: dict[str, float] = {}
        start = now - (days + 2) * 86400
        while start < now:
            span = min(180, (now - start) // 86400 + 1)
            data = get_json(f"{COINS}/coingecko:{coin}?start={start}&span={span}&period=1d",
                            max_age_s=6 * 3600)
            for p in data["coins"][f"coingecko:{coin}"]["prices"]:
                series[_day(p["timestamp"])] = p["price"]
            start += span * 86400
        out[coin] = series
    return out
