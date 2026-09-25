"""
Live (paper) runner for eth-venue-premium -- the Coinbase ETH-USD / Binance ETHUSDT
price premium as a long/flat spot ETH timer.

Spec:   alphas/spot-eth/eth-venue-premium/2026-09-25_alpha_spec.md
Signal: code/spot-eth/eth-venue-premium/strategy.py :: target_weight()   (imported)
Report: past_research/spot-eth/eth-venue-premium/2026-09-25_eth_venue_premium.md

Long/flat spot ETH, weight in [0, 1], rebalanced hourly on the UTC hour. The weight is
`state x trend x inverse-vol`, where `state` is a hysteresis machine on the 30-day
z-score of the Coinbase ETH-USD / Binance ETHUSDT premium (long once z > 0, flat once
z < -1.5). Parameters are the live spot-btc/coinbase-premium spec, unchanged.

**Book: sim, not venue.** The strategy is long/flat spot crypto and would belong on the
venue, but the venue pool was fully subscribed (10000/10000 USDT across four strategies)
when this was deployed. It runs as a `SimBroker` marked to REAL Binance spot
(`quotes="binance-public"`) -- so the price is the market's, but there is no order book,
no rejection and no queue. Weaker evidence than the venue sleeves; do not read it as if
it had cleared the testnet.

Two data feeds:

* Binance ETHUSDT hourly comes from `MarketData(source="public")` -- REAL spot klines,
  never the testnet's simulated book.
* Coinbase ETH-USD hourly comes from the research fetcher itself
  (`code/spot-eth/eth-venue-premium/fetch_coinbase.py :: fetch`), refreshed
  incrementally into the shared `data/COINBASE_ETHUSD_1h.parquet` cache.

Cost: research charges 10 bp/side and nothing else, so the sim book charges fee 10 bp,
slippage 0 -- the live track is costed exactly like the backtest.
"""
import logging
import os
import sys

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "spot-eth", "eth-venue-premium"))

from live_lib import MarketData, SimBroker, StrategyRunner, _atomic_parquet  # noqa: E402
from fetch_coinbase import fetch as fetch_coinbase  # noqa: E402
from strategy import target_weight  # noqa: E402

log = logging.getLogger("eth-venue-premium")

NAME = "spot-eth/eth-venue-premium"
SYMBOL = "ETHUSDT"
SCHEDULE = "1h"
# This strategy's own book. Capital is allocated, not divided. See live_lib.allocate().
CAPITAL_USDT = 2_500.0

# The longest lookback is the 1200-bar (50-day) trend SMA, but the EWMA-vol scalar has
# infinite memory and the hysteresis state is path-dependent, so the window is set by
# how much history it takes for the live weight to reproduce the full-history weight.
# Measured on ETH over the last 720 bars of the research cache (see the deploy PR):
# 9000 bars (~375 days) is where the difference is numerical noise.
HOURLY_BARS = 9000
MIN_HOURLY_BARS = 6000

CB_PRODUCT = "ETH-USD"
CB_CACHE = os.path.join(REPO, "data", "COINBASE_ETHUSD_1h.parquet")
# A single missing Coinbase bar makes z NaN and the hysteresis keeps its state -- the
# spec's own rule. Past this many hours the premium is no longer being tracked and the
# runner raises rather than holding a frozen state.
CB_MAX_LAG_HOURS = 3

md = MarketData(source="public")  # real Binance spot -- NEVER testnet prices


def coinbase_hourly() -> pd.Series:
    """Coinbase ETH-USD hourly closes, index = bar open (UTC, tz-naive), closed bars only."""
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
        # Overlap by a few bars so a row written while its candle was still forming
        # is replaced, not trusted.
        start = cached.index.max() - pd.Timedelta(hours=6)
    else:
        start = now - pd.Timedelta(hours=HOURLY_BARS + 48)

    fresh = pd.DataFrame()
    try:
        fresh = fetch_coinbase(CB_PRODUCT, start=start.strftime("%Y-%m-%d %H:%M:%S"), gran=3600)
    except Exception as e:  # noqa: BLE001 -- a stale premium is caught by the lag guard
        log.warning("coinbase refresh failed, using cache: %s", e)

    df = pd.concat([cached, fresh]) if len(cached) else fresh
    if not len(df):
        raise RuntimeError("no Coinbase ETH-USD data: cache empty and refresh failed")
    df = df[~df.index.duplicated(keep="last")].sort_index()

    if len(fresh):
        try:
            _atomic_parquet(df, CB_CACHE)
        except Exception as e:  # noqa: BLE001
            log.warning("could not write coinbase cache: %s", e)

    # Drop the candle still being printed: a partial Coinbase close against a closed
    # Binance bar is a premium that never existed.
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
            f"Coinbase ETH-USD is {lag_h:.1f}h behind Binance "
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
        broker=SimBroker(SYMBOL, capital_usdt=CAPITAL_USDT, quotes="binance-public",
                         max_weight=1.0, allow_short=False,
                         fee_bps=10.0, slippage_bps=0.0),
        offset_s=20.0,
    ).cli()
