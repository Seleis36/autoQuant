"""Is the contrarian retail-ratio state just short-term momentum in disguise?

The global account long/short ratio falls on up days (retail fades rallies), so `not crowded`
correlates with recent returns. Controls, same sizing and costs:
  M_k   1{ret_k > 0} x vol          k = 1, 2, 3, 5, 7 days
  RES   state from the ratio's RESIDUAL after regressing its daily change on the same-day and
        previous-day returns (expanding OLS, no look-ahead): the part of retail positioning
        that is not a mechanical reaction to price.
Also: overlap of P1 with M_1..M_3 and the Sharpe of P1 on days where it disagrees with M_1.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily, evaluate  # noqa: E402
import research_lib as rl  # noqa: E402
from exp02_backtest import START, exp_rank  # noqa: E402
from exp04_validate import glob_daily  # noqa: E402


def expanding_resid(y, X, minp=180):
    """Residual of y_t on X_t using OLS coefficients fitted on data up to t (inclusive)."""
    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    out = pd.Series(np.nan, index=df.index)
    Xv = np.column_stack([np.ones(len(df)), df.drop(columns="y").values])
    yv = df.y.values
    XtX = np.zeros((Xv.shape[1], Xv.shape[1]))
    Xty = np.zeros(Xv.shape[1])
    for i in range(len(df)):
        XtX += np.outer(Xv[i], Xv[i])
        Xty += Xv[i] * yv[i]
        if i >= minp:
            b = np.linalg.solve(XtX, Xty)
            out.iloc[i] = yv[i] - Xv[i] @ b
    return out.reindex(y.index)


def main():
    d = btc_daily()
    close = d.Close
    r = close.pct_change()
    vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    trend = (close > close.rolling(50).mean()).astype(float)
    g = glob_daily(close.index)
    on = (exp_rank(g) < 0).astype(float).where(exp_rank(g).notna(), 0.0)
    rows = []

    def run(nm, w):
        net, st = evaluate(w.fillna(0), close, start=START, name=nm)
        rows.append(st)
        return net

    run("P1 retail-ratio state", on * vs)
    run("P2 ... x trend", on * trend * vs)
    moms = {}
    for k in (1, 2, 3, 5, 7):
        m = (close.pct_change(k) > 0).astype(float)
        moms[k] = m
        run(f"M{k} 1{{ret_{k}>0}} x vol", m * vs)
        run(f"M{k} x trend", m * trend * vs)
    # residual positioning: daily change of the ratio net of same-day and lagged returns
    dg = g.diff()
    resid = expanding_resid(dg, pd.DataFrame({"r0": r, "r1": r.shift(1), "r2": r.shift(2)}))
    level_res = resid.rolling(10, min_periods=5).sum()          # 10-day accumulated non-price positioning
    rk = exp_rank(level_res)
    on_res = (rk < 0).astype(float).where(rk.notna(), 0.0)
    run("RES residual-positioning state x vol", on_res * vs)
    run("RES x trend", on_res * trend * vs)
    # combined: ratio state AND momentum M1 (does the ratio add to momentum?)
    run("P1 AND M1", on * moms[1] * vs)
    run("M1 AND NOT P1", (1 - on) * moms[1] * vs)
    run("P1 AND NOT M1", on * (1 - moms[1]) * vs)
    res = pd.concat(rows)
    pd.set_option("display.width", 200)
    print(res.round(2).to_string())
    x = pd.DataFrame({"P1": on, **{f"M{k}": moms[k] for k in moms}, "RES": on_res}).loc[START:]
    print("\nstate correlation:\n", x.corr().round(2).to_string())
    fwd1 = close.shift(-1) / close - 1
    for half, (a, b) in {"IS": (START, "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
        s = pd.DataFrame({"P1": on, "M1": moms[1], "f": fwd1}).loc[a:b].dropna()
        tab = s.groupby(["P1", "M1"]).f.agg(["mean", "count"])
        tab["mean"] *= 1e4
        print(half, "next-day bp by (P1, M1):\n", tab.round(1).to_string())


if __name__ == "__main__":
    main()
