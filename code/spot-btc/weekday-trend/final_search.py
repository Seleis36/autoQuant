"""Final search: multi-signal combined strategy on daily BTC.

Signals (all long/flat, lookahead-safe):
    trend        = 1{close_t > SMA(T)}
    momentum     = 1{ret_M > 0}
    vol_scalar   = clip(target/ewma_vol_hl, 0, cap)
    dip          = 1{close < 0.95 * max(close, H)}  (add extra weight)
    weekday      = optional gate (skip Thu)

Combine via multiplicative gates; add dip as additive boost.
"""
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

def one(T=100, M=20, target=0.4, hl=20, cap=1.5, skip_dow=None,
        dip_h=10, dip_thresh=0.06, dip_boost=0.5, use_mom=True,
        use_trend=True, use_dip=False):
    w = pd.Series(0.0, index=c.index)
    sma = c.rolling(T).mean()
    trend = (c > sma).astype(float) if use_trend else pd.Series(1.0, index=c.index)
    mom = (c.pct_change(M) > 0).astype(float) if use_mom else pd.Series(1.0, index=c.index)
    v = ewm_vol(r, halflife=hl)
    scale = (target / v).clip(0, cap).fillna(0)
    base = trend * mom * scale
    if use_dip:
        ref = c.rolling(dip_h).max()
        dip = ((c / ref - 1) < -dip_thresh).astype(float)
        base = (base + dip * dip_boost * scale).clip(upper=cap)
    if skip_dow is not None:
        next_dow = (c.index + pd.Timedelta(days=1)).dayofweek
        gate = pd.Series([0.0 if d in skip_dow else 1.0 for d in next_dow], index=c.index)
        base = base * gate
    return base.fillna(0)

# ------------ walk-forward with 3-yr rolling params -------------
def walk_forward(param_grid, train_yrs=3, step_yrs=1):
    """Run walk-forward: at each period start, pick best (by IS Sharpe over train_yrs), apply next step_yrs."""
    start = pd.Timestamp("2016-01-01")
    end = pd.Timestamp("2026-09-01")
    equity_pieces = []
    dates = pd.date_range(start, end, freq=pd.DateOffset(years=step_yrs))
    for i in range(1, len(dates)):
        train_end = dates[i]
        train_start = train_end - pd.DateOffset(years=train_yrs)
        test_end = train_end + pd.DateOffset(years=step_yrs) if i+1 < len(dates) else end
        best_sh, best_params, best_ret = -np.inf, None, None
        for params in param_grid:
            w = one(**params)
            n, s = backtest(w, c, cost_bps=10.0)
            train_sh = perf_stats(n.loc[train_start:train_end]).Sharpe
            if train_sh > best_sh:
                best_sh, best_params = train_sh, params
                best_ret = n
        equity_pieces.append(best_ret.loc[train_end:test_end])
    net = pd.concat(equity_pieces)
    return net

# Try many configurations
print("=== Multi-config screening (full + IS + OOS Sharpe) ===")
configs = []
for T in [50, 100, 150, 200]:
    for M in [10, 20, 40]:
        for tv in [0.3, 0.4, 0.5]:
            for hl in [10, 20]:
                for skip in [None, (3,), (1, 3)]:
                    for use_dip in [False, True]:
                        for use_mom in [False, True]:
                            configs.append(dict(T=T, M=M, target=tv, hl=hl,
                                                skip_dow=skip, use_dip=use_dip, use_mom=use_mom))

results = []
for p in configs:
    w = one(**p)
    n, s = backtest(w, c, cost_bps=10.0)
    s_is = perf_stats(n.loc[IS[0]:IS[1]]).Sharpe
    s_oos = perf_stats(n.loc[OOS[0]:OOS[1]]).Sharpe
    results.append((p, s.Sharpe, s_is, s_oos, s.MaxDD, s.CAGR, s.AvgExposure))

df = pd.DataFrame(results, columns=["params", "Sharpe", "IS", "OOS", "MDD", "CAGR", "Expo"])
df["min_split"] = df[["IS", "OOS"]].min(axis=1)
top = df.sort_values("min_split", ascending=False).head(15)
print("\nTop 15 by min(IS,OOS) Sharpe:")
for _, row in top.iterrows():
    print(f"Full={row.Sharpe:.2f} IS={row.IS:.2f} OOS={row.OOS:.2f} MDD={row.MDD*100:.1f}% CAGR={row.CAGR*100:.1f}% Expo={row.Expo*100:.1f}% - {row.params}")

# best OOS
print("\nTop 10 by OOS Sharpe (with min_split filter > 0.7 IS):")
df_f = df[df["IS"] > 0.7].sort_values("OOS", ascending=False).head(10)
for _, row in df_f.iterrows():
    print(f"Full={row.Sharpe:.2f} IS={row.IS:.2f} OOS={row.OOS:.2f} MDD={row.MDD*100:.1f}% CAGR={row.CAGR*100:.1f}% - {row.params}")
