"""Screen 2 on the a-priori spec (resid_MS_12_1_t, beta-hedged): risk management and holding.
  * vol-managed (Barroso & Santa-Clara 2015): scale the book by target / trailing 126d realised
    vol of its own unscaled daily returns (known at t), cap 2x;
  * 2- and 3-month overlapping tranches;
  * quintile vs linear;
  * correlation with the quality-value-composite blend and an equal-risk combination
    (weights from IS vol only)."""
import os, sys, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from common import *
from panel import load_panel

P = load_panel()
close = P["close"]; dates = close.index
ret = close.pct_change(fill_method=None)
mem = P["member"]; sec = sector_map(P)
sig = pickle.load(open("/tmp/rm_sig.pkl", "rb"))["resid_MS_12_1_t"]
M = ret.where(mem).mean(axis=1)
beta = ret.rolling(252, min_periods=200).cov(M).div(M.rolling(252, min_periods=200).var(), axis=0)
mw = mem.astype(float); mw = mw.div(mw.sum(axis=1), axis=0)
rebal = month_ends(dates); rebal = rebal[rebal >= "2010-12-31"]
mask = mem & sig.notna()
z = sector_z(sig, sec, mask)


def hedge(w):
    bw = (w * beta.reindex_like(w).fillna(1.0)).sum(axis=1)
    return w - mw.loc[w.index].mul(bw, axis=0)


def gross_ret(w):
    return (w.shift(1) * ret.loc[w.index].fillna(0)).sum(axis=1)


rows = []; NET = {}
for kind in ("quintile", "linear"):
    w0 = hold_monthly(book_weights(z, mask, kind=kind), rebal).loc["2011-01-01":]
    for tr in (1, 2, 3):
        w = w0 if tr == 1 else w0.rolling(21 * tr, min_periods=1).mean()
        w = hedge(w)
        for vm in (False, True):
            ww = w
            if vm:
                g = gross_ret(w)
                rv = g.rolling(126, min_periods=60).std() * np.sqrt(252)
                target = rv.loc[:"2017"].mean()           # IS-average vol as the target
                sc = (target / rv).clip(upper=2.0).shift(0).fillna(1.0)
                # rebalance the scale monthly only (turnover)
                sc = sc.reindex(rebal).reindex(w.index).ffill().fillna(1.0)
                ww = w.mul(sc, axis=0)
            net, st = xs_backtest(ww, ret.loc["2011-01-01":], cost_bps=5.0)
            r = splits_row(net, st); r.update({"kind": kind, "tranche_m": tr, "volman": vm, "avg_gross": st["AvgGross"]})
            rows.append(r); NET[(kind, tr, vm)] = net
d = pd.DataFrame(rows).set_index(["kind", "tranche_m", "volman"])
pd.set_option("display.width", 200)
print(d.round(3).to_string())
d.round(4).to_csv(os.path.join(HERE, "screen2_results.csv"))

qvc = pd.read_parquet(os.path.join(HERE, "..", "quality-value-composite", "nets_0_blend.parquet"))["blend"]
rm = NET[("linear", 1, False)]
J = pd.concat([rm.rename("rm"), qvc.rename("qvc")], axis=1).dropna()
print("\ncorr resid-mom vs QVC blend: full %.2f IS %.2f OOS %.2f" % (J.corr().iloc[0, 1], J.loc[:"2017"].corr().iloc[0, 1], J.loc["2018":].corr().iloc[0, 1]))
iv = 1 / J.loc[:"2017"].std(); wts = iv / iv.sum()
comb = (J * wts).sum(axis=1)
print("equal-risk combo weights", wts.round(3).to_dict(), splits_row(comb))
pd.DataFrame(NET).to_parquet(os.path.join(HERE, "nets_0_screen2.parquet")) if False else None
rm.to_frame("rm").to_parquet(os.path.join(HERE, "nets_0_rm_linear_bh.parquet"))
