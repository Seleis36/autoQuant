"""Backtest/evaluation helpers shared by the sector-etf ideas.

Fixed before any result was seen (applies to every idea in this asset class):
  * IS  = 1999-01-01 .. 2014-12-31, OOS = 2015-01-01 .. end. Never re-picked.
  * Base cost 2 bp per side on every traded dollar (sector SPDR quoted spreads are
    ~0.3-2 bp half-spread; XLRE/XLC the widest), stress test at 5 bp.
  * Weights are TARGET weights known at the close of day t, earning day t+1 (research_lib
    convention, same bar the live book fills at).
"""
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "code", "shared"))
sys.path.insert(0, _HERE)
import research_lib as rl  # noqa: E402

ANN = 252.0
IS = ("1999-01-01", "2014-12-31")
OOS = ("2015-01-01", "2100-01-01")
SPLITS = {"full": ("1999-01-01", "2100-01-01"), "IS": IS, "OOS": OOS}
COST = 2.0
COST_STRESS = 5.0


def bt(weights, close, cost_bps=COST, name="s", start="1999-01-01"):
    """research_lib.backtest_xs on the 252-day calendar, trimmed to `start`."""
    net, st = rl.backtest_xs(weights, close, cost_bps=cost_bps, ann=ANN, name=name)
    net = net.loc[start:]
    return net


def stats(net, name="s"):
    s = rl.perf_stats(net, ann=ANN, name=name)
    return s


def split_table(net, name="s"):
    rows = {}
    for k, (a, b) in SPLITS.items():
        seg = net.loc[a:b]
        s = rl.perf_stats(seg, ann=ANN, name=k)
        rows[f"{name}|{k}"] = s
    return pd.DataFrame(rows).T


def summary(weights, close, name="s", cost_bps=COST, start="1999-01-01"):
    """One row: full/IS/OOS Sharpe, CAGR, MaxDD, turnover, gross exposure."""
    ret = close.pct_change()
    w = weights.reindex(index=ret.index, columns=ret.columns).fillna(0.0)
    w_eff = w.shift(1).fillna(0.0)
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs().sum(axis=1)
    gross = (w_eff * ret.fillna(0.0)).sum(axis=1)
    net = (gross - turn * cost_bps / 1e4).loc[start:]
    turn = turn.loc[start:]
    out = {}
    for k, (a, b) in SPLITS.items():
        seg = net.loc[a:b]
        sd = seg.std()
        out[f"Sh_{k}"] = seg.mean() / sd * np.sqrt(ANN) if sd > 0 else np.nan
    st = rl.perf_stats(net, ann=ANN)
    out.update({"CAGR": st["CAGR"], "Vol": st["Vol"], "MaxDD": st["MaxDD"],
                "t_NW": st["t_NW"],
                "Turn": turn.sum() / (len(turn) / ANN),
                "Gross": w_eff.loc[start:].abs().sum(axis=1).mean(),
                "Net": w_eff.loc[start:].sum(axis=1).mean()})
    return pd.Series(out, name=name), net


def tranche(w_fn_or_frame, n):
    """Average of n staggered copies of a daily-computed target: the standard way to
    hold for n days without a start-date lottery. Equivalent to a rolling mean of
    daily targets over n days."""
    return w_fn_or_frame.rolling(n, min_periods=1).mean()


def beta_to(ret, bench, halflife=126, min_periods=126):
    """EWM beta of each column of ret to bench, using data up to t (inclusive)."""
    cov = ret.apply(lambda c: c.ewm(halflife=halflife, min_periods=min_periods).cov(bench))
    var = bench.ewm(halflife=halflife, min_periods=min_periods).var()
    return cov.div(var, axis=0)


def dsr(sr_ann, n_obs, n_trials, skew=0.0, kurt=3.0):
    return rl.deflated_sharpe(sr_ann, n_obs, n_trials, skew=skew, kurt=kurt, ann=ANN)


def fmt(df):
    d = df.copy()
    for c in d.columns:
        if c in ("CAGR", "Vol", "MaxDD"):
            d[c] = (d[c] * 100).round(1)
        else:
            d[c] = d[c].astype(float).round(2)
    return d


def rf_daily(index):
    """Daily T-bill return (FRED DGS3MO, never revised) known at t-1, on `index`."""
    d = pd.read_parquet(os.path.join(rl.DATA_DIR, "FRED_DGS3MO_d.parquet"))["DGS3MO"]
    d.index = pd.to_datetime(d.index)
    return (d.reindex(index.union(d.index)).ffill().reindex(index) / 100 / ANN).shift(1).fillna(0)


def summary_rf(weights, close, name="s", cost_bps=COST, start="1999-01-01"):
    """`summary` on excess returns: charge the T-bill rate on the net dollar exposure
    (a net-long book borrows it, a net-short book earns it). Use for books whose net
    exposure is not ~0 (BAB, long-only timing) so Sharpe is an excess-return Sharpe."""
    ret = close.pct_change()
    w = weights.reindex(index=ret.index, columns=ret.columns).fillna(0.0)
    rf = rf_daily(ret.index)
    exret = ret.sub(rf, axis=0)
    w_eff = w.shift(1).fillna(0.0)
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs().sum(axis=1)
    gross = (w_eff * exret.fillna(0.0)).sum(axis=1)
    net = (gross - turn * cost_bps / 1e4).loc[start:]
    turn = turn.loc[start:]
    out = {}
    for k, (a, b) in SPLITS.items():
        seg = net.loc[a:b]
        sd = seg.std()
        out[f"Sh_{k}"] = seg.mean() / sd * np.sqrt(ANN) if sd > 0 else np.nan
    st = rl.perf_stats(net, ann=ANN)
    out.update({"CAGRx": st["CAGR"], "Vol": st["Vol"], "MaxDD": st["MaxDD"],
                "t_NW": st["t_NW"],
                "Turn": turn.sum() / (len(turn) / ANN),
                "Gross": w_eff.loc[start:].abs().sum(axis=1).mean(),
                "Net": w_eff.loc[start:].sum(axis=1).mean()})
    return pd.Series(out, name=name), net
