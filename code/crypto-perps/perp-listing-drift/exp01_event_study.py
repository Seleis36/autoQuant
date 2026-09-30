"""exp01 — event study: spot abnormal returns around Binance USDT-M perp listings.

Abnormal return = coin spot return minus BTC spot return (beta 1). Day 0 = listing day
(close of D0 is the earliest entry); CAR(a,b) sums days a..b inclusive, where day k's return
is close(D0+k)/close(D0+k-1)-1. Pre-event window [-30,-1] shows the announcement run-up.
Splits: IS (D0 <= 2022) / OOS; spot age at listing; pre-event run-up tercile.
"""
import numpy as np
import pandas as pd

from common import load_listings, spot_close_panel, clean_close, IS_END

s = load_listings()
close = clean_close(spot_close_panel(sorted(set(s.spot_base) | {"BTC"})))
ret = close.pct_change(fill_method=None)
ab = ret.sub(ret["BTC"], axis=0)

K = list(range(-30, 121))
rows, paths = [], {}
for _, e in s.iterrows():
    b = e.spot_base
    if b not in ab or b == "BTC":
        continue
    d0 = e.D0
    if d0 not in ab.index or pd.isna(close.at[d0, b]):
        continue                              # spot not trading on D0 -> not tradeable
    idx = ab.index.get_loc(d0)
    seg = ab[b].iloc[max(0, idx - 30): idx + 121]
    rel = np.arange(len(seg)) + (max(0, idx - 30) - idx)
    path = pd.Series(seg.values, index=rel)
    paths[e.symbol] = path
    row = dict(symbol=e.symbol, base=b, D0=d0, spot_age=e.spot_age, status=e.status)
    for a, bb in [(-30, -1), (-5, -1), (0, 0), (1, 1), (1, 7), (1, 14), (1, 30), (1, 60), (1, 90), (1, 120)]:
        w = path.loc[a:bb]
        need = bb - a + 1
        row[f"car_{a}_{bb}"] = w.sum() if w.notna().sum() >= 0.8 * need else np.nan
    rows.append(row)

ev = pd.DataFrame(rows)
ev["period"] = np.where(ev.D0 <= IS_END, "IS", "OOS")
ev["age_bucket"] = pd.cut(ev.spot_age, [-1, 30, 180, 730, 1e5], labels=["<30d", "30-180d", "180d-2y", ">2y"])
print(f"events with spot on D0: {len(ev)}  (IS {sum(ev.period=='IS')}, OOS {sum(ev.period=='OOS')})")
print("per year:", ev.D0.dt.year.value_counts().sort_index().to_dict())

cars = [c for c in ev.columns if c.startswith("car_")]


def summ(g):
    out = {}
    for c in cars:
        x = g[c].dropna()
        out[c] = f"{x.mean()*100:+.1f} ({x.mean()/x.std()*np.sqrt(len(x)) if len(x)>2 else np.nan:+.1f}) med {x.median()*100:+.1f}"
    out["n"] = len(g)
    return pd.Series(out)


pd.set_option("display.width", 250)
print("\nMean CAR % (t) median % — by period")
print(ev.groupby("period").apply(summ).T.to_string())
print("\nby spot-age bucket")
print(ev.groupby("age_bucket", observed=True).apply(summ).T.to_string())
print("\nby year")
print(ev.groupby(ev.D0.dt.year).apply(summ)[["car_1_30", "car_1_60", "car_1_90", "n"]].to_string())
ev["runup_t"] = pd.qcut(ev["car_-30_-1"], 3, labels=["low", "mid", "high"])
print("\nby pre-event run-up tercile")
print(ev.groupby("runup_t", observed=True).apply(summ)[["car_-30_-1", "car_1_30", "car_1_60", "car_1_90", "n"]].to_string())

# share of events with negative drift
for c in ["car_1_30", "car_1_60", "car_1_90"]:
    x = ev[c].dropna()
    print(c, "share<0:", round((x < 0).mean(), 3), "n", len(x))

ev.to_csv("exp01_events.csv", index=False)
P = pd.DataFrame(paths)
P.to_parquet("exp01_paths.parquet")
