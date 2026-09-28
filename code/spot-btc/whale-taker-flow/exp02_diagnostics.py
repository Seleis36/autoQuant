"""Is LmS (whale-minus-retail imbalance) a regime or trend proxy?

1. yearly mean/std of LmS_3, imb_L_3, imb_S_3 and the yearly IC (h = 1 and 3).
2. partial IC with a wider control set: same-window return, 20-day return, SMA50 state,
   log RV30, and the 90-day mean of LmS itself (does the *deviation* carry it?).
3. decile profile of next-3-day return on LmS_3 (expanding deciles, no look-ahead).
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
from exp01_screen import daily_flow, features, ranks  # noqa: E402


def pic(x, y, ctrls):
    m = x.notna() & y.notna()
    for c in ctrls:
        m &= c.notna()
    xr, yr = ranks(x[m]), ranks(y[m])
    C = np.column_stack([ranks(c[m]).values for c in ctrls] + [np.ones(m.sum())])
    xr = pd.Series(xr.values - C @ np.linalg.lstsq(C, xr.values, rcond=None)[0], index=xr.index)
    p = (xr / xr.std() * yr).values
    return round(p.mean(), 3), round(rl.newey_west_t(p, lags=1), 2)


def main():
    d = btc_daily()
    close = d.Close.loc[:"2026-08-31"]
    f = features(daily_flow(), close)
    r = close.pct_change()
    f["trend"] = (close > close.rolling(50).mean()).astype(float)
    f["rv30"] = np.log(r.rolling(30).std())
    f["LmS_3_m90"] = f.LmS_3.rolling(90, min_periods=45).mean()
    f["LmS_3_dev"] = f.LmS_3 - f.LmS_3_m90
    fwd1 = close.shift(-1) / close - 1
    fwd3 = close.shift(-3) / close - 1
    y = f.index.year
    tab = pd.DataFrame({
        "LmS_3": f.LmS_3.groupby(y).mean(), "imb_L_3": f.imb_L_3.groupby(y).mean(),
        "imb_S_3": f.imb_S_3.groupby(y).mean(), "shareL": f.shareL_1.groupby(y).mean(),
        "IC1": [ranks(f.LmS_3[y == k]).corr(ranks(fwd1[y == k])) for k in sorted(set(y))],
        "IC3": [ranks(f.LmS_3[y == k][::3]).corr(ranks(fwd3[y == k][::3])) for k in sorted(set(y))],
    })
    print(tab.round(3).to_string())
    for h, fwd in ((1, fwd1), (3, fwd3)):
        samp = f.index[::h]
        for half, (a, b) in {"IS": ("2017-09-01", "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
            F = f.loc[samp].loc[a:b]
            Y = fwd.loc[samp].loc[a:b]
            print(f"h={h} {half}: LmS_3 | ret_3: {pic(F.LmS_3, Y, [F.ret_3])}"
                  f"  | ret_3,ret_14,trend,rv30: {pic(F.LmS_3, Y, [F.ret_3, F.ret_14, F.trend, F.rv30])}"
                  f"  | +own m90: {pic(F.LmS_3, Y, [F.ret_3, F.ret_14, F.trend, F.rv30, F.LmS_3_m90])}"
                  f"  | dev only: {pic(F.LmS_3_dev, Y, [F.ret_3])}")
    x = f.LmS_3.dropna()
    rk = x.expanding(min_periods=180).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True)
    q = (np.floor(rk * 10).clip(0, 9) + 1).rename("dec")
    df = pd.concat([q, fwd3.rename("f3"), fwd1.rename("f1")], axis=1).dropna()
    for half, (a, b) in {"IS": (None, "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
        s = df.loc[a:b]
        print(half, "next-1d bp by decile:", (s.groupby("dec").f1.mean() * 1e4).round(0).astype(int).tolist())
        print(half, "next-3d bp by decile:", (s.groupby("dec").f3.mean() * 1e4).round(0).astype(int).tolist())


if __name__ == "__main__":
    main()
