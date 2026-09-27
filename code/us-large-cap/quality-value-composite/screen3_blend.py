"""Screen 3: IS-only sleeve selection and equal-risk blend.

Protocol (fixed before looking at OOS): from the 40 screen-2 books, keep every book whose IS
(2011-17) net Sharpe >= 0.5, one per composite (the best IS variant), equal-risk weights
estimated on IS vol, then read OOS 2018-26. Also industry-neutral (GICS sub-industry) re-run
of the selected composites, and yearly returns."""
import os, sys, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import *
from screen2 import COMPOS, composite, beta, base, sec, rebal, ret, P, xs_backtest

res2 = pd.read_csv(os.path.join(HERE, "screen2_results.csv"))
cand = res2[res2.IS >= 0.5].sort_values("IS", ascending=False).drop_duplicates("compo")
print("IS-selected sleeves:\n", cand[["compo", "kind", "variant", "IS", "OOS"]].to_string())


def sleeve(cname, kind, variant, groups=sec):
    c = composite(COMPOS[cname]); mask = base & c.notna(); c = sector_z(c, groups, mask)
    if variant == "3m_tranche":
        w1 = book_weights(c, mask, kind="linear")
        w = hold_monthly(w1, rebal).rolling(63, min_periods=1).mean().loc["2011-01-01":]
    else:
        w = hold_monthly(book_weights(c, mask, kind=kind), rebal).loc["2011-01-01":]
    if variant == "beta_hedged":
        bw = (w * beta.reindex_like(w).fillna(1.0)).sum(axis=1)
        mw = P["member"].astype(float); mw = mw.div(mw.sum(axis=1), axis=0).loc[w.index]
        w = w - mw.mul(bw, axis=0)
    return w


W = {}; R = {}
for _, r in cand.iterrows():
    k = f"{r.compo}|{r.kind}|{r.variant}"
    W[k] = sleeve(r.compo, r.kind, r.variant)
    R[k], _ = xs_backtest(W[k], ret.loc["2011-01-01":], cost_bps=5.0, name=k)
R = pd.DataFrame(R)
print("\nsleeve return correlations (daily):\n", R.corr().round(2).to_string())
is_vol = R.loc[:"2017"].std()
wts = (1 / is_vol) / (1 / is_vol).sum()
print("\nequal-risk weights (IS vol):", wts.round(3).to_dict())
Wb = sum(W[k] * wts[k] for k in W)
net, st = xs_backtest(Wb, ret.loc["2011-01-01":], cost_bps=5.0, name="blend")
row = splits_row(net, st)
print("\nBLEND @5bp:", {k: round(v, 3) if isinstance(v, float) else v for k, v in row.items()})
# scale to 10% vol using IS vol only
lev = 0.10 / (net.loc[:"2017"].std() * np.sqrt(252))
net10, st10 = xs_backtest(Wb * lev, ret.loc["2011-01-01":], cost_bps=5.0, name="blend10")
print(f"lever x{lev:.2f} (IS vol) ->", {k: round(v, 3) if isinstance(v, float) else v for k, v in splits_row(net10, st10).items()},
      "avg gross", round(st10["AvgGross"], 2))
yr = net10.groupby(net10.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(252))
yrr = net10.groupby(net10.index.year).sum()
print(pd.DataFrame({"sharpe": yr, "ret": yrr}).round(2).T.to_string())
for c in (2.0, 10.0):
    n_c, s_c = xs_backtest(Wb * lev, ret.loc["2011-01-01":], cost_bps=c)
    print(f"cost {c}bp:", {k: round(v, 3) if isinstance(v, float) else v for k, v in splits_row(n_c, s_c).items()})

# industry-neutral variant of the same selection
cur = pd.read_csv(os.path.join(HERE, "..", "shared", "sp500_current_raw.csv"))
from universe import _yf
ind = pd.Series(cur["GICS Sub-Industry"].values, index=cur["Symbol"].map(_yf).values)
ind = ind[~ind.index.duplicated()].reindex(sec.index)
ind = ind.fillna(sec)   # past names: fall back to sector
Wi = {}
for _, r in cand.iterrows():
    k = f"{r.compo}|{r.kind}|{r.variant}"
    Wi[k] = sleeve(r.compo, r.kind, r.variant, groups=ind)
Ri = pd.DataFrame({k: xs_backtest(Wi[k], ret.loc["2011-01-01":], cost_bps=5.0)[0] for k in Wi})
print("\nindustry-neutral sleeves:")
for k in Ri:
    print(k, {kk: round(v, 3) for kk, v in splits_row(Ri[k]).items()})
net.to_frame("blend").to_parquet("/tmp/qvc_blend_net.parquet")
