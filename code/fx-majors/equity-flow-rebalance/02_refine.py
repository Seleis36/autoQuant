"""equity-flow-rebalance -- refinement of the rival sign (equity momentum -> currency up).

01 found the Hau-Rey rebalancing sign negative in every sub-period, and its mirror image --
past relative local-equity outperformance -> future currency appreciation (Brooks 2017 macro
momentum; return-chasing inflows) -- positive in all three sub-periods on the H.10 sample.

Checks here:
  1. Mechanical-bias control. `tr` converts USD ETF prices to local currency with the same
     FX series that is then traded, so FX noise at the rebalance date enters both the
     signal and the next return. `px` (local indices, no FX in the signal) is clean; `tr`
     is re-run with the signal window ending `skip` business days before the rebalance.
  2. Lookback composite: mean of cross-sectionally z-scored 1/3/6/12-month signals
     (pre-specified, equal weights) instead of choosing one lookback.
  3. Weekly rebalance (last row of each ISO week) as well as monthly.
  4. Sub-period stability on H.10 1999-2026 (monthly) and =X 2010-2026 (daily, 1 bp).
"""
import os
import sys
import importlib

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, HERE)
from fx_panel import CCYS, backtest, lag_to_fx, load_px, split_table, usd_per_ccy  # noqa: E402
from macro_data import h10_fx  # noqa: E402
from research_lib import perf_stats  # noqa: E402
s01 = importlib.import_module("01_screen")
G8 = ["USD"] + CCYS
LOOK = {1: 21, 3: 63, 6: 126, 12: 252}


def zxs(x):
    return x.sub(x.mean(axis=1), axis=0).div(x.std(axis=1), axis=0)


def signal_daily(eq_on_rows, k_days, skip):
    e = eq_on_rows.shift(skip)
    return np.log(e / e.shift(k_days))


def composite(eq_on_rows, skip, looks=(1, 3, 6, 12)):
    return sum(zxs(signal_daily(eq_on_rows, LOOK[k], skip)) for k in looks) / len(looks)


def hold(sig, idx, freq):
    s = pd.Series(idx, index=idx)
    key = idx.to_period("M") if freq == "M" else idx.to_period("W-FRI")
    last = s.groupby(key).transform("max").eq(s).values
    return sig.reindex(idx)[last].reindex(idx).ffill().fillna(0.0)


def main():
    rows = []
    # ---- H.10 1999-2026 monthly, on business-day H.10 rows
    h10 = h10_fx().loc["1998-01-01":].ffill().dropna()
    idx = h10.index
    for src in ("px", "tr"):
        eq = s01.equity_local(src, h10)
        eqr = eq.reindex(eq.index.union(idx)).ffill().reindex(idx)
        for skip in ((0, 3, 10) if src == "tr" else (0, 3)):
            sigs = {f"k{k}": signal_daily(eqr, LOOK[k], skip) for k in LOOK}
            sigs["combo"] = composite(eqr, skip)
            for name, sg in sigs.items():
                for freq in ("M", "W"):
                    W = hold(s01.xs_linear(sg.dropna(axis=1, how="all")).reindex(columns=CCYS).fillna(0.0), idx, freq)
                    r = h10.pct_change()
                    net = (W.shift(1) * r).sum(axis=1) - (W.shift(1) - W.shift(2)).abs().sum(axis=1) * 1e-4
                    net = net.loc["2000-01-01":]
                    row = {"data": "H10", "src": src, "skip": skip, "sig": name, "freq": freq}
                    for per, a, b in (("99-09", "2000", "2009"), ("10-19", "2010", "2019"),
                                      ("20-26", "2020", "2026"), ("ALL", "2000", "2026")):
                        row[per] = perf_stats(net.loc[a:b], ann=252)["Sharpe"]
                    rows.append(row)
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(df.round(2).to_string())
    df.to_csv(os.path.join(HERE, "02_refine_h10.csv"))

    # ---- =X 2010-2026 daily with 1 bp/side
    px = load_px()
    usd = usd_per_ccy(px)
    rows = []
    for src in ("px", "tr"):
        eq = s01.equity_local(src, usd)
        eqL = lag_to_fx(eq, px.index, lag=1)
        for skip in (0, 3):
            sigs = {f"k{k}": signal_daily(eqL, LOOK[k], skip) for k in LOOK}
            sigs["combo"] = composite(eqL, skip)
            for name, sg in sigs.items():
                for freq in ("M", "W"):
                    W = hold(s01.xs_linear(sg), px.index, freq)
                    net, gross, turn, st = backtest(W, px, cost=1.0)
                    t = split_table(net)
                    rows.append({"src": src, "skip": skip, "sig": name, "freq": freq,
                                 "FULL": t.loc["FULL", "Sharpe"], "IS": t.loc["IS", "Sharpe"],
                                 "OOS": t.loc["OOS", "Sharpe"], "turn": st["Turnover_ann"]})
    dx = pd.DataFrame(rows)
    print(dx.round(2).to_string())
    dx.to_csv(os.path.join(HERE, "02_refine_fx.csv"))


if __name__ == "__main__":
    main()
