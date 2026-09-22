"""Step 2 (IS only) -- fix two defects found in step 1:
   * carry as a trailing z-score inverts the premium (IS SR -0.49). The bond carry
     premium is a *level* effect -- steep curve, long duration -- not a deviation
     from its own recent mean. Test the raw level.
   * daily re-scaling churned 60-115x notional a year. Smooth the signal and add a
     no-trade band.
"""
import os, sys
import numpy as np, pandas as pd
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
sys.path.insert(0, os.path.join(H, "..", "..", "shared"))
from curve_lib import yields, total_returns, excess_returns, carry
from research_lib import perf_stats
from backtest_is import build, bt, ivol, MATS, IS, OOS, ANN
pd.set_option("display.width", 220, "display.max_columns", 40)

y = yields(); tr = total_returns(y, MATS); ex = excess_returns(tr, y)[list(MATS)]
cy = carry(y, MATS)
idx = (1 + ex.fillna(0)).cumprod()


def band(w, tol=0.05):
    """Rebalance a leg only when it has drifted more than `tol` of notional."""
    out = np.array(w.values, dtype=float, copy=True)
    prev = np.zeros(w.shape[1])
    for i in range(len(out)):
        tgt = out[i]
        keep = np.abs(tgt - prev) < tol
        tgt = np.where(keep, prev, tgt)
        out[i] = tgt; prev = tgt
    return pd.DataFrame(out, index=w.index, columns=w.columns)


def s_carry_level(scale=0.02):
    """Long duration when carry (yield pickup + roll) is positive, size ~ carry/scale.
    `scale` = 200bp/yr is the full-sample median 10y carry, fixed a priori, not fitted."""
    return (cy / scale).clip(-1.5, 1.5)


def s_carry_sign():
    return np.sign(cy)


def s_trend(lbs=(63, 126, 252)):
    return sum(np.sign(idx / idx.rolling(L).mean() - 1) for L in lbs) / len(lbs)


def run(sig, smooth=10, tol=0.05, name="s", **kw):
    w = build(sig, **kw)
    if smooth:
        w = w.rolling(smooth).mean()
    w = band(w.fillna(0.0), tol=tol)
    n, st = bt(w, ex, name=name)
    return n, st, w


cands = {
    "carry_level": s_carry_level(),
    "carry_sign": s_carry_sign(),
    "trend": s_trend(),
    "carry_level+trend": (s_carry_level().clip(-1, 1) + s_trend()) / 2,
    "carry_sign+trend": (s_carry_sign() + s_trend()) / 2,
}
rows, nets, ws = {}, {}, {}
for k, s in cands.items():
    n, st, w = run(s, name=k)
    nets[k] = n; ws[k] = w
    rows[k] = perf_stats(n.loc[IS[0]:IS[1]].dropna(), ann=ANN, name=k)
    wi = w.loc[IS[0]:IS[1]]
    t = (wi.shift(1) - wi.shift(2)).abs().sum(axis=1)
    rows[k]["Turnover_ann"] = t.sum() / (len(t) / ANN)
    rows[k]["AvgGross"] = wi.abs().sum(axis=1).mean()
print("=== IS 1990-2009, smoothed + banded, 2bp/side ===")
print(pd.DataFrame(rows).T[["CAGR", "Vol", "Sharpe", "MaxDD", "Calmar", "t_NW", "Turnover_ann", "AvgGross"]].round(3))

print("\n=== IS: smoothing / band sensitivity on carry_sign+trend ===")
rows = {}
for sm in [1, 5, 10, 21]:
    for tol in [0.0, 0.05, 0.10]:
        n, st, w = run(cands["carry_sign+trend"], smooth=sm, tol=tol, name=f"sm{sm}_tol{tol}")
        s = n.loc[IS[0]:IS[1]].dropna()
        wi = w.loc[IS[0]:IS[1]]
        t = (wi.shift(1) - wi.shift(2)).abs().sum(axis=1)
        rows[f"sm{sm}_tol{tol}"] = {"Sharpe": s.mean() / s.std() * np.sqrt(ANN),
                                    "ann": s.mean() * ANN, "TO": t.sum() / (len(t) / ANN)}
print(pd.DataFrame(rows).T.round(3))

print("\n=== IS: per-maturity, carry_sign+trend ===")
w = ws["carry_sign+trend"]
for m in MATS:
    n = (w[m].shift(1) * ex[m]).loc[IS[0]:IS[1]].dropna()
    print(f"  {m}y: SR {n.mean()/n.std()*np.sqrt(ANN):5.2f}  ann {n.mean()*ANN:6.2%}  avg|w| {w[m].loc[IS[0]:IS[1]].abs().mean():.2f}")

print("\n=== IS: sleeves separately, 5-year blocks ===")
for k in ["carry_sign", "trend", "carry_sign+trend"]:
    n = nets[k].loc[IS[0]:IS[1]]
    line = "  ".join(f"{a[:4]}-{b[:4]}:{n.loc[a:b].mean()/n.loc[a:b].std()*np.sqrt(ANN):5.2f}"
                     for a, b in [("1990", "1994"), ("1995", "1999"), ("2000", "2004"), ("2005", "2009")])
    print(f"  {k:18s} {line}")
print("\nIS corr carry_sign vs trend:",
      round(pd.DataFrame(nets).loc[IS[0]:IS[1]][["carry_sign", "trend"]].corr().iloc[0, 1], 3))
