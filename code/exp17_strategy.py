"""Exp 17 - Full strategy: liquidity-regime base + US-close dip-buy overlay.

  DAILY (known 00:00 UTC):  base = regime * volscalar
  INTRADAY (known 20:00 UTC): overlay = b if hour in {20,21,22} and pre-window return < thr
  w = clip(base + overlay, 0, 1)
"""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

H = pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h.parquet"))
hclose = H["Close"]; hidx = hclose.index; hret = hclose.pct_change().fillna(0.0)
hh = pd.DatetimeIndex(hidx).hour; hday = pd.DatetimeIndex(hidx).normalize()
HANN = 24*365.0
dclose = hclose.resample("1D").last(); dret = dclose.pct_change()

# ---------- daily base
G = lambda t: load_series(t)["Close"].reindex(dclose.index).ffill()
S_trend = pd.concat([(dclose > dclose.rolling(n).mean()).astype(float) for n in [20,50,100,150,200]],axis=1).mean(axis=1)
MAC = {"HYG":(G("HYG"),1),"LQD":(G("LQD"),1),"DXY":(G("DX-Y.NYB"),-1),"SPX":(G("^GSPC"),1)}
def ens_ma(s,sg,lbs=[50,100,150,200,250]):
    m = pd.concat([(s>s.rolling(n).mean()).astype(float) for n in lbs],axis=1).mean(axis=1)
    return m if sg>0 else 1-m
S_macro = pd.concat([ens_ma(s,sg) for s,sg in MAC.values()],axis=1).mean(axis=1)
regime = (S_trend*S_macro).clip(0,1)
volsc  = vol_target_scalar(dret, target=0.35, halflife=20, cap=1.0)
base_h = (regime*volsc).shift(1).reindex(hidx, method="ffill").shift(1).fillna(0.0)

# ---------- pre-window return, known at 20:00 UTC each day
pre = hret.where(hh < 20, 0.0).groupby(hday).cumsum()      # running sum within day
pre_at20 = pre[hh == 19].groupby(hday[hh == 19]).last()    # cumulative 00:00->20:00
pre_h = pre_at20.reindex(hday).values                       # same value for every bar of that day
pre_h = pd.Series(pre_h, index=hidx)

WIN = np.isin(hh, [20,21,22])

def bt(w, cost_bps):
    w = pd.Series(w, index=hidx).clip(0,1).fillna(0.0)
    turn = (w - w.shift(1).fillna(0.0)).abs()
    net = w*hret - turn*cost_bps/1e4
    eq = (1+net).cumprod(); dd = (eq/eq.cummax()-1).min(); yrs = len(net)/HANN
    f = lambda a,b: (lambda x: x.mean()/x.std()*np.sqrt(HANN) if x.std()>0 else np.nan)(net.loc[a:b])
    return net, pd.Series({
        "CAGR%": (eq.iloc[-1]**(1/yrs)-1)*100, "Vol%": net.std()*np.sqrt(HANN)*100,
        "SR": net.mean()/net.std()*np.sqrt(HANN), "MaxDD%": dd*100,
        "Calmar": ((eq.iloc[-1]**(1/yrs)-1)/abs(dd)) if dd<0 else np.nan,
        "RT/yr": turn.sum()/2/yrs, "AvgExp%": w.mean()*100,
        "SR_IS": f(None,"2021-12-31"), "SR_OOS": f("2022-01-01",None), "SR_ETF": f("2024-01-11",None),
        "t_NW": newey_west_t(net.values, lags=24*21)})

print("=== overlay gate = (pre-window return < thr) ; b = overlay size ; cost 3bp/side ===")
for thr in [None, 0.0, -0.005, -0.010, -0.015]:
    out = {}
    for b in [0.3, 0.5, 0.7, 1.0]:
        gate = WIN if thr is None else (WIN & (pre_h.values < thr))
        _, out[f"b={b}"] = bt(base_h + b*pd.Series(gate.astype(float), index=hidx), 3.0)
    lab = "no gate (every day)" if thr is None else f"pre < {thr:+.3f}"
    print(f"\n--- gate: {lab} ---")
    print(pd.DataFrame(out).T[["CAGR%","Vol%","SR","MaxDD%","Calmar","RT/yr","SR_IS","SR_OOS","SR_ETF"]].round(2).to_string())

print("\n\n=== cost sensitivity of the leading spec: gate pre<0, b=1.0 ===")
gate = pd.Series((WIN & (pre_h.values < 0)).astype(float), index=hidx)
out = {}
for c in [0.0,1.0,2.0,3.0,5.0,7.5,10.0,15.0]:
    _, out[f"{c}bp/side"] = bt(base_h + 1.0*gate, c)
print(pd.DataFrame(out).T.round(2).to_string())

print("\n=== reference points @ same cost ===")
out = {}
_, out["BuyHold"] = bt(pd.Series(1.0,index=hidx), 0.0)
_, out["Base only (daily regime)"] = bt(base_h, 3.0)
_, out["Base + ungated session b=1"] = bt(base_h + pd.Series(WIN.astype(float),index=hidx), 3.0)
_, out["Base + GATED session b=1"] = bt(base_h + gate, 3.0)
print(pd.DataFrame(out).T.round(2).to_string())

print("\n=== yearly breakdown: Base + GATED session (b=1, 3bp/side) ===")
net, _ = bt(base_h + gate, 3.0)
rows = {}
for y in range(2017, 2027):
    s = net.loc[str(y)]
    if len(s) < 24*30: continue
    eq = (1+s).cumprod()
    rows[y] = {"ret%": (eq.iloc[-1]-1)*100, "vol%": s.std()*np.sqrt(HANN)*100,
               "SR": s.mean()/s.std()*np.sqrt(HANN), "MaxDD%": (eq/eq.cummax()-1).min()*100}
bh, _ = bt(pd.Series(1.0,index=hidx), 0.0)
for y in rows:
    s = bh.loc[str(y)]; rows[y]["BTC_ret%"] = ((1+s).cumprod().iloc[-1]-1)*100
    rows[y]["BTC_SR"] = s.mean()/s.std()*np.sqrt(HANN)
print(pd.DataFrame(rows).T.round(2).to_string())
