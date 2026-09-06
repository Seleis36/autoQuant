"""Exp 10 - Intraday structure of BTC (Binance hourly, 2017-08 -> 2026-09)."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import *
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

h = pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h.parquet"))
hr = h["Close"].pct_change()
print(f"hourly bars {h.shape[0]}  {h.index[0]} -> {h.index[-1]}")
HANN = 24*365.0

IS  = slice(None, "2021-12-31")
OOS = slice("2022-01-01", None)
ETF = slice("2024-01-11", None)
def sr(x, ann=HANN):
    x = x.dropna();  return x.mean()/x.std()*np.sqrt(ann) if len(x)>50 and x.std()>0 else np.nan

d = pd.DataFrame({"r": hr}).dropna()
d["h"] = d.index.hour; d["dow"] = d.index.dayofweek

print("\n=== Mean hourly return (bp) and annualised Sharpe by UTC hour ===")
tab = pd.DataFrame({
  "ALL_bp": d.groupby("h")["r"].mean()*1e4,   "ALL_SR": d.groupby("h")["r"].apply(sr),
  "IS_bp":  d.loc[IS].groupby("h")["r"].mean()*1e4, "IS_SR":  d.loc[IS].groupby("h")["r"].apply(sr),
  "OOS_bp": d.loc[OOS].groupby("h")["r"].mean()*1e4,"OOS_SR": d.loc[OOS].groupby("h")["r"].apply(sr),
  "ETF_bp": d.loc[ETF].groupby("h")["r"].mean()*1e4,"ETF_SR": d.loc[ETF].groupby("h")["r"].apply(sr),
})
tab.index.name = "UTC_hour"
# annotate US session
tab["US_sess"] = ["" if not (13 <= i <= 21) else "US" for i in tab.index]
print(tab.round(2).to_string())

print("\n=== Session aggregates (sum of hourly returns within session, per day) ===")
SESS = {"Asia 00-07":  range(0,8),   "Europe 08-13": range(8,14),
        "US 14-21":    range(14,22), "LateUS 22-23": range(22,24),
        "USeq 14-20":  range(14,21), "NAVwin 20-21": range(20,22)}
rows = {}
for nm, hrs in SESS.items():
    m = d[d.h.isin(list(hrs))]
    # daily-aggregated session return
    dr = m.groupby(m.index.normalize())["r"].sum()
    rows[nm] = {"n_days": len(dr),
        "ALL_bp/day": dr.mean()*1e4, "ALL_SR": sr(dr, 365), "ALL_ann%": dr.mean()*365*100,
        "IS_SR": sr(dr.loc[IS],365), "OOS_SR": sr(dr.loc[OOS],365), "ETF_SR": sr(dr.loc[ETF],365),
        "IS_bp": dr.loc[IS].mean()*1e4, "OOS_bp": dr.loc[OOS].mean()*1e4, "ETF_bp": dr.loc[ETF].mean()*1e4,
        "vol_ann%": dr.std()*np.sqrt(365)*100}
print(pd.DataFrame(rows).T.round(2).to_string())

print("\n=== Full day for reference ===")
full = d.groupby(d.index.normalize())["r"].sum()
print(f"  ALL bp/day={full.mean()*1e4:.2f}  SR={sr(full,365):.2f}  vol={full.std()*np.sqrt(365)*100:.1f}%"
      f"  | IS SR={sr(full.loc[IS],365):.2f}  OOS SR={sr(full.loc[OOS],365):.2f}  ETF SR={sr(full.loc[ETF],365):.2f}")

print("\n=== Session x day-of-week (Sharpe, OOS 2022+) ===")
for nm, hrs in [("US 14-21", range(14,22)), ("Asia 00-07", range(0,8))]:
    m = d.loc[OOS]; m = m[m.h.isin(list(hrs))]
    dr = m.groupby([m.index.normalize()])["r"].sum()
    dw = pd.DataFrame({"r": dr}); dw["dow"] = dw.index.dayofweek
    print(f"  {nm}: " + "  ".join(f"{'MTWTFSS'[i]}{i}={sr(dw[dw.dow==i]['r'],365):5.2f}" for i in range(7)))

print("\n=== Intraday momentum: does session A predict session B same day? (OOS) ===")
piv = d.pivot_table(index=d.index.normalize(), columns="h", values="r")
for a, b, la, lb in [(range(0,8), range(14,22), "Asia00-07", "US14-21"),
                     (range(0,14), range(14,24), "pre14", "post14"),
                     (range(14,22), range(0,8), "US(t)", "Asia(t+1)")]:
    x = piv[list(a)].sum(axis=1)
    y = piv[list(b)].sum(axis=1)
    if lb.endswith("(t+1)"): y = y.shift(-1)
    z = pd.concat([x, y], axis=1).dropna(); z.columns = ["x","y"]
    for lab, sl in [("ALL", slice(None)), ("IS", IS), ("OOS", OOS)]:
        s = z.loc[sl]
        if len(s) < 200: continue
        c = s["x"].corr(s["y"])
        # sign-following strategy on session B
        strat = np.sign(s["x"]) * s["y"]
        print(f"  {la:10s} -> {lb:10s} [{lab:4s}] corr={c:+.3f}  signfollow SR={sr(strat,365):5.2f}  bp/day={strat.mean()*1e4:6.2f}")
