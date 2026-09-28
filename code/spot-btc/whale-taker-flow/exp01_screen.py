"""Daily taker-flow features by aggTrade size vs forward BTC returns.

Buckets (USD notional per aggTrade): S = <1k (retail), M = 1k-100k, L = >=100k (block/whale).
Features over trailing L days (known at the close of day D = D+1 00:00 UTC):
  imb_X   (buy_X - sell_X) / (buy_X + sell_X)          order-flow imbalance of bucket X
  net_X   (buy_X - sell_X) / total volume                signed flow share
  LmS     imb_L - imb_S                                  "whale minus retail"
  shareL  (L volume) / total volume, z-scored 90d        block participation
  each also z-scored vs its own trailing 90 days (z_...).
Partial IC controls for the same-window return (flow pushes price contemporaneously).
IS <= 2022, OOS 2023+ (tick store ends 2026-08).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily  # noqa: E402
import research_lib as rl  # noqa: E402

FLOW = os.path.join(REPO, "data", "BTCUSDT_spot_takerflow_size_1h.parquet")
GROUPS = {"S": [0], "M": [1, 2], "L": [3, 4]}


def daily_flow():
    h = pd.read_parquet(FLOW)
    d = h.resample("1D").sum()
    out = pd.DataFrame(index=d.index)
    for g, bs in GROUPS.items():
        out[f"buy_{g}"] = sum(d[f"buy_b{b}"] for b in bs if f"buy_b{b}" in d)
        out[f"sell_{g}"] = sum(d[f"sell_b{b}"] for b in bs if f"sell_b{b}" in d)
    out["tot"] = sum(out[f"buy_{g}"] + out[f"sell_{g}"] for g in GROUPS)
    return out[out.tot > 0]


def features(fl, close):
    f = pd.DataFrame(index=close.index)
    fl = fl.reindex(close.index)
    for L in (1, 3, 7, 14):
        s = fl.rolling(L, min_periods=L).sum()
        for g in GROUPS:
            f[f"imb_{g}_{L}"] = (s[f"buy_{g}"] - s[f"sell_{g}"]) / (s[f"buy_{g}"] + s[f"sell_{g}"])
            f[f"net_{g}_{L}"] = (s[f"buy_{g}"] - s[f"sell_{g}"]) / s.tot
        f[f"LmS_{L}"] = f[f"imb_L_{L}"] - f[f"imb_S_{L}"]
        f[f"shareL_{L}"] = (s.buy_L + s.sell_L) / s.tot
        f[f"ret_{L}"] = close.pct_change(L)
    for c in [c for c in f.columns if not c.startswith("ret_")]:
        f[f"z_{c}"] = (f[c] - f[c].rolling(90, min_periods=45).mean()) / f[c].rolling(90, min_periods=45).std()
    return f


def ranks(x):
    r = x.rank()
    return (r - r.mean()) / r.std()


def ic(x, y, ctrl=None):
    m = x.notna() & y.notna()
    if ctrl is not None:
        m &= ctrl.notna()
    xr, yr = ranks(x[m]), ranks(y[m])
    if ctrl is not None:
        c = ranks(ctrl[m])
        xr = xr - (xr * c).mean() / (c * c).mean() * c
        xr = xr / xr.std()
    p = (xr * yr).values
    return p.mean(), rl.newey_west_t(p, lags=1)


def main():
    d = btc_daily()
    close = d.Close.loc[:"2026-08-31"]
    f = features(daily_flow(), close)
    rows = []
    for h in (1, 3, 7):
        fwd = close.shift(-h) / close - 1
        samp = f.index[::h]
        for c in f.columns:
            if c.startswith("ret_"):
                continue
            L = c.split("_")[-1]
            r = {"feat": c, "h": h}
            for k, (a, b) in {"IS": ("2017-09-01", "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
                x, y = f.loc[samp, c].loc[a:b], fwd.loc[samp].loc[a:b]
                r[f"IC_{k}"], r[f"t_{k}"] = ic(x, y)
                r[f"pIC_{k}"], r[f"pt_{k}"] = ic(x, y, f.loc[samp, f"ret_{L}"].loc[a:b])
            rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(HERE, "exp01_screen.csv"), index=False)
    pd.set_option("display.width", 220)
    for h in (1, 3, 7):
        s = res[res.h == h]
        print(f"\n=== h={h}: top 20 by min(|pt_IS|,|pt_OOS|) with same sign ===")
        s = s.assign(k=np.where(np.sign(s.pt_IS) == np.sign(s.pt_OOS), np.minimum(s.pt_IS.abs(), s.pt_OOS.abs()), 0))
        print(s.sort_values("k", ascending=False).head(20).drop(columns=["h"]).round(3).to_string(index=False))
        print("IS->OOS spearman (partial t):", round(s.pt_IS.corr(s.pt_OOS, method="spearman"), 2),
              " raw:", round(s.t_IS.corr(s.t_OOS, method="spearman"), 2))


if __name__ == "__main__":
    main()
