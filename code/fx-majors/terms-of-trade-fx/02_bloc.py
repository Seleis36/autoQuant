"""terms-of-trade-fx -- re-framing inside the commodity bloc.

01: across the G8 the ToT signal is noise (the five currencies with ~zero ToT dilute it and
USD/risk moves dominate). Here the trade is restricted to where ToT differs most and the
common factors cancel:
  BLOC   -- AUD, CAD, NZD only, demeaned among themselves (AUDCAD / AUDNZD / NZDCAD
            exposure, no USD, little risk-on beta); signal = relative ToT momentum
            (k = 1, 3, 6, 12 months) or relative ToT gap (12m dToT vs 12m dFX, z-scored).
  TS     -- each exporter vs USD on its own ToT momentum sign (pair-level trend in ToT).
Rebalance monthly and weekly. =X 2010-2026 (measured costs); H.10 2000-2026 (1 bp).
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
BLOC = ["AUD", "CAD", "NZD"]


def bloc_book(sig):
    s = sig[BLOC].sub(sig[BLOC].mean(axis=1), axis=0)
    W = s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return W.reindex(columns=CCYS).fillna(0.0)


def ts_book(sig):
    return (np.sign(sig[BLOC]) / 3).reindex(columns=CCYS).fillna(0.0)


def hold(W, idx, freq):
    s = pd.Series(idx, index=idx)
    key = idx.to_period("M") if freq == "M" else idx.to_period("W-SUN")
    last = s.groupby(key).transform("max").eq(s).values
    return W.reindex(idx)[last].reindex(idx).ffill().fillna(0.0)


def zb(x):
    return x.sub(x[BLOC].mean(axis=1), axis=0).div(x[BLOC].std(axis=1), axis=0)


def main():
    cmd = s01.load_cmd()
    rows = []
    px = load_px()
    idx = px.index
    fxl = np.log(usd_per_ccy(px))
    for k in (1, 3, 6, 12):
        d = lag_to_fx(s01.tot_change(cmd, 21 * k), idx, lag=1)
        for bname, bf in (("BLOC", bloc_book), ("TS", ts_book)):
            for freq in ("M", "W"):
                net, gross, turn, st = backtest(hold(bf(d), idx, freq), px, cost=None)
                t = split_table(net)
                rows.append({"sig": f"MOM{k}", "book": bname, "freq": freq, "FULL": t.loc["FULL", "Sharpe"],
                             "IS": t.loc["IS", "Sharpe"], "OOS": t.loc["OOS", "Sharpe"], "turn": st["Turnover_ann"]})
    for k in (6, 12):
        d = lag_to_fx(s01.tot_change(cmd, 21 * k), idx, lag=1)
        gap = zb(d) - zb(fxl - fxl.shift(21 * k))
        for freq in ("M", "W"):
            net, gross, turn, st = backtest(hold(bloc_book(gap), idx, freq), px, cost=None)
            t = split_table(net)
            rows.append({"sig": f"GAP{k}", "book": "BLOC", "freq": freq, "FULL": t.loc["FULL", "Sharpe"],
                         "IS": t.loc["IS", "Sharpe"], "OOS": t.loc["OOS", "Sharpe"], "turn": st["Turnover_ann"]})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(df.round(2).to_string())
    df.to_csv(os.path.join(HERE, "02_bloc_fx.csv"))

    h = h10_fx().loc["1999-01-01":].ffill().dropna()
    hidx = h.index
    r = h.pct_change()
    hl = np.log(h)
    out = []
    for k in (1, 3, 6, 12):
        cm = cmd.reindex(cmd.index.union(hidx)).ffill().reindex(hidx).shift(1)
        d = s01.tot_change(cm, 21 * k)
        sigs = {f"MOM{k}": (d, bloc_book), f"MOM{k}_TS": (d, ts_book)}
        if k in (6, 12):
            sigs[f"GAP{k}"] = (zb(d) - zb(hl - hl.shift(21 * k)), bloc_book)
        for name, (sg, bf) in sigs.items():
            for freq in ("M", "W"):
                W = hold(bf(sg), hidx, freq)
                net = (W.shift(1) * r[CCYS]).sum(axis=1) - (W.shift(1) - W.shift(2)).abs().sum(axis=1) * 1e-4
                row = {"sig": name, "freq": freq}
                for per, a, b in (("00-09", "2000", "2009"), ("10-19", "2010", "2019"), ("20-26", "2020", "2026"), ("ALL", "2000", "2026")):
                    row[per] = perf_stats(net.loc[a:b], ann=252)["Sharpe"]
                out.append(row)
    dh = pd.DataFrame(out)
    print("H.10 2000-2026:")
    print(dh.round(2).to_string())
    dh.to_csv(os.path.join(HERE, "02_bloc_h10.csv"))


if __name__ == "__main__":
    main()
