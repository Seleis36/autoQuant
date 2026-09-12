"""exp03b -- daily composites: premium signal x trend gate x vol sizing, 10bp/side.
Also: premium change signals, top-quintile stats, and the signal's overlap with bult/weekday-trend style gates.
All cells reported. IS <= 2022-12-31, OOS >= 2023-01-01.
"""
import os, sys, warnings, itertools
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared"))
from research_lib import ANN, backtest, split_stats, newey_west_t
IS_END, OOS_START = "2022-12-31", "2023-01-01"
P = pd.read_parquet(os.path.join(HERE, "panel.parquet"))
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 300)
close = P["close"]; ret = close.pct_change()
ewv = ret.ewm(halflife=20, min_periods=20).std() * np.sqrt(ANN)
vscale = (0.40 / ewv).clip(0, 1).fillna(0)
prem = P["cbprem_bin_mean"]
z90 = P["cbprem_bin_z90"]; z30 = (prem - prem.rolling(30).mean()) / prem.rolling(30).std()
dprem = prem - prem.shift(1)
dprem3 = prem - prem.rolling(3).mean().shift(1)

def run(w, name):
    net, st = backtest(w.fillna(0), close, cost_bps=10)
    sp = split_stats(net, {"IS": (None, IS_END), "OOS": (OOS_START, None)})
    return dict(name=name, Sharpe=st["Sharpe"], IS=sp.loc["IS", "Sharpe"], OOS=sp.loc["OOS", "Sharpe"],
                CAGR=st["CAGR"], MaxDD=st["MaxDD"], TO=st["Turnover_ann"], Expo=st["AvgExposure"], tNW=st["t_NW"])

print("=== top-quintile-day stats (z90), IS/OOS: mean bp, Sharpe of those days, n")
for nm, seg in (("IS", P.loc[:IS_END]), ("OOS", P.loc[OOS_START:])):
    q = pd.qcut(seg["cbprem_bin_z90"].rank(method="first"), 5, labels=False)
    t = seg["ret_fwd"][q == 4].dropna()
    print(nm, round(t.mean() * 1e4, 1), round(t.mean() / t.std() * np.sqrt(ANN), 2), len(t))

rows = []
gates = {"none": pd.Series(1.0, index=P.index),
         "sma200": P["sma200_up"], "sma50": P["sma50_up"], "sma20": P["sma20_up"],
         "mom20>0": (P["mom20"] > 0).astype(float),
         "sma200&mom20": P["sma200_up"] * (P["mom20"] > 0).astype(float),
         "ens_trend": (P[["sma20_up", "sma50_up", "sma100_up", "sma200_up"]].mean(axis=1))}
sigs = {"z90>0": (z90 > 0).astype(float), "z90>0.5": (z90 > 0.5).astype(float), "z90>1": (z90 > 1).astype(float),
        "clipz90": z90.clip(0, 2) / 2, "z30>0": (z30 > 0).astype(float), "clipz30": z30.clip(0, 2) / 2,
        "prem>0": (prem > 0).astype(float), "dprem>0": (dprem > 0).astype(float), "dprem3>0": (dprem3 > 0).astype(float),
        "z90>0|dprem>0": ((z90 > 0) | (dprem > 0)).astype(float), "z90>0&dprem>0": ((z90 > 0) & (dprem > 0)).astype(float)}
for (gn, g), (sn, s), vs in itertools.product(gates.items(), sigs.items(), ("novol", "vol")):
    w = g * s * (vscale if vs == "vol" else 1.0)
    rows.append(run(w, f"{gn} x {sn} x {vs}"))
# gates alone
for gn, g in gates.items():
    rows.append(run(g, f"{gn} alone novol")); rows.append(run(g * vscale, f"{gn} alone vol"))
df = pd.DataFrame(rows).set_index("name")
df["minIO"] = df[["IS", "OOS"]].min(axis=1)
print("\n=== all composites sorted by min(IS,OOS) Sharpe (10bp/side)")
print(df.sort_values("minIO", ascending=False).round(2).to_string())
df.to_csv(os.path.join(HERE, "exp03b_composites.csv"))
