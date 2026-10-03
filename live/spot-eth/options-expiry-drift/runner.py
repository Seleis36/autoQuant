"""
Live (paper) runner for options-expiry-drift -- short spot ETH over the eight hours
before the month-end Deribit option settlement.

Spec:   alphas/spot-eth/options-expiry-drift/2026-10-03_alpha_spec.md
Signal: code/spot-eth/options-expiry-drift/strategy.py :: target_weight()   (imported)
Report: past_research/spot-eth/options-expiry-drift/2026-10-03_options_expiry_drift.md

Short 1x ETH from Friday 00:00 UTC to Friday 08:00 UTC on the last Friday of each
calendar month, flat at every other time. Weight is -1.0 or 0.0; no fitted parameter.
The schedule is hourly but the book trades twice a month.

**Book: sim.** The rule is short-only and the spot testnet is long/flat, so this is a
`SimBroker` with `allow_short=True`, marked to REAL Binance spot
(`quotes="binance-public"`). There is no order book, no rejection, no borrow and no
queue -- weaker evidence than a venue sleeve; do not read it as if it had cleared the
testnet.

Bar convention, straight from strategy.py: hourly bars indexed by bar-open time (UTC);
`w[t]` is the weight to hold over the bar stamped t+1h. At Fri 00:00 the last closed
bar is Thu 23:00 and `target_weight(...).iloc[-1]` is -1; at Fri 08:00 the last closed
bar is Fri 07:00 and it is 0. Only the index is used -- the calendar is a function of
the timestamp -- so the one way to get this wrong is a stale last bar, which would
shift the window. The runner raises instead of trading on one.

Cost: research charges 10 bp/side and nothing else, so the sim book charges fee 10 bp,
slippage 0 -- the live track is costed exactly like the backtest.
"""
import os
import sys

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "spot-eth", "options-expiry-drift"))

from live_lib import MarketData, SimBroker, StrategyRunner  # noqa: E402
from strategy import target_weight  # noqa: E402

NAME = "spot-eth/options-expiry-drift"
SYMBOL = "ETHUSDT"
SCHEDULE = "1h"
# This strategy's own book. Capital is allocated, not divided. See live_lib.allocate().
CAPITAL_USDT = 2_500.0
# The signal has no lookback: the weight depends on the last closed bar's timestamp
# alone. A few days of bars are fetched only to hand strategy.py a real index.
HOURLY_BARS = 200

md = MarketData(source="public")  # real Binance spot -- NEVER testnet prices


def compute_weight(now):
    """Target weight for the bar starting at `now`, per the alpha spec."""
    hourly = md.klines(SYMBOL, "1h", limit=HOURLY_BARS)  # closed bars only
    if not len(hourly):
        raise RuntimeError("no hourly ETHUSDT bars")
    close = hourly["Close"]
    close.index = close.index.tz_localize(None)  # research convention

    # The weight is a function of the last closed bar's stamp. If that bar is not the
    # one that just closed, the entry or the exit would land on the wrong hour.
    expected = pd.Timestamp(now).tz_convert("UTC").tz_localize(None).floor("h") - pd.Timedelta(hours=1)
    if close.index[-1] != expected:
        raise RuntimeError(f"last closed ETHUSDT bar is {close.index[-1]}, expected {expected}; "
                           "refusing to place the expiry window on a stale bar")

    w = float(target_weight(close).iloc[-1])
    return max(-1.0, min(0.0, w))


if __name__ == "__main__":
    StrategyRunner(
        name=NAME,
        symbol=SYMBOL,
        schedule=SCHEDULE,
        compute_weight=compute_weight,
        broker=SimBroker(SYMBOL, capital_usdt=CAPITAL_USDT, quotes="binance-public",
                         max_weight=1.0, allow_short=True,
                         fee_bps=10.0, slippage_bps=0.0),
        offset_s=20.0,
    ).cli()
