"""Vol-complex daily panel + backtest helpers shared by the vol-complex ideas.

All series are yfinance auto-adjusted daily closes from the flat cache `data/`, tz-naive,
indexed by US session date. Timing: ^VIX-family indices close at 16:15 ET, the ETPs and
SPY at 16:00 ET, so a same-day index signal has 15 minutes of look-ahead on the ETP fill.
`panel(lag_index=True)` shifts every index series by one session to remove it.

Split used by every vol-complex idea (fixed before any result was looked at, same as
term-structure-carry): IS = 2011-01 -> 2018-12, OOS = 2019-01 -> 2026-09.
"""
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
import research_lib as rl  # noqa: E402

ANN = 252.0
IS = ("2011-01-01", "2018-12-31")
OOS = ("2019-01-01", "2026-12-31")
SPLITS = {"FULL": ("2011-01-01", "2026-12-31"), "IS": IS, "OOS": OOS}
INDEX = ["^VIX", "^VIX3M", "^VIX9D", "^VVIX"]
ETPS = ["VIXY", "VIXM", "UVXY", "SVXY", "VXX", "SPY", "HYG", "LQD", "IEF", "BIL"]
NAMES = {"^VIX": "VIX", "^VIX3M": "VIX3M", "^VIX9D": "VIX9D", "^VVIX": "VVIX"}


def load_close(tickers, field="Close"):
    out = {}
    for t in tickers:
        df = rl.load_series(t)
        out[NAMES.get(t, t)] = df[field]
    return pd.DataFrame(out)


def panel(start="2011-01-01", field="Close"):
    """Closes of the index family and the tradables on VIXY's session index, ffilled."""
    etp = load_close(ETPS, field)
    idx = etp["VIXY"].dropna().index
    idx = idx[idx >= start]
    ix = load_close(INDEX, field)
    return pd.concat([ix, etp], axis=1).reindex(idx).ffill()


def bt(w, close, cost_bps=5.0, name="s"):
    """Single-instrument backtest on 252-day annualisation (research_lib.backtest)."""
    return rl.backtest(w, close, cost_bps=cost_bps, ann=ANN, name=name)


def bt_xs(w, close, cost_bps=5.0, name="s"):
    return rl.backtest_xs(w, close, cost_bps=cost_bps, ann=ANN, name=name)


def sh(r):
    r = pd.Series(r).dropna()
    s = r.std()
    return float(r.mean() / s * np.sqrt(ANN)) if s > 0 else np.nan


def split_row(net, extra=None):
    """One-line summary: Sharpe full/IS/OOS, CAGR, MaxDD, skew."""
    st = rl.perf_stats(net.loc[SPLITS["FULL"][0]:], ann=ANN)
    row = {"Sh": sh(net.loc[SPLITS["FULL"][0]:]), "IS": sh(net.loc[IS[0]:IS[1]]),
           "OOS": sh(net.loc[OOS[0]:OOS[1]]), "CAGR": st["CAGR"], "MaxDD": st["MaxDD"],
           "Skew": st["Skew"], "tNW": st["t_NW"]}
    if extra:
        row.update(extra)
    return row


def yearly_sharpe(net):
    return net.groupby(net.index.year).apply(sh)
