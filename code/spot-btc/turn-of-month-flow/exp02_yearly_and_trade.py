"""Turn-of-month by year, trend-conditioned, and the costed sleeve (IS-chosen window [-3,+3])."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily, evaluate, yearly_sharpe  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_tom_profile import tdm_index  # noqa: E402

d = btc_daily()
close = d.Close
r = close.pct_change()
tdm = pd.Series(tdm_index(d.index), index=d.index)
tom = tdm.between(-3, 3) & (tdm != 0)
trend_prev = (close > close.rolling(50).mean()).shift(1)       # known before the day
df = pd.DataFrame({"r": r, "tom": tom, "tr": trend_prev}).dropna()
g = df.groupby([df.index.year, "tom"]).r.mean().unstack() * 1e4
g["diff"] = g[True] - g[False]
print("bp/day by year (TOM [-3,+3] vs rest):\n", g.round(1).to_string())
for half, (a, b) in {"IS": (None, "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
    s = df.loc[a:b]
    print(half, "trend on: TOM", round(s[s.tr & s.tom].r.mean() * 1e4, 1), "rest", round(s[s.tr & ~s.tom].r.mean() * 1e4, 1),
          "| trend off: TOM", round(s[~s.tr & s.tom].r.mean() * 1e4, 1), "rest", round(s[~s.tr & ~s.tom].r.mean() * 1e4, 1))

vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
trend = (close > close.rolling(50).mean()).astype(float)
# weight decided at close of D applies to D+1: hold on TOM days => w_D = tom(D+1)
tom_next = tom.shift(-1).fillna(False).astype(float)
rows = []
for nm, w in (("vol B&H", vs), ("SMA50 x vol", trend * vs), ("TOM[-3,3] x vol", tom_next * vs),
              ("TOM x trend x vol", tom_next * trend * vs), ("trend x vol, skip TOM", trend * vs * (1 - tom_next))):
    net, st = evaluate(w, close, start="2017-09-01", name=nm)
    rows.append(st)
    if nm.startswith("TOM[-3"):
        print("TOM sleeve yearly Sharpe:", yearly_sharpe(net).to_dict())
print(pd.concat(rows).round(2).to_string())
