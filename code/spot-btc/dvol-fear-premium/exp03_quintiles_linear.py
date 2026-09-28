"""Quintile profile of forward returns by log(IV/RV30) (expanding-quantile buckets, no
look-ahead), and linear sizing w = vol x clip(0.5 + rank_365(IVRV), 0, 1) x (trend or 1)."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import evaluate  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import build  # noqa: E402
START = "2021-10-01"   # same window as exp02_backtest.py

d, f = build()
close = d.Close
r1 = close.shift(-1) / close - 1
r7 = close.shift(-7) / close - 1
x = f.IVRV30
# expanding quintile using data up to t only (min 180 obs)
xv = x.dropna()
rk = xv.expanding(min_periods=180).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True).reindex(x.index)
q = np.floor(rk * 5).clip(0, 4) + 1
df = pd.DataFrame({"q": q, "r1": r1, "r7": r7}).dropna()
for half, (a, b) in {"IS": (None, "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
    s = df.loc[a:b]
    print(half, "next-day bp by quintile:", (s.groupby("q").r1.mean() * 1e4).round(1).to_dict(),
          "| next-7d %:", (s.groupby("q").r7.mean() * 100).round(2).to_dict(), "| n", s.groupby("q").size().to_dict())

r = close.pct_change()
vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
trend = (close > close.rolling(50).mean()).astype(float)
lin = (rk.fillna(0.5)).clip(0, 1)
rows = []
for nm, w in (("vol B&H", vs), ("SMA50 x vol", trend * vs),
              ("lin IVRV x vol", lin * vs), ("lin IVRV x trend x vol", lin * trend * vs),
              ("top2 quintiles x vol", (q >= 4).astype(float) * vs),
              ("top2 x trend x vol", (q >= 4).astype(float) * trend * vs)):
    _, st = evaluate(w, close, start=START, name=nm); rows.append(st)
print(pd.concat(rows).round(2).to_string())
