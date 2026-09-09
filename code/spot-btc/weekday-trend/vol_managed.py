"""Pure vol-managed BTC (Moreira-Muir) and variations."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import numpy as np
import pandas as pd
from research_lib import load_btc, backtest, perf_stats, ewm_vol, realized_vol, split_stats, fmt

btc = load_btc()
c = btc["Close"]
r = c.pct_change()

IS = ("2015-01-01", "2021-12-31")
OOS = ("2022-01-01", "2026-09-06")

def perf(name, w, cost=10.0):
    n, s = backtest(w, c, cost_bps=cost, name=name)
    ss = split_stats(n, {"IS": IS, "OOS": OOS})
    print(f"\n=== {name} ===")
    print(fmt(pd.DataFrame([s]).T.T))
    print(fmt(ss))
    return n, s

# 1) pure vol-managed (no trend filter) — long only
for tv in [0.3, 0.4, 0.5]:
    for hl in [10, 20, 30, 60]:
        for cap in [1.0, 1.5, 2.0]:
            v = ewm_vol(r, halflife=hl)
            w = (tv / v).clip(0, cap).fillna(0)
            n, s = backtest(w, c, cost_bps=10.0)
            s_oos = perf_stats(n.loc[OOS[0]:OOS[1]]).Sharpe
            s_is = perf_stats(n.loc[IS[0]:IS[1]]).Sharpe
            if s.Sharpe > 1.2 or s_oos > 1.0:
                print(f"vol-mngd tv={tv} hl={hl} cap={cap}: full={s.Sharpe:.2f} IS={s_is:.2f} OOS={s_oos:.2f} MDD={s.MaxDD*100:.1f}%")

# 2) vol-managed with **inverse** shape (Moreira-Muir literally uses 1/rv^2)
print("\n\n=== Moreira-Muir 1/rv^2 form ===")
for tv2 in [0.05, 0.08, 0.12, 0.15]:
    for hl in [10, 20, 30]:
        v = ewm_vol(r, halflife=hl)
        w = (tv2 / v**2).clip(0, 1.5).fillna(0)
        n, s = backtest(w, c, cost_bps=10.0)
        s_oos = perf_stats(n.loc[OOS[0]:OOS[1]]).Sharpe
        s_is = perf_stats(n.loc[IS[0]:IS[1]]).Sharpe
        print(f"MM tv2={tv2} hl={hl}: full={s.Sharpe:.2f} IS={s_is:.2f} OOS={s_oos:.2f} MDD={s.MaxDD*100:.1f}% Expo={s.AvgExposure*100:.1f}%")

# 3) vol-managed + vol trend (only in when vol falling)
print("\n\n=== vol-managed + vol-trend filter (rvol_20 < rvol_90) ===")
for hl in [10, 20, 30]:
    v20 = realized_vol(r, 20)
    v90 = realized_vol(r, 90)
    vol_falling = (v20 < v90).astype(float)
    v = ewm_vol(r, halflife=hl)
    for tv in [0.35, 0.5, 0.7]:
        w = (tv / v).clip(0, 1.5).fillna(0) * vol_falling
        n, s = backtest(w, c, cost_bps=10.0)
        s_oos = perf_stats(n.loc[OOS[0]:OOS[1]]).Sharpe
        s_is = perf_stats(n.loc[IS[0]:IS[1]]).Sharpe
        print(f"vol-fall + vm tv={tv} hl={hl}: full={s.Sharpe:.2f} IS={s_is:.2f} OOS={s_oos:.2f} MDD={s.MaxDD*100:.1f}%")
