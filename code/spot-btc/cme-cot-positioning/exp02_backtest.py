"""Strategy expressions of the COT features, selected on IS only.

Selection rule (fixed before looking at OOS): every feature with |t_IS| >= 1.5 at the
7-day horizon in exp01; direction = sign of its IS IC. Each feature is standardised
by its own trailing 52-report z-score (so level drifts cannot masquerade as signal).

Expressions (10 bp/side, daily Binance bars, weight set at the close after release):
  A  standalone:    w = 1{signed z > 0} x inverse-vol(40%, hl 20d, cap 1)
  B  trend gate:    w = 1{close > SMA50} x inverse-vol x 1{signed z > 0}
  C  trend tilt:    w = 1{close > SMA50} x inverse-vol x (0.5 + 0.5 x 1{signed z > 0})
  D  IS composite:  mean of the signed z of all selected features, used as in A/B.
Baselines: vol-scaled buy & hold, trend x vol.
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
import fetch_cot_btc as cot  # noqa: E402
from features import weekly_base, weekly_features  # noqa: E402

START = "2018-10-01"   # first date with a 26-report z-score


def main():
    d = btc_daily()
    close = d["Close"]
    r = close.pct_change()
    vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    trend = (close > close.rolling(50).mean()).astype(float)

    c, avail = weekly_base()
    wf = weekly_features(c)
    scr = pd.read_csv(os.path.join(HERE, "exp01_screen.csv"))
    sel = scr[(scr.h == 7) & (scr.t_IS.abs() >= 1.5)].sort_values("t_IS", key=abs, ascending=False)
    sel = sel.drop_duplicates("IC_IS")            # nonrep_net == leg_nr_net etc.
    zw = {}
    for _, s in sel.iterrows():
        x = wf[s.feat]
        z = (x - x.rolling(52, min_periods=26).mean()) / x.rolling(52, min_periods=26).std()
        zw[s.feat] = np.sign(s.IC_IS) * z
    zw = pd.DataFrame(zw)
    zw["COMPOSITE"] = zw.mean(axis=1)
    zd = cot.on_daily_rows(zw, d.index, avail)

    rows = []
    _, st = evaluate(vs, close, start=START, name="volscaled B&H"); rows.append(st)
    _, st = evaluate(trend * vs, close, start=START, name="SMA50 x vol"); rows.append(st)
    for f in zd.columns:
        on = (zd[f] > 0).astype(float)
        _, st = evaluate(on * vs, close, start=START, name=f"A {f}"); rows.append(st)
        _, st = evaluate(trend * vs * on, close, start=START, name=f"B {f}"); rows.append(st)
        _, st = evaluate(trend * vs * (0.5 + 0.5 * on), close, start=START, name=f"C {f}"); rows.append(st)
    res = pd.concat(rows)
    pd.set_option("display.width", 200)
    print(sel[["feat", "IC_IS", "t_IS", "IC_OOS", "t_OOS"]].round(3).to_string(index=False))
    print(res.round(2).to_string())
    res.to_csv(os.path.join(HERE, "exp02_backtest.csv"))
    for k in ("A", "B", "C"):
        s = res[res.index.str.startswith(k + " ")]
        print(k, "median Sh full/IS/OOS:", s[["Sh_full", "Sh_IS", "Sh_OOS"]].median().round(2).tolist(),
              " n =", len(s))


if __name__ == "__main__":
    main()
