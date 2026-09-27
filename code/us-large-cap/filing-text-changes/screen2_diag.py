"""Is text similarity a new signal or a proxy? (a) average cross-sectional rank correlation of
jac|all with the quality-value-composite signals; (b) spanning regression of the text book's
daily net returns on the QVC blend and residual momentum, IS and OOS; (c) the text book's
returns after removing size/low-vol exposure (double-sort style: sector-neutral z of the
text signal residualised cross-sectionally on size, lowvol, roa, gpa each month)."""
import os, sys, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from common import sector_map, sector_z, book_weights, hold_monthly, splits_row, month_ends
from xs_lib import xs_backtest

Sq, P, aux = pickle.load(open("/tmp/qvc_signals.pkl", "rb"))
Z = pickle.load(open("/tmp/qvc_Z.pkl", "rb"))
T = pickle.load(open("/tmp/lp_sig.pkl", "rb"))["jac|all"]
close = P["close"]; dates = close.index
ret = close.pct_change(fill_method=None); mem = P["member"]; sec = sector_map(P)
rebal = month_ends(dates); rebal = rebal[rebal >= "2010-12-31"]
mask = mem & close.notna() & T.notna()
zt = sector_z(T, sec, mask)
cor = {}
for k, z in Z.items():
    cc = []
    for d in rebal[::3]:
        x = zt.loc[d]; y = z.loc[d]; m = x.notna() & y.notna()
        if m.sum() > 50:
            cc.append(x[m].rank().corr(y[m].rank()))
    cor[k] = np.mean(cc)
print("rank corr of text similarity with QVC signals:", {k: round(v, 2) for k, v in sorted(cor.items(), key=lambda x: -abs(x[1]))})

# residualise the text z on size, lowvol, roa, gpa, lev each rebalance date (cross-sectional OLS)
ctrl = ["size", "lowvol", "roa", "gpa", "lev"]
zr = pd.DataFrame(np.nan, index=rebal, columns=close.columns)
for d in rebal:
    y = zt.loc[d]; X = pd.concat([Z[c].loc[d] for c in ctrl], axis=1).fillna(0.0)
    m = y.notna()
    if m.sum() < 100:
        continue
    A = np.c_[np.ones(m.sum()), X[m].values]
    b = np.linalg.lstsq(A, y[m].values, rcond=None)[0]
    zr.loc[d, m[m].index] = y[m].values - A @ b
zr = zr.reindex(dates)
M = ret.where(mem).mean(axis=1)
beta = ret.rolling(252, min_periods=200).cov(M).div(M.rolling(252, min_periods=200).var(), axis=0)
mw = mem.astype(float); mw = mw.div(mw.sum(axis=1), axis=0)
out = {}
for name, z in {"text raw": zt, "text resid(size,lowvol,roa,gpa,lev)": zr}.items():
    m_ = mask & z.notna()
    w = hold_monthly(book_weights(z, m_, kind="quintile"), rebal).loc["2011-01-01":]
    bw = (w * beta.reindex_like(w).fillna(1.0)).sum(axis=1)
    w = w - mw.loc[w.index].mul(bw, axis=0)
    net, st = xs_backtest(w, ret.loc["2011-01-01":], cost_bps=5.0)
    out[name] = net
    print(name, {k: round(v, 3) for k, v in splits_row(net, st).items()})

pd.DataFrame({"text_raw": out["text raw"], "text_resid": out["text resid(size,lowvol,roa,gpa,lev)"]}).to_parquet(
    os.path.join(HERE, "nets_0_text.parquet"))
qvc = pd.read_parquet(os.path.join(HERE, "..", "quality-value-composite", "nets_0_blend.parquet"))["blend"]
rm = pd.read_parquet(os.path.join(HERE, "..", "residual-momentum", "nets_0_rm_linear_bh.parquet"))["rm"]
for name, y in out.items():
    J = pd.concat([y.rename("y"), qvc.rename("qvc"), rm.rename("rm")], axis=1).dropna()
    print(f"\n{name}: corr", J.corr().round(2).loc["y"].to_dict())
    for per, (a, b) in {"FULL": ("2011", "2026"), "IS": ("2011", "2017"), "OOS": ("2018", "2026")}.items():
        j = J.loc[a:b]; A = np.c_[np.ones(len(j)), j[["qvc", "rm"]].values]
        coef, res, *_ = np.linalg.lstsq(A, j.y.values, rcond=None)
        e = j.y.values - A @ coef
        print(f"  {per}: alpha ann {coef[0]*252:.4f}  resid Sharpe {(coef[0] + e).mean() / e.std() * np.sqrt(252):.2f}  betas {coef[1:].round(2)}")
