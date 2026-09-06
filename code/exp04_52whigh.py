"""Exp 04 - The 52-week-high proximity signal (George & Hwang 2004, applied time-series to BTC).
Long/flat: hold BTC when price is within `thr` of its rolling N-day high."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)

df = load_btc(); close, vol = df["Close"], df["Volume"]
ret = close.pct_change()
IS, OOS = slice(None, "2020-12-31"), slice("2021-01-01", None)

# actual quintile cut points of dd_from_252h, for reference
dd = (close / close.rolling(252).max() - 1).dropna()
print("dd_from_252h quintile cutpoints:", np.round(np.percentile(dd, [20,40,60,80]), 3))

print("\n=== GRID: long if close >= (1-thr) * rolling-N-day high   [10 bps] ===")
rows = []
for N in [50, 100, 150, 200, 252, 300, 365]:
    for thr in [0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20, 0.25, 0.30]:
        sig = (close >= (1 - thr) * close.rolling(N).max()).astype(float)
        net, st = backtest(sig, close, cost_bps=10)
        rows.append({"N": N, "thr": thr,
                     "SR_IS": perf_stats(net.loc[IS])["Sharpe"],
                     "SR_OOS": perf_stats(net.loc[OOS])["Sharpe"],
                     "SR_all": st["Sharpe"], "CAGR": st["CAGR"], "MaxDD": st["MaxDD"],
                     "Turn": st["Turnover_ann"], "TiM": st["TimeInMkt"]})
G = pd.DataFrame(rows)
piv_is  = G.pivot(index="N", columns="thr", values="SR_IS")
piv_oos = G.pivot(index="N", columns="thr", values="SR_OOS")
piv_all = G.pivot(index="N", columns="thr", values="SR_all")
print("\n-- Sharpe IS (2014-2020) --");  print(piv_is.round(2).to_string())
print("\n-- Sharpe OOS (2021-2026) --"); print(piv_oos.round(2).to_string())
print("\n-- Sharpe FULL --");            print(piv_all.round(2).to_string())
print(f"\nIS/OOS spearman across grid: {G['SR_IS'].corr(G['SR_OOS'], method='spearman'):.3f}")
print(f"Frac of grid with OOS Sharpe > 1.0: {(G['SR_OOS']>1).mean():.1%}   > 0.8: {(G['SR_OOS']>0.8).mean():.1%}")
print(f"Median OOS Sharpe over whole grid: {G['SR_OOS'].median():.3f}  (vs B&H OOS 0.60, SMA-grid median ~0.64)")

print("\n=== Best-by-IS pick, evaluated OOS ===")
best = G.sort_values("SR_IS", ascending=False).head(5)
print(best.round(3).to_string(index=False))

print("\n=== ROBUST CENTRE-OF-PLATEAU pick: N=252, thr=0.15 ===")
sig = (close >= 0.85 * close.rolling(252).max()).astype(float)
net, st = backtest(sig, close, cost_bps=10, name="HighProx")
print(fmt(pd.DataFrame([st])).to_string())
SPL = {"IS 2014-2020": ("2014-01-01","2020-12-31"), "OOS 2021-2026": ("2021-01-01","2026-12-31"),
       "2021": ("2021-01-01","2021-12-31"), "2022": ("2022-01-01","2022-12-31"),
       "2023-24": ("2023-01-01","2024-12-31"), "2025-26": ("2025-01-01","2026-12-31")}
print(fmt(split_stats(net, SPL)).to_string())
