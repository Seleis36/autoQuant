import sys; sys.path.insert(0, sys.argv[1]); from common import *
from numpy.linalg import solve
mac = macro_lagged(["SPY","^VIX","^TNX","GLD","USO","DX-Y.NYB","HYG","TLT"])
feats = {}
for L in [1,2,3,5,10,21,63]:
    for c in r.columns: feats[f"{c}_r{L}"] = lp[c].diff(L)
    for t in ["SPY","GLD","USO","DX-Y.NYB","HYG","TLT"]: feats[f"{t}_r{L}"] = np.log(mac[t]).diff(L)
    feats[f"VIX_d{L}"] = np.log(mac["^VIX"]).diff(L); feats[f"TNX_d{L}"] = mac["^TNX"].diff(L)
X = pd.DataFrame(feats).replace([np.inf,-np.inf], np.nan)
X = X.div(X.rolling(252, min_periods=60).std()).clip(-4,4).fillna(0)  # scale
Y = r.shift(-1)  # next-row return
vol = r.ewm(halflife=20).std()
years = sorted(set(idx.year))
for lam in [10.0, 100.0, 1000.0]:
    P = pd.DataFrame(np.nan, index=idx, columns=r.columns)
    for y in years:
        if y < 2013: continue
        tr = (idx.year >= y-3) & (idx.year < y); te = idx.year == y
        Xtr = X[tr].values; n = Xtr.shape[1]
        for c in r.columns:
            ytr = (Y[c][tr] / vol[c][tr]).fillna(0).values
            beta = solve(Xtr.T@Xtr + lam*np.eye(n), Xtr.T@ytr)
            P.loc[te, c] = X[te].values @ beta
    W = np.sign(P).fillna(0)/7
    rep(f"ridge_sign_lam{lam}", W)
    Ws = (P/ P.rolling(252,min_periods=60).std()).clip(-2,2).fillna(0)/14
    rep(f"ridge_scaled_lam{lam}", Ws)
    Wx = P.sub(P.mean(axis=1), axis=0); Wx = Wx.div(Wx.abs().sum(axis=1), axis=0).fillna(0)
    rep(f"ridge_XS_lam{lam}", Wx)
    # weekly hold to cut turnover
    Wk = np.sign(P).where(idx.dayofweek == 0).ffill().fillna(0)/7
    rep(f"ridge_sign_weekly_lam{lam}", Wk)
