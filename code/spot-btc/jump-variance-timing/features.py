"""Daily realized-moment features from 5-minute Binance BTCUSDT returns.

Day D covers [D 00:00, D+1 00:00) UTC; a feature stamped D uses only 5m returns inside
days D-L+1..D, so it is known at the close of D (the decision time).

  RV    sum r^2                                  realized variance
  RSP   sum r^2 1{r>0}, RSM  sum r^2 1{r<0}      semivariances (Barndorff-Nielsen et al.)
  RSJ   (RSP - RSM) / RV                         relative signed jump (Bollerslev et al. 2020)
  RSK   sqrt(N) sum r^3 / RV^1.5                 realized skewness (Amaya et al. 2015)
  RKU   N sum r^4 / RV^2                         realized kurtosis
  JV    max(RV - BPV, 0) / RV                    jump share, BPV = pi/2 sum |r_t||r_t-1|
  PJV / NJV  jump share split by the sign of the day's largest |r| (Lee & Wang proxy)
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import btc_data  # noqa: E402,F401
from bars import load_bars  # noqa: E402

CACHE = os.path.join(HERE, "_daily_moments.parquet")   # derived, not market data; git-ignored by name


def daily_moments(refresh=False):
    if os.path.exists(CACHE) and not refresh:
        return pd.read_parquet(CACHE)
    m = load_bars("BTCUSDT", "1m", columns=["Close"])["Close"]
    p5 = m.resample("5min", label="left", closed="left").last().dropna()
    r = np.log(p5).diff()
    # drop returns spanning a gap (> 5 min between consecutive bars)
    gap = p5.index.to_series().diff() > pd.Timedelta(minutes=5)
    r[gap.values] = np.nan
    r = r.dropna()
    day = r.index.normalize()
    df = pd.DataFrame({"r": r.values, "day": day})
    df["r2"] = df.r ** 2
    df["r3"] = df.r ** 3
    df["r4"] = df.r ** 4
    df["rp2"] = np.where(df.r > 0, df.r2, 0.0)
    df["rm2"] = np.where(df.r < 0, df.r2, 0.0)
    df["absr"] = df.r.abs()
    df["bp"] = df.absr * df.groupby("day").absr.shift(1)
    g = df.groupby("day")
    out = pd.DataFrame({
        "N": g.r.count(), "ret": g.r.sum(), "RV": g.r2.sum(), "RSP": g.rp2.sum(), "RSM": g.rm2.sum(),
        "S3": g.r3.sum(), "S4": g.r4.sum(), "BPV": g.bp.sum() * np.pi / 2,
    })
    idx = g.absr.idxmax()
    out["maxsign"] = np.sign(df.loc[idx.values, "r"].values)
    out.to_parquet(CACHE)
    return out


def window_features(dm, L):
    """Aggregate daily sums over trailing L days and build the ratios."""
    s = dm[["N", "ret", "RV", "RSP", "RSM", "S3", "S4", "BPV"]].rolling(L, min_periods=L).sum()
    f = pd.DataFrame(index=dm.index)
    f[f"ret_{L}"] = s.ret
    f[f"RV_{L}"] = np.log(s.RV)
    f[f"RSJ_{L}"] = (s.RSP - s.RSM) / s.RV
    f[f"RSK_{L}"] = np.sqrt(s.N) * s.S3 / s.RV ** 1.5
    f[f"RKU_{L}"] = s.N * s.S4 / s.RV ** 2
    jv = ((s.RV - s.BPV).clip(lower=0) / s.RV)
    f[f"JV_{L}"] = jv
    djv = ((dm.RV - dm.BPV).clip(lower=0))
    pj = (djv * (dm.maxsign > 0)).rolling(L).sum() / s.RV
    nj = (djv * (dm.maxsign < 0)).rolling(L).sum() / s.RV
    f[f"PJV_{L}"] = pj
    f[f"NJV_{L}"] = nj
    f[f"RVz_{L}"] = f[f"RV_{L}"] - np.log(dm.RV.rolling(180, min_periods=90).mean() * L)
    return f
