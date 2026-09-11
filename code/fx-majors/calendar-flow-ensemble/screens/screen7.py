import sys; sys.path.insert(0, sys.argv[1]); from common import *
print("== gotobi (5,10,15,20,25,EOM) Tokyo-fix sessions: long USDJPY (short JPY) over the session bar")
sd = session.dt.day; eom = (session.dt.to_period("M") != session.shift(-1).dt.to_period("M"))
goto = (sd.isin([5,10,15,20,25]) | eom)
# if the gotobi date falls on a weekend the fix demand is on the previous business day: approximate by shifting to session on/after
nxt = goto.shift(-1).fillna(False).astype(float)
W = pd.DataFrame(0.0, index=idx, columns=r.columns); W["JPY"] = -nxt; rep("gotobi_shortJPY", W)
W = pd.DataFrame(0.0, index=idx, columns=r.columns); W["JPY"] = -(nxt - (eom.shift(-1).fillna(False)).astype(float)); rep("gotobi_ex_eom_shortJPY", W)
rep("gotobi_longUSD_basket", basket(-nxt))
print("== quarter-end dollar funding: long USD basket over last k sessions of quarter")
sq = session.dt.to_period("Q"); q_from_end = session.groupby(sq).cumcount(ascending=False)
for k in [3,5,10]:
    g = (q_from_end.shift(-1) < k).astype(float); rep(f"longUSD_last{k}_of_quarter", basket(-g))
    g = (q_from_end.shift(-1) < k).astype(float); rep(f"shortUSD_last{k}_of_quarter", basket(g))
sy = session.dt.year; y_from_end = session.groupby(sy).cumcount(ascending=False)
for k in [5,10]:
    g = (y_from_end.shift(-1) < k).astype(float); rep(f"shortUSD_last{k}_of_year", basket(g))
print("== post-NFP reversal: fade the NFP-session basket move on the following session")
sess_dow = session.dt.dayofweek
nfp_row = ((sess_dow == 4) & (session.dt.day <= 7))   # row whose bar is the NFP session
bask = r.mean(axis=1)
sig = (-np.sign(bask)).where(nfp_row, 0.0)   # at row of NFP session (known at its close), fade next bar
rep("fade_NFP_session", basket(sig)); rep("follow_NFP_session", basket(-sig))
print("== after-hours (20:00->00:00 UTC) lead-lag via ETF vs spot")
etf = load_closes(["FXE","FXB","FXY","FXA","FXC","FXF"])
m = {"EUR":"FXE","GBP":"FXB","JPY":"FXY","AUD":"FXA","CAD":"FXC","CHF":"FXF"}
etfL = etf.reindex(idx.union(etf.index)).ffill().shift(1).reindex(idx)   # ETF close of session D-1 (20:00 UTC) for row D (00:00 UTC D)
ah = pd.DataFrame(index=idx)
for c,e in m.items():
    ah[c] = r[c] - np.log(etfL[e]).diff()     # today's after-hours minus yesterday's
for L in [1, 3]:
    s = np.sign(ah.rolling(L).sum()); W = pd.DataFrame(0.0, index=idx, columns=r.columns)
    for c in m: W[c] = s[c]/6
    rep(f"afterhours_follow{L}", W); rep(f"afterhours_fade{L}", -W)
print("== ridge XS with EWMA-smoothed predictions to cut turnover")
from numpy.linalg import solve
mac = macro_lagged(["SPY","^VIX","^TNX","GLD","USO","DX-Y.NYB","HYG","TLT"])
feats = {}
for L in [1,2,3,5,10,21,63]:
    for c in r.columns: feats[f"{c}_r{L}"] = lp[c].diff(L)
    for t in ["SPY","GLD","USO","DX-Y.NYB","HYG","TLT"]: feats[f"{t}_r{L}"] = np.log(mac[t]).diff(L)
    feats[f"VIX_d{L}"] = np.log(mac["^VIX"]).diff(L); feats[f"TNX_d{L}"] = mac["^TNX"].diff(L)
X = pd.DataFrame(feats).replace([np.inf,-np.inf], np.nan); X = X.div(X.rolling(252, min_periods=60).std()).clip(-4,4).fillna(0)
Y = r.shift(-1); vol = r.ewm(halflife=20).std(); years = sorted(set(idx.year))
lam = 100.0
P = pd.DataFrame(np.nan, index=idx, columns=r.columns)
for y in years:
    if y < 2013: continue
    tr = (idx.year >= y-3) & (idx.year < y); te = idx.year == y; Xtr = X[tr].values; n = Xtr.shape[1]
    for c in r.columns:
        ytr = (Y[c][tr] / vol[c][tr]).fillna(0).values
        beta = solve(Xtr.T@Xtr + lam*np.eye(n), Xtr.T@ytr); P.loc[te, c] = X[te].values @ beta
for hl in [2, 5, 10]:
    Ps = P.ewm(halflife=hl).mean(); Wx = Ps.sub(Ps.mean(axis=1), axis=0); Wx = Wx.div(Wx.abs().sum(axis=1), axis=0).fillna(0)
    rep(f"ridge_XS_smooth{hl}", Wx)
    Wt = (Ps/Ps.rolling(252,min_periods=60).std()).clip(-2,2).fillna(0)/14; rep(f"ridge_TS_smooth{hl}", Wt)
pd.DataFrame(LOG, columns=["name","Sh","gross","IS","OOS","t","turn"]).to_csv(sys.argv[1]+"/screen7.csv", index=False)
