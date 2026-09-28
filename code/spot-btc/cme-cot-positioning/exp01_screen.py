"""Screen every COT feature against forward BTC returns, weekly sampling.

Sample point = the Saturday daily bar (decision at Sunday 00:00 UTC, after the
conservative Saturday 21:00 UTC availability of Friday's release). Forward returns from
that close over 7 / 14 / 28 days. IS = report weeks <= 2022, OOS = 2023+ (fixed in advance).
Statistic: rank IC (Pearson on cross-time ranks) with Newey-West t (lags = h/7).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily  # noqa: E402
import research_lib as rl  # noqa: E402
from features import daily_features  # noqa: E402


def ic_t(x, y, lags):
    m = x.notna() & y.notna()
    x, y = x[m], y[m]
    if len(x) < 30:
        return np.nan, np.nan, 0
    xr = (x.rank() - x.rank().mean()) / x.rank().std()
    yr = (y.rank() - y.rank().mean()) / y.rank().std()
    prod = (xr * yr).values
    return prod.mean(), rl.newey_west_t(prod, lags=lags), len(x)


def main():
    d = btc_daily()
    close = d["Close"]
    feats, _ = daily_features(d.index)
    sat = d.index[d.index.dayofweek == 5]
    rows = []
    for h in (7, 14, 28):
        fwd = close.shift(-h) / close - 1
        for c in feats.columns:
            x = feats.loc[sat, c]
            y = fwd.loc[sat]
            r = {"feat": c, "h": h}
            for k, (a, b) in {"IS": (None, "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
                ic, t, n = ic_t(x.loc[a:b], y.loc[a:b], lags=max(1, h // 7))
                r[f"IC_{k}"], r[f"t_{k}"], r[f"n_{k}"] = ic, t, n
            rows.append(r)
    res = pd.DataFrame(rows)
    res["same_sign"] = np.sign(res.IC_IS) == np.sign(res.IC_OOS)
    res["min_abs_t"] = np.where(res.same_sign, np.minimum(res.t_IS.abs(), res.t_OOS.abs()), 0)
    res.to_csv(os.path.join(HERE, "exp01_screen.csv"), index=False)
    pd.set_option("display.width", 200)
    for h in (7, 14, 28):
        s = res[res.h == h].sort_values("t_IS", key=abs, ascending=False)
        print(f"\n=== h={h}d  top by |t_IS| ===")
        print(s.head(20).round(3).to_string(index=False))
    print("\n=== survivors: |t_IS|>=2 and same sign OOS ===")
    print(res[(res.t_IS.abs() >= 2) & res.same_sign].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
