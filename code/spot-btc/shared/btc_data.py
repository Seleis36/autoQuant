"""Spot-BTC research helpers shared across ideas.

Daily bars are Binance BTCUSDT spot built from the 1m store: bar D covers
[D 00:00, D+1 00:00) UTC, so a weight decided "at the close of D" is set at D+1 00:00 UTC
and earns the return of bar D+1 (research_lib.backtest shifts by one bar).
"""
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
import research_lib as rl  # noqa: E402
from bars import load_bars  # noqa: E402

IS_END = "2022-12-31"
OOS_START = "2023-01-01"


def _complete(df, freq_minutes):
    """Drop the trailing bar if it is still forming (fewer than 90% of its minutes)."""
    if len(df) and "n_min" in df:
        if df["n_min"].iloc[-1] < 0.9 * freq_minutes:
            df = df.iloc[:-1]
    return df


def btc_daily(start="2017-08-17"):
    m = load_bars("BTCUSDT", "1m", start=start)
    d = m.resample("1D", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    d["n_min"] = m["Close"].resample("1D", label="left", closed="left").count()
    d = d.dropna(subset=["Close"])
    return _complete(d, 1440)


def btc_hourly(start="2017-08-17"):
    m = load_bars("BTCUSDT", "1m", start=start)
    h = m.resample("1h", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    h["n_min"] = m["Close"].resample("1h", label="left", closed="left").count()
    h = h.dropna(subset=["Close"])
    return _complete(h, 60)


def splits(start=None):
    return {"full": (start, None), "IS": (start, IS_END), "OOS": (OOS_START, None)}


def evaluate(w, close, cost_bps=10.0, start=None, name="s", ann=rl.ANN):
    """Backtest target weights (decided at close of each bar) and return
    (net returns, one-row DataFrame with full/IS/OOS Sharpe etc.)."""
    net, st = rl.backtest(w, close, cost_bps=cost_bps, ann=ann, name=name)
    if start is not None:
        net = net.loc[start:]
    row = {}
    for k, (a, b) in splits().items():
        seg = net.loc[a:b]
        ps = rl.perf_stats(seg, ann=ann)
        row[f"Sh_{k}"] = ps["Sharpe"]
        if k == "full":
            row.update(CAGR=ps["CAGR"], MaxDD=ps["MaxDD"], Vol=ps["Vol"], t_NW=ps["t_NW"])
    ws = pd.Series(w).reindex(close.index).fillna(0).shift(1).fillna(0)
    if start is not None:
        ws = ws.loc[start:]
    row["Turn"] = ws.diff().abs().sum() / (len(ws) / ann)
    row["Expo"] = ws.mean()
    return net, pd.DataFrame(row, index=[name])


def yearly_sharpe(net, ann=rl.ANN):
    g = net.groupby(net.index.year)
    return (g.mean() / g.std() * np.sqrt(ann)).round(2)
