"""Exp 03 - Systematic conditional-Sharpe scan over candidate state variables.
For each feature we bucket days by the feature value KNOWN AT t-1 close and
measure the Sharpe of holding BTC on day t. IS and OOS reported separately."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import *
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)

df = load_btc(); close, op, hi, lo, vol = df["Close"], df["Open"], df["High"], df["Low"], df["Volume"]
ret = close.pct_change()
lr  = np.log(close).diff()

F = {}
# --- volatility state
F["vol_ewm20"]      = ewm_vol(ret, 20)
F["vol_pctile_252"] = ewm_vol(ret, 20).rolling(252).rank(pct=True)
F["vol_ratio_5_60"] = ewm_vol(ret, 5) / ewm_vol(ret, 60)
# Parkinson range vol vs close-to-close (a proxy for intraday churn / trendiness)
park = np.sqrt((np.log(hi / lo) ** 2).rolling(20).mean() / (4 * np.log(2))) * np.sqrt(ANN)
F["park_over_cc"]   = park / ewm_vol(ret, 20)
# --- trend / momentum
F["mom_20"]  = close / close.shift(20) - 1
F["mom_60"]  = close / close.shift(60) - 1
F["mom_200"] = close / close.shift(200) - 1
F["macd_z"]  = macd_trend(close, 16, 64)
F["px_over_sma200"] = close / close.rolling(200).mean() - 1
# --- position within range / drawdown
F["dd_from_252h"] = close / close.rolling(252).max() - 1
F["dd_from_ath"]  = close / close.cummax() - 1
F["pctrank_252"]  = close.rolling(252).rank(pct=True)
# --- short-term reversal
F["rev_1"]  = -ret
F["rev_5"]  = -(close / close.shift(5) - 1)
F["rsi_14"] = (lambda d: 100 - 100/(1 + d.clip(lower=0).ewm(alpha=1/14).mean() /
                                       (-d.clip(upper=0)).ewm(alpha=1/14).mean()))(close.diff())
# --- volume / flow
F["volz_20"]  = (vol / vol.rolling(20).mean()).replace([np.inf,-np.inf], np.nan)
F["dollar_v_trend"] = (vol*close).rolling(20).mean() / (vol*close).rolling(100).mean()
# --- higher moments
F["skew_60"] = lr.rolling(60).skew()
F["kurt_60"] = lr.rolling(60).kurt()

def bucket_report(name, f, nq=5):
    f = f.shift(1)                       # STRICTLY known at t-1 close
    d = pd.DataFrame({"f": f, "r": ret}).dropna()
    if len(d) < 500 or d["f"].nunique() < nq * 5: return None
    try: d["q"] = pd.qcut(d["f"], nq, labels=range(1, nq+1), duplicates="drop")
    except Exception: return None
    out = {"feature": name}
    for lab, sl in [("ALL", slice(None)), ("IS", slice(None, "2020-12-31")), ("OOS", slice("2021-01-01", None))]:
        s = d.loc[sl]
        g = s.groupby("q", observed=True)["r"]
        sr = g.mean() / g.std() * np.sqrt(ANN)
        for qq in sr.index: out[f"{lab}_Q{qq}"] = sr[qq]
        out[f"{lab}_spread"] = sr.iloc[-1] - sr.iloc[0]
    return out

rows = [r for k, v in F.items() if (r := bucket_report(k, v)) is not None]
R = pd.DataFrame(rows).set_index("feature")

qc = [c for c in R.columns if c.startswith(("ALL_Q","IS_Q","OOS_Q"))]
print("=== Conditional 1-day Sharpe by feature quintile (Q1=low feature value) ===\n")
for lab in ["ALL", "IS", "OOS"]:
    cols = [c for c in R.columns if c.startswith(lab + "_")]
    print(f"--- {lab} ---")
    print(R[cols].round(2).to_string())
    print()

# best single-bucket opportunities: which (feature,quintile) has high Sharpe in BOTH IS and OOS
print("=== Buckets with Sharpe > 0.9 in BOTH IS and OOS (robust conditional edge) ===")
hits = []
for f in R.index:
    for q in range(1, 6):
        i, o = R.loc[f, f"IS_Q{q}"], R.loc[f, f"OOS_Q{q}"]
        if i > 0.9 and o > 0.9:
            hits.append({"feature": f, "quintile": q, "IS": i, "OOS": o, "ALL": R.loc[f, f"ALL_Q{q}"]})
print(pd.DataFrame(hits).sort_values("OOS", ascending=False).round(2).to_string(index=False) if hits else "  (none)")
