"""Shared plumbing for the quality-value-composite screens: sectors, universe, monthly books."""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
from xs_lib import xs_backtest, zscore_xs, group_demean, ic_series, ic_summary, SPLITS
from research_lib import perf_stats

YF2GICS = {"Technology": "Information Technology", "Healthcare": "Health Care",
           "Financial Services": "Financials", "Consumer Cyclical": "Consumer Discretionary",
           "Consumer Defensive": "Consumer Staples", "Basic Materials": "Materials",
           "Industrials": "Industrials", "Energy": "Energy", "Utilities": "Utilities",
           "Real Estate": "Real Estate", "Communication Services": "Communication Services"}


def sector_map(P):
    sec = P["sector"].copy()
    h = pd.read_csv(os.path.join(_HERE, "..", "shared", "sectors_hist.csv")).set_index("ticker")["sector"].map(YF2GICS)
    sec = sec.fillna(h.reindex(sec.index))
    return sec.fillna("UNK")


def month_ends(idx):
    s = pd.Series(idx, index=idx)
    return pd.DatetimeIndex(s.groupby([idx.year, idx.month]).last().values)


def sector_z(sig, sec, mask, clip=3.0):
    """Winsorised cross-sectional z-score, demeaned within sector (sector-neutral)."""
    z = zscore_xs(sig, mask, clip=clip)
    return group_demean(z, sec, mask)


def book_weights(score, mask, kind="quintile", q=0.2, gross=1.0):
    s = score.where(mask)
    if kind == "linear":
        s = s.sub(s.mean(axis=1), axis=0)
        return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0) * gross
    n = s.notna().sum(axis=1)
    k = (n * q).round().clip(lower=1)
    hi = s.rank(axis=1, ascending=False).le(k, axis=0) & s.notna()
    lo = s.rank(axis=1, ascending=True).le(k, axis=0) & s.notna()
    w = hi.astype(float).div(hi.sum(axis=1).replace(0, np.nan), axis=0) * gross / 2 \
        - lo.astype(float).div(lo.sum(axis=1).replace(0, np.nan), axis=0) * gross / 2
    return w.fillna(0.0)


def hold_monthly(w_daily, rebal_dates):
    """Weights set at each rebalance close, held (constant) until the next one."""
    w = w_daily.reindex(rebal_dates)
    return w.reindex(w_daily.index).ffill().fillna(0.0)


def run_book(score, mask, ret, rebal, kind="quintile", cost=5.0, name="x", start="2011-01-01"):
    w = book_weights(score, mask, kind=kind)
    w = hold_monthly(w, rebal).loc[start:]
    net, st = xs_backtest(w, ret.loc[start:], cost_bps=cost, name=name)
    return net, st, w


def splits_row(net, st=None):
    row = {}
    for k, (a, b) in {"FULL": ("2011-01-01", "2026-12-31"), "IS": ("2011-01-01", "2017-12-31"),
                      "OOS": ("2018-01-01", "2026-12-31")}.items():
        seg = net.loc[a:b]
        row[k] = seg.mean() / seg.std() * np.sqrt(252) if seg.std() > 0 else np.nan
    if st is not None:
        row.update({"gross": st["GrossSharpe"], "cagr": st.get("CAGR"), "mdd": st.get("MaxDD"),
                    "vol": st.get("Vol"), "turn": st["Turnover_ann"]})
    return row
