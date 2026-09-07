"""
Live (paper) runner for BULT -- BTC US-Close Liquidity Timer.

Spec:   alphas/spot-btc/bult/BULT.md
Signal: code/spot-btc/bult/strategy.py :: build_signals()   (imported, not restated)

The alpha is a long/flat SPOT BTC strategy and trades as one: BTCUSDT on the
Binance spot testnet, unlevered, weight in [0, 1].

Signals come from REAL Binance spot klines (api.binance.com), never from testnet
prices -- the testnet book is simulated. Only orders and balances touch the venue.

Cost note: the research assumes 3 bp/side maker. The runner sends market orders and
pays the taker fee (~10 bp), which the BULT report puts at roughly Sharpe 1.10 vs
1.48. That is a known live-vs-backtest gap, not a defect.

Rebalance is hourly on the UTC hour, which is what the research assumes -- BULT
loses ~0.34 Sharpe per hour of execution delay, so the runner fires 20s after the
bar closes and computes the weight from closed bars only.

This file is also the reference deployment: /deploy-strategy copies its shape.
"""
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "spot-btc", "bult"))

from live_lib import MarketData, PaperBroker, StrategyRunner  # noqa: E402
from strategy import MACRO, build_signals  # noqa: E402

NAME = "spot-btc/bult"
SYMBOL = "BTCUSDT"
SCHEDULE = "1h"
# This strategy's own book. Capital is allocated, not divided: deploying another
# strategy never resizes this one. See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# 9000 hourly bars ~= 375 days, comfortably past the 250-day macro lookback and
# the 200-day trend lookback that build_signals() resamples out of the hourly series.
HOURLY_BARS = 9000

md = MarketData(source="public")  # real Binance spot -- NEVER testnet prices


def compute_weight(now):
    """Target weight for the bar starting at `now`, per BULT.md."""
    # Refresh the shared daily caches that strategy.load_series() reads for the
    # macro composite (HYG, LQD, DX-Y.NYB, ^GSPC).
    for ticker in MACRO:
        md.daily(ticker, lookback_days=1500, cache_hours=6)

    hourly = md.history(SYMBOL, "1h", bars=HOURLY_BARS)
    if len(hourly) < 6000:
        raise RuntimeError(f"only {len(hourly)} hourly bars; need >= 6000 for the 250d lookback")

    weight, _ = build_signals(hourly)
    w = float(weight.iloc[-1])

    # build_signals returns the weight applicable to each bar; the last row is the
    # bar that just closed, and BULT's weight for the coming hour is computed from
    # information known at that boundary. Guard against a silently-empty signal.
    if weight.iloc[-72:].isna().all():
        raise RuntimeError("signal is all-NaN over the last 72 bars -- stale inputs")
    return max(0.0, min(1.0, w))


if __name__ == "__main__":
    StrategyRunner(
        name=NAME,
        symbol=SYMBOL,
        schedule=SCHEDULE,
        compute_weight=compute_weight,
        broker=PaperBroker(SYMBOL, capital_usdt=CAPITAL_USDT, max_weight=1.0),
        offset_s=20.0,
    ).cli()
