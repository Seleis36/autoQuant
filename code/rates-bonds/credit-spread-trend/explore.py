"""Step 1 -- characterise the HY credit risk premium and screen trend lookbacks.

Split fixed BEFORE any backtest and never moved:
    PRE  2007-04-11 -> 2009-12-31   (HYG inception; untouched holdout, printed last)
    IS   2010-01-01 -> 2017-12-31   (everything is chosen here)
    OOS  2018-01-01 -> 2026-09-21
Cost: 3 bp per side on gross turnover across both legs.
"""
import numpy as np, pandas as pd, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_lib import prices, hy_excess, crypto_book, hedge_report, ANN, DUR_HEDGE
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
from research_lib import perf_stats

pd.set_option("display.width", 200, "display.max_columns", 40)
PRE = ("2007-04-11", "2009-12-31"); IS = ("2010-01-01", "2017-12-31"); OOS = ("2018-01-01", "2026-09-21")

px = prices(["HYG", "IEF", "SHY", "LQD", "TLT", "AGG", "TIP", "SPY"])
px = px.dropna(subset=["HYG", "IEF"])
hx = hy_excess(px)
print("HYG/IEF span:", px.index.min().date(), "->", px.index.max().date(), len(px), "rows")

print("\n=== buy-and-hold HY credit premium (long HYG / short %.2f IEF) ===" % DUR_HEDGE)
rows = {}
for k, (a, b) in {"PRE": PRE, "IS": IS, "OOS": OOS, "FULL10": ("2010-01-01", OOS[1])}.items():
    rows[k] = perf_stats(hx.loc[a:b], ann=ANN, name=k)
print(pd.DataFrame(rows).T[["CAGR", "Vol", "Sharpe", "MaxDD", "Skew", "t_NW"]].round(3))

# ---------------------------------------------------------------- trend screen (IS only)
def trend_w(sig, mode="binary", cap=1.0):
    if mode == "binary":
        return np.sign(sig).clip(-1, 1)
    z = sig / sig.rolling(252, min_periods=126).std()
    return z.clip(-cap, cap)

def bt(w, r, cost_bps=3.0, legs=1 + DUR_HEDGE, ann=ANN, name="s"):
    """w known at close t, applied to r_{t+1}. Cost charged on gross turnover of both legs."""
    w = w.reindex(r.index).fillna(0.0)
    we = w.shift(1).fillna(0.0)
    turn = (we - we.shift(1).fillna(0.0)).abs() * legs
    net = we * r - turn * cost_bps / 1e4
    st = perf_stats(net.dropna(), ann=ann, name=name)
    st["Turnover_ann"] = turn.sum() / (len(turn) / ann)
    st["AvgAbsExp"] = we.abs().mean()
    st["PctLong"] = (we > 0).mean(); st["PctShort"] = (we < 0).mean()
    return net, st

print("\n=== IS 2010-2017: momentum on the HY excess return, binary sign ===")
res = {}
for L in [5, 10, 20, 40, 60, 90, 120, 180, 252]:
    sig = hx.rolling(L).mean()
    net, st = bt(trend_w(sig), hx, name=f"mom{L}")
    res[f"mom{L}"] = st
print(pd.DataFrame(res).T[["CAGR", "Vol", "Sharpe", "MaxDD", "t_NW", "Turnover_ann", "PctLong"]].round(3))

print("\n=== IS: same, long/flat only (no short) ===")
res = {}
for L in [10, 20, 40, 60, 90, 120, 180, 252]:
    sig = hx.rolling(L).mean()
    net, st = bt((np.sign(sig) > 0).astype(float), hx, name=f"lf{L}")
    res[f"lf{L}"] = st
print(pd.DataFrame(res).T[["CAGR", "Vol", "Sharpe", "MaxDD", "t_NW", "Turnover_ann", "PctLong"]].round(3))

print("\n=== IS: price-vs-MA on the HY excess *index* (cumulative) ===")
hidx = (1 + hx.fillna(0)).cumprod()
res = {}
for L in [20, 40, 60, 90, 120, 180, 252]:
    sig = hidx / hidx.rolling(L).mean() - 1
    net, st = bt(trend_w(sig), hx, name=f"ma{L}")
    res[f"ma{L}"] = st
print(pd.DataFrame(res).T[["CAGR", "Vol", "Sharpe", "MaxDD", "t_NW", "Turnover_ann", "PctLong"]].round(3))
