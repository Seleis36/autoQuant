"""Exp 14 - FUSION v2, corrected bar alignment.

Bar T covers [T, T+1h). hret[T] = Close_T/Close_{T-1}-1 = the return EARNED during [T,T+1h).
A clock-based weight for bar T is known AT time T => it is applied to hret[T] with NO shift.
Daily-derived components are lagged one full day PLUS one hour so they are strictly
knowable before the bar they act on."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

H = pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h.parquet"))
hclose = H["Close"]; hidx = hclose.index; hret = hclose.pct_change().fillna(0.0)
HANN = 24*365.0
dclose = hclose.resample("1D").last(); dret = dclose.pct_change()

G = lambda t: load_series(t)["Close"].reindex(dclose.index).ffill()
S_trend = pd.concat([(dclose > dclose.rolling(n).mean()).astype(float)
                     for n in [20,50,100,150,200]], axis=1).mean(axis=1)
MAC = {"HYG": (G("HYG"), +1), "LQD": (G("LQD"), +1), "DXY": (G("DX-Y.NYB"), -1), "SPX": (G("^GSPC"), +1)}
def ens_ma(s, sign, lbs=[50,100,150,200,250]):
    m = pd.concat([(s > s.rolling(n).mean()).astype(float) for n in lbs], axis=1).mean(axis=1)
    return m if sign > 0 else 1.0 - m
S_macro = pd.concat([ens_ma(s, sg) for s, sg in MAC.values()], axis=1).mean(axis=1)
regime = (S_trend * S_macro).clip(0,1)
volsc  = vol_target_scalar(dret, target=0.35, halflife=20, cap=1.0)

base_d  = (regime * volsc).shift(1)                       # lag 1 day
base_h  = base_d.reindex(hidx, method="ffill").shift(1).fillna(0.0)   # +1h safety lag
sess    = pd.Series(np.where(pd.DatetimeIndex(hidx).hour.isin([20,21,22]), 1.0, 0.0), index=hidx)

def bt(w, cost_bps, name="s"):
    w = pd.Series(w, index=hidx).clip(0,1).fillna(0.0)
    turn = (w - w.shift(1).fillna(0.0)).abs()
    net = w * hret - turn * cost_bps/1e4                  # NO shift on w: known at bar open
    eq = (1+net).cumprod(); dd = (eq/eq.cummax()-1).min(); yrs = len(net)/HANN
    def s_(a,b):
        x = net.loc[a:b]; return x.mean()/x.std()*np.sqrt(HANN) if x.std()>0 else np.nan
    return net, pd.Series({
        "CAGR%": (eq.iloc[-1]**(1/yrs)-1)*100, "Vol%": net.std()*np.sqrt(HANN)*100,
        "SR": net.mean()/net.std()*np.sqrt(HANN), "MaxDD%": dd*100,
        "Calmar": ((eq.iloc[-1]**(1/yrs)-1)/abs(dd)) if dd<0 else np.nan,
        "RT/yr": turn.sum()/2/yrs, "AvgExp%": w.mean()*100,
        "SR_IS": s_(None,"2021-12-31"), "SR_OOS": s_("2022-01-01",None),
        "SR_ETF": s_("2024-01-11",None), "t_NW": newey_west_t(net.values, lags=24*21)}, name=name)

print("=== sanity: pure session (clock only), gross ===")
_, s0 = bt(sess, 0.0); print(s0.round(2).to_string())

print("\n=== components @ 3bp/side (realistic maker fee, VIP tier) ===")
out = {}
_, out["BuyHold"]            = bt(pd.Series(1.0,index=hidx), 0.0)
_, out["Daily regime only"]  = bt(base_h, 3.0)
_, out["Session only"]       = bt(sess, 3.0)
print(pd.DataFrame(out).T.round(2).to_string())

print("\n=== FUSION: w = clip(base + b*session, 0, 1) — additive overlay (low turnover) ===")
for c in [0.0, 2.0, 3.0, 5.0, 7.5, 10.0]:
    out = {}
    for b in [0.0, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0]:
        _, out[f"b={b}"] = bt(base_h + b*sess, c)
    print(f"\n--- cost {c} bp/side ---")
    print(pd.DataFrame(out).T[["CAGR%","Vol%","SR","MaxDD%","Calmar","RT/yr","SR_IS","SR_OOS","SR_ETF"]].round(2).to_string())
