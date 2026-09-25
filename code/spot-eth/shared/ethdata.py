"""Shared spot-eth research helpers: hourly/daily Binance bars, splits, trend baseline.

Conventions follow research_lib: signal known at the close of bar t, applied to the
return of bar t+1 (research_lib.backtest shifts by one bar), cost on |dw| per side.
Binance bars are stamped at the bar OPEN (UTC); `close_stamped` re-stamps them at the
bar close so a daily bar labelled D covers [D, D+1) and its close is known at D+1 00:00.
"""
import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(_ROOT, "code", "shared"))

from bars import load_bars  # noqa: E402
import research_lib as rl  # noqa: E402

HOURS = 24 * 365.0
IS_END = "2023-12-31 23:59:59"
OOS_START = "2024-01-01"
START = "2017-09-01"          # first full month of Binance ETHUSDT history

_cache = {}


def bars(symbol="ETHUSDT", freq="1h", start=START):
    key = (symbol, freq, start)
    if key not in _cache:
        if freq == "1m":
            df = load_bars(symbol, "1m", start=start)
        else:
            df = load_bars(symbol, freq, start=start, resample_from="1m")
        _cache[key] = df
    return _cache[key].copy()


def splits(index_end=None):
    return {"Full": (START, None), "IS": (START, IS_END), "OOS": (OOS_START, None)}


def bt(weights, close, cost_bps=10.0, ann=HOURS, name="s"):
    return rl.backtest(weights, close, cost_bps=cost_bps, ann=ann, name=name)


def row(net, ann=HOURS, extra=None):
    """Full / IS / OOS Sharpe + headline stats in one dict."""
    out = {}
    for k, (a, b) in splits().items():
        seg = net.loc[a:b]
        s = rl.perf_stats(seg, ann=ann)
        out[f"Sh_{k}"] = s["Sharpe"]
        if k == "Full":
            out.update(CAGR=s["CAGR"], MDD=s["MaxDD"], Vol=s["Vol"], tNW=s["t_NW"])
    if extra is not None:
        out.update(extra)
    return out


def to_daily(net_hourly):
    """Compound hourly returns into UTC-day returns (for daily-convention Sharpe)."""
    return (1 + net_hourly).groupby(net_hourly.index.floor("D")).prod() - 1


def trend_filter_weights_daily(close_d, win=40, target=0.5, hl=20):
    """The live `eth-trend-filter` spec, for correlation checks (daily bars)."""
    ret = close_d.pct_change()
    gate = (close_d > close_d.rolling(win).mean()).astype(float)
    return gate * rl.vol_target_scalar(ret, target=target, halflife=hl, cap=1.0)
