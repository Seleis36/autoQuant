"""Exp 05 - Cross-asset / macro conditioning. BTC post-2020 is a liquidity/risk asset;
its own price history is mined out, so test EXOGENOUS state variables.
Alignment: exogenous close on date D is known ~20:00 UTC D; harness shifts weights 1 day,
so the signal is applied to BTC's D+1 bar. No lookahead."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import *
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)

df = load_btc(); close = df["Close"]; ret = close.pct_change()
cal = close.index

TICKERS = {"NDX":"^IXIC","SPX":"^GSPC","VIX":"^VIX","DXY":"DX-Y.NYB","TNX":"^TNX",
           "GLD":"GLD","HYG":"HYG","TLT":"TLT","ETH":"ETH-USD","GBTC":"GBTC",
           "COIN":"COIN","MSTR":"MSTR","XLK":"XLK","IWM":"IWM","LQD":"LQD","USO":"USO"}
S = {}
for k, t in TICKERS.items():
    try:
        s = load_series(t)["Close"]
        S[k] = s.reindex(cal).ffill()      # weekday series onto 7-day crypto calendar
        print(f"  {k:5s} {t:10s} {s.index[0].date()} -> {s.index[-1].date()}  n={len(s)}")
    except Exception as e:
        print(f"  {k:5s} FAILED {e}")

F = {}
for k, s in S.items():
    r = s.pct_change()
    F[f"{k}_mom20"]   = s / s.shift(20) - 1
    F[f"{k}_mom60"]   = s / s.shift(60) - 1
    F[f"{k}_vs200ma"] = s / s.rolling(200).mean() - 1
    F[f"{k}_vol20"]   = r.rolling(20).std()
F["VIX_lvl"]     = S["VIX"]
F["VIX_pct252"]  = S["VIX"].rolling(252).rank(pct=True)
F["VIX_chg20"]   = S["VIX"] / S["VIX"].shift(20) - 1
F["TNX_chg60"]   = S["TNX"] - S["TNX"].shift(60)
F["ETHBTC"]      = (S["ETH"] / close)
F["ETHBTC_m60"]  = (S["ETH"]/close) / (S["ETH"]/close).shift(60) - 1
F["HYG_o_TLT"]   = (S["HYG"]/S["TLT"]) / (S["HYG"]/S["TLT"]).shift(60) - 1   # credit risk appetite
F["GBTC_prem_m"] = (S["GBTC"]/close) / (S["GBTC"]/close).shift(60) - 1        # GBTC prem/disc trend
F["BTC_beta_NDX"]= ret.rolling(120).corr(S["NDX"].pct_change())

def bucket(name, f, nq=5):
    f = f.shift(1)
    d = pd.DataFrame({"f": f, "r": ret}).dropna()
    if len(d) < 700: return None
    try: d["q"] = pd.qcut(d["f"], nq, labels=range(1,nq+1), duplicates="drop")
    except Exception: return None
    out = {"feature": name, "n": len(d), "start": d.index[0].date()}
    for lab, sl in [("IS", slice(None,"2020-12-31")), ("OOS", slice("2021-01-01",None))]:
        s = d.loc[sl]
        if len(s) < 300:
            for qq in range(1,nq+1): out[f"{lab}_Q{qq}"] = np.nan
            continue
        g = s.groupby("q", observed=True)["r"]
        sr = g.mean()/g.std()*np.sqrt(ANN)
        for qq in sr.index: out[f"{lab}_Q{qq}"] = sr[qq]
    return out

rows = [r for k,v in F.items() if (r := bucket(k,v)) is not None]
R = pd.DataFrame(rows).set_index("feature")
print("\n=== Conditional BTC 1-day Sharpe by EXOGENOUS feature quintile ===")
print(R[[c for c in R.columns if c.startswith("IS_")]].round(2).to_string())
print()
print(R[[c for c in R.columns if c.startswith("OOS_")]].round(2).to_string())

print("\n=== Monotonic + robust: |IS spread| and OOS spread same sign, both > 0.7 ===")
hits=[]
for f in R.index:
    qs_is  = [R.loc[f,f"IS_Q{q}"]  for q in range(1,6)]
    qs_oos = [R.loc[f,f"OOS_Q{q}"] for q in range(1,6)]
    if any(pd.isna(qs_is)) or any(pd.isna(qs_oos)): continue
    si, so = qs_is[-1]-qs_is[0], qs_oos[-1]-qs_oos[0]
    if np.sign(si)==np.sign(so) and abs(si)>0.7 and abs(so)>0.7:
        # monotonicity: spearman of quintile index vs sharpe
        from scipy.stats import spearmanr
        mi = spearmanr(range(5), qs_is).statistic; mo = spearmanr(range(5), qs_oos).statistic
        hits.append({"feature":f,"IS_spread":si,"OOS_spread":so,"mono_IS":mi,"mono_OOS":mo,
                     "IS_top":max(qs_is[0],qs_is[-1]),"OOS_top":max(qs_oos[0],qs_oos[-1])})
H = pd.DataFrame(hits)
print(H.sort_values("OOS_spread", key=abs, ascending=False).round(2).to_string(index=False) if len(H) else "  (none)")
