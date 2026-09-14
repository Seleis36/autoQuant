import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsc_lib import *
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
df = load_all(); f = features(df)
df["vixm"] = rl.load_series("VIXM").loc[:END]["Close"].reindex(df.index)
closes = df[["vixy", "spy", "vixm", "svxy"]]
COST = {"vixy": 5.0, "spy": 5.0, "vixm": 10.0, "svxy": 5.0}
res = {}
def run(name, **legs):
    w = pd.DataFrame({k: v for k, v in legs.items()}, index=df.index).fillna(0.0)
    net, st = bt_multi(w, closes, COST, name=name)
    r = report(net)
    res[name] = {"Sh_full": r.Sharpe["full"], "Sh_IS": r.Sharpe["IS"], "Sh_OOS": r.Sharpe["OOS"],
                 "CAGR": r.CAGR["full"], "MDD": r.MaxDD["full"], "Vol": r.Vol["full"], "Skew": r.Skew["full"],
                 "TO": st["Turnover_ann"], "Gross": st["GrossExp"], "t_NW": r.t_NW["full"]}
    return net

# 1. weekday effect
rv = df.vixy.pct_change(); rm = df.vixm.pct_change()
wd = pd.DataFrame({"vixy": rv, "vixm": rm, "spy": df.spy.pct_change()})
wd["dow"] = wd.index.dayofweek
print("Mean daily return (bp) by weekday, and Sharpe of short VIXY that day only:")
g = wd.groupby("dow")
print(pd.DataFrame({"vixy_bp": g.vixy.mean() * 1e4, "vixy_sh": -g.vixy.mean() / g.vixy.std() * np.sqrt(252),
                    "vixm_bp": g.vixm.mean() * 1e4, "spy_bp": g.spy.mean() * 1e4, "n": g.size()}).round(2))
# weekday of the held return: weight set at close t is applied to day t+1 return. dow(t+1).
nxt_dow = pd.Series(df.index.dayofweek, index=df.index).shift(-1)   # NOTE: uses next bar's calendar: knowable (calendar)
contango = (f.slope > 1).astype(float)
for d in range(5):
    run(f"short VIXY if contango & next day is dow{d}", vixy=-contango * (nxt_dow == d))
run("short VIXY contango, skip Monday", vixy=-contango * (nxt_dow != 0))

# 2. front-vs-mid roll spread: short VIXY, long VIXM, ratio by rolling vol
volratio = (rl.ewm_vol(rv, 20, ANN) / rl.ewm_vol(rm, 20, ANN)).clip(1, 4)
run("spread: -1 VIXY +volratio VIXM", vixy=-1.0, vixm=volratio)
run("spread: -1 VIXY +2 VIXM", vixy=-1.0, vixm=2.0)
run("spread contango-gated: -1 VIXY +2 VIXM", vixy=-contango, vixm=2 * contango)
run("spread beta-neutral (-1,+2.5)", vixy=-1.0, vixm=2.5)
run("spread (-1,+1.5)", vixy=-1.0, vixm=1.5)
# 3. VVIX gating
for q in [85, 95, 105]:
    run(f"contango & VVIX<{q}", vixy=-contango * (f.vvix < q))
    run(f"contango & VVIX>{q}", vixy=-contango * (f.vvix > q))
# 4. Cooper momentum on SVXY-like (use -VIXY): mom_k = VIXY k-day return < 0 -> short
for k in [5, 10, 21, 42, 83]:
    mom = df.vixy.pct_change(k)
    run(f"mom{k}: short if VIXY {k}d ret<0 else long", vixy=-np.sign(mom))
    run(f"mom{k} short-only", vixy=-(mom < 0).astype(float))
# 5. VRP smoothed
for w in [5, 10, 21]:
    v = f[f"vrp{w}"].rolling(5).mean()
    run(f"VRP{w} MA5 sign", vixy=-np.sign(v))
    run(f"VRP{w} MA5 short-only", vixy=-(v > 0).astype(float))
# 6. hysteresis on slope
def hyst(x, lo, hi):
    s = pd.Series(np.nan, index=x.index); s[x > hi] = 1.0; s[x < lo] = 0.0
    return s.ffill().fillna(0.0)
for lo, hi in [(0.98, 1.02), (0.95, 1.05), (1.0, 1.05), (0.9, 1.0)]:
    run(f"hyst slope in/out {hi}/{lo}", vixy=-hyst(f.slope, lo, hi))
# 7. SVXY long instead of VIXY short (post-2018 it's -0.5x)
run("long SVXY if contango", svxy=contango)
out = pd.DataFrame(res).T
print(out.round(2).to_string())
