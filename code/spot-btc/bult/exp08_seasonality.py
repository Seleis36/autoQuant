"""Exp 08 - Hunt for a THIRD orthogonal alpha source: calendar seasonality,
intrabar (OHLC) microstructure, flow, and cross-crypto risk appetite."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import *
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)

df = load_btc(); close, op, hi, lo, vlm = df["Close"], df["Open"], df["High"], df["Low"], df["Volume"]
ret = close.pct_change()
IS_, OOS_ = slice(None,"2020-12-31"), slice("2021-01-01",None)

def sr(x): 
    x = x.dropna()
    return x.mean()/x.std()*np.sqrt(ANN) if len(x)>20 and x.std()>0 else np.nan

# ---------- A. DAY OF WEEK ----------
print("=== A. Day-of-week (BTC bar = UTC 00:00->24:00) ===")
dow = pd.DataFrame({"r": ret, "d": ret.index.dayofweek}).dropna()
tab = pd.DataFrame({
    "ALL_SR":  dow.groupby("d")["r"].apply(sr),
    "ALL_bp":  dow.groupby("d")["r"].mean()*1e4,
    "IS_SR":   dow.loc[IS_].groupby("d")["r"].apply(sr),
    "OOS_SR":  dow.loc[OOS_].groupby("d")["r"].apply(sr),
    "OOS_bp":  dow.loc[OOS_].groupby("d")["r"].mean()*1e4,
    "ETF_SR":  dow.loc["2024-01-11":].groupby("d")["r"].apply(sr),
    "n": dow.groupby("d")["r"].size()})
tab.index = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
print(tab.round(2).to_string())

print("\n--- weekday (Mon-Fri) vs weekend (Sat-Sun) ---")
wd = dow[dow.d<5]["r"]; we = dow[dow.d>=5]["r"]
for lab, sl in [("ALL", slice(None)), ("IS", IS_), ("OOS", OOS_), ("ETF era 2024+", slice("2024-01-11",None))]:
    a, b = dow.loc[sl]; a = dow.loc[sl]
    w1 = a[a.d<5]["r"]; w2 = a[a.d>=5]["r"]
    print(f"  {lab:14s} weekday SR={sr(w1):5.2f} ({w1.mean()*1e4:6.1f}bp)   weekend SR={sr(w2):5.2f} ({w2.mean()*1e4:6.1f}bp)")

# ---------- B. TURN OF MONTH ----------
print("\n=== B. Turn-of-month (trading-day-of-month index) ===")
dom = pd.DataFrame({"r": ret}).dropna()
dom["dm"] = dom.index.day
dom["tom"] = np.where(dom.dm >= 27, "T-last", np.where(dom.dm <= 4, "T+1..4", "middle"))
for lab, sl in [("ALL", slice(None)), ("IS", IS_), ("OOS", OOS_)]:
    g = dom.loc[sl].groupby("tom")["r"]
    print(f"  {lab:5s} " + "  ".join(f"{k}: SR={sr(v):5.2f} ({v.mean()*1e4:5.1f}bp,n={len(v)})" for k,v in g))

# ---------- C. INTRABAR OHLC MICROSTRUCTURE ----------
print("\n=== C. Intrabar OHLC features -> next-day Sharpe by quintile ===")
rng = (hi - lo).replace(0, np.nan)
FO = {
  "close_loc_in_range": (close - lo) / rng,             # where close sits H-L
  "body_over_range":    (close - op).abs() / rng,
  "upper_wick":         (hi - np.maximum(close, op)) / rng,
  "lower_wick":         (np.minimum(close, op) - lo) / rng,
  "range_expansion":    rng / rng.rolling(20).mean(),
  "intraday_ret":       close / op - 1,
  "gap":                op / close.shift(1) - 1,
  "vlm_z20":            (vlm - vlm.rolling(20).mean()) / vlm.rolling(20).std(),
  "vlm_trend":          vlm.rolling(5).mean() / vlm.rolling(60).mean(),
  "amihud_illiq":       (ret.abs() / (vlm*close)).rolling(20).mean() * 1e12,
  "vol_of_vol":         ewm_vol(ret,20).rolling(60).std() / ewm_vol(ret,20).rolling(60).mean(),
}
rows = []
for k, f in FO.items():
    d = pd.DataFrame({"f": f.shift(1), "r": ret}).dropna()
    if len(d) < 700: continue
    try: d["q"] = pd.qcut(d["f"], 5, labels=range(1,6), duplicates="drop")
    except Exception: continue
    o = {"feature": k}
    for lab, sl in [("IS", IS_), ("OOS", OOS_)]:
        g = d.loc[sl].groupby("q", observed=True)["r"]
        s = g.mean()/g.std()*np.sqrt(ANN)
        for q in s.index: o[f"{lab}_Q{q}"] = s[q]
        o[f"{lab}_spr"] = s.iloc[-1]-s.iloc[0]
    rows.append(o)
R = pd.DataFrame(rows).set_index("feature")
print(R[[c for c in R.columns if c.startswith("IS_")]].round(2).to_string())
print()
print(R[[c for c in R.columns if c.startswith("OOS_")]].round(2).to_string())
print("\n-- consistent-sign spreads (both |.|>0.6) --")
cons = R[(np.sign(R["IS_spr"])==np.sign(R["OOS_spr"])) & (R["IS_spr"].abs()>0.6) & (R["OOS_spr"].abs()>0.6)]
print(cons[["IS_spr","OOS_spr"]].round(2).to_string() if len(cons) else "  (none)")

# ---------- D. CROSS-CRYPTO RISK APPETITE ----------
print("\n=== D. ETH/BTC ratio as crypto risk-appetite gauge ===")
eth = load_series("ETH-USD")["Close"].reindex(close.index).ffill()
ethbtc = (eth/close)
for nm, f in [("ETHBTC vs MA100", (ethbtc > ethbtc.rolling(100).mean()).astype(float)),
              ("ETHBTC mom60", (ethbtc > ethbtc.shift(60)).astype(float))]:
    d = pd.DataFrame({"f": f.shift(1), "r": ret}).dropna()
    for lab, sl in [("IS(2018+)", slice(None,"2020-12-31")), ("OOS", OOS_)]:
        g = d.loc[sl].groupby("f")["r"]
        print(f"  {nm:18s} {lab:10s} " + "  ".join(f"state{int(k)}: SR={sr(v):5.2f}" for k,v in g))
