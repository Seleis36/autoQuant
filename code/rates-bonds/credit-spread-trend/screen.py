"""Step 2 -- screen candidate rates sleeves on IS 2010-2017 only.

Sleeve A  credit carry, risk-managed (HYG vs IEF)
Sleeve B  duration trend (TLT)
Sleeve C  curve carry / roll-down (IEF vs SHY, conditioned on 10y-2y slope)
Sleeve D  breakeven trend (TIP vs IEF)
The point of the screen is not to find one winner but to find sleeves that are
individually positive and mutually uncorrelated.
"""
import numpy as np, pandas as pd, sys, os
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
sys.path.insert(0, os.path.join(H, "..", "..", "shared"))
from data_lib import prices, hy_excess, ANN, DUR_HEDGE
from research_lib import perf_stats
pd.set_option("display.width", 220, "display.max_columns", 40)

IS = ("2010-01-01", "2017-12-31")
px = prices(["HYG", "IEF", "SHY", "LQD", "TLT", "AGG", "TIP", "SPY"]).dropna(subset=["HYG", "IEF"])
yl = prices(["^IRX", "^FVX", "^TNX", "^TYX"], include_pre2010=False)
vix = prices(["^VIX"], include_pre2010=False)["^VIX"]
r = px.pct_change()
hx = hy_excess(px)

def bt(w, ret, cost_bps=3.0, legs=1.0, name="s", ann=ANN):
    w = w.reindex(ret.index).fillna(0.0)
    we = w.shift(1).fillna(0.0)
    turn = (we - we.shift(1).fillna(0.0)).abs() * legs
    net = (we * ret - turn * cost_bps / 1e4).rename(name)
    st = perf_stats(net.dropna(), ann=ann, name=name)
    st["Turnover_ann"] = turn.sum() / (len(turn) / ann)
    st["AvgAbsExp"] = we.abs().mean()
    return net, st

def rv(x, w=20):
    return x.rolling(w).std() * np.sqrt(ANN)

out, nets = {}, {}
def add(name, w, ret, legs=1.0):
    n, s = bt(w, ret, legs=legs, name=name)
    out[name] = s; nets[name] = n

# ---- A: credit carry with risk management
for tv in [0.08]:
    for vw in [20, 40, 60]:
        w = (tv / rv(hx, vw)).clip(0, 3).shift(0)
        add(f"A_ivol{vw}", w, hx, legs=1 + DUR_HEDGE)
# gate on drawdown of the credit index from its rolling high
hidx = (1 + hx.fillna(0)).cumprod()
for L in [60, 120, 250]:
    dd = hidx / hidx.rolling(L).max() - 1
    for thr in [-0.01, -0.02, -0.03]:
        w = (dd > thr).astype(float)
        add(f"A_dd{L}_{int(-thr*100)}", w, hx, legs=1 + DUR_HEDGE)
# gate on VIX vs its own MA
for L in [20, 60]:
    g = (vix < vix.rolling(L).mean()).astype(float).reindex(hx.index).ffill()
    add(f"A_vixgate{L}", g, hx, legs=1 + DUR_HEDGE)
# equity momentum leads credit
for L in [20, 60, 120]:
    g = (px["SPY"] > px["SPY"].rolling(L).mean()).astype(float)
    add(f"A_spygate{L}", g, hx, legs=1 + DUR_HEDGE)

# ---- B: duration trend on TLT
for L in [20, 40, 60, 90, 120, 180, 252]:
    w = np.sign(px["TLT"] / px["TLT"].rolling(L).mean() - 1)
    add(f"B_tlt_ma{L}", w, r["TLT"])
# multi-horizon
w = np.sign(sum(np.sign(px["TLT"] / px["TLT"].rolling(L).mean() - 1) for L in [40, 90, 180]))
add("B_tlt_multi", w, r["TLT"])

# ---- C: curve carry, IEF vs SHY, long duration when the curve is steep
slope = (yl["^TNX"] - yl["^IRX"]).reindex(px.index).ffill()
ief_ex = r["IEF"] - r["SHY"] * 0.0   # SHY duration ~1.9y, IEF ~7.3y
ief_hedged = r["IEF"] - (1.9 / 7.3) * 0.0
for thr in [0.5, 1.0, 1.5]:
    w = (slope > thr).astype(float) - (slope < 0).astype(float)
    add(f"C_slope{thr}", w, r["IEF"] - r["SHY"])
for L in [252]:
    z = (slope - slope.rolling(L).mean()) / slope.rolling(L).std()
    add("C_slopez", z.clip(-1, 1), r["IEF"] - r["SHY"])

# ---- D: breakeven trend (TIP vs IEF)
be = r["TIP"] - r["IEF"]
for L in [40, 90, 180]:
    bidx = (1 + be.fillna(0)).cumprod()
    add(f"D_be_ma{L}", np.sign(bidx / bidx.rolling(L).mean() - 1), be, legs=2.0)

df = pd.DataFrame(out).T
isdf = {}
for k, n in nets.items():
    isdf[k] = perf_stats(n.loc[IS[0]:IS[1]].dropna(), ann=ANN, name=k)
isdf = pd.DataFrame(isdf).T
isdf["Turnover_ann"] = df["Turnover_ann"]
print("=== IS 2010-2017 ===")
print(isdf[["CAGR", "Vol", "Sharpe", "MaxDD", "t_NW", "Turnover_ann"]].sort_values("Sharpe", ascending=False).round(3))

best = ["A_ivol40", "A_dd120_2", "A_spygate60", "B_tlt_multi", "C_slopez", "D_be_ma90"]
N = pd.DataFrame({k: nets[k] for k in best}).loc[IS[0]:IS[1]]
print("\n=== IS correlation between sleeves ===")
print(N.corr().round(2))
