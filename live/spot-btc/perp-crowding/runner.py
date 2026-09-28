"""
Live (paper) runner for perp-crowding -- contrarian retail positioning on Binance
BTCUSDT perps, traded as a long/flat spot BTC timer.

Spec:   alphas/spot-btc/perp-crowding/2026-09-28_alpha_spec.md
Signal: code/spot-btc/perp-crowding/strategy.py :: target_weight()   (imported, P1 defaults)
Report: past_research/spot-btc/perp-crowding/2026-09-28_perp_crowding.md

Long/flat spot BTC, weight in [0, 1], rebalanced daily at 00:00 UTC on the close of the
Binance daily bar. Hold BTC while log(global long/short ACCOUNT ratio), taken from the
last 5-min snapshot stamped <= 22:55 UTC, ranks below the median of all prior daily
values since 2020-09 (expanding, min 180 days); size = clip(0.40 / EWMA-vol(hl 20d), 0, 1).

**Book: sim, not venue.** Long/flat spot crypto belongs on the venue, but the venue pool
was fully subscribed (10000/10000 USDT across four strategies) at deployment. It runs as
a `SimBroker` marked to REAL Binance spot (`quotes="binance-public"`): no order book, no
rejection, no queue. Weaker evidence than the venue sleeves.

Data feeds:

* BTCUSDT daily closes from `MarketData(source="public")` -- REAL spot klines, the same
  Binance bars the research built from its 1m store. The history reaches back before
  2020-09 because `crowd_level` is reindexed onto the close index: a shorter close series
  would silently truncate the expanding-rank history and change the rank.
* The global L/S account ratio is the research archive `data/BTCUSDT_metrics_5m.parquet`
  (column `count_long_short_ratio`), topped up with the research's own resumable
  `fetch_metrics.py` when it is more than ARCHIVE_STALE_DAYS old, plus the REST endpoint
  `fapi/futures/data/globalLongShortAccountRatio` for the days the archive has not
  published yet. REST stamps are 5 min LATER than the archive's `create_time` for the same
  value (verified at deploy: shift -5 min -> max|diff| 3e-4, the REST 4-dp rounding), so
  they are shifted back 5 min before stitching. Archive values win where both exist.

Cost: research charges 10 bp/side and nothing else, so fee 10 bp, slippage 0.
"""
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "harness"))
sys.path.insert(0, os.path.join(REPO, "code", "spot-btc", "perp-crowding"))

from live_lib import MarketData, SimBroker, StrategyRunner  # noqa: E402
from strategy import target_weight  # noqa: E402

log = logging.getLogger("perp-crowding")

NAME = "spot-btc/perp-crowding"
SYMBOL = "BTCUSDT"
SCHEDULE = "1d"
# This strategy's own book. Capital is allocated, not divided. See live_lib.allocate().
CAPITAL_USDT = 2_500.0

# The rank is expanding over every daily level since the archive starts (2020-09-01), and
# the level is reindexed onto the close index -- so the close series must cover that
# start or the rank history is truncated.
RANK_START = pd.Timestamp("2020-09-01")
DAILY_BARS = 2600

METRICS = os.path.join(REPO, "data", "BTCUSDT_metrics_5m.parquet")
RATIO_COL = "count_long_short_ratio"
ARCHIVE_STALE_DAYS = 3        # top up the archive past this (REST keeps 30 days only)
REST_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
REST_SHIFT = pd.Timedelta(minutes=5)   # REST stamp - archive create_time for the same value
CUTOFF = pd.Timedelta(hours=1)         # strategy default cutoff_hours=1.0

md = MarketData(source="public")  # real Binance spot -- NEVER testnet prices


def _archive() -> pd.Series:
    s = pd.read_parquet(METRICS, columns=[RATIO_COL])[RATIO_COL]
    s.index = pd.to_datetime(s.index)
    return s.dropna().sort_index()


def _rest(start: pd.Timestamp) -> pd.Series:
    """Global account ratio from REST since `start`, re-stamped onto the archive clock."""
    out, t = {}, start
    now = pd.Timestamp.now("UTC").tz_localize(None)
    for _ in range(40):
        q = {"symbol": SYMBOL, "period": "5m", "limit": 500,
             "startTime": int(t.tz_localize("UTC").timestamp() * 1000)}
        with urllib.request.urlopen(f"{REST_URL}?{urllib.parse.urlencode(q)}", timeout=20) as r:
            rows = json.load(r)
        if not rows:
            break
        for x in rows:
            out[pd.to_datetime(x["timestamp"], unit="ms")] = float(x["longShortRatio"])
        last = pd.to_datetime(rows[-1]["timestamp"], unit="ms")
        if len(rows) < 500 or last >= now - pd.Timedelta(minutes=10):
            break
        t = last + pd.Timedelta(minutes=5)
        time.sleep(0.2)
    s = pd.Series(out, dtype=float).sort_index()
    s.index = s.index - REST_SHIFT
    return s


def ls_ratio() -> pd.Series:
    now = pd.Timestamp.now("UTC").tz_localize(None)
    arc = _archive()
    if arc.index.max() < now - pd.Timedelta(days=ARCHIVE_STALE_DAYS):
        try:
            from fetch_metrics import fetch
            log.info("metrics archive ends %s -- topping up from data.binance.vision", arc.index.max())
            fetch(SYMBOL)
            arc = _archive()
        except Exception as e:  # noqa: BLE001 -- REST covers 30 days; the gap guard below catches the rest
            log.warning("archive top-up failed, relying on REST: %s", e)
    rest = _rest(max(arc.index.max() - pd.Timedelta(hours=6), now - pd.Timedelta(days=29)))
    if rest.empty:
        raise RuntimeError("global L/S REST returned nothing")
    if rest.index.min() > arc.index.max() + pd.Timedelta(minutes=5):
        raise RuntimeError(f"hole in L/S ratio between archive end {arc.index.max()} and REST "
                           f"start {rest.index.min()}; run code/spot-btc/perp-crowding/fetch_metrics.py")
    return pd.concat([arc, rest[rest.index > arc.index.max()]]).sort_index()


def compute_weight(now):
    """Target weight for the day starting at `now`, per the alpha spec (P1)."""
    daily = md.history(SYMBOL, "1d", bars=DAILY_BARS)
    close = daily["Close"]
    close.index = close.index.tz_localize(None)  # research convention: bar-open, tz-naive UTC
    if close.index[0] > RANK_START:
        raise RuntimeError(f"daily closes start {close.index[0]}, after {RANK_START}: "
                           "the expanding rank would be truncated")

    ls = ls_ratio()
    # The level for the last closed bar D is the snapshot stamped <= D 23:00 - 5 min. If it
    # is missing the rank is NaN and strategy.py goes flat -- a stale feed, not a signal.
    last_day = close.index[-1]
    usable = ls[ls.index + CUTOFF < last_day + pd.Timedelta(days=1)]
    if usable.empty or usable.index[-1] < last_day + pd.Timedelta(hours=21):
        raise RuntimeError(f"no L/S snapshot near {last_day.date()} 22:55 UTC "
                           f"(latest usable {usable.index[-1] if len(usable) else None})")

    w = target_weight(close, ls)
    log.info("bar %s  L/S %.4f @ %s  weight %.4f", last_day.date(), usable.iloc[-1],
             usable.index[-1], w.iloc[-1])
    if not np.isfinite(w.iloc[-1]):
        raise RuntimeError("non-finite weight")
    return max(0.0, min(1.0, float(w.iloc[-1])))


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
