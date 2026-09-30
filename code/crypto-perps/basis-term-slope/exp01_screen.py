"""exp01 — does the quarterly-futures term structure time BTC / ETH spot?

Row D (close = D+1 00:00 UTC):
  basis_ann  log(F/S) x 365 / days-to-expiry, F = COIN-M current-quarter close if >= 30 days
             to expiry, else next-quarter (avoids the near-expiry blow-up); S = Binance spot
  fund_ann   trailing 7-day mean of daily USDT-M perp funding (lag-safe: settlements <= D 16:00)
             x 365
  slope      basis_ann - fund_ann      (term premium of the dated contract over the perp)
Pre-declared: z = (x - 365d mean) / 365d std; Spearman IC with forward 7/30d spot returns
(IS 2020-07..2023-12, OOS 2024+); partial IC controlling for mom30 and SMA50 distance;
rules on spot x inverse-vol (40 %, cap 1), 10 bp: flat if z > 1 (crowded longs) and
flat if z < -1 (backwardation / fear), vs inverse-vol alone and SMA50 x inverse-vol.
"""
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-perps", "shared"))
import research_lib as rl  # noqa: E402
import funding_panel as fp  # noqa: E402
from fetch_quarterly import path_of, expiry_after  # noqa: E402


def build(pair, spot_sym, perp_tk):
    cq = pd.read_parquet(path_of(pair, "CURRENT_QUARTER"))["Close"]
    nq = pd.read_parquet(path_of(pair, "NEXT_QUARTER"))["Close"]
    s = pd.read_parquet(os.path.join(rl.DATA_DIR, f"BINANCE_{spot_sym}_1d.parquet"))["Close"]
    df = pd.DataFrame({"cq": cq, "nq": nq, "s": s}).dropna()
    tc = df.index + pd.Timedelta(days=1)
    d1 = np.array([(expiry_after(t) - t).total_seconds() / 86400 for t in tc])
    d2 = np.array([(expiry_after(t, 1) - t).total_seconds() / 86400 for t in tc])
    use_cq = d1 >= 30
    df["basis_ann"] = np.where(use_cq, np.log(df.cq / df.s) * 365 / d1, np.log(df.nq / df.s) * 365 / d2)
    f, _ = fp.daily_funding([perp_tk])
    df["fund_ann"] = f[perp_tk].reindex(df.index).rolling(7, min_periods=5).mean() * 365
    df["slope"] = df.basis_ann - df.fund_ann
    return df


def zf(x, win=365):
    return (x - x.rolling(win, min_periods=win // 2).mean()) / x.rolling(win, min_periods=win // 2).std()


def partial_ic(y, x, ctrls):
    d = pd.concat([y, x] + ctrls, axis=1).dropna().rank()
    X = np.column_stack([np.ones(len(d))] + [d.iloc[:, 2 + i] for i in range(len(ctrls))])
    ry = d.iloc[:, 0] - X @ np.linalg.lstsq(X, d.iloc[:, 0], rcond=None)[0]
    rx = d.iloc[:, 1] - X @ np.linalg.lstsq(X, d.iloc[:, 1], rcond=None)[0]
    return np.corrcoef(ry, rx)[0, 1]


PER = {"IS": ("2020-07-01", "2023-12-31"), "OOS": ("2024-01-01", "2026-12-31")}
rows = []
for pair, spot, tk in (("BTCUSD", "BTCUSDT", "BTC-USD"), ("ETHUSD", "ETHUSDT", "ETH-USD")):
    df = build(pair, spot, tk)
    print(pair, "basis_ann mean/median by year:", df.basis_ann.groupby(df.index.year).median().round(3).to_dict())
    px = df.s
    mom30 = px.pct_change(30)
    trend = np.log(px / px.rolling(50).mean())
    for feat in ("basis_ann", "slope", "fund_ann"):
        z = zf(df[feat])
        for h in (7, 30):
            f = px.shift(-h) / px - 1
            for per, (a, b) in PER.items():
                g = pd.concat([z, f], axis=1).loc[a:b].dropna()
                pic = partial_ic(f.loc[a:b], z.loc[a:b], [mom30.loc[a:b], trend.loc[a:b]])
                print(f"  {pair} {feat:9s} h{h:2d} {per}: IC {g.corr(method='spearman').iloc[0, 1]:+.3f}  partial {pic:+.3f}  n={len(g)}")
    ret = px.pct_change()
    vt = rl.vol_target_scalar(ret, target=0.40, halflife=20, cap=1.0)
    sma = (px > px.rolling(50).mean()).astype(float)
    zb, zs = zf(df.basis_ann), zf(df.slope)
    start = zs.dropna().index[0]
    rules = {"inverse-vol alone": vt, "SMA50 x inverse-vol": sma * vt,
             "basis: flat if z>1": (zb <= 1).astype(float) * vt, "basis: flat if z<-1": (zb >= -1).astype(float) * vt,
             "slope: flat if z>1": (zs <= 1).astype(float) * vt, "slope: flat if z<-1": (zs >= -1).astype(float) * vt,
             "SMA50 x inv-vol x basis flat if z>1": sma * vt * (zb <= 1).astype(float)}
    for nm, w in rules.items():
        net, st = rl.backtest(w.fillna(0).loc[start:], px.loc[start:], cost_bps=10)
        rows.append({"pair": pair, "rule": nm, "SR_full": rl.perf_stats(net)["Sharpe"],
                     "SR_IS": rl.perf_stats(net.loc[:PER["IS"][1]])["Sharpe"],
                     "SR_OOS": rl.perf_stats(net.loc[PER["OOS"][0]:])["Sharpe"], "MaxDD": st["MaxDD"],
                     "expo": st["AvgExposure"]})
    df.to_parquet(f"exp01_{pair}.parquet")
pd.set_option("display.width", 200)
print(pd.DataFrame(rows).round(2).to_string(index=False))
pd.DataFrame(rows).to_csv("exp01_results.csv", index=False)
