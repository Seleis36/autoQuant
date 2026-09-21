"""Shared loaders and the two-leg P&L engine for the funding-carry study.

Position = long 1 unit of spot, short 1 unit of USD-M perp on the same coin. Per hour,
return on the *notional* of one leg is

    r_t = (S_t - S_{t-1})/S_{t-1} - (P_t - P_{t-1})/S_{t-1} + f_t * P_t / S_{t-1}
        ~= -(b_t - b_{t-1}) + f_t                      (b = P/S - 1, the basis)

where f_t is the funding rate settled at the hour stamp t (00/08/16 UTC), positive when
longs pay shorts. A position held over the settlement receives it; nothing else does.

Decision at the close of hour t sets the position for hour t+1 (weight shifted by one bar),
so a signal may only use data stamped <= t. Funding settled at t is *known* at t (it is
computed from the premium index over [t-8h, t]) and is used as a signal for later hours.

Costs are charged per unit of notional traded on *each* leg: spot taker 10 bp + perp taker
5 bp = 15 bp per switch, plus `slip_bps` for half-spread and basis slippage on both legs.
"""
import os, sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
import bars as barstore
from research_lib import perf_stats, DATA_DIR

HOURS = 24 * 365

def load_spot_1h(sym):
    if sym in ("BTCUSDT", "ETHUSDT"):
        return barstore.load_bars(sym, "1h", resample_from="1m")
    return barstore.load_bars(sym, "1h")

def load_perp_1h(sym):
    return barstore.load_bars(f"{sym}_PERP", "1h")

def load_funding(sym):
    f = pd.read_parquet(os.path.join(DATA_DIR, f"{sym}_fundingRate.parquet"))
    f.index = pd.to_datetime(f.index).round("h")
    f = f[~f.index.duplicated(keep="last")].sort_index()
    return f["last_funding_rate"].astype(float)

def load_pair(sym, start=None, end=None):
    """Hourly frame: S (spot close), P (perp close), f (funding settled at that stamp, 0 else), b (basis)."""
    s = load_spot_1h(sym)["Close"].rename("S")
    p = load_perp_1h(sym)["Close"].rename("P")
    f = load_funding(sym).rename("f")
    df = pd.concat([s, p], axis=1).dropna()
    df = df.loc[:f.index.max()]                 # no funding data past this stamp: stop the sample there
    df["f"] = f.reindex(df.index).fillna(0.0)
    df["b"] = df["P"] / df["S"] - 1.0
    if start: df = df.loc[start:]
    if end: df = df.loc[:end]
    return df

def leg_returns(df):
    """Hourly return on one-leg notional of the hedged position (before costs)."""
    rs = df["S"].pct_change()
    rp = df["P"].diff() / df["S"].shift(1)
    fund = df["f"] * df["P"] / df["S"].shift(1)
    return (rs - rp + fund).fillna(0.0)

def backtest_carry(df, weight, fee_bps=15.0, slip_bps=5.0, capital_factor=1.0):
    """weight: pd.Series in [0,1] decided at the close of hour t, applied to hour t+1.
    capital_factor scales notional to capital (e.g. 1/(1+1/L) for perp leverage L).
    Returns hourly net return on capital."""
    r = leg_returns(df)
    w = weight.reindex(df.index).fillna(0.0).clip(0, 1)
    w_eff = w.shift(1).fillna(0.0)
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs()
    net = (w_eff * r - turn * (fee_bps + slip_bps) / 1e4) * capital_factor
    return net, w_eff, turn

def daily(net):
    return (1 + net).resample("1D").prod() - 1

def stats(net_h, name="carry", ann=365):
    d = daily(net_h)
    s = perf_stats(d, ann=ann, name=name)
    return s

def summarize(net_h, w_eff, turn, name="carry", splits=None):
    d = daily(net_h)
    s = perf_stats(d, name=name)
    s["TimeInMkt"] = (w_eff > 0).mean()
    s["Switches/yr"] = (turn > 0).sum() / (len(turn) / HOURS)
    s["Turnover_ann"] = turn.sum() / (len(turn) / HOURS)
    if splits:
        for k, (a, b) in splits.items():
            seg = d.loc[a:b]
            s[f"Sharpe_{k}"] = seg.mean() / seg.std() * np.sqrt(365) if seg.std() > 0 else np.nan
    return s

SPLITS = {"IS": ("2019-01-01", "2022-12-31"), "OOS": ("2023-01-01", "2030-01-01")}
