"""Exp 01 - Baselines: buy&hold, and the trend-following parameter landscape."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import *

pd.set_option("display.width", 200); pd.set_option("display.max_columns", 50)

df = load_btc(cache=False)
close = df["Close"]
ret = close.pct_change()
print(f"Sample: {close.index[0].date()} -> {close.index[-1].date()}  n={len(close)}")

SPLITS = {
    "IS  2014-2020": ("2014-01-01", "2020-12-31"),
    "OOS 2021-2026": ("2021-01-01", "2026-12-31"),
    " .  2021 bull": ("2021-01-01", "2021-12-31"),
    " .  2022 bear": ("2022-01-01", "2022-12-31"),
    " .  2023-24   ": ("2023-01-01", "2024-12-31"),
    " .  2025-26   ": ("2025-01-01", "2026-12-31"),
}

# ---- Buy & hold
bh, bh_s = backtest(pd.Series(1.0, index=close.index), close, cost_bps=0, name="BuyHold")
print("\n=== BUY & HOLD ===")
print(fmt(pd.DataFrame([bh_s]).join(split_stats(bh, SPLITS).add_prefix("")).iloc[:0]) if False else "")
print(fmt(pd.DataFrame([bh_s])).to_string())
print(fmt(split_stats(bh, SPLITS)).to_string())

# ---- SMA crossover landscape (long/flat), IS vs OOS
print("\n=== SMA CROSSOVER LANDSCAPE (long/flat, 10bps) ===")
rows = []
for f in [1, 3, 5, 8, 10, 15, 20, 25, 30, 40, 50]:
    for s in [20, 30, 50, 75, 100, 150, 200, 250]:
        if f >= s: continue
        sig = (close.rolling(f).mean() > close.rolling(s).mean()).astype(float)
        net, st = backtest(sig, close, cost_bps=10)
        is_s = perf_stats(net.loc[:"2020-12-31"])["Sharpe"]
        oos_s = perf_stats(net.loc["2021-01-01":])["Sharpe"]
        rows.append({"fast": f, "slow": s, "Sharpe_all": st["Sharpe"],
                     "Sharpe_IS": is_s, "Sharpe_OOS": oos_s,
                     "CAGR": st["CAGR"], "MaxDD": st["MaxDD"], "Turn": st["Turnover_ann"]})
res = pd.DataFrame(rows)
print("\nTop 12 by IS Sharpe (and their OOS):")
print(res.sort_values("Sharpe_IS", ascending=False).head(12).round(3).to_string(index=False))
print(f"\nIS/OOS Sharpe rank correlation (spearman): {res['Sharpe_IS'].corr(res['Sharpe_OOS'], method='spearman'):.3f}")
print(f"Mean Sharpe  IS={res['Sharpe_IS'].mean():.3f}  OOS={res['Sharpe_OOS'].mean():.3f}  All={res['Sharpe_all'].mean():.3f}")
print(f"Frac of grid with OOS Sharpe > 1: {(res['Sharpe_OOS']>1).mean():.1%}")

# ---- TSMOM landscape
print("\n=== TSMOM (price vs price k days ago) LANDSCAPE ===")
rows = []
for k in [5, 10, 15, 20, 30, 40, 50, 60, 90, 120, 150, 200, 250]:
    sig = (close > close.shift(k)).astype(float)
    net, st = backtest(sig, close, cost_bps=10)
    rows.append({"k": k, "Sharpe_all": st["Sharpe"],
                 "Sharpe_IS": perf_stats(net.loc[:"2020-12-31"])["Sharpe"],
                 "Sharpe_OOS": perf_stats(net.loc["2021-01-01":])["Sharpe"],
                 "CAGR": st["CAGR"], "MaxDD": st["MaxDD"], "Turn": st["Turnover_ann"]})
print(pd.DataFrame(rows).round(3).to_string(index=False))
