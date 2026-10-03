"""exp04 — robustness and re-framings.

1. ETH own-ratio family (3 ratios x 4 normalisations): is the exp01 failure an artefact of the
   expanding rank on a short, drifting history?
2. Market-wide crowd composite (mean expanding rank over 7 majors) vs the BTC crowd alone.
3. A (ETH px x BTC crowd) and C1 (TF AND BTC-uncrowded): circular-shift placebo, +-1 day lag,
   snapshot cutoff, truncation test, costs.
4. Place in the ETH book: daily P&L of the live hourly eth-venue-premium sleeve, blends.
"""
import importlib.util
import os

import numpy as np
import pandas as pd

import common as c
from common import ek

pd.set_option("display.width", 250)
eth, btc = c.closes()
me, mb = c.metrics("ETHUSDT"), c.metrics("BTCUSDT")
tw, er = c.btc_spec.target_weight, c.btc_spec.expanding_rank
base = ek.baselines(eth)
vol, tf = base["volBH"], base["TF_live"]
cols = ["Sh_Full", "Sh_IS", "Sh_OOS", "MDD", "Turn", "Expo", "rho_Full", "a_t_Full", "a_t_IS", "a_t_OOS"]


def z(x, n):
    return (x - x.rolling(n).mean()) / x.rolling(n).std()


# ---------------------------------------------------------------- 1. ETH own-ratio family
print("1. ETH own-ratio family, standalone x vol, 2022-06+ (IS<=2023 / OOS 2024+)")
fam = {}
for k, col in c.RATIOS.items():
    lv = c.daily_level(me[col], eth.index)
    states = {"exprank<.5": er(lv, 180) < 0.5,
              "rank365<.5": lv.rolling(365, min_periods=180).rank(pct=True) < 0.5,
              "z90<0": z(lv, 90) < 0, "z180<0": z(lv, 180) < 0}
    for n, s in states.items():
        fam[f"{k} {n}"] = s.astype(float) * vol
        fam[f"{k} {n} AND TF"] = s.astype(float) * tf
t = ek.table(fam, eth, start=c.EVAL_START, splits=c.SPLITS, bench_w=tf)
print(ek.show(t[cols]))
ref = ek.table({"volBH": vol, "TF_live": tf}, eth, start=c.EVAL_START, splits=c.SPLITS)
print(ek.show(ref[["Sh_Full", "Sh_IS", "Sh_OOS", "MDD"]]))
sa = t[~t.index.str.contains("AND TF")]
ga = t[t.index.str.contains("AND TF")]
print(f"standalone median full/IS/OOS {sa.Sh_Full.median():.2f}/{sa.Sh_IS.median():.2f}/{sa.Sh_OOS.median():.2f}; "
      f"gate-on-TF median {ga.Sh_Full.median():.2f}/{ga.Sh_IS.median():.2f}/{ga.Sh_OOS.median():.2f}")

# ---------------------------------------------------------------- 2. market-wide composite
print("\n2. market-wide crowd composite vs BTC crowd alone, 2022-06+")
MAJ = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"]
ranks = {}
for s in MAJ:
    m = c.metrics(s).loc["2021-12-01":]
    ranks[s] = er(c.daily_level(m["count_long_short_ratio"], eth.index), 180)
R = pd.DataFrame(ranks)
comp = {
    "BTC crowd (rank from 2021-12)": (R["BTCUSDT"] < 0.5),
    "ETH crowd": (R["ETHUSDT"] < 0.5),
    "mean rank BTC+ETH": (R[["BTCUSDT", "ETHUSDT"]].mean(axis=1) < 0.5),
    "mean rank 7 majors": (R.mean(axis=1) < 0.5),
    "median rank 7 majors": (R.median(axis=1) < 0.5),
    "mean rank 5 alts (ex BTC, ETH)": (R.drop(columns=["BTCUSDT", "ETHUSDT"]).mean(axis=1) < 0.5),
}
w2 = {}
for k, s in comp.items():
    s = s.astype(float).where(R.notna().all(axis=1), 0.0)
    w2[k] = s * vol
    w2[k + " AND TF"] = s * tf
print(ek.show(ek.table(w2, eth, start=c.EVAL_START, splits=c.SPLITS, bench_w=tf)[cols]))
print("rank correlations:"); print(R.loc[c.EVAL_START:].corr().round(2).to_string())

# ---------------------------------------------------------------- 3. validation of A and C1
START = "2021-03-01"
SP = {"Full": (START, None), "IS": (START, "2023-12-31"), "OOS": ("2024-01-01", None)}
lvl_b = c.daily_level(mb["count_long_short_ratio"], eth.index)
rb = er(lvl_b, 180)
unc = (rb < 0.5).astype(float).where(rb.notna(), 0.0)
A, C1 = unc * vol, unc * tf


def sh(w, a=START, b=None, cost=10.0):
    n = ek.bt(w, eth, cost_bps=cost, start=a, end=b)[0]
    return n.mean() / n.std() * np.sqrt(365)


print("\n3. validation (window 2021-03+)")
print("lag of the crowd state (days; negative = illegal peek):")
for L in (-1, 0, 1, 2, 3):
    print(f"  lag {L:+d}: A {sh(unc.shift(L).fillna(0) * vol):.2f}   C1 {sh(unc.shift(L).fillna(0) * tf):.2f}")
print("snapshot cutoff (hours before the 00:00 UTC close):")
for h in (0, 1, 2, 6):
    r = er(c.daily_level(mb["count_long_short_ratio"], eth.index, cutoff_hours=h), 180)
    u = (r < 0.5).astype(float).where(r.notna(), 0.0)
    print(f"  {h} h: A {sh(u * vol):.2f}   C1 {sh(u * tf):.2f}")
print("threshold on the expanding rank:")
for th in (0.3, 0.4, 0.5, 0.6, 0.7):
    u = (rb < th).astype(float).where(rb.notna(), 0.0)
    print(f"  rank < {th}: A {sh(u * vol):.2f} / OOS {sh(u * vol, '2024-01-01'):.2f}   C1 {sh(u * tf):.2f} / OOS {sh(u * tf, '2024-01-01'):.2f}   on {u.loc[START:].mean():.2f}")
print("costs (bp/side):")
for cst in (0, 5, 10, 20, 30):
    print(f"  {cst:>2}: A {sh(A, cost=cst):.2f}   C1 {sh(C1, cost=cst):.2f}   TF {sh(tf, cost=cst):.2f}")

# truncation: recompute on data cut at three dates and compare with the full run
for cut in ("2022-06-30", "2024-03-15", "2025-11-01"):
    e2, m2 = eth.loc[:cut], mb.loc[:pd.Timestamp(cut) + pd.Timedelta(hours=23)]
    r2 = er(c.daily_level(m2["count_long_short_ratio"], e2.index), 180)
    u2 = (r2 < 0.5).astype(float).where(r2.notna(), 0.0)
    w2_ = u2 * ed_tf if (ed_tf := ek.ed.trend_filter_weights_daily(e2)) is not None else None
    print(f"  truncation at {cut}: max|dw| C1 = {(w2_ - C1.loc[:cut]).abs().max():.2e}")

# circular-shift placebo of the crowd state
rng = np.random.default_rng(7)
st = unc.loc[START:]
pa, pc = [], []
for _ in range(500):
    k = int(rng.integers(90, len(st) - 90))
    u = pd.Series(np.roll(st.to_numpy(), k), index=st.index).reindex(eth.index).fillna(0.0)
    pa.append(sh(u * vol)); pc.append(sh(u * tf))
pa, pc = np.array(pa), np.array(pc)
print(f"placebo (500 circular shifts >= 90 d): A {sh(A):.2f} vs mean {pa.mean():.2f} sd {pa.std():.2f} p={np.mean(pa >= sh(A)):.3f}; "
      f"C1 {sh(C1):.2f} vs mean {pc.mean():.2f} sd {pc.std():.2f} p={np.mean(pc >= sh(C1)):.3f}  (TF alone {sh(tf):.2f})")

# block bootstrap of the C1 - TF Sharpe difference
nC, nT = ek.bt(C1, eth, start=START)[0], ek.bt(tf, eth, start=START)[0]
d = pd.DataFrame({"c": nC, "t": nT})
n, blk, diffs = len(d), 21, []
for _ in range(2000):
    ix = np.concatenate([np.arange(s, s + blk) % n for s in rng.integers(0, n, n // blk + 1)])[:n]
    x = d.to_numpy()[ix]
    diffs.append(x[:, 0].mean() / x[:, 0].std() - x[:, 1].mean() / x[:, 1].std())
diffs = np.array(diffs) * np.sqrt(365)
print(f"bootstrap Sharpe(C1) - Sharpe(TF): median {np.median(diffs):+.2f}, 5-95% [{np.percentile(diffs, 5):+.2f}, {np.percentile(diffs, 95):+.2f}], P(>0) {np.mean(diffs > 0):.2f}")

# ---------------------------------------------------------------- 4. place in the ETH book
spec = importlib.util.spec_from_file_location("vp", os.path.join(c.REPO, "code", "spot-eth", "eth-venue-premium", "strategy.py"))
vp = importlib.util.module_from_spec(spec); spec.loader.exec_module(vp)
h = ek.ed.bars("ETHUSDT", "1h")["Close"]
cb = pd.read_parquet(os.path.join(c.DATA, "COINBASE_ETHUSD_1h.parquet"))["Close"]
wv = vp.target_weight(h, cb)
nv = ek.ed.to_daily(ek.ed.bt(wv, h)[0])
# hourly book of the daily crowd state: decided at 00:00, held all day
unc_h = unc.shift(1).reindex(h.index.floor("D")).set_axis(h.index).fillna(0.0)   # state decided at D 00:00 applies to hours of day D
wv_c = wv * unc_h.shift(-1).fillna(0.0)   # weights are shifted one bar by the backtest: state for hour t+1
nvc = ek.ed.to_daily(ek.ed.bt(wv_c, h)[0])
book = pd.DataFrame({"TF_live": nT, "C1": nC, "A": ek.bt(A, eth, start=START)[0],
                     "venue-premium": nv, "venue-premium AND uncrowded": nvc}).loc[START:].dropna()
book["TF + VP (50/50)"] = 0.5 * book["TF_live"] + 0.5 * book["venue-premium"]
book["C1 + VP"] = 0.5 * book["C1"] + 0.5 * book["venue-premium"]
book["TF + VP + A (thirds)"] = (book["TF_live"] + book["venue-premium"] + book["A"]) / 3
book["C1 + VPc (50/50)"] = 0.5 * book["C1"] + 0.5 * book["venue-premium AND uncrowded"]
rows = {}
for k in book:
    x = book[k]
    eq = (1 + x).cumprod()
    rows[k] = {s: x.loc[a:b].mean() / x.loc[a:b].std() * np.sqrt(365) for s, (a, b) in SP.items()}
    rows[k]["MDD"] = (eq / eq.cummax() - 1).min()
print("\n4. place in the ETH book (daily P&L, 10 bp/side)")
print(pd.DataFrame(rows).T.round(2).to_string())
print(book[["TF_live", "C1", "A", "venue-premium"]].corr().round(2).to_string())
