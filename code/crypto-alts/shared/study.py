"""Common study scaffolding for crypto-alts ideas: panel + PIT universe, fixed splits,
frozen BTC bear windows, summary tables, tranche smoothing, BAB reference book.

Splits, cost and bear windows are the ones fixed by the first crypto-alts study
(`xs-momentum-neutral`, 2026-09-17) before any strategy was scored; later ideas reuse them
unchanged so results are comparable and nothing is re-picked after seeing results.
"""
import os, sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_HERE)), "shared"))
import research_lib as rl  # noqa: E402
from universe import load_panel, clean_close, pit_universe, ALTS, MAJORS  # noqa: E402

ANN = 365
COST = 10.0
IS = ("2018-01-01", "2022-12-31")
OOS = ("2023-01-01", "2026-12-31")
SPLITS = {"full": ("2018-01-01", "2026-12-31"), "IS": IS, "OOS": OOS}

BEAR_WINDOWS = [
    ("2017-12-16", "2018-12-15", -0.83),
    ("2019-06-26", "2020-03-12", -0.62),
    ("2021-04-13", "2021-07-20", -0.53),
    ("2021-11-08", "2022-11-21", -0.77),
    ("2025-10-06", "2026-06-30", -0.53),
]


def load(n_top=20, lookback=90, min_history=120, min_dv=5e6):
    p = load_panel()
    close = clean_close(p["Close"])
    vol = p["Volume"].reindex(columns=close.columns)
    alts = [t for t in ALTS if t in close]
    c_alt, v_alt = close[alts], vol[alts]
    mask = pit_universe(c_alt, v_alt, n_top=n_top, lookback=lookback,
                        min_history=min_history, min_dv=min_dv)
    return dict(close=close, c_alt=c_alt, v_alt=v_alt, mask=mask,
                btc=close["BTC-USD"], eth=close["ETH-USD"], ret=c_alt.pct_change())


def sharpe(x, ann=ANN):
    x = pd.Series(x).dropna()
    return x.mean() / x.std() * np.sqrt(ann) if len(x) > 2 and x.std() > 0 else np.nan


def bear_mask(index):
    m = pd.Series(False, index=index)
    for s, e, _ in BEAR_WINDOWS:
        m.loc[s:e] = True
    return m


def row(net, name=""):
    """One-line summary: Sharpe full/IS/OOS, bear pooled, per-bear, CAGR, MaxDD, t_NW."""
    net = net.loc["2018-03-08":]
    st = rl.perf_stats(net)
    bm = bear_mask(net.index)
    out = {"name": name, "full": sharpe(net), "IS": sharpe(net.loc[IS[0]:IS[1]]),
           "OOS": sharpe(net.loc[OOS[0]:OOS[1]]), "bear": sharpe(net[bm]), "nonbear": sharpe(net[~bm]),
           "CAGR": st["CAGR"], "MaxDD": st["MaxDD"], "tNW": st["t_NW"]}
    for i, (s, e, _) in enumerate(BEAR_WINDOWS):
        out[f"b{i+1}"] = sharpe(net.loc[s:e])
    return out


def yearly(net, ann=ANN):
    g = net.groupby(net.index.year)
    return g.apply(lambda s: s.mean() / s.std() * np.sqrt(ann) if s.std() > 0 else np.nan)


def tranche(w, hold):
    return w.rolling(hold, min_periods=1).mean() if hold > 1 else w


def ewm_beta(ret, mkt_ret, halflife=60):
    cov = ret.ewm(halflife=halflife, min_periods=halflife).cov(mkt_ret)
    var = mkt_ret.ewm(halflife=halflife, min_periods=halflife).var()
    return cov.div(var, axis=0)


def beta_neutralize(w, beta):
    """Add a BTC position so the book's EWM beta to BTC is zero. Returns (w_alts, w_btc)."""
    b = (w * beta.reindex_like(w)).sum(axis=1)
    return w, -b


def xs_zscore(sig, mask):
    s = sig.where(mask)
    return s.sub(s.mean(axis=1), axis=0).div(s.std(axis=1), axis=0)


def bt(w, close, cost=COST, name="xs"):
    """research_lib.backtest_xs on the columns of w (close must contain them)."""
    cols = list(w.columns)
    return rl.backtest_xs(w, close[cols], cost_bps=cost, ann=ANN, name=name)


def bab_reference():
    """Net daily returns of the live BAB book (xs-momentum-neutral spec defaults) for
    correlation / blend checks."""
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "xs-momentum-neutral"))
    from strategy import alt_bab_weights  # noqa: E402
    d = load()
    w = alt_bab_weights(d["c_alt"], d["v_alt"], d["btc"])
    net, _ = bt(w, d["c_alt"])
    return net
