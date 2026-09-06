"""Exp 16 - What conditions the 20-23 UTC session edge? Goal: trade fewer days,
bigger edge per trade, so the effect survives realistic fees."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

H = pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h.parquet"))
hclose = H["Close"]; hr = hclose.pct_change()
hh = pd.DatetimeIndex(hr.index).hour
day = pd.DatetimeIndex(hr.index).normalize()

WIN = [20,21,22]
sess_r = hr[np.isin(hh, WIN)].groupby(day[np.isin(hh, WIN)]).sum()          # 20:00-23:00 return
pre_r  = hr[hh < 20].groupby(day[hh < 20]).sum()                            # 00:00-20:00, known at 20:00
dclose = hclose.resample("1D").last(); dret = dclose.pct_change()

def sr(x, ann=365):
    x = pd.Series(x).dropna(); return x.mean()/x.std()*np.sqrt(ann) if len(x)>30 and x.std()>0 else np.nan
def line(nm, s, cost_rt_bp=6.0):
    s = pd.Series(s).dropna()
    if len(s) < 60: return None
    net = s - cost_rt_bp/1e4
    return {"n": len(s), "gross_bp": s.mean()*1e4, "gross_SR": sr(s), "net_SR": sr(net),
            "net_ann%": net.mean()*365*100,
            "IS_SR": sr(s.loc[:"2021-12-31"]), "OOS_SR": sr(s.loc["2022-01-01":]),
            "ETF_SR": sr(s.loc["2024-01-11":])}

# ---- regime / vol / calendar conditioners, all known BEFORE 20:00 UTC
G = lambda t: load_series(t)["Close"].reindex(dclose.index).ffill()
S_trend = pd.concat([(dclose > dclose.rolling(n).mean()).astype(float) for n in [20,50,100,150,200]],axis=1).mean(axis=1)
MAC = {"HYG":(G("HYG"),1),"LQD":(G("LQD"),1),"DXY":(G("DX-Y.NYB"),-1),"SPX":(G("^GSPC"),1)}
def ens_ma(s,sg,lbs=[50,100,150,200,250]):
    m = pd.concat([(s>s.rolling(n).mean()).astype(float) for n in lbs],axis=1).mean(axis=1)
    return m if sg>0 else 1-m
S_macro = pd.concat([ens_ma(s,sg) for s,sg in MAC.values()],axis=1).mean(axis=1)
regime = (S_trend*S_macro).clip(0,1).shift(1)      # known at 00:00 UTC of the day
rvol   = ewm_vol(dret,20).shift(1)
dow    = pd.Series(sess_r.index.dayofweek, index=sess_r.index)
dm     = pd.Series(sess_r.index.day, index=sess_r.index)
eom    = pd.Series(sess_r.index.days_in_month, index=sess_r.index)
tom    = ((dm >= eom-4) | (dm <= 4))

print("=== baseline: trade the window EVERY day ===")
print(pd.Series(line("all", sess_r)).round(2).to_string())

print("\n=== conditioned on daily REGIME score (known 00:00 UTC) ===")
rows = {}
q = pd.qcut(regime.reindex(sess_r.index).dropna(), 4, duplicates="drop")
for k, idx in q.groupby(q, observed=True):
    rows[str(k)] = line(k, sess_r.reindex(idx.index))
rows["regime>0.5"] = line("r>.5", sess_r[regime.reindex(sess_r.index) > 0.5])
rows["regime>0.7"] = line("r>.7", sess_r[regime.reindex(sess_r.index) > 0.7])
print(pd.DataFrame(rows).T.round(2).to_string())

print("\n=== conditioned on PRE-WINDOW return (00:00-20:00 UTC, known at 20:00) ===")
rows = {}
z = pd.concat([pre_r.rename("pre"), sess_r.rename("s")], axis=1).dropna()
qq = pd.qcut(z["pre"], 5, labels=[f"Q{i}" for i in range(1,6)])
for k, g in z.groupby(qq, observed=True): rows[f"pre {k}"] = line(str(k), g["s"])
rows["pre > 0"] = line("pre>0", z[z.pre>0]["s"]); rows["pre < 0"] = line("pre<0", z[z.pre<0]["s"])
print(pd.DataFrame(rows).T.round(2).to_string())

print("\n=== conditioned on VOLATILITY quartile ===")
rows = {}
qv = pd.qcut(rvol.reindex(sess_r.index).dropna(), 4, labels=["V1 low","V2","V3","V4 high"], duplicates="drop")
for k, idx in qv.groupby(qv, observed=True): rows[str(k)] = line(k, sess_r.reindex(idx.index))
print(pd.DataFrame(rows).T.round(2).to_string())

print("\n=== calendar conditioners ===")
rows = {}
for i in range(7): rows[f"dow {'MonTueWedThuFriSatSun'[i*3:i*3+3]}"] = line(str(i), sess_r[dow==i])
rows["weekday"] = line("wd", sess_r[dow<5]); rows["weekend"] = line("we", sess_r[dow>=5])
rows["turn-of-month"] = line("tom", sess_r[tom]); rows["mid-month"] = line("mid", sess_r[~tom])
print(pd.DataFrame(rows).T.round(2).to_string())

print("\n=== BEST COMBINATIONS: fewer trades, bigger edge (net @3bp/side = 6bp RT) ===")
rows = {}
reg = regime.reindex(sess_r.index)
cands = {
 "all days":                   pd.Series(True, index=sess_r.index),
 "regime>0.5":                 reg > 0.5,
 "regime>0.3":                 reg > 0.3,
 "weekday only":               dow < 5,
 "regime>0.3 & weekday":       (reg > 0.3) & (dow < 5),
 "regime>0.5 & weekday":       (reg > 0.5) & (dow < 5),
 "regime>0.3 & pre-ret>0":     (reg > 0.3) & (pre_r.reindex(sess_r.index) > 0),
 "regime>0.3 & tom":           (reg > 0.3) & tom,
 "regime>0.3 & lowvol(V1-3)":  (reg > 0.3) & (qv.reindex(sess_r.index) != "V4 high"),
}
for k, m in cands.items():
    m = m.reindex(sess_r.index).fillna(False)
    r = line(k, sess_r[m])
    if r: r["days/yr"] = m.sum()/ (len(sess_r)/365); rows[k] = r
print(pd.DataFrame(rows).T.round(2).to_string())
