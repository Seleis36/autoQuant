"""rate-diff-lag -- re-framings after 01 (H1 dd20 pair-vs-USD ~0.4 on =X, ~0.2 on H.10).

  COMP   : composite of z(dd5), z(dd20), z(dd60) over both tenors (2y where available, 5y),
           pair vs USD. Pre-specified equal weights.
  GATED  : COMP traded only while the pair is rate-driven -- trailing 60-day correlation of
           daily d(log FX) with d(differential) (same lagged alignment) above its own
           expanding median. Idea: the lead exists when rates are the dominant FX driver.
  SCALED : COMP x that correlation (continuous, clipped at 0).
Weekly rebalance; measured costs; =X 2010-2026 and H.10 2002-2026 (1 bp).
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
from fetch_yields import yields  # noqa: E402
from macro_data import h10_fx  # noqa: E402
from research_lib import perf_stats  # noqa: E402
s1 = importlib.import_module("01_screen")
PAIRS = s1.PAIRS


def composite(d2, d5):
    parts = []
    for d in (d2, d5):
        for k in (5, 20, 60):
            parts.append(s1.zroll(d.diff(k)).clip(-3, 3))
    return sum(parts) / len(parts)


def books(fxl, d2, d5):
    comp = composite(d2, d5)
    dfx = fxl[PAIRS].diff()
    corr = dfx.rolling(60, min_periods=40).corr(d5.diff())
    gate = (corr > corr.expanding(250).median()).astype(float)
    return {"COMP": comp, "GATED": comp * gate, "SCALED": comp * corr.clip(lower=0) * 2}


def main():
    y = yields()
    rows = []
    px = load_px()
    idx = px.index
    fxl = np.log(usd_per_ccy(px))
    d2 = lag_to_fx(s1.diffs(y, 2), idx, lag=1)
    d5 = lag_to_fx(s1.diffs(y, 5), idx, lag=1)
    B = books(fxl, d2, d5)
    nets = {}
    for name, z in B.items():
        for kind, f in (("bil", s1.bil), ("xs", s1.xs)):
            net, gross, turn, st = backtest(s1.hold(f(z), idx, "W"), px, cost=None)
            nets[f"{name}_{kind}"] = net
            t = split_table(net)
            rows.append({"book": f"{name}_{kind}", "FULL": t.loc["FULL", "Sharpe"], "IS": t.loc["IS", "Sharpe"],
                         "OOS": t.loc["OOS", "Sharpe"], "t": t.loc["FULL", "t_NW"], "turn": st["Turnover_ann"]})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(df.round(2).to_string())
    df.to_csv(os.path.join(HERE, "02_regime_fx.csv"))
    pd.DataFrame(nets).to_parquet(os.path.join(HERE, "02_regime_nets.parquet"))
    N = pd.DataFrame(nets)
    print("per-year COMP_bil:", N["COMP_bil"].groupby(N.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(252)).round(2).to_dict())

    h = h10_fx().loc["2002-01-01":].ffill().dropna()
    hidx = h.index
    r = h.pct_change()
    hl = np.log(h)
    out = []

    def lagh(x):
        x = x.copy(); x.index = x.index + pd.Timedelta(days=1)
        return x.reindex(x.index.union(hidx)).ffill().reindex(hidx)
    Bh = books(hl, lagh(s1.diffs(y, 2)), lagh(s1.diffs(y, 5)))
    for name, z in Bh.items():
        for kind, f in (("bil", s1.bil), ("xs", s1.xs)):
            W = s1.hold(f(z), hidx, "W")
            net = (W.shift(1) * r[CCYS]).sum(axis=1) - (W.shift(1) - W.shift(2)).abs().sum(axis=1) * 1e-4
            row = {"book": f"{name}_{kind}"}
            for per, a, b in (("02-09", "2002", "2009"), ("10-19", "2010", "2019"), ("20-26", "2020", "2026"), ("ALL", "2002", "2026")):
                row[per] = perf_stats(net.loc[a:b], ann=252)["Sharpe"]
            out.append(row)
    dh = pd.DataFrame(out)
    print("H.10 2002-2026:")
    print(dh.round(2).to_string())
    dh.to_csv(os.path.join(HERE, "02_regime_h10.csv"))


if __name__ == "__main__":
    main()
