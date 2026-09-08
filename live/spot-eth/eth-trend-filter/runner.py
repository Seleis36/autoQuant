"""
Live (paper) runner for `spot-eth/eth-trend-filter`.

Spec:   alphas/spot-eth/eth-trend-filter/spec.md
Report: past_research/spot-eth/eth-trend-filter/2026-09-07_eth_trend_filter.md

Long/flat spot ETH, unlevered, daily rebalance on the 00:00 UTC bar boundary.

    trend_t = 1{ close_t > SMA(close, 40)_t }
    vol_t   = EWMstd(pct_change(close), halflife=20)_t * sqrt(365)
    w_t     = trend_t * clip(0.5 / vol_t, 0.0, 1.0)

The PR does not ship a reusable `strategy.py` (this cycle predates that convention),
so the three-line signal is implemented here directly from the spec (window 40,
target 0.5, halflife 20, cap 1.0).

Signals come from REAL Binance spot klines (ETHUSDT daily close via MarketData
source="public"), the same series the report accepts as equivalent to yfinance
`ETH-USD`. Testnet klines are simulated and never used for the signal.

Cost note: the research assumes 10 bp per side. The runner sends market orders and
pays the ~10 bp taker fee -- no gap.
"""
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))

from live_lib import MarketData, PaperBroker, StrategyRunner  # noqa: E402

NAME = "spot-eth/eth-trend-filter"
SYMBOL = "ETHUSDT"
SCHEDULE = "1d"
CAPITAL_USDT = 2_500.0

SMA_WIN = 40
VOL_TARGET = 0.5
VOL_HALFLIFE = 20
WEIGHT_CAP = 1.0
DAILY_BARS = 400  # comfortably past the 40-day SMA and 20-day halflife EWM

md = MarketData(source="public")  # real Binance spot -- NEVER testnet prices


def compute_weight(now):
    """Target weight for the day starting at `now`, per spec.md."""
    daily = md.history(SYMBOL, "1d", bars=DAILY_BARS)
    if len(daily) < 60:
        raise RuntimeError(f"only {len(daily)} daily bars; need >= 60")

    close = daily["Close"].astype(float)
    ret = close.pct_change()

    trend = (close > close.rolling(SMA_WIN).mean()).astype(float)
    vol = ret.ewm(halflife=VOL_HALFLIFE, adjust=False).std() * np.sqrt(365)
    scalar = (VOL_TARGET / vol).clip(0.0, WEIGHT_CAP).fillna(0.0)
    weight = trend * scalar

    if weight.iloc[-10:].isna().all():
        raise RuntimeError("signal is all-NaN over the last 10 bars -- stale inputs")

    w = float(weight.iloc[-1])
    return max(0.0, min(WEIGHT_CAP, w))


if __name__ == "__main__":
    StrategyRunner(
        name=NAME,
        symbol=SYMBOL,
        schedule=SCHEDULE,
        compute_weight=compute_weight,
        broker=PaperBroker(SYMBOL, capital_usdt=CAPITAL_USDT, max_weight=WEIGHT_CAP),
        offset_s=20.0,
    ).cli()
