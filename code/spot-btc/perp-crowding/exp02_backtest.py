"""Diagnostics and IS-selected strategy forms for the perp-positioning (crowding) signal.

Selection (IS only, fixed): every feature with |partial t_IS| >= 2 at h = 1 or h = 3 in
exp01, signed by its IS partial IC. Standardisation: expanding percentile rank of past values
(min 180 obs). Composite = mean signed rank (centred). Forms at 10 bp/side, daily bars:
  A  1{C > 0} x inv-vol           L  (0.5 + C) x inv-vol  (linear)
  B  gate on SMA50 x vol          T  tilt: SMA50 x vol x (0.5 + 0.5 x 1{C > 0})
  E  EMA(5) smoothed composite, as A and B
Evaluation from 2021-03-01 (after the rank warm-up), IS <= 2022, OOS 2023+.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily, evaluate, yearly_sharpe  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import daily_metrics, features, ranks  # noqa: E402

START = "2021-03-01"


def exp_rank(x, minp=180):
    xv = x.dropna()
    return xv.expanding(min_periods=minp).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True).reindex(x.index) - 0.5


def main():
    d = btc_daily()
    close = d.Close
    met = daily_metrics(close.index)
    f = features(met, close)
    # diagnostics: yearly level and IC of the headline levels
    fwd3 = close.shift(-3) / close - 1
    y = f.index.year
    diag = {}
    for c in ("glob", "topacc", "toppos", "top_m_glob"):
        diag[f"{c}_mean"] = f[c].groupby(y).mean()
        diag[f"{c}_IC3"] = pd.Series({k: ranks(f[c][y == k][::3]).corr(ranks(fwd3[y == k][::3])) for k in sorted(set(y))})
    print(pd.DataFrame(diag).loc[2020:].round(3).to_string())

    scr = pd.read_csv(os.path.join(HERE, "exp01_screen.csv"))
    sel = scr[(scr.h.isin([1, 3])) & (scr.pt_IS.abs() >= 2)].sort_values("pt_IS", key=abs, ascending=False)
    sel = sel.drop_duplicates("feat")
    print("\nselected:", sel[["feat", "h", "pIC_IS", "pt_IS", "pIC_OOS", "pt_OOS"]].round(3).to_string(index=False))
    Z = pd.DataFrame({s.feat: np.sign(s.pIC_IS) * exp_rank(f[s.feat]) for _, s in sel.iterrows()})
    C = Z.mean(axis=1)
    CE = C.ewm(span=5).mean()
    r = close.pct_change()
    vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    trend = (close > close.rolling(50).mean()).astype(float)
    rows, nets = [], {}

    def run(nm, w):
        nets[nm], st = evaluate(w.fillna(0), close, start=START, name=nm)
        rows.append(st)

    run("vol B&H", vs)
    run("SMA50 x vol", trend * vs)
    for nm, s in (("C", C), ("CE5", CE)):
        on = (s > 0).astype(float)
        run(f"A {nm}", on * vs)
        run(f"L {nm}", (0.5 + s).clip(0, 1) * vs)
        run(f"B {nm}", on * trend * vs)
        run(f"T {nm}", (0.5 + 0.5 * on) * trend * vs)
    for c in ("topacc", "glob", "top_m_glob_d1"):
        s = np.sign(sel.set_index("feat").loc[c, "pIC_IS"]) * exp_rank(f[c])
        run(f"A single {c}", (s > 0).astype(float) * vs)
        run(f"B single {c}", (s > 0).astype(float) * trend * vs)
    res = pd.concat(rows)
    base = nets["SMA50 x vol"].loc[START:]
    res["corr_trend"] = [nets[k].loc[START:].corr(base) for k in res.index]
    pd.set_option("display.width", 200)
    print(res.round(2).to_string())
    res.to_csv(os.path.join(HERE, "exp02_backtest.csv"))
    for k in ("A C", "B C", "vol B&H", "SMA50 x vol"):
        print(k, yearly_sharpe(nets[k].loc[START:]).to_dict())


if __name__ == "__main__":
    main()
