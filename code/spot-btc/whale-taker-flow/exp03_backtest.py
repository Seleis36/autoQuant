"""Pre-specified strategy forms of LmS_3 (chosen on IS in exp01; no OOS-based threshold).

  A  w = 1{rank_exp(LmS_3) > 0.5} x inv-vol          (above its own expanding median)
  L  w = rank_exp(LmS_3) x inv-vol                     (linear in the expanding rank)
  B  gate on SMA50 x vol, C tilt 0.5 + 0.5 x signal on SMA50 x vol
Rank = expanding percentile of past values only (min 180 obs). 10 bp/side, Binance daily,
2018-03 -> 2026-08 (tick store end). Yearly Sharpe and correlation to SMA50 x vol shown.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import evaluate, btc_daily, yearly_sharpe  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import daily_flow, features  # noqa: E402

START = "2018-03-01"


def exp_rank(x, minp=180):
    xv = x.dropna()
    return xv.expanding(min_periods=minp).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True).reindex(x.index)


def main():
    d = btc_daily()
    close = d.Close.loc[:"2026-08-31"]
    f = features(daily_flow(), close)
    r = close.pct_change()
    vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    trend = (close > close.rolling(50).mean()).astype(float)
    rows, nets = [], {}
    for nm, w in (("vol B&H", vs), ("SMA50 x vol", trend * vs)):
        nets[nm], st = evaluate(w, close, start=START, name=nm); rows.append(st)
    for feat in ("LmS_3", "LmS_7", "imb_L_3"):
        rk = exp_rank(f[feat]).fillna(0.5)
        on = (rk > 0.5).astype(float)
        for nm, w in ((f"A {feat}", on * vs), (f"L {feat}", rk * vs), (f"B {feat}", on * trend * vs),
                      (f"C {feat}", (0.5 + 0.5 * on) * trend * vs), (f"LC {feat}", (0.5 + 0.5 * rk) * trend * vs)):
            nets[nm], st = evaluate(w, close, start=START, name=nm); rows.append(st)
    res = pd.concat(rows)
    base = nets["SMA50 x vol"]
    res["corr_trend"] = [nets[k].loc[START:].corr(base.loc[START:]) for k in res.index]
    pd.set_option("display.width", 200)
    print(res.round(2).to_string())
    for k in ("A LmS_3", "L LmS_3", "SMA50 x vol", "vol B&H"):
        print(k, yearly_sharpe(nets[k].loc[START:]).to_dict())
    res.to_csv(os.path.join(HERE, "exp03_backtest.csv"))


if __name__ == "__main__":
    main()
