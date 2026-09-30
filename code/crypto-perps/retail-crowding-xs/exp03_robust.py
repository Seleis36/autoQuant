"""exp03 — is the raw-ratio book just 'majors beat alts in 2022-26'? Robustness grid.

A. Benchmarks for the static tilt: long BTC+ETH / short EW rest of the universe (beta-neutral);
   and a book frozen on the IS coin means (from exp02).
B. The signal inside alts only (BTC, ETH, BNB, TRX removed from the universe) - if the edge is
   a majors tilt it dies here.
C. Yearly Sharpe, cost 5/20/30 bp, +1 day lag, q 0.2/0.5, linear weights, top-15/30 universe.
D. Blend with the within-coin (x - expanding mean) component.
"""
import numpy as np
import pandas as pd

from common import (load, btc_beta, beta_neutral, quantile_ls, linear_ls, tranche, evaluate,
                    IS, OOS)
import research_lib as rl

close, vol, met, mask = load()
beta = btc_beta(close)
x = np.log(met["count_long_short_ratio"])
rows = []


def run(sig, name, m=mask, h=7, cost=10.0, lag=0, weight="q30"):
    if weight == "lin":
        w = linear_ls(sig, m)
    else:
        w = quantile_ls(sig, m, q=float(weight[1:]) / 100)
    w = tranche(beta_neutral(w, beta), h)
    if lag:
        w = w.shift(lag).fillna(0.0)
    net, row = evaluate(w, close, name, cost=cost)
    rows.append(row)
    return net


base = run(-x, "base -raw q30 h7")
# A. static majors-vs-alts benchmark
maj = pd.DataFrame(False, index=close.index, columns=close.columns)
maj[["BTC-USD", "ETH-USD"]] = True
w = pd.DataFrame(0.0, index=close.index, columns=close.columns)
alts = mask & ~maj
w[["BTC-USD", "ETH-USD"]] = 0.25
w = w.add(-0.5 * alts.astype(float).div(alts.sum(axis=1), axis=0), fill_value=0.0)
w = beta_neutral(w.where(mask | maj, 0.0), beta)
bm, row = evaluate(w, close, "BENCH long BTC+ETH / short EW alts")
rows.append(row)
# B. alts only
ex = ["BTC-USD", "ETH-USD", "BNB-USD", "TRX-USD"]
m_alt = mask.copy()
m_alt[ex] = False
alt_only = run(-x, "alts only (ex BTC,ETH,BNB,TRX)", m=m_alt)
m_alt2 = mask.copy()
m_alt2[["BTC-USD", "ETH-USD"]] = False
run(-x, "alts only (ex BTC,ETH)", m=m_alt2)
# C. robustness
for c in (5, 20, 30):
    run(-x, f"cost {c}bp", cost=c)
run(-x, "+1 day lag", lag=1)
run(-x, "q20", weight="q20")
run(-x, "q50", weight="q50")
run(-x, "linear rank", weight="lin")
for n in (15, 30):
    close_n, vol_n, met_n, mask_n = load(n_top=n, refresh=True)
    run(-np.log(met_n["count_long_short_ratio"]), f"top-{n} universe", m=mask_n)
load(refresh=True)  # restore the top-20 cache
# D. blend level + within
within = x - x.expanding(min_periods=60).mean()
r_lvl = (-x).where(mask).rank(axis=1, pct=True)
r_win = (-within).where(mask).rank(axis=1, pct=True)
run(r_lvl + r_win, "blend rank(level)+rank(within)")
run(r_lvl + 0.5 * r_win, "blend rank(level)+0.5 rank(within)")

pd.set_option("display.width", 220)
res = pd.DataFrame(rows)
print(res.round(2).to_string(index=False))
res.to_csv("exp03_results.csv", index=False)
print("corr(base, bench) daily:", round(base.corr(bm.reindex(base.index)), 2),
      " corr(base, alts-only):", round(base.corr(alt_only), 2))
yr = pd.DataFrame({"base": base, "alts_only": alt_only, "bench": bm.reindex(base.index)}).loc[IS[0]:]
print(yr.groupby(yr.index.year).apply(lambda g: g.mean() / g.std() * np.sqrt(365)).round(2).to_string())
print(yr.groupby(yr.index.year).sum().round(3).to_string())
