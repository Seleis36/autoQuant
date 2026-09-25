"""Rapach-Strauss-Tu-Zhou (2019)-style cross-industry + cross-asset predictive model, walk-forward.

Features at close t (vol-standardised): past-k (k = 1, 5, 21) beta-residual returns of all
11 sectors, SPY, oil, copper, gold, natgas, dollar (lagged one extra day: those markets do not
close at 16:00 ET), 10y yield change and curve-slope change (also lagged one day).
Target: next-h-day beta-residual return of each sector (h in {1, 5, 21}).
Model: one ridge regression per sector, re-fit at every month end on all data up to t-h
(expanding, min 3 years; or rolling 5 years), penalty lambda in a fixed small set.
Forecasts are only ever produced out of sample. Book: linear cross-sectional weights on the
forecast, h-day tranches, SPY hedge to beta 0, 2 bp/side.
"""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

c = data.load_panel()
S = data.SECTORS
r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126)
resid = r[S] - beta.shift(1).mul(spy, axis=0)
mask = data.universe_mask(c[S])

def px(t):
    return data.load_ohlcv(t)["Close"].reindex(c.index).ffill(limit=3)
ext = {}
for t, nm in [("CL=F", "oil"), ("HG=F", "copper"), ("GC=F", "gold"), ("NG=F", "natgas"), ("DX-Y.NYB", "dollar")]:
    x = np.log(px(t)).diff(); ext[nm] = x.where(x.abs() < 0.25).shift(1)
ext["y10"] = px("^TNX").diff().shift(1)
ext["slope"] = (px("^TNX") - px("^IRX")).diff().shift(1)
base = pd.concat([resid.add_prefix("s_"), spy.rename("spy"), pd.DataFrame(ext)], axis=1)
base = base.loc["2000-09-01":]           # futures start 2000-08
feats = {}
for k in [1, 5, 21]:
    x = base.rolling(k).sum()
    sd = base.rolling(252, min_periods=126).std() * np.sqrt(k)
    feats.update({f"{col}_k{k}": (x[col] / sd[col]).clip(-4, 4) for col in base.columns})
X = pd.DataFrame(feats).fillna(0.0)      # missing sector (pre-listing) -> neutral 0
me = X.index.to_series().groupby(X.index.to_period("M")).transform("max") == X.index.to_series()
refit_days = X.index[me.values]

def ridge_forecasts(h, lam, window):
    Y = resid.loc[X.index].rolling(h).sum().shift(-h)
    F = pd.DataFrame(np.nan, index=X.index, columns=S)
    Xv = X.values
    for sec in S:
        y = Y[sec].values
        coef = None; last = None
        for i, d in enumerate(X.index):
            if d in refit_set:
                end = i - h                        # last sample whose target is fully known at d
                start = 0 if window is None else max(0, end - window)
                if end - start > 756:
                    xs = Xv[start:end]; ys = y[start:end]
                    ok = ~np.isnan(ys)
                    xs, ys = xs[ok], ys[ok]
                    if len(ys) > 500:
                        mu = xs.mean(0); sdv = xs.std(0) + 1e-9
                        Z = (xs - mu) / sdv
                        A = Z.T @ Z + lam * len(ys) * np.eye(Z.shape[1])
                        b = np.linalg.solve(A, Z.T @ (ys - ys.mean()))
                        coef = (mu, sdv, b, ys.mean())
            if coef is not None:
                mu, sdv, b, a = coef
                F.iat[i, S.index(sec)] = a + ((Xv[i] - mu) / sdv) @ b
    return F

refit_set = set(refit_days)
rows = []
out = {}
for h, lam, window in itertools.product([1, 5, 21], [0.1, 1.0, 10.0], [None, 1260]):
    F = ridge_forecasts(h, lam, window)
    s_ = F.where(mask.loc[F.index]); s_ = s_.sub(s_.mean(axis=1), axis=0)
    w = s_.div(s_.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    w = sx.tranche(w, h)
    W = w.reindex(c.index).fillna(0); W["SPY"] = -(W[S] * beta.fillna(1)).sum(axis=1)
    name = f"h{h}|lam{lam}|win{window}"
    st, net = sx.summary(W, c, name=name)
    st0, _ = sx.summary(W, c, name=name, cost_bps=0)
    st["Sh0_OOS"] = st0["Sh_OOS"]
    # forecast IC
    fwd = resid.rolling(h).sum().shift(-h).loc[F.index]
    ic = F.where(mask.loc[F.index]).rank(axis=1).corrwith(fwd.where(mask.loc[F.index]).rank(axis=1), axis=1)
    st["IC_IS"] = ic.loc[:"2014"].mean(); st["IC_OOS"] = ic.loc["2015":].mean()
    rows.append(st); out[name] = net
    print(name, st[["Sh_full", "Sh_IS", "Sh_OOS", "Sh0_OOS", "IC_IS", "IC_OOS", "Turn"]].round(3).to_dict(), flush=True)
df = pd.DataFrame(rows)
df.to_csv(os.path.join(os.path.dirname(__file__), "ridge_wf.csv"))
pd.DataFrame(out).to_parquet(os.path.join(os.path.dirname(__file__), "ridge_wf_returns.parquet"))
