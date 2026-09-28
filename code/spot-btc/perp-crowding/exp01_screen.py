"""Binance USD-M BTCUSDT positioning metrics vs forward spot BTC returns.

Metrics (5-minute snapshots, stamped at create_time): open interest (BTC and USD), top-trader
long/short ratio by accounts and by positions, global long/short account ratio (the
"retail" crowd), taker long/short volume ratio. For daily bar D (decision at D+1 00:00 UTC)
we use the last snapshot stamped STRICTLY before D+1 00:00 (i.e. <= 23:55 of D).

Features: log ratios (level, 90d z, 1/3/7 d change), top-minus-global positioning spread,
OI growth 1/3/7 d, OI growth x sign of same-window return (new longs vs short covering vs
long liquidation), taker ratio averages. Partial IC controls for the same-window return.
IS = 2020-09 -> 2022-12, OOS = 2023+.
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

MET = os.path.join(REPO, "data", "BTCUSDT_metrics_5m.parquet")


def daily_metrics(idx):
    m = pd.read_parquet(MET)
    m = m[m.index < m.index.max().normalize() + pd.Timedelta(days=1)]
    # snapshot strictly before D+1 00:00 -> shift stamps by 1 ns and take last in [D, D+1)
    d = m.resample("1D", label="left", closed="left").last()
    d["taker_mean"] = np.log(m["sum_taker_long_short_vol_ratio"]).resample("1D").mean()
    return d.reindex(idx)


def features(d, close):
    f = pd.DataFrame(index=close.index)
    lr = {"glob": np.log(d.count_long_short_ratio), "topacc": np.log(d.count_toptrader_long_short_ratio),
          "toppos": np.log(d.sum_toptrader_long_short_ratio)}
    lr["top_m_glob"] = lr["toppos"] - lr["glob"]
    for k, v in lr.items():
        f[f"{k}"] = v
        f[f"{k}_z90"] = (v - v.rolling(90, min_periods=45).mean()) / v.rolling(90, min_periods=45).std()
        for L in (1, 3, 7):
            f[f"{k}_d{L}"] = v.diff(L)
    loi = np.log(d.sum_open_interest)
    for L in (1, 3, 7):
        ret = close.pct_change(L)
        f[f"oi_g{L}"] = loi.diff(L)
        f[f"oi_g{L}_x_sign"] = loi.diff(L) * np.sign(ret)          # >0: OI moving with price
        f[f"oi_down_px_down_{L}"] = ((loi.diff(L) < 0) & (ret < 0)).astype(float)   # long liquidation
        f[f"oi_up_px_up_{L}"] = ((loi.diff(L) > 0) & (ret > 0)).astype(float)       # new longs
        f[f"taker_{L}"] = d.taker_mean.rolling(L).mean()
        f[f"ret_{L}"] = ret
    oiv = np.log(d.sum_open_interest_value)
    f["oi_z90"] = (oiv - oiv.rolling(90, min_periods=45).mean()) / oiv.rolling(90, min_periods=45).std()
    return f


def ranks(x):
    r = x.rank()
    return (r - r.mean()) / r.std()


def ic(x, y, c=None):
    m = x.notna() & y.notna()
    if c is not None:
        m &= c.notna()
    xr, yr = ranks(x[m]), ranks(y[m])
    if c is not None:
        cr = ranks(c[m])
        xr = xr - (xr * cr).mean() / (cr * cr).mean() * cr
        xr = xr / xr.std()
    p = (xr * yr).values
    return p.mean(), rl.newey_west_t(p, lags=1)


def main():
    dd = btc_daily()
    close = dd.Close
    f = features(daily_metrics(close.index), close)
    rows = []
    for h in (1, 3, 7):
        fwd = close.shift(-h) / close - 1
        samp = f.index[::h]
        for c in f.columns:
            if c.startswith("ret_"):
                continue
            digits = [ch for ch in c.split("_")[-1] if ch.isdigit()]
            L = int("".join(digits)) if digits and c.split("_")[-1][-1].isdigit() else 1
            L = L if L in (1, 3, 7) else 1
            r = {"feat": c, "h": h}
            for k, (a, b) in {"IS": ("2020-09-01", "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
                x, y = f.loc[samp, c].loc[a:b], fwd.loc[samp].loc[a:b]
                r[f"IC_{k}"], r[f"t_{k}"] = ic(x, y)
                r[f"pIC_{k}"], r[f"pt_{k}"] = ic(x, y, f.loc[samp, f"ret_{L}"].loc[a:b])
            rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(HERE, "exp01_screen.csv"), index=False)
    pd.set_option("display.width", 220)
    for h in (1, 3, 7):
        s = res[res.h == h]
        s = s.assign(k=np.where(np.sign(s.pt_IS) == np.sign(s.pt_OOS), np.minimum(s.pt_IS.abs(), s.pt_OOS.abs()), 0))
        print(f"\n=== h={h}: top 15 by consistent partial t ===")
        print(s.sort_values("k", ascending=False).head(15).drop(columns=["h"]).round(3).to_string(index=False))
        print("IS->OOS spearman partial t:", round(s.pt_IS.corr(s.pt_OOS, method="spearman"), 2),
              "| n IS-significant (|pt|>=2):", int((s.pt_IS.abs() >= 2).sum()),
              "of which same sign OOS:", int(((s.pt_IS.abs() >= 2) & (np.sign(s.pt_IS) == np.sign(s.pt_OOS))).sum()))


if __name__ == "__main__":
    main()
