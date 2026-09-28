"""Strategy expressions of the IS-selected realized-moment features (h = 1 day).

Selection (IS only, fixed): |t_IS| >= 2 at h=1 in exp01 -> ret_1, RSJ_1, RSK_1, RSK_3,
PJV_3, NJV_3, each signed by its IS IC. Real-time standardisation: rolling 365-day
percentile rank (no future data). Composite = mean of signed ranks (centred at 0).

  A  standalone: w = 1{S > 0} x inv-vol
  B  gate on SMA50 x vol:   w = trend x vol x 1{S > 0}
  C  tilt on SMA50 x vol:   w = trend x vol x (0.5 + 0.5 x 1{S > 0})
  D  smoothed composite (EMA 3d, 7d) to cut turnover, as A
Costs 10 bp/side on daily Binance bars.
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
from features import daily_moments, window_features  # noqa: E402

SEL = {"ret_1": -1, "RSJ_1": -1, "RSK_1": -1, "RSK_3": -1, "PJV_3": -1, "NJV_3": +1}


def rolling_pct_rank(x, w=365):
    return x.rolling(w, min_periods=180).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True) - 0.5


def main():
    d = btc_daily()
    close = d.Close
    dm = daily_moments().reindex(d.index)
    feats = pd.concat([window_features(dm, L) for L in (1, 3)], axis=1)
    r = close.pct_change()
    vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    trend = (close > close.rolling(50).mean()).astype(float)
    z = pd.DataFrame({k: s * rolling_pct_rank(feats[k]) for k, s in SEL.items()})
    z["COMP"] = z.mean(axis=1)
    z["COMP_ema3"] = z["COMP"].ewm(span=3).mean()
    z["COMP_ema7"] = z["COMP"].ewm(span=7).mean()
    start = "2018-03-01"
    rows = []
    _, st = evaluate(vs, close, start=start, name="vol B&H"); rows.append(st)
    _, st = evaluate(trend * vs, close, start=start, name="SMA50 x vol"); rows.append(st)
    for k in z.columns:
        on = (z[k] > 0).astype(float)
        for nm, w in (("A", on * vs), ("B", trend * vs * on), ("C", trend * vs * (0.5 + 0.5 * on))):
            _, st = evaluate(w, close, start=start, name=f"{nm} {k}"); rows.append(st)
        _, st = evaluate(on * vs, close, start=start, cost_bps=0.0, name=f"A {k} @0bp"); rows.append(st)
    res = pd.concat(rows)
    pd.set_option("display.width", 200)
    print(res.round(2).to_string())
    res.to_csv(os.path.join(HERE, "exp02_backtest.csv"))


if __name__ == "__main__":
    main()
