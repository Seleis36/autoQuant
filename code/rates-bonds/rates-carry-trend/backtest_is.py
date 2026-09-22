"""Step 1 -- design the carry+trend rates portfolio on IS 1990-2009 ONLY.

Split fixed before the first run and never moved:
    IS   1990-01-01 -> 2009-12-31   synthetic CMT returns; every choice made here
    OOS  2010-01-01 -> 2026-09-21   ETF era (SHY/IEF/TLT), and the crypto-book overlap
The ETFs this strategy trades barely existed in the IS window, so the split is not a
convenience -- it is a genuine out-of-sample instrument as well as period.
"""
import os, sys
import numpy as np, pandas as pd
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
sys.path.insert(0, os.path.join(H, "..", "..", "shared"))
from curve_lib import yields, total_returns, excess_returns, carry
from research_lib import perf_stats
pd.set_option("display.width", 220, "display.max_columns", 40)

ANN = 252.0
MATS = (2, 10, 30)
IS = ("1990-01-01", "2009-12-31")
OOS = ("2010-01-01", "2026-09-21")

y = yields()
tr = total_returns(y, MATS)
ex = excess_returns(tr, y)[list(MATS)]
cy = carry(y, MATS)


def zs(x, win=1260, minp=504):
    """Trailing z-score -- 5y window, expanding-safe, strictly backward-looking."""
    return (x - x.rolling(win, min_periods=minp).mean()) / x.rolling(win, min_periods=minp).std()


def sig_carry(win=1260):
    return zs(cy, win).clip(-2, 2)


def sig_trend(lbs=(63, 126, 252)):
    idx = (1 + ex.fillna(0)).cumprod()
    s = sum(np.sign(idx / idx.rolling(L).mean() - 1) for L in lbs) / len(lbs)
    return s


def ivol(win=252, minp=126):
    return ex.rolling(win, min_periods=minp).std() * np.sqrt(ANN)


def build(signal, target_vol=0.10, leg_vol=0.05, port_win=252, gross_cap=6.0):
    """signal -> ETF-notional weights per maturity, vol-scaled twice:
    each leg to `leg_vol`, then the whole book to `target_vol`."""
    v = ivol(win=port_win)
    w = signal * (leg_vol / v)
    w = w.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    gross = w.abs().sum(axis=1)
    # portfolio vol target from the realised vol of the *unscaled* book, lagged
    pr = (w.shift(1) * ex).sum(axis=1)
    pv = pr.rolling(port_win, min_periods=126).std() * np.sqrt(ANN)
    k = (target_vol / pv).clip(0, 3).shift(1).fillna(0.0)
    w = w.mul(k, axis=0)
    g = w.abs().sum(axis=1)
    over = (g / gross_cap).clip(lower=1.0)
    return w.div(over, axis=0)


def bt(w, rets, cost_bps=2.0, name="s", ann=ANN):
    we = w.shift(1).fillna(0.0)
    turn = (we - we.shift(1).fillna(0.0)).abs().sum(axis=1)
    net = ((we * rets).sum(axis=1) - turn * cost_bps / 1e4).rename(name)
    st = perf_stats(net.dropna(), ann=ann, name=name)
    st["Turnover_ann"] = turn.sum() / (len(turn) / ann)
    st["AvgGross"] = we.abs().sum(axis=1).mean()
    st["MaxGross"] = we.abs().sum(axis=1).max()
    return net, st


if __name__ == "__main__":
    print("excess-return span:", ex.index.min().date(), "->", ex.index.max().date())
    sc, st_ = sig_carry(), sig_trend()
    cand = {
        "carry_only": sc,
        "trend_only": st_,
        "carry+trend": (sc.clip(-1, 1) + st_) / 2.0,
        "carry_sign": np.sign(sc),
        "trend_252": np.sign((1 + ex.fillna(0)).cumprod().pipe(lambda i: i / i.rolling(252).mean() - 1)),
    }
    rows, nets = {}, {}
    for k, s in cand.items():
        w = build(s)
        n, stt = bt(w, ex, name=k)
        nets[k] = n
        rows[k] = perf_stats(n.loc[IS[0]:IS[1]].dropna(), ann=ANN, name=k)
        rows[k]["Turnover_ann"] = stt["Turnover_ann"]; rows[k]["AvgGross"] = stt["AvgGross"]
    print("\n=== IS 1990-2009, synthetic CMT, 2bp/side ===")
    print(pd.DataFrame(rows).T[["CAGR", "Vol", "Sharpe", "MaxDD", "Calmar", "t_NW", "Turnover_ann", "AvgGross"]].round(3))

    N = pd.DataFrame(nets).loc[IS[0]:IS[1]]
    print("\nIS sleeve correlation:\n", N[["carry_only", "trend_only"]].corr().round(2))
    print("\nIS by 5-year block (carry+trend):")
    n = nets["carry+trend"].loc[IS[0]:IS[1]]
    for a, b in [("1990", "1994"), ("1995", "1999"), ("2000", "2004"), ("2005", "2009")]:
        s = n.loc[a:b]
        print(f"  {a}-{b}: SR {s.mean()/s.std()*np.sqrt(ANN):5.2f}  ann {s.mean()*ANN:6.2%}")
