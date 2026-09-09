"""
Live (paper) runner for weekday-trend -- long/flat vol-managed BTC that never
holds into Thursday.

Spec:   alphas/spot-btc/weekday-trend/2026-09-08_alpha_spec.md
Signal: code/spot-btc/weekday-trend/strategy.py :: target_weight()  (imported)

Long/flat spot BTC, weight in [0, 1], rebalanced daily at the 00:00 UTC close
boundary. Signal is computed from real Binance spot daily klines (never testnet
prices); only orders and balances touch the venue.

Cost note: research assumes 10 bp/side. The runner sends market orders and pays
the taker fee (~10 bp), which matches -- no live-vs-backtest cost gap.
"""
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "spot-btc", "weekday-trend"))

from live_lib import MarketData, PaperBroker, StrategyRunner  # noqa: E402
from strategy import target_weight  # noqa: E402

NAME = "spot-btc/weekday-trend"
SYMBOL = "BTCUSDT"
SCHEDULE = "1d"
CAPITAL_USDT = 2_500.0
# 200-day SMA is the longest lookback; 500 daily bars is comfortably past it.
DAILY_BARS = 500

md = MarketData(source="public")


def compute_weight(now):
    daily = md.history(SYMBOL, "1d", bars=DAILY_BARS)
    if len(daily) < 260:
        raise RuntimeError(f"only {len(daily)} daily bars; need >= 260 for the 200d SMA")
    weights = target_weight(daily["Close"])
    if weights.iloc[-30:].isna().all():
        raise RuntimeError("signal is all-NaN over the last 30 bars -- stale inputs")
    return float(weights.iloc[-1])


if __name__ == "__main__":
    StrategyRunner(
        name=NAME,
        symbol=SYMBOL,
        schedule=SCHEDULE,
        compute_weight=compute_weight,
        broker=PaperBroker(SYMBOL, capital_usdt=CAPITAL_USDT, max_weight=1.0),
        offset_s=20.0,
    ).cli()
