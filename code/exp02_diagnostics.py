"""Exp 02 - Diagnostics: where does BTC risk-adjusted return actually live?"""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 60)

df = load_btc(); close, op, hi, lo = df["Close"], df["Open"], df["High"], df["Low"]
ret = close.pct_change()

# --- 0. Is there an overnight/intraday split to exploit? (24/7 asset)
gap = (op / close.shift(1) - 1).dropna()
intr = (close / op - 1).dropna()
print("=== bar structure ===")
print(f"close->open gap: mean={gap.mean()*1e4:.2f}bp  std={gap.std()*1e4:.1f}bp  (24/7 => ~0 expected)")
print(f"open->close    : mean={intr.mean()*1e4:.2f}bp  std={intr.std()*1e4:.1f}bp")

# --- 1. Forward return by EX-ANTE vol quintile (the core vol-targeting hypothesis)
print("\n=== forward 1d return by EX-ANTE (t-1) realized-vol quintile ===")
for hl, lbl in [(20, "ewm hl=20")]:
    v = ewm_vol(ret, halflife=hl).shift(1)
    q = pd.qcut(v.dropna(), 5, labels=[f"Q{i+1}" for i in range(5)])
    fwd = ret.reindex(q.index)
    tab = pd.DataFrame({"vol_q": q, "fwd": fwd}).dropna()
    g = tab.groupby("vol_q", observed=True)["fwd"]
    out = pd.DataFrame({
        "ann_ret_%": g.mean() * ANN * 100,
        "ann_vol_%": g.std() * np.sqrt(ANN) * 100,
        "Sharpe": g.mean() / g.std() * np.sqrt(ANN),
        "n": g.size(),
    })
    out["mean_exante_vol_%"] = tab.groupby("vol_q", observed=True).apply(
        lambda x: v.reindex(x.index).mean() * 100, include_groups=False)
    print(f"[{lbl}] FULL SAMPLE"); print(out.round(2).to_string())

    for lab, sl in [("IS 14-20", slice(None, "2020-12-31")), ("OOS 21-26", slice("2021-01-01", None))]:
        t2 = tab.loc[sl]
        g2 = t2.groupby("vol_q", observed=True)["fwd"]
        o2 = pd.DataFrame({"ann_ret_%": g2.mean()*ANN*100, "ann_vol_%": g2.std()*np.sqrt(ANN)*100,
                           "Sharpe": g2.mean()/g2.std()*np.sqrt(ANN), "n": g2.size()})
        print(f"\n[{lbl}] {lab}"); print(o2.round(2).to_string())

# --- 2. Does ex-ante vol predict realized vol? (needed for vol targeting to work)
v = ewm_vol(ret, halflife=20).shift(1)
fwd_v = ret.rolling(20).std(ddof=1).shift(-20) * np.sqrt(ANN)
c = pd.concat([v, fwd_v], axis=1).dropna()
print(f"\n=== vol predictability: corr(ex-ante vol, next-20d realized vol) = {c.iloc[:,0].corr(c.iloc[:,1]):.3f}"
      f" | rank={c.iloc[:,0].corr(c.iloc[:,1], method='spearman'):.3f} ===")

# --- 3. Trend signal quality over time: IC of 40d momentum vs fwd 1d return, by year
print("\n=== rolling signal quality: yearly Sharpe of (long if 40d mom>0) vs B&H ===")
sig40 = (close > close.shift(40)).astype(float)
n40, _ = backtest(sig40, close, cost_bps=10)
yr = pd.DataFrame({"trend40": n40, "bh": ret}).dropna()
ys = yr.groupby(yr.index.year).apply(
    lambda x: pd.Series({"trend40_SR": x["trend40"].mean()/x["trend40"].std()*np.sqrt(ANN),
                         "bh_SR": x["bh"].mean()/x["bh"].std()*np.sqrt(ANN),
                         "bh_vol%": x["bh"].std()*np.sqrt(ANN)*100}), include_groups=False)
print(ys.round(2).to_string())
