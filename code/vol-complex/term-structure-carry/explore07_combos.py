import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsc_lib import *
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
df = load_all(); f = features(df)
df["vixm"] = rl.load_series("VIXM").loc[:END]["Close"].reindex(df.index)
closes = df[["vixy", "spy", "vixm"]]; COST = {"vixy": 5.0, "spy": 5.0, "vixm": 10.0}
res = {}; nets = {}
def run(name, lag=0, **legs):
    w = pd.DataFrame({k: v for k, v in legs.items()}, index=df.index).fillna(0.0)
    if lag: w = w.shift(lag).fillna(0.0)
    net, st = bt_multi(w, closes, COST, name=name); r = report(net); nets[name] = net
    res[name] = {"Sh_full": r.Sharpe["full"], "Sh_IS": r.Sharpe["IS"], "Sh_OOS": r.Sharpe["OOS"], "CAGR": r.CAGR["full"], "MDD": r.MaxDD["full"], "Vol": r.Vol["full"], "Skew": r.Skew["full"], "TO": st["Turnover_ann"], "Gross": st["GrossExp"], "t_NW": r.t_NW["full"]}
    return net
cal = df.index
def flag_next(days):
    nxt = pd.Series(cal[1:], index=cal[:-1]); return nxt.isin(pd.DatetimeIndex(days)).astype(float).reindex(cal).fillna(0.0)
def offs(events, ks):
    ev = pd.DatetimeIndex(events); ev = ev[(ev >= cal[0]) & (ev <= cal[-1])]; p0 = cal.searchsorted(ev)
    return pd.DatetimeIndex(sorted({cal[p + k] for p in p0 for k in ks if 0 <= p + k < len(cal)}))
fomc = pd.to_datetime(pd.read_csv("code/rates-bonds/treasury-flow-calendar/calendar_snapshots/fomc.csv")["date"])
def third_friday(y, m):
    d = pd.Timestamp(y, m, 15); return d + pd.offsets.Week(weekday=4) if d.weekday() != 4 else d
opex = [third_friday(y, m) for y in range(2011, 2027) for m in range(1, 13)]
vxexp = [x - pd.Timedelta(days=30) for x in opex]
contango = (f.slope > 1).astype(float); sgn = np.sign(f.slope - 1)
# A. two-sided curve spread
rv, rm = df.vixy.pct_change(), df.vixm.pct_change()
for k in [1.5, 2.0]:
    run(f"A curve spread sign(slope)x(-VIXY+{k}VIXM)", vixy=-sgn, vixm=k * sgn)
    run(f"A' contango-only spread (-VIXY+{k}VIXM), 3x", vixy=-3 * contango, vixm=3 * k * contango)
spr = (-rv + 2 * rm); sv = rl.ewm_vol(spr, 20, ANN)
run("A vol-scaled spread (target 15%)", vixy=-sgn * (0.15 / sv).clip(upper=3), vixm=2 * sgn * (0.15 / sv).clip(upper=3))
# B. calendar legs
L_fomc_m1 = flag_next(offs(fomc, [-1])); L_fomc_p1 = flag_next(offs(fomc, [1])); L_vx = flag_next(offs(vxexp, [-2, -1])); L_opex = flag_next(offs(opex, [1]))
run("B short FOMC-1", vixy=-L_fomc_m1); run("B long FOMC+1", vixy=L_fomc_p1); run("B short VXexp-2,-1", vixy=-L_vx); run("B short opex+1", vixy=-L_opex)
calw = (-L_fomc_m1 + L_fomc_p1 - L_vx - L_opex).clip(-1, 1)
run("B all calendar legs", vixy=calw)
run("B calendar + contango carry (0.5)", vixy=(calw - 0.5 * contango).clip(-1, 1))
run("B calendar legs, lag1", lag=1, vixy=calw)
# D. ensemble score
sma200 = df.spy / df.spy.rolling(200).mean()
comps = pd.DataFrame({"slope": f.slope > 1, "vrp": f.vrp10 > 0, "vixma": f.vix_ma10 < 1, "spy": sma200 > 1, "vvix": f.vvix < 95}).astype(float)
score = comps.mean(axis=1)
run("D ensemble -score", vixy=-score); run("D ensemble short if score>=0.8", vixy=-(score >= 0.8).astype(float)); run("D ensemble short if score==1", vixy=-(score >= 1).astype(float))
run("D ensemble +-: -(score-0.5)*2", vixy=-(score - 0.5) * 2)
# E. long-vol tail leg
tail = ((df.vix9d > df.vix) & (f.vix_ma10 > 1)).astype(float)
run("E long tail leg only", vixy=tail); run("E contango short + tail long", vixy=(-contango + tail).clip(-1, 1))
tail2 = ((df.vix9d > df.vix) & (f.vix_ma10 > 1.1)).astype(float)
run("E contango short + tail2 long", vixy=(-contango + tail2).clip(-1, 1))
# F. next-day reversal after big moves
r1 = rv
for th in [0.05, 0.10, 0.15]:
    run(f"F short after VIXY>+{th}", vixy=-(r1 > th).astype(float)); run(f"F long after VIXY<-{th}", vixy=(r1 < -th).astype(float))
    run(f"F reversal +-{th}", vixy=-(r1 > th).astype(float) + (r1 < -th).astype(float))
print("cond mean of next-day VIXY ret (bp) by today's ret bucket:")
b = pd.cut(r1, [-1, -0.10, -0.05, -0.02, 0.02, 0.05, 0.10, 2]); print((rv.shift(-1).groupby(b).agg(["mean", "count"]).assign(mean=lambda x: x["mean"] * 1e4)).round(1))
print(pd.DataFrame(res).T.round(2).to_string())
