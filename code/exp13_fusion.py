"""Exp 13 - FUSION: US-close session concentration x daily liquidity/trend regime.

!! SUPERSEDED BY exp14_fusion2.py -- DO NOT CITE THESE NUMBERS !!
This version shifts the clock-based session weight by one bar, so it captures hours
21-23 UTC instead of the intended 20-22 and picks up hour 23, which is consistently
NEGATIVE. Kept for the research trail; exp14 has the corrected alignment.
Hourly backtest, full turnover-based cost accounting, no lookahead.

Timing: daily regime score uses data through 00:00 UTC of day D (i.e. the previous
UTC day's close) and is applied to hours of day D. Session weight is clock-only."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

H = pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h.parquet"))
hclose = H["Close"]; hidx = hclose.index
hret = hclose.pct_change().fillna(0.0)
HANN = 24*365.0

# ---- daily series (UTC) built from the same hourly data
dclose = hclose.resample("1D").last()
dret = dclose.pct_change()

# ---- daily regime sleeves (all known at 00:00 UTC of the NEXT day)
G = lambda t: load_series(t)["Close"].reindex(dclose.index).ffill()
S_trend = pd.concat([(dclose > dclose.rolling(n).mean()).astype(float)
                     for n in [20,50,100,150,200]], axis=1).mean(axis=1)
MAC = {"HYG": (G("HYG"), +1), "LQD": (G("LQD"), +1), "DXY": (G("DX-Y.NYB"), -1), "SPX": (G("^GSPC"), +1)}
def ens_ma(s, sign, lbs=[50,100,150,200,250]):
    m = pd.concat([(s > s.rolling(n).mean()).astype(float) for n in lbs], axis=1).mean(axis=1)
    return m if sign > 0 else 1.0 - m
S_macro = pd.concat([ens_ma(s, sg) for s, sg in MAC.values()], axis=1).mean(axis=1)
regime = (S_trend * S_macro).clip(0, 1)
volsc  = vol_target_scalar(dret, target=0.35, halflife=20, cap=1.0)

# shift by 1 day => score for day D uses info through end of day D-1 (00:00 UTC of D)
regime_h = regime.shift(1).reindex(hidx, method="ffill")
volsc_h  = volsc.shift(1).reindex(hidx, method="ffill")
sess     = pd.Series(np.where(pd.DatetimeIndex(hidx).hour.isin([20,21,22]), 1.0, 0.0), index=hidx)

def bt_hourly(w, cost_bps, name="s"):
    w = w.clip(0, 1).fillna(0.0)
    w_eff = w.shift(1).fillna(0.0)              # decide at bar open, earn that bar
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs()
    net = w_eff * hret - turn * cost_bps / 1e4
    eq = (1 + net).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    yrs = len(net) / HANN
    return net, pd.Series({
        "CAGR%": (eq.iloc[-1] ** (1/yrs) - 1) * 100,
        "Vol%": net.std() * np.sqrt(HANN) * 100,
        "SR": net.mean() / net.std() * np.sqrt(HANN),
        "MaxDD%": dd * 100,
        "Calmar": ((eq.iloc[-1] ** (1/yrs) - 1) / abs(dd)) if dd < 0 else np.nan,
        "RT/yr": turn.sum() / 2 / yrs,
        "AvgExp%": w_eff.mean() * 100,
        "t_NW": newey_west_t(net.values, lags=24*21)}, name=name)

def sub(net, a, b):
    s = net.loc[a:b]
    return s.mean()/s.std()*np.sqrt(HANN) if s.std() > 0 else np.nan

IS_A, IS_B = "2017-08-17", "2021-12-31"
OS_A, OS_B = "2022-01-01", "2026-12-31"

print("=== FUSION: w = max(session, alpha*regime) * volscalar ; cost 2bp/side ===")
out = {}
for alpha in [0.0, 0.25, 0.5, 0.75, 1.0]:
    w = np.maximum(sess, alpha * regime_h) * volsc_h
    net, st = bt_hourly(w, 2.0)
    st["SR_IS"] = sub(net, IS_A, IS_B); st["SR_OOS"] = sub(net, OS_A, OS_B)
    st["SR_ETF"] = sub(net, "2024-01-11", None)
    out[f"alpha={alpha}"] = st
# references
w_bh = pd.Series(1.0, index=hidx); net, st = bt_hourly(w_bh, 0.0)
st["SR_IS"]=sub(net,IS_A,IS_B); st["SR_OOS"]=sub(net,OS_A,OS_B); st["SR_ETF"]=sub(net,"2024-01-11",None)
out["BuyHold"] = st
w_d = (regime_h*volsc_h); net, st = bt_hourly(w_d, 2.0)
st["SR_IS"]=sub(net,IS_A,IS_B); st["SR_OOS"]=sub(net,OS_A,OS_B); st["SR_ETF"]=sub(net,"2024-01-11",None)
out["daily regime only"] = st
print(pd.DataFrame(out).T.round(2).to_string())

print("\n=== cost sensitivity for the leading alphas ===")
for alpha in [0.0, 0.5, 0.75, 1.0]:
    out = {}
    for c in [0.0, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0]:
        w = np.maximum(sess, alpha * regime_h) * volsc_h
        net, st = bt_hourly(w, c)
        st["SR_IS"] = sub(net, IS_A, IS_B); st["SR_OOS"] = sub(net, OS_A, OS_B)
        st["SR_ETF"] = sub(net, "2024-01-11", None)
        out[f"{c}bp"] = st
    print(f"\n--- alpha={alpha} ---")
    print(pd.DataFrame(out).T[["CAGR%","Vol%","SR","MaxDD%","Calmar","RT/yr","SR_IS","SR_OOS","SR_ETF"]].round(2).to_string())
