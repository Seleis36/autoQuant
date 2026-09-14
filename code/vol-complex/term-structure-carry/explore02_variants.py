import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsc_lib import *
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)

df = load_all(); f = features(df)
closes = df[["vixy", "spy"]]
COST = {"vixy": 5.0, "spy": 5.0}
res = {}
def run(name, w_v, w_s=None, lag=0):
    w = pd.DataFrame({"vixy": w_v, "spy": (w_s if w_s is not None else 0.0)}, index=df.index).fillna(0.0)
    if lag: w = w.shift(lag).fillna(0.0)
    net, st = bt_multi(w, closes, COST, name=name)
    r = report(net)
    res[name] = {"Sh_full": r.Sharpe["full"], "Sh_IS": r.Sharpe["IS"], "Sh_OOS": r.Sharpe["OOS"],
                 "CAGR": r.CAGR["full"], "MDD": r.MaxDD["full"], "Vol": r.Vol["full"], "Skew": r.Skew["full"],
                 "TO": st["Turnover_ann"], "Gross": st["GrossExp"], "t_NW": r.t_NW["full"]}
    return net

# signals
contango = (f.slope > 1).astype(float)
sgn = np.sign(f.slope - 1)
beta = rolling_beta(f.vixy_ret, f.spy_ret, 63).shift(0)   # beta of VIXY on SPY, known at t
# vol scaling: target 15% ann on the VIXY leg's own vol (EWMA hl=10)
scal = (0.15 / f.vixy_vol).clip(upper=1.0)
scal40 = (0.40 / f.vixy_vol).clip(upper=1.0)
# 1/VIX scaling: size = 15/VIX capped 1
inv_vix = (15.0 / df.vix).clip(upper=1.0)

run("A short-if-contango, unit", -contango)
run("B sign(slope) +-1", -sgn)
run("C A x volscale15", -contango * scal)
run("D B x volscale15", -sgn * scal)
run("E A x volscale40", -contango * scal40)
run("F A x 1/VIX", -contango * inv_vix)
run("G B x 1/VIX", -sgn * inv_vix)
# hedged: short VIXY w, hedge SPY with -w*beta (beta negative -> short SPY)
wv = -contango * scal
run("H C + beta hedge", wv, -wv * beta)
wv = -sgn * scal
run("I D + beta hedge", wv, -wv * beta)
wv = -contango
run("J A + beta hedge", wv, -wv * beta)
# half hedge
wv = -contango * scal
run("K C + half hedge", wv, -0.5 * wv * beta)
# gating with VIX momentum: short only if VIX below 10d MA too
g1 = ((f.slope > 1) & (f.vix_ma10 < 1.0)).astype(float)
run("L contango & VIX<MA10, volscale", -g1 * scal)
g2 = ((f.slope > 1) & (f.slope9 > 1)).astype(float)
run("M contango & 9d-contango, volscale", -g2 * scal)
g3 = ((f.slope > 1) & (f.vrp10 > 0)).astype(float)
run("N contango & VRP10>0, volscale", -g3 * scal)
# long side gating: long vix when backwardation & VIX rising
l1 = ((f.slope < 1) & (f.vix_ma10 > 1)).astype(float)
run("O short g1 / long l1, volscale", (-g1 + l1) * scal)
run("P short g2 / long backwardation, volscale", (-g2 + (f.slope < 1)) * scal)
# lag-1 robustness for C
run("C lag1", (-contango * scal), lag=1)
run("D lag1", (-sgn * scal), lag=1)
run("L lag1", -g1 * scal, lag=1)

out = pd.DataFrame(res).T
print(out.round(2).to_string())
