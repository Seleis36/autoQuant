"""Shared setup for the xs-momentum-neutral study: panel, PIT universe, regimes, splits."""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
HERE = _HERE
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import research_lib as rl
from universe import load_panel, clean_close, pit_universe, dollar_volume, ALTS, MAJORS, btc_regime

ANN = 365
COST = 10.0                      # bp per side, base case (large-cap alt spot on a major venue)
IS = ("2018-01-01", "2022-12-31")   # fixed in advance
OOS = ("2023-01-01", "2026-12-31")
SPLITS = {"full": ("2018-01-01", "2026-12-31"), "IS": IS, "OOS": OOS}


def load(n_top=15, lookback=90, min_history=120, min_dv=5e6):
    p = load_panel()
    close = clean_close(p["Close"])
    vol = p["Volume"].reindex(columns=close.columns)
    alts = [t for t in ALTS if t in close]
    c_alt, v_alt = close[alts], vol[alts]
    mask = pit_universe(c_alt, v_alt, n_top=n_top, lookback=lookback,
                        min_history=min_history, min_dv=min_dv)
    btc = close["BTC-USD"]
    eth = close["ETH-USD"]
    return dict(close=close, c_alt=c_alt, v_alt=v_alt, mask=mask, btc=btc, eth=eth,
                ret=c_alt.pct_change())


def regime_table(net, btc, sma=200, ann=ANN):
    """Sharpe / CAGR in BTC bull (above SMA) vs bear (below) regimes, plus calendar years."""
    reg = btc_regime(btc, sma).reindex(net.index).fillna(0)
    rows = {}
    for name, m in (("bull", reg == 1), ("bear", reg == 0)):
        seg = net[m]
        rows[name] = rl.perf_stats(seg, ann=ann, name=name)
        rows[name]["Days"] = len(seg)
    return pd.DataFrame(rows).T


def yearly(net, ann=ANN):
    g = net.groupby(net.index.year)
    return pd.DataFrame({"Sharpe": g.apply(lambda s: s.mean() / s.std() * np.sqrt(ann) if s.std() > 0 else np.nan),
                         "Ret": g.apply(lambda s: (1 + s).prod() - 1),
                         "MaxDD": g.apply(lambda s: ((1 + s).cumprod() / (1 + s).cumprod().cummax() - 1).min())})


def summarize(net, btc, label=""):
    st = rl.split_stats(net, SPLITS, ann=ANN)
    rg = regime_table(net, btc)
    out = pd.concat([st[["Sharpe", "CAGR", "MaxDD", "t_NW", "N"]], rg[["Sharpe", "CAGR", "MaxDD", "Days"]]])
    return out


# Ex-post BTC bear phases (peak -> trough of every drawdown deeper than 30% from a
# trailing-1y high, overlapping episodes merged). Frozen 2026-09-17 BEFORE any strategy was
# evaluated against them; used only for evaluation, never as a trading signal.
BEAR_WINDOWS = [
    ("2017-12-16", "2018-12-15", -0.83),
    ("2019-06-26", "2020-03-12", -0.62),
    ("2021-04-13", "2021-07-20", -0.53),
    ("2021-11-08", "2022-11-21", -0.77),
    ("2025-10-06", "2026-06-30", -0.53),
]


def bear_windows(btc=None, **kw):
    return [(pd.Timestamp(s), pd.Timestamp(e), t) for s, e, t in BEAR_WINDOWS]


def bear_mask(index, btc=None, **kw):
    m = pd.Series(False, index=index)
    for s, e, _ in bear_windows():
        m.loc[s:e] = True
    return m


def bear_stats(net, btc=None, ann=ANN, **kw):
    """Perf inside ex-post bear phases (pooled) and per window."""
    m = bear_mask(net.index)
    rows = {"bear_pooled": rl.perf_stats(net[m], ann=ann, name="bear_pooled")}
    for s, e, t in bear_windows():
        seg = net.loc[s:e]
        if len(seg) > 10:
            rows[f"{s.date()}..{e.date()} ({t:+.0%})"] = rl.perf_stats(seg, ann=ann)
    rows["non_bear"] = rl.perf_stats(net[~m], ann=ann, name="non_bear")
    return pd.DataFrame(rows).T[["Sharpe", "CAGR", "MaxDD", "N"]]
