"""Exp 18 - Rigorous validation of BULT: walk-forward, deflated Sharpe, bootstrap,
parameter surface, execution stress, alternate-venue replication, vectorbt cross-check."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
from strategy import *
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

H = load_hourly()
SPEC = dict(vol_target=0.35, vol_hl=20, gate_thr=-0.010, b=0.5)
COST = 3.0
w, P = build_signals(H, **SPEC); hret = P["hret"]
net, turn = backtest_hourly(w, hret, COST)
print("=== HEADLINE: BULT, 3bp/side ===")
print(stats(net, turn).round(3).to_string())

def sub(a, b, lab):
    s = net.loc[a:b]; t = turn.loc[a:b]
    return stats(s, t, lab)
print("\n=== period breakdown ===")
rows = [sub(None,"2021-12-31","IS  2017-2021"), sub("2022-01-01",None,"OOS 2022-2026"),
        sub("2024-01-11",None,"ETF era 2024+")]
for y in range(2017, 2027):
    s = net.loc[str(y)]
    if len(s) > 24*60: rows.append(stats(s, turn.loc[str(y)], str(y)))
print(pd.DataFrame(rows).round(2).to_string())

# ---------------- 1. PARAMETER SURFACE (is it a plateau or a spike?)
print("\n=== 1. parameter surface: Sharpe (full / OOS) @3bp ===")
surf_all, surf_oos = {}, {}
for thr in [-0.000, -0.005, -0.010, -0.015, -0.020, -0.030]:
    ra, ro = {}, {}
    for bb in [0.25, 0.5, 0.75, 1.0]:
        ww, PP = build_signals(H, **{**SPEC, "gate_thr": thr, "b": bb})
        nn, tt = backtest_hourly(ww, PP["hret"], COST)
        ra[f"b={bb}"] = nn.mean()/nn.std()*np.sqrt(HANN)
        o = nn.loc["2022-01-01":]; ro[f"b={bb}"] = o.mean()/o.std()*np.sqrt(HANN)
    surf_all[f"thr={thr:+.3f}"] = ra; surf_oos[f"thr={thr:+.3f}"] = ro
print("-- full sample --"); print(pd.DataFrame(surf_all).T.round(2).to_string())
print("-- OOS 2022+ --");   print(pd.DataFrame(surf_oos).T.round(2).to_string())

print("\n=== window sensitivity (start hour x length), full/OOS Sharpe @3bp ===")
rows = []
for st in [18,19,20,21,22]:
    for L in [1,2,3,4,5]:
        win = tuple(((st+i) % 24) for i in range(L))
        ww, PP = build_signals(H, **SPEC, window=win)
        nn, _ = backtest_hourly(ww, PP["hret"], COST)
        o = nn.loc["2022-01-01":]
        rows.append({"start": st, "len": L, "SR_all": nn.mean()/nn.std()*np.sqrt(HANN),
                     "SR_OOS": o.mean()/o.std()*np.sqrt(HANN)})
Wd = pd.DataFrame(rows)
print("full:"); print(Wd.pivot(index="start", columns="len", values="SR_all").round(2).to_string())
print("OOS:");  print(Wd.pivot(index="start", columns="len", values="SR_OOS").round(2).to_string())

# ---------------- 2. EXECUTION STRESS: late entry / early exit / extra slippage
print("\n=== 2. execution stress ===")
rows = {}
rows["as specified"] = stats(net, turn)
for lag in [1, 2]:
    wl = w.shift(lag).fillna(0.0)
    nl, tl = backtest_hourly(wl, hret, COST); rows[f"{lag}h late execution"] = stats(nl, tl)
for c in [5.0, 7.5, 10.0]:
    nc, tc = backtest_hourly(w, hret, c); rows[f"cost {c}bp/side"] = stats(nc, tc)
# adverse fill: assume we always transact 2bp worse than the bar close on every trade
n_adv = w*hret - turn*(COST+2.0)/1e4; rows["cost 3bp + 2bp slippage"] = stats(n_adv, turn)
print(pd.DataFrame(rows).T.round(2).to_string())

# ---------------- 3. WALK-FORWARD (parameters chosen ONLY on past data)
print("\n=== 3. strict walk-forward: re-select (thr,b) each year on prior data only ===")
grid = [(t,b) for t in [0.0,-0.005,-0.010,-0.015,-0.020] for b in [0.25,0.5,0.75,1.0]]
cache = {}
for g in grid:
    ww, PP = build_signals(H, **{**SPEC, "gate_thr": g[0], "b": g[1]})
    cache[g] = backtest_hourly(ww, PP["hret"], COST)[0]
wf = []
years = list(range(2020, 2027))
for y in years:
    tr_end = f"{y-1}-12-31"
    best, bs = None, -9
    for g, r in cache.items():
        s = r.loc[:tr_end]
        if len(s) < 24*365: continue
        v = s.mean()/s.std()*np.sqrt(HANN)
        if v > bs: bs, best = v, g
    seg = cache[best].loc[str(y)]
    if len(seg) > 24*60:
        wf.append({"year": y, "chosen_thr": best[0], "chosen_b": best[1],
                   "train_SR": bs, "test_SR": seg.mean()/seg.std()*np.sqrt(HANN),
                   "test_ret%": ((1+seg).cumprod().iloc[-1]-1)*100})
WF = pd.DataFrame(wf); print(WF.round(2).to_string(index=False))
wf_net = pd.concat([cache[(r.chosen_thr, r.chosen_b)].loc[str(int(r.year))] for _, r in WF.iterrows()])
print("\nSTITCHED WALK-FORWARD (2020-2026, params never see the future):")
print(stats(wf_net, label="walk-forward").round(3).to_string())

# ---------------- 4. DEFLATED SHARPE + BOOTSTRAP
print("\n=== 4. statistical significance ===")
sr_ann = net.mean()/net.std()*np.sqrt(HANN)
n_obs = len(net)
N_TRIALS = 400          # honest count of specs examined across this whole study
dsr = deflated_sharpe(sr_ann, n_obs, N_TRIALS, skew=net.skew(), kurt=net.kurtosis()+3, ann=HANN)
print(f"  annualised Sharpe        : {sr_ann:.3f}")
print(f"  Newey-West t (21d lags)  : {newey_west_t(net.values, lags=24*21):.2f}")
print(f"  Deflated Sharpe (P[SR>0]) after {N_TRIALS} trials: {dsr:.4f}")
rng = np.random.default_rng(7)
dn = pd.Series(net).resample("1D").sum().values           # daily blocks
bs = []
BL = 21
for _ in range(4000):
    idx = rng.integers(0, len(dn)-BL, size=int(np.ceil(len(dn)/BL)))
    samp = np.concatenate([dn[i:i+BL] for i in idx])[:len(dn)]
    bs.append(samp.mean()/samp.std()*np.sqrt(365))
bs = np.array(bs)
print(f"  stationary-block bootstrap (21d blocks, 4000 reps): "
      f"mean SR={bs.mean():.2f}, 5-95% CI=[{np.percentile(bs,5):.2f}, {np.percentile(bs,95):.2f}], "
      f"P(SR<=0)={np.mean(bs<=0):.4f}, P(SR<1)={np.mean(bs<1):.3f}")
