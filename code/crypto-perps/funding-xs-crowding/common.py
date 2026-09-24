"""Shared data + helpers for funding-xs-crowding.

Pre-registered before any result was looked at:
  IS  = 2020-09-01 .. 2022-12-31   (first date with >= 20 funded, liquid names)
  OOS = 2023-01-01 .. end
  cost = 10 bp per side on traded notional (same as crypto-alts research)
  universe = point-in-time top-20 by trailing 90d median USD volume among coins that have a
             Binance USDT-M perp with >= 30 days of funding history on that date.
"""
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-perps", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-alts", "shared"))
import research_lib as rl  # noqa: E402
import funding_panel as fp  # noqa: E402
import universe as uv  # noqa: E402

IS = ("2020-09-01", "2022-12-31")
OOS = ("2023-01-01", "2026-12-31")
FULL = ("2020-09-01", "2026-12-31")
SPLITS = {"full": FULL, "IS": IS, "OOS": OOS}
COST = 10.0
TICKERS = list(fp.PERP_OF)


def load(n_top=20, min_funding_days=30):
    panel = uv.load_panel(TICKERS)
    close = uv.clean_close(panel["Close"])
    vol = panel["Volume"].reindex_like(close)
    fund, cnt = fp.daily_funding(close.columns)
    fund = fund.reindex(close.index)
    cnt = cnt.reindex(close.index)
    has_f = cnt.notna().cumsum() >= min_funding_days
    has_f = has_f.reindex(columns=close.columns, fill_value=False)
    fund = fund.reindex(columns=close.columns)
    # universe: top-n by volume among coins with a funded perp
    dv = vol
    med = dv.rolling(90, min_periods=45).median()
    hist = close.notna().cumsum()
    elig = (hist >= 120) & (med >= 1e6) & close.notna() & has_f & fund.notna()
    ranked = med.where(elig).rank(axis=1, ascending=False)
    mask = (ranked <= n_top) & elig
    close = close.loc["2020-01-01":]
    return close, vol.loc[close.index], fund.loc[close.index], mask.loc[close.index]


def rebalance_every(w, h):
    """Hold target weights for h days (rebalance on every h-th row)."""
    if h <= 1:
        return w
    keep = np.arange(len(w)) % h == 0
    return w.where(pd.Series(keep, index=w.index), np.nan).ffill().fillna(0.0)


def tranche(w, h):
    """h overlapping tranches (each rebalanced every h days, staggered): smooth weekly holding."""
    if h <= 1:
        return w
    parts = []
    for off in range(h):
        keep = (np.arange(len(w)) - off) % h == 0
        parts.append(w.where(pd.Series(keep, index=w.index), np.nan).ffill().fillna(0.0))
    return sum(parts) / h


def evaluate(w, close, name, cost=COST):
    net, st = rl.backtest_xs(w, close, cost_bps=cost, name=name)
    net = net.loc[FULL[0]:]
    row = {"name": name}
    for k, (a, b) in SPLITS.items():
        s = rl.perf_stats(net.loc[a:b], name=k)
        row[f"SR_{k}"] = s["Sharpe"]
        if k == "full":
            row["CAGR"] = s["CAGR"]
            row["MaxDD"] = s["MaxDD"]
    row["Turn"] = st["Turnover_ann"]
    row["Gross"] = st["AvgGross"]
    return net, row
