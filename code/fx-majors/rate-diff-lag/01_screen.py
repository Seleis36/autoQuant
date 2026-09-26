"""rate-diff-lag -- does spot FX under-react to daily moves in the rate differential?

The rate differential is the first-order driver of G10 FX. Market yields move every day with
policy expectations, unlike the realised policy path tested (and failed) in
`policy-rate-momentum`. Pre-registered hypotheses, on the four pairs with free daily foreign
yields (EUR, GBP, JPY, CAD vs USD; 5y primary for all, 2y variant where it exists):

  H1 under-reaction: the change of the differential d = y_ccy - y_usd over k business days
     predicts the currency in the same direction.  weight = +z(dd_k)  (k = 1, 5, 20)
  H2 fair-value gap: FX drifts back to the level the differential implies. Rolling 250-day
     OLS of log FX on d; weight = -z(residual)  (currency rich vs rates -> sell it)

Timing: every yield stamped D-1 (local close, final before 00:00 UTC D) is used for the
=X row D weight (fx_panel.lag_to_fx(lag=1)); nothing stamped D. H1 k=1 rebalances daily,
everything else weekly (first row of the ISO week). Books: `bil` = each pair vs USD on its
own z-score, clipped at +-2, equal gross per pair; `xs` = demeaned across the 5 currencies
(USD + 4). Costs: measured 00:00 UTC half-spreads. =X 2010-2026; H.10 2002-2026 for the
weekly variants (1 bp).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from fx_panel import CCYS, backtest, lag_to_fx, load_px, split_table, usd_per_ccy  # noqa: E402
from fetch_yields import yields  # noqa: E402
from macro_data import h10_fx  # noqa: E402
from research_lib import perf_stats  # noqa: E402

PAIRS = ["EUR", "GBP", "JPY", "CAD"]


def diffs(y, tenor):
    out = {}
    for c in PAIRS:
        k = f"{c}{tenor}" if f"{c}{tenor}" in y else f"{c}5"
        out[c] = y[k] - y[f"USD{tenor}" if f"{c}{tenor}" in y else "USD5"]
    return pd.DataFrame(out)


def zroll(x, win=252, minp=120):
    return x / x.rolling(win, min_periods=minp).std()


def resid_z(fxl, d, win=250):
    """Rolling OLS of log FX on d (both on the same rows), residual at the last point,
    z-scored by the residual std in the window. Uses rows <= t only."""
    out = pd.DataFrame(index=fxl.index, columns=PAIRS, dtype=float)
    for c in PAIRS:
        y, x = fxl[c], d[c]
        mx, my = x.rolling(win, min_periods=120).mean(), y.rolling(win, min_periods=120).mean()
        cov = (x * y).rolling(win, min_periods=120).mean() - mx * my
        var = (x * x).rolling(win, min_periods=120).mean() - mx * mx
        b = cov / var
        a = my - b * mx
        e = y - (a + b * x)
        out[c] = e / (e.rolling(win, min_periods=120).std())
    return out


def bil(z):
    return (z[PAIRS].clip(-2, 2) / 2 / len(PAIRS)).reindex(columns=CCYS).fillna(0.0)


def xs(z):
    s = z[PAIRS].copy()
    s["USD"] = 0.0
    s = s.sub(s.mean(axis=1), axis=0)
    return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)[PAIRS].reindex(columns=CCYS).fillna(0.0)


def hold(W, idx, freq):
    if freq == "D":
        return W.reindex(idx).fillna(0.0)
    s = pd.Series(idx, index=idx)
    first = s.groupby(idx.to_period("W-SUN")).transform("min").eq(s).values
    return W.reindex(idx)[first].reindex(idx).ffill().fillna(0.0)


def main():
    y = yields()
    px = load_px()
    idx = px.index
    fxl = np.log(usd_per_ccy(px))
    rows = []
    for tenor in (5, 2):
        d = lag_to_fx(diffs(y, tenor), idx, lag=1)
        for k, freq in ((1, "D"), (5, "W"), (20, "W")):
            z = zroll(d.diff(k))
            for kind, f in (("bil", bil), ("xs", xs)):
                for sign, lab in ((1, "H1"), (-1, "H1rev")):
                    net, gross, turn, st = backtest(hold(f(sign * z), idx, freq), px, cost=None)
                    t = split_table(net)
                    rows.append({"tenor": tenor, "sig": f"{lab}_dd{k}", "book": kind, "FULL": t.loc["FULL", "Sharpe"],
                                 "IS": t.loc["IS", "Sharpe"], "OOS": t.loc["OOS", "Sharpe"],
                                 "gross": gross.mean() / gross.std() * np.sqrt(252), "turn": st["Turnover_ann"]})
        # H2: FX row D and d stamped D-1 are near-synchronous (the gap is FX's last ~4h)
        rz = resid_z(fxl[PAIRS], d)
        for kind, f in (("bil", bil), ("xs", xs)):
            for sign, lab in ((-1, "H2"), (1, "H2rev")):
                net, gross, turn, st = backtest(hold(f(sign * rz), idx, "W"), px, cost=None)
                t = split_table(net)
                rows.append({"tenor": tenor, "sig": lab, "book": kind, "FULL": t.loc["FULL", "Sharpe"],
                             "IS": t.loc["IS", "Sharpe"], "OOS": t.loc["OOS", "Sharpe"],
                             "gross": gross.mean() / gross.std() * np.sqrt(252), "turn": st["Turnover_ann"]})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(df.round(2).to_string())
    df.to_csv(os.path.join(HERE, "01_screen_fx.csv"))

    # H.10 (noon NY). Yields stamped D-1 for the noon-D row -- conservative (Bunds/JGB/gilts
    # of day D are partly known by noon NY, US yields are not).
    h = h10_fx().loc["2002-01-01":].ffill().dropna()
    hidx = h.index
    r = h.pct_change()
    hl = np.log(h)
    out = []
    d = diffs(y, 5)
    d.index = d.index + pd.Timedelta(days=1)
    d = d.reindex(d.index.union(hidx)).ffill().reindex(hidx)
    sigs = {"H1_dd5": zroll(d.diff(5)), "H1_dd20": zroll(d.diff(20)), "H2": -resid_z(hl[PAIRS], d)}
    for name, z in sigs.items():
        for kind, f in (("bil", bil), ("xs", xs)):
            W = hold(f(z), hidx, "W")
            net = (W.shift(1) * r[CCYS]).sum(axis=1) - (W.shift(1) - W.shift(2)).abs().sum(axis=1) * 1e-4
            row = {"sig": name, "book": kind}
            for per, a, b in (("02-09", "2002", "2009"), ("10-19", "2010", "2019"), ("20-26", "2020", "2026"), ("ALL", "2002", "2026")):
                row[per] = perf_stats(net.loc[a:b], ann=252)["Sharpe"]
            out.append(row)
    dh = pd.DataFrame(out)
    print("H.10 2002-2026 weekly (5y):")
    print(dh.round(2).to_string())
    dh.to_csv(os.path.join(HERE, "01_screen_h10.csv"))


if __name__ == "__main__":
    main()
