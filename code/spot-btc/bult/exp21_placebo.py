"""Exp 21 - Placebo / integrity tests. A real effect must FAIL these mirrors."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import *
from strategy import *
pd.set_option("display.width", 240)

H = load_hourly(); SPEC = dict(vol_target=0.35, vol_hl=20, gate_thr=-0.010, b=0.5); COST = 3.0
w, P = build_signals(H, **SPEC); hret = P["hret"]
net, turn = backtest_hourly(w, hret, COST)
real = net.mean()/net.std()*np.sqrt(HANN)
print(f"REAL strategy Sharpe: {real:.3f}\n")

# 1) placebo windows: every other 3-hour window
print("=== 1. placebo: same strategy, every other 3h window ===")
rows = []
for st in range(24):
    win = tuple((st+i) % 24 for i in range(3))
    ww, PP = build_signals(H, **SPEC, window=win)
    nn, _ = backtest_hourly(ww, PP["hret"], COST)
    o = nn.loc["2022-01-01":]
    rows.append({"start_hr": st, "SR": nn.mean()/nn.std()*np.sqrt(HANN),
                 "SR_OOS": o.mean()/o.std()*np.sqrt(HANN)})
R = pd.DataFrame(rows).sort_values("SR", ascending=False)
print(R.round(2).to_string(index=False))
print(f"\n  chosen window (20) rank: {list(R.start_hr).index(20)+1} of 24 by full Sharpe, "
      f"{list(R.sort_values('SR_OOS',ascending=False).start_hr).index(20)+1} of 24 by OOS")
print(f"  median placebo Sharpe: {R.SR.median():.3f}  vs real {real:.3f}")

# 2) shuffled gate: keep the window, randomise WHICH days are gated (same count)
print("\n=== 2. placebo: window kept, gate days randomly reassigned (200 draws) ===")
hh = pd.DatetimeIndex(hret.index).hour; hday = pd.DatetimeIndex(hret.index).normalize()
in_win = np.isin(hh, [20,21,22])
gate_days = P["gate"].groupby(hday).max()
n_on = int(gate_days.sum()); all_days = gate_days.index
rng = np.random.default_rng(0); sims = []
for _ in range(200):
    on = pd.Series(0.0, index=all_days); on.loc[rng.choice(all_days, n_on, replace=False)] = 1.0
    g = pd.Series(in_win * on.reindex(hday).values, index=hret.index)
    ww = (P["base"] + 0.5*g).clip(0,1)
    nn, _ = backtest_hourly(ww, hret, COST)
    sims.append(nn.mean()/nn.std()*np.sqrt(HANN))
sims = np.array(sims)
print(f"  random-gate Sharpe: mean {sims.mean():.3f}, 95th pct {np.percentile(sims,95):.3f}, max {sims.max():.3f}")
print(f"  real {real:.3f}  ->  empirical p-value = {np.mean(sims >= real):.4f}")

# 3) sign-flip: gate on pre > +1% instead of < -1% (mirror image)
print("\n=== 3. mirror: gate on pre > +1% (should be much weaker) ===")
pre_h = P["pre"]
g = pd.Series((in_win & (pre_h.values > 0.010)).astype(float), index=hret.index)
nn, _ = backtest_hourly((P["base"] + 0.5*g).clip(0,1), hret, COST)
o = nn.loc["2022-01-01":]
print(f"  mirrored gate Sharpe: {nn.mean()/nn.std()*np.sqrt(HANN):.3f} (OOS {o.mean()/o.std()*np.sqrt(HANN):.3f})"
      f"   vs real {real:.3f}")

# 4) lookahead probe: deliberately leak 1 bar of future. MUST improve; if it doesn't, alignment is wrong.
print("\n=== 4. lookahead probe (deliberate leak; must IMPROVE if alignment is correct) ===")
for k in [-2, -1, 0, 1, 2]:
    nn, _ = backtest_hourly(w.shift(k).fillna(0.0), hret, COST)
    tag = "LEAK (future)" if k < 0 else ("as specified" if k == 0 else "extra lag")
    print(f"  shift {k:+d} bars: Sharpe {nn.mean()/nn.std()*np.sqrt(HANN):6.3f}   {tag}")

# 5) randomised returns: strategy on shuffled returns must give ~0
print("\n=== 5. strategy applied to block-shuffled returns (must be ~0) ===")
sims = []
for s in range(100):
    r2 = pd.Series(rng.permutation(hret.values), index=hret.index)
    nn, _ = backtest_hourly(w, r2, COST)
    sims.append(nn.mean()/nn.std()*np.sqrt(HANN))
sims = np.array(sims)
print(f"  shuffled-return Sharpe: mean {sims.mean():.3f}  sd {sims.std():.3f}  max {sims.max():.3f}  (real {real:.3f})")
