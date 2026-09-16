"""Cross-sectional (long/short basket) research helpers for the US large-cap panel.

Conventions (lookahead-safe, identical to research_lib.backtest):
  * signal / weight matrices are indexed by the CLOSE of day t;
  * weights at t earn the close-to-close return of t+1 (shifted inside `xs_backtest`);
  * cost charged on sum |w_t - w_{t-1}| at `cost_bps` per side, bar t.
"""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
from research_lib import perf_stats, newey_west_t

ANN = 252


def zscore_xs(sig, mask=None, clip=3.0):
    """Cross-sectional z-score per row over the masked universe."""
    s = sig.where(mask) if mask is not None else sig
    mu = s.mean(axis=1); sd = s.std(axis=1, ddof=1)
    z = s.sub(mu, axis=0).div(sd, axis=0)
    return z.clip(-clip, clip)


def rank_xs(sig, mask=None):
    """Cross-sectional rank in [-0.5, 0.5] per row over the masked universe."""
    s = sig.where(mask) if mask is not None else sig
    r = s.rank(axis=1, pct=True)
    return r.sub(r.mean(axis=1), axis=0)


def group_demean(sig, groups, mask=None):
    """Subtract group (e.g. sector) mean per row. `groups`: Series ticker->group."""
    s = sig.where(mask) if mask is not None else sig
    g = groups.reindex(s.columns)
    out = s.copy()
    for gname, cols in g.groupby(g).groups.items():
        cols = [c for c in cols if c in s.columns]
        sub = s[cols]
        out[cols] = sub.sub(sub.mean(axis=1), axis=0)
    return out


def decile_weights(sig, mask, q=0.1, gross=1.0):
    """Long top-q / short bottom-q equal weight, each side gross/2. Dollar-neutral."""
    s = sig.where(mask)
    n = s.notna().sum(axis=1)
    k = (n * q).round().clip(lower=1)
    r = s.rank(axis=1, ascending=False)          # 1 = highest signal
    rl = s.rank(axis=1, ascending=True)
    long = r.le(k, axis=0) & s.notna()
    short = rl.le(k, axis=0) & s.notna()
    w = long.astype(float).div(long.sum(axis=1).replace(0, np.nan), axis=0) * (gross / 2) \
        - short.astype(float).div(short.sum(axis=1).replace(0, np.nan), axis=0) * (gross / 2)
    return w.fillna(0.0)


def linear_weights(sig, mask, gross=1.0):
    """Weights proportional to demeaned rank/zscore, scaled to `gross` total |w|. Dollar-neutral."""
    s = sig.where(mask)
    s = s.sub(s.mean(axis=1), axis=0)
    denom = s.abs().sum(axis=1).replace(0, np.nan)
    return s.div(denom, axis=0).fillna(0.0) * gross


def smooth_weights(w, n):
    """Overlapping-tranche (n-day holding) smoothing: mean of the last n daily target weights."""
    if n <= 1:
        return w
    return w.rolling(n, min_periods=1).mean()


def xs_backtest(w, ret, cost_bps=5.0, name="xs"):
    """w: weights at close t (DataFrame). ret: close-to-close simple returns (DataFrame, same axes).
    Returns (net daily series, stats)."""
    w = w.reindex(index=ret.index, columns=ret.columns).fillna(0.0)
    w_eff = w.shift(1).fillna(0.0)
    r = ret.fillna(0.0)
    gross = (w_eff * r).sum(axis=1)
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs().sum(axis=1)
    net = gross - turn * cost_bps / 1e4
    net.name = name
    st = perf_stats(net, ann=ANN, name=name)
    st["GrossSharpe"] = gross.mean() / gross.std(ddof=1) * np.sqrt(ANN) if gross.std() > 0 else np.nan
    st["Turnover_ann"] = turn.sum() / (len(turn) / ANN)     # one-way, in units of book
    st["AvgGross"] = w_eff.abs().sum(axis=1).mean()
    st["AvgNet"] = w_eff.sum(axis=1).mean()
    st["AvgNames"] = (w_eff != 0).sum(axis=1).mean()
    return net, st


def ic_series(sig, fwd, mask, method="spearman"):
    """Daily cross-sectional rank IC between signal at t and forward return."""
    s = sig.where(mask); f = fwd.where(mask)
    if method == "spearman":
        s = s.rank(axis=1); f = f.rank(axis=1)
    sm = s.sub(s.mean(axis=1), axis=0); fm = f.sub(f.mean(axis=1), axis=0)
    num = (sm * fm).sum(axis=1)
    den = np.sqrt((sm ** 2).sum(axis=1) * (fm ** 2).sum(axis=1))
    return (num / den).replace([np.inf, -np.inf], np.nan)


def ic_summary(ic):
    ic = ic.dropna()
    return {"IC": ic.mean(), "IC_t": ic.mean() / ic.std(ddof=1) * np.sqrt(len(ic)), "IC_IR_ann": ic.mean() / ic.std(ddof=1) * np.sqrt(ANN), "N": len(ic)}


def split_perf(net, splits, cost_note=""):
    rows = {}
    for k, (a, b) in splits.items():
        seg = net.loc[a:b]
        rows[k] = perf_stats(seg, ann=ANN, name=k)
    return pd.DataFrame(rows).T


SPLITS = {"FULL": ("2010-01-01", "2026-12-31"), "IS": ("2010-01-01", "2017-12-31"), "OOS": ("2018-01-01", "2026-12-31")}
