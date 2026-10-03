"""exp02 — (1) why the slow composite stops discriminating after 2023, (2) a faster macro state
(20/60-day momentum of the same four series plus VIX) fixed a priori, (3) robustness of the one
variant that beats the trend filter in both halves (TF AND composite > 0.5): threshold, lag,
lookbacks, placebo, bootstrap of the lift."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from exp01_replicate import MACRO, macro_composite, ek, rl  # noqa: E402

pd.set_option("display.width", 260)
eth = ek.daily()["Close"]
base = ek.baselines(eth)
vol, tf = base["volBH"], base["TF_live"]
mac = macro_composite(eth.index)
START = "2018-06-01"
cols = ["Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Turn", "Expo", "rho_Full", "a_t_Full", "a_t_IS", "a_t_OOS"]

print("1. share of days with the composite above 0.5, by year (a gate that is always open gates nothing)")
on = (mac > 0.5).loc[START:]
print(on.groupby(on.index.year).mean().round(2).to_string())

print("\n2. fast macro state: k-day momentum sign of HYG, LQD, SPX (+), DXY and VIX (-); mean of the five")
FAST = {"HYG": +1, "LQD": +1, "^GSPC": +1, "DX-Y.NYB": -1, "^VIX": -1}
ctl = ek.trend_controls(eth)
w = {"TF_live": tf}
for k in (20, 60):
    parts = []
    for t, sgn in FAST.items():
        s = rl.load_series(t)["Close"]
        m = (np.sign(s / s.shift(k) - 1) * sgn > 0).astype(float).where(s.shift(k).notna())
        parts.append(m.reindex(eth.index, method="ffill"))
    fast = pd.concat(parts, axis=1).mean(axis=1)
    for h in (1, 7, 30):
        q = [ek.ic(fast, eth, h, *ek.SPLITS[s], controls=ctl) for s in ("IS", "OOS")]
        print(f"  k={k} h={h:>2}: partial IC IS {q[0]['ic']:+.3f} ({q[0]['t']:+.1f}) OOS {q[1]['ic']:+.3f} ({q[1]['t']:+.1f})")
    w[f"fast{k} x vol"] = fast * vol
    w[f"fast{k} > 0.5 x vol"] = (fast > 0.5).astype(float) * vol
    w[f"TF x fast{k}"] = tf * fast
    w[f"TF AND fast{k} > 0.5"] = tf * (fast > 0.5)
print(ek.show(ek.table(w, eth, start=START, bench_w=tf)[cols]))

print("\n3. robustness of G2 = TF_live AND composite > threshold")


def sh(w_, a=START, b=None, cost=10.0):
    n = ek.bt(w_, eth, cost_bps=cost, start=a, end=b)[0]
    return n.mean() / n.std() * np.sqrt(365)


print("threshold:")
for th in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
    g = tf * (mac > th)
    print(f"  > {th}: full {sh(g):.2f}  IS {sh(g, START, '2023-12-31'):.2f}  OOS {sh(g, '2024-01-01'):.2f}   open {(mac > th).loc[START:].mean():.2f}")
print("lag of the macro rows (days):")
for lag in (0, 1, 2, 5):
    m = macro_composite(eth.index, lag=lag)
    g = tf * (m > 0.5)
    print(f"  lag {lag}: full {sh(g):.2f}  IS {sh(g, START, '2023-12-31'):.2f}  OOS {sh(g, '2024-01-01'):.2f}")
print("lookback sets:")
for lbs in ((50,), (100,), (200,), (50, 100, 150, 200, 250), (20, 50, 100), (150, 200, 250)):
    m = macro_composite(eth.index, lbs=lbs)
    g = tf * (m > 0.5)
    print(f"  {str(lbs):28s}: full {sh(g):.2f}  IS {sh(g, START, '2023-12-31'):.2f}  OOS {sh(g, '2024-01-01'):.2f}")
print("leave one macro series out:")
for drop in MACRO:
    m = macro_composite(eth.index, macro={k: v for k, v in MACRO.items() if k != drop})
    g = tf * (m > 0.5)
    print(f"  without {drop:9s}: full {sh(g):.2f}  IS {sh(g, START, '2023-12-31'):.2f}  OOS {sh(g, '2024-01-01'):.2f}")

G2 = tf * (mac > 0.5)
nG, nT = ek.bt(G2, eth, start=START)[0], ek.bt(tf, eth, start=START)[0]
rng = np.random.default_rng(5)
st = (mac > 0.5).astype(float).loc[START:]
pl = []
for _ in range(500):
    k = int(rng.integers(120, len(st) - 120))
    u = pd.Series(np.roll(st.to_numpy(), k), index=st.index).reindex(eth.index).fillna(0.0)
    pl.append(sh(tf * u))
pl = np.array(pl)
print(f"\ncircular-shift placebo of the macro state (500 draws): G2 {sh(G2):.2f} vs mean {pl.mean():.2f} sd {pl.std():.2f}, p = {np.mean(pl >= sh(G2)):.3f} (TF alone {sh(tf):.2f})")
d = pd.DataFrame({"g": nG, "t": nT}).to_numpy()
n, blk, diffs, diffs_oos = len(d), 21, [], []
for _ in range(2000):
    ix = np.concatenate([np.arange(s, s + blk) % n for s in rng.integers(0, n, n // blk + 1)])[:n]
    x = d[ix]
    diffs.append((x[:, 0].mean() / x[:, 0].std() - x[:, 1].mean() / x[:, 1].std()) * np.sqrt(365))
diffs = np.array(diffs)
print(f"block bootstrap Sharpe(G2) - Sharpe(TF): median {np.median(diffs):+.2f}, 5-95% [{np.percentile(diffs, 5):+.2f}, {np.percentile(diffs, 95):+.2f}], P(>0) {np.mean(diffs > 0):.2f}")
days_off = ((mac <= 0.5) & (tf > 0)).loc[START:]
print(f"days on which the gate actually removes a trend-filter position: {int(days_off.sum())} ({days_off.mean():.1%}); by year:")
print(days_off.groupby(days_off.index.year).sum().to_string())
r1 = eth.pct_change().shift(-1)
x = r1[days_off.reindex(r1.index).fillna(False)]
for k, (a, b) in ek.SPLITS.items():
    xx = x.loc[max(a, START):b].dropna()
    print(f"  {k}: next-day return on removed days {xx.mean() * 1e4:+.0f} bp (t {xx.mean() / xx.std() * np.sqrt(len(xx)):+.1f}, n {len(xx)})")
