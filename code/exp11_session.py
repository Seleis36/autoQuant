"""Exp 11 - The US-close / ETF-NAV session effect in BTC.
Bar convention: h.Close.pct_change() indexed at hour H = return from H:00 to H+1:00 UTC.
Signal = clock only => zero lookahead. Entry at 20:00 open, exit at window end."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

h = pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h.parquet"))
hr = h["Close"].pct_change()
d = pd.DataFrame({"r": hr}).dropna(); d["h"] = d.index.hour
day = d.index.normalize()

def sess_daily(hours):
    m = d[d.h.isin(list(hours))]
    return m.groupby(m.index.normalize())["r"].sum()

def stats(dr, cost_bps, n_sides=2, ann=365):
    """dr = daily session log-ish return; charge n_sides * cost per traded day."""
    net = dr - n_sides * cost_bps / 1e4
    return pd.Series({
        "gross_bp/d": dr.mean()*1e4, "net_ann%": net.mean()*ann*100,
        "vol%": net.std()*np.sqrt(ann)*100,
        "SR": net.mean()/net.std()*np.sqrt(ann) if net.std()>0 else np.nan,
        "MaxDD%": ((1+net).cumprod()/(1+net).cumprod().cummax()-1).min()*100,
        "t_NW": newey_west_t(net.values, lags=21)})

print("=== window search: contiguous UTC-hour windows, Sharpe (gross) ===")
rows = []
for start in range(24):
    for L in range(1, 9):
        hrs = [(start+i) % 24 for i in range(L)]
        dr = sess_daily(hrs)
        rows.append({"start": start, "len": L,
            "ALL_SR": dr.mean()/dr.std()*np.sqrt(365), "bp/d": dr.mean()*1e4,
            "IS_SR": (lambda x: x.mean()/x.std()*np.sqrt(365))(dr.loc[:"2021-12-31"]),
            "OOS_SR": (lambda x: x.mean()/x.std()*np.sqrt(365))(dr.loc["2022-01-01":]),
            "ETF_SR": (lambda x: x.mean()/x.std()*np.sqrt(365))(dr.loc["2024-01-11":]),
            "vol%": dr.std()*np.sqrt(365)*100})
W = pd.DataFrame(rows)
W["minSR"] = W[["IS_SR","OOS_SR","ETF_SR"]].min(axis=1)
print("\n-- top 15 by WORST-of(IS,OOS,ETF) Sharpe: robustness-first ranking --")
print(W.sort_values("minSR", ascending=False).head(15).round(2).to_string(index=False))

print("\n=== chosen window 20:00-23:00 UTC (hours 20,21,22) : cost sensitivity ===")
dr = sess_daily([20,21,22])
tab = {}
for c in [0.0, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0]:
    tab[f"{c}bp/side"] = stats(dr, c)
print(pd.DataFrame(tab).T.round(2).to_string())

print("\n=== 20-23 UTC window: period breakdown (gross, and net @2bp/side) ===")
per = {"2017-21 IS": ("2017-01-01","2021-12-31"), "2022-26 OOS": ("2022-01-01","2026-12-31"),
       "2018":("2018-01-01","2018-12-31"),"2019":("2019-01-01","2019-12-31"),
       "2020":("2020-01-01","2020-12-31"),"2021":("2021-01-01","2021-12-31"),
       "2022":("2022-01-01","2022-12-31"),"2023":("2023-01-01","2023-12-31"),
       "2024":("2024-01-01","2024-12-31"),"2025":("2025-01-01","2025-12-31"),
       "2026":("2026-01-01","2026-12-31")}
rows = {}
for k,(a,b) in per.items():
    seg = dr.loc[a:b]
    if len(seg) < 60: continue
    g = stats(seg, 0.0); n = stats(seg, 2.0)
    rows[k] = {"n_days": len(seg), "gross_bp/d": g["gross_bp/d"], "gross_SR": g["SR"],
               "net2_ann%": n["net_ann%"], "net2_SR": n["SR"], "vol%": n["vol%"], "t_NW": n["t_NW"]}
print(pd.DataFrame(rows).T.round(2).to_string())

print("\n=== Is it the equity close? DST check: window in ET terms ===")
idx = pd.DatetimeIndex(dr.index)
dst = pd.Series(idx.tz_localize("UTC").tz_convert("America/New_York").map(lambda t: t.dst().total_seconds()>0), index=idx)
for lab, mask in [("EDT (summer, 16-19 ET)", dst), ("EST (winter, 15-18 ET)", ~dst)]:
    s = dr[mask.values]
    print(f"  {lab}: n={len(s)} bp/d={s.mean()*1e4:.2f} SR={s.mean()/s.std()*np.sqrt(365):.2f}")

print("\n=== weekday vs weekend (ETF-flow mechanism implies weekday concentration) ===")
dow = pd.Series(dr.index.dayofweek, index=dr.index)
for lab, sl in [("ALL", slice(None)), ("OOS 2022+", slice("2022-01-01",None)), ("ETF 2024+", slice("2024-01-11",None))]:
    s = dr.loc[sl]; w = dow.loc[sl]
    wd, we = s[w<5], s[w>=5]
    print(f"  {lab:10s} weekday: bp/d={wd.mean()*1e4:6.2f} SR={wd.mean()/wd.std()*np.sqrt(365):5.2f} | "
          f"weekend: bp/d={we.mean()*1e4:6.2f} SR={we.mean()/we.std()*np.sqrt(365):5.2f}")
print("\n  per-weekday bp/day (ETF era):")
s = dr.loc["2024-01-11":]; w = dow.loc["2024-01-11":]
print("   " + "  ".join(f"{'MonTueWedThuFriSatSun'[i*3:i*3+3]}={s[w==i].mean()*1e4:6.2f}" for i in range(7)))
