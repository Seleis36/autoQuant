"""Exp 07 - Parameter-free-ish ENSEMBLE version + vol-scaling overlay.
No single lookback is chosen: every block is averaged over 5 lookbacks."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import *
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)

df = load_btc(); close = df["Close"]; ret = close.pct_change(); cal = close.index
G = lambda t: load_series(t)["Close"].reindex(cal).ffill()
MAC = {"HYG": (G("HYG"), +1), "LQD": (G("LQD"), +1),
       "DXY": (G("DX-Y.NYB"), -1), "SPX": (G("^GSPC"), +1)}
LOOKBACKS = [50, 100, 150, 200, 250]

def ens_ma(s, sign, lbs=LOOKBACKS):
    """mean over lookbacks of 1{s above its MA_n} (or below, if sign<0)"""
    parts = [(s > s.rolling(n).mean()).astype(float) for n in lbs]
    m = pd.concat(parts, axis=1).mean(axis=1)
    return m if sign > 0 else 1.0 - m

macro = pd.concat([ens_ma(s, sg) for s, sg in MAC.values()], axis=1).mean(axis=1)
btc_tr = pd.concat([(close > close.rolling(n).mean()).astype(float)
                    for n in [20, 50, 100, 150, 200]], axis=1).mean(axis=1)

SPL = {"IS 2014-2020": ("2014-01-01","2020-12-31"), "OOS 2021-2026": ("2021-01-01","2026-12-31"),
       "2021": ("2021-01-01","2021-12-31"), "2022": ("2022-01-01","2022-12-31"),
       "2023": ("2023-01-01","2023-12-31"), "2024": ("2024-01-01","2024-12-31"),
       "2025": ("2025-01-01","2025-12-31"), "2026": ("2026-01-01","2026-12-31")}

def row(w, name, cost=10):
    net, st = backtest(w, close, cost_bps=cost, name=name)
    return net, pd.concat([st[["CAGR","Vol","Sharpe","Sortino","MaxDD","Calmar","Turnover_ann","TimeInMkt","t_NW"]],
        pd.Series({"SR_IS": perf_stats(net.loc[:"2020-12-31"])["Sharpe"],
                   "SR_OOS": perf_stats(net.loc["2021-01-01":])["Sharpe"],
                   "Calmar_OOS": perf_stats(net.loc["2021-01-01":])["Calmar"]})])

print("=== Ensemble building blocks ===")
out = {}
for nm, w in [("Macro ens (4 series x 5 lb)", macro),
              ("BTC trend ens (5 lb)", btc_tr),
              ("Macro x Trend", macro * btc_tr),
              ("0.5(Macro+Trend)", 0.5*(macro+btc_tr)),
              ("sqrt(Macro x Trend)", np.sqrt(macro*btc_tr))]:
    _, out[nm] = row(w, nm)
_, out["BuyHold"] = row(pd.Series(1.0, index=cal), "BuyHold", cost=0)
print(fmt(pd.DataFrame(out).T).to_string())

print("\n=== + vol-scaling overlay on (Macro x Trend), cap=1.0 (spot, no leverage) ===")
out = {}
base = macro * btc_tr
for tgt in [0.25, 0.30, 0.35, 0.40, 0.50, 0.60]:
    vs = vol_target_scalar(ret, target=tgt, halflife=20, cap=1.0)
    _, out[f"voltgt {int(tgt*100)}%"] = row(base * vs, f"voltgt{tgt}")
print(fmt(pd.DataFrame(out).T).to_string())

print("\n=== + vol-scaling overlay on Macro-only, cap=1.0 ===")
out = {}
for tgt in [0.25, 0.30, 0.35, 0.40, 0.50, 0.60]:
    vs = vol_target_scalar(ret, target=tgt, halflife=20, cap=1.0)
    _, out[f"voltgt {int(tgt*100)}%"] = row(macro * vs, f"m_voltgt{tgt}")
print(fmt(pd.DataFrame(out).T).to_string())

print("\n=== Leverage sensitivity (spot-margin extension), Macro x Trend, target 40% ===")
out = {}
for cap in [1.0, 1.25, 1.5, 2.0]:
    vs = vol_target_scalar(ret, target=0.40, halflife=20, cap=cap)
    _, out[f"cap {cap}x"] = row(base * vs, f"cap{cap}")
print(fmt(pd.DataFrame(out).T).to_string())

# detail on the leading no-leverage candidate
vs = vol_target_scalar(ret, target=0.35, halflife=20, cap=1.0)
net, _ = row(base * vs, "BLRT")
print("\n--- Macro x Trend x volscale(35%) : by period ---")
print(fmt(split_stats(net, SPL)).to_string())
