"""BTC implied-vol (Deribit DVOL) features vs forward BTC returns, with realized-vol controls.

DVOL daily bar D Close = index at D+1 00:00 UTC = the decision time of Binance bar D.
RV30 = 30-day realized vol from 5-minute returns (jump-variance-timing/features.py).
Partial IC: feature rank residualised on rank(log RV30) and rank(ret_20) -- the ETH
dvol-vrp study found its lift was an RV effect in disguise, so every IV feature must beat RV.
IS = 2021-04 -> 2022-12 (DVOL starts 2021-03-24), OOS = 2023+.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "jump-variance-timing"))
sys.path.insert(0, os.path.join(REPO, "code", "spot-eth", "dvol-vrp"))
from btc_data import btc_daily  # noqa: E402
import research_lib as rl  # noqa: E402
from features import daily_moments  # noqa: E402
from fetch_dvol import load as load_dvol  # noqa: E402


def build():
    d = btc_daily()
    close = d.Close
    dm = daily_moments().reindex(d.index)
    iv = load_dvol("1d", currency="BTC")["Close"].reindex(d.index) / 100.0
    f = pd.DataFrame(index=d.index)
    rv30 = np.sqrt(dm.RV.rolling(30).sum() * 365 / 30)
    rv7 = np.sqrt(dm.RV.rolling(7).sum() * 365 / 7)
    f["IV"] = np.log(iv)
    f["RV30"] = np.log(rv30)
    f["RV7"] = np.log(rv7)
    f["VRP"] = iv ** 2 - rv30 ** 2
    f["IVRV30"] = np.log(iv / rv30)
    f["IVRV7"] = np.log(iv / rv7)
    for w in (90, 180):
        f[f"IVz{w}"] = (f.IV - f.IV.rolling(w, min_periods=w // 2).mean()) / f.IV.rolling(w, min_periods=w // 2).std()
        f[f"VRPz{w}"] = (f.VRP - f.VRP.rolling(w, min_periods=w // 2).mean()) / f.VRP.rolling(w, min_periods=w // 2).std()
        f[f"IVRVz{w}"] = (f.IVRV30 - f.IVRV30.rolling(w, min_periods=w // 2).mean()) / f.IVRV30.rolling(w, min_periods=w // 2).std()
        f[f"RVz{w}"] = (f.RV30 - f.RV30.rolling(w, min_periods=w // 2).mean()) / f.RV30.rolling(w, min_periods=w // 2).std()
    for k in (1, 5, 20):
        f[f"dIV{k}"] = f.IV.diff(k)
    f["ret_20"] = close.pct_change(20)
    f["ret_5"] = close.pct_change(5)
    return d, f


def ranks(x):
    r = x.rank()
    return (r - r.mean()) / r.std()


def ic(x, y, ctrls=()):
    m = x.notna() & y.notna()
    for c in ctrls:
        m &= c.notna()
    xr, yr = ranks(x[m]), ranks(y[m])
    if ctrls:
        C = np.column_stack([ranks(c[m]).values for c in ctrls] + [np.ones(m.sum())])
        beta = np.linalg.lstsq(C, xr.values, rcond=None)[0]
        xr = pd.Series(xr.values - C @ beta, index=xr.index)
        xr = xr / xr.std()
    p = (xr * yr).values
    return p.mean(), rl.newey_west_t(p, lags=1), len(p)


def main():
    d, f = build()
    close = d.Close
    rows = []
    for h in (1, 7, 28):
        fwd = close.shift(-h) / close - 1
        samp = f.index[::h]
        for c in f.columns:
            if c.startswith("ret_"):
                continue
            r = {"feat": c, "h": h}
            for k, (a, b) in {"IS": ("2021-04-01", "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
                x, y = f.loc[samp, c].loc[a:b], fwd.loc[samp].loc[a:b]
                r[f"IC_{k}"], r[f"t_{k}"], r[f"n_{k}"] = ic(x, y)
                ctr = [] if c.startswith("RV") else [f.loc[samp, "RV30"].loc[a:b]]
                ctr.append(f.loc[samp, "ret_20"].loc[a:b])
                r[f"pIC_{k}"], r[f"pt_{k}"], _ = ic(x, y, ctr)
            rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(HERE, "exp01_screen.csv"), index=False)
    pd.set_option("display.width", 220)
    for h in (1, 7, 28):
        print(f"\n=== h={h} ===")
        print(res[res.h == h].drop(columns=["h"]).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
