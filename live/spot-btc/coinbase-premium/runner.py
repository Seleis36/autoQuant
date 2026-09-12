"""
Live (paper) runner for coinbase-premium -- USD-venue-vs-Binance-USDT price
dislocation as a long/flat spot BTC timer.

Spec:   alphas/spot-btc/coinbase-premium/2026-09-12_alpha_spec.md
Signal: code/spot-btc/coinbase-premium/strategy.py :: target_weight()   (imported)
Report: past_research/spot-btc/coinbase-premium/2026-09-12_coinbase_premium.md

Long/flat spot BTC, weight in [0, 1], rebalanced hourly on the UTC hour. The weight
is `state x trend x inverse-vol`, where `state` is a hysteresis machine on the 30-day
z-score of the Coinbase BTC-USD / Binance BTCUSDT premium (long once z > 0, flat once
z < -1.5).

**This strategy did NOT clear the Sharpe >= 2.0 bar of the brief that produced it** --
PR #6 was archived as a Failed result at net Sharpe 1.48. It is deployed on an explicit
operator decision to trade it at its honest 1.48, not on the research clearing its own
criterion. Read `backtest` in meta.json as the claim, and note the report's own advice to
discount the 1.48 toward ~1.35 for best-of-310 selection.

Two data feeds, and only one of them is Binance:

* Binance BTCUSDT hourly comes from `MarketData(source="public")` -- REAL spot klines,
  never the testnet's simulated book. Only orders and balances touch the venue.
* Coinbase BTC-USD hourly comes from the research fetcher itself
  (`code/spot-btc/coinbase-premium/fetch_data.py :: fetch_coinbase`), refreshed
  incrementally into the shared `data/COINBASE_BTCUSD_1h.parquet` cache. `MarketData`
  has no Coinbase source, and restating the fetch here would be a second implementation
  of the endpoint the backtest was built on.

Cost note: research assumes 10 bp/side, and the runner sends market orders that pay the
~10 bp taker fee -- no live-vs-backtest cost gap. Live turnover should come in *under*
the backtest's, because the 5 USDT minimum notional swallows the sub-0.2%-of-equity
drift of the inverse-vol scalar that the backtest charged in full.
"""
import logging
import os
import sys

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "spot-btc", "coinbase-premium"))

from live_lib import MarketData, PaperBroker, StrategyRunner, _atomic_parquet  # noqa: E402
from fetch_data import fetch_coinbase  # noqa: E402
from strategy import target_weight  # noqa: E402

log = logging.getLogger("coinbase-premium")

NAME = "spot-btc/coinbase-premium"
SYMBOL = "BTCUSDT"
SCHEDULE = "1h"
# This strategy's own book. Capital is allocated, not divided. See live_lib.allocate().
CAPITAL_USDT = 2_500.0

# The longest lookback in the signal is the 1200-bar (50-day) trend SMA, but the
# EWMA-vol scalar has infinite memory and the hysteresis state is path-dependent, so
# the window is set by how much history it takes for the live weight to reproduce the
# full-history backtest weight. Measured over the last 720 bars of the research cache:
#   2000 bars -> max|diff| 9.0e-3 · 3000 -> 2.4e-4 · 9000 -> 6.1e-7
# 9000 (~375 days) is the first window where the difference is numerical noise.
HOURLY_BARS = 9000
MIN_HOURLY_BARS = 6000

CB_PRODUCT = "BTC-USD"
CB_CACHE = os.path.join(REPO, "data", "COINBASE_BTCUSD_1h.parquet")
# The premium at the final Binance bar is what decides today's state. A missing
# Coinbase bar makes that z NaN, and the state machine then *keeps its state* -- which
# is the research's own rule for a NaN, so a one-off hole is not an incident. Past this
# many hours it is: the premium has stopped being tracked and the operator should know
# rather than have the daemon quietly hold whatever it last decided.
CB_MAX_LAG_HOURS = 3

md = MarketData(source="public")  # real Binance spot -- NEVER testnet prices


def coinbase_hourly() -> pd.Series:
    """Coinbase BTC-USD hourly closes, index = bar open (UTC, tz-naive).

    Refreshes the tail of the shared `data/` cache rather than refetching the series:
    `fetch_coinbase` pages 300 bars per request from `start`, so a healthy cache costs
    one request an hour and a daemon that was down for a month still catches up.
    """
    now = pd.Timestamp.now("UTC").tz_localize(None)
    cached = pd.DataFrame()
    if os.path.exists(CB_CACHE):
        try:
            cached = pd.read_parquet(CB_CACHE)
            cached.index = pd.to_datetime(cached.index)
        except Exception as e:  # noqa: BLE001
            log.warning("coinbase cache unreadable (%s), refetching: %s", CB_CACHE, e)
            cached = pd.DataFrame()

    if len(cached):
        # Overlap the cache by a few bars so the last row -- which may have been a
        # still-forming candle when it was written -- is replaced, not trusted.
        start = cached.index.max() - pd.Timedelta(hours=6)
    else:
        start = now - pd.Timedelta(hours=HOURLY_BARS + 48)

    fresh = pd.DataFrame()
    try:
        fresh = fetch_coinbase(CB_PRODUCT, start=start.strftime("%Y-%m-%d %H:%M:%S"), gran=3600)
    except Exception as e:  # noqa: BLE001 -- a stale premium is caught by the lag guard below
        log.warning("coinbase refresh failed, using cache: %s", e)

    df = pd.concat([cached, fresh]) if len(cached) else fresh
    if not len(df):
        raise RuntimeError("no Coinbase BTC-USD data: cache empty and refresh failed")
    df = df[~df.index.duplicated(keep="last")].sort_index()

    if len(fresh):
        try:
            _atomic_parquet(df, CB_CACHE)
        except Exception as e:  # noqa: BLE001
            log.warning("could not write coinbase cache: %s", e)

    # Drop the candle still being printed -- the Coinbase endpoint returns it, and a
    # partial close against a closed Binance bar is a premium that never existed.
    return df.loc[df.index < now.floor("h"), "Close"]


def compute_weight(now):
    """Target weight for the bar starting at `now`, per the alpha spec."""
    hourly = md.history(SYMBOL, "1h", bars=HOURLY_BARS)
    if len(hourly) < MIN_HOURLY_BARS:
        raise RuntimeError(f"only {len(hourly)} hourly bars; need >= {MIN_HOURLY_BARS} "
                           "for the weight to match the backtest")
    binance_close = hourly["Close"]
    binance_close.index = binance_close.index.tz_localize(None)  # research convention

    cb = coinbase_hourly()
    lag_h = (binance_close.index[-1] - cb.index[-1]).total_seconds() / 3600.0
    if lag_h > CB_MAX_LAG_HOURS:
        raise RuntimeError(
            f"Coinbase BTC-USD is {lag_h:.1f}h behind Binance "
            f"(coinbase {cb.index[-1]}, binance {binance_close.index[-1]}); "
            "the premium is no longer being tracked")
    if binance_close.index[-1] not in cb.index:
        log.warning("no Coinbase bar at %s -- premium z is NaN there and the hysteresis "
                    "state carries over, per the spec", binance_close.index[-1])

    weights = target_weight(binance_close, cb)
    if weights.iloc[-720:].isna().all():
        raise RuntimeError("signal is all-NaN over the last 720 bars -- stale inputs")
    return max(0.0, min(1.0, float(weights.iloc[-1])))


if __name__ == "__main__":
    StrategyRunner(
        name=NAME,
        symbol=SYMBOL,
        schedule=SCHEDULE,
        compute_weight=compute_weight,
        broker=PaperBroker(SYMBOL, capital_usdt=CAPITAL_USDT, max_weight=1.0),
        offset_s=20.0,
    ).cli()
