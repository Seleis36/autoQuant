import sys; sys.path.insert(0, sys.argv[1]); from common import *
from fomc_dates import fomc_days
print("== month-end on SESSION calendar. Fix session = last business day L. Row stamped L+1 covers it; weight set at row L using macro <= L-1")
smon = session.dt.to_period("M")
# rows whose SESSION is the k-th last of its month
s_from_end = session.groupby(smon).cumcount(ascending=False)  # 0 => session is last bday of month
mac = macro_lagged(["SPY","EFA","EWJ","EWG","EWU","EWA","EWC","ACWI","TLT"])
mtd = {}
for t in mac.columns:
    mtd[t] = np.log(mac[t] / mac[t].groupby(smon).transform("first"))  # MTD through previous macro close
mtd = pd.DataFrame(mtd)
for hold in [[0],[0,1],[0,1,2],[1],[1,2]]:
    # we hold the bar of row t+1 when its session index is in `hold` => weight at row t when s_from_end.shift(-1) in hold
    nxt = s_from_end.shift(-1)
    gate = nxt.isin(hold).astype(float)
    rep(f"ME_spy_sess{hold}", basket(np.sign(mtd["SPY"])*gate))
    rep(f"ME_spy_scaled_sess{hold}", basket((mtd["SPY"]/0.03).clip(-1,1)*gate))
    rel = mtd["SPY"] - mtd["EFA"]
    rep(f"ME_spy-efa_sess{hold}", basket(np.sign(rel)*gate))
    # country-level: EUR<-EWG, GBP<-EWU, JPY<-EWJ, AUD<-EWA, CAD<-EWC ; CHF,NZD use EFA
    W = pd.DataFrame(0.0, index=idx, columns=r.columns)
    for c,e in {"EUR":"EWG","GBP":"EWU","JPY":"EWJ","AUD":"EWA","CAD":"EWC","CHF":"EFA","NZD":"EFA"}.items():
        W[c] = np.sign(mtd["SPY"] - mtd[e]) * gate / 7
    rep(f"ME_country_sess{hold}", W)
    # bonds too: TLT MTD
    rep(f"ME_spy+tlt_sess{hold}", basket(np.sign(mtd["SPY"]*0.6 + mtd["TLT"]*0.4)*gate))
print("== FOMC: announcement 14:00 ET on F is inside row F+1; weight at row F (macro <= F-1)")
fd = fomc_days()
tgt = pd.Series(0.0, index=idx)
for d in fd:
    p = idx.searchsorted(d)  # row stamped F (or next)
    if p < len(idx) and idx[p] == d: tgt.iloc[p] = 1.0
rep("FOMC_shortUSD_over_F+1", basket(tgt))
rep("FOMC_shortUSD_over_F", basket(tgt.shift(-1).fillna(0)))
rep("FOMC_shortUSD_over_F+2", basket(tgt.shift(1).fillna(0)))
print("== Friday session (Mon-stamped row) long USD; NFP = first Friday of month (approx)")
sess_dow = session.dt.dayofweek
nxt_is_fri = (sess_dow.shift(-1) == 4).astype(float)
rep("longUSD_friday_session", basket(-nxt_is_fri))
first_fri = ((sess_dow == 4) & (session.dt.day <= 7)).astype(float).shift(-1).fillna(0)
rep("longUSD_NFP_friday", basket(-first_fri))
rep("longUSD_nonNFP_friday", basket(-(nxt_is_fri - first_fri)))
for d in range(5):
    g = (sess_dow.shift(-1) == d).astype(float); rep(f"longUSD_session_dow{d}", basket(-g))
print("== calendar month seasonality (IS-estimated sign applied OOS: leave-one-year-out)")
smonth = session.dt.month
# leave-one-year-out mean by month -> sign
yrs = session.dt.year
sig = pd.Series(0.0, index=idx)
mm = r.mean(axis=1)
for y in yrs.unique():
    mask = yrs != y
    mbym = mm[mask].groupby(smonth[mask]).mean()
    sig[yrs == y] = smonth[yrs == y].map(np.sign(mbym)).values
rep("month_season_LOYO_basket", basket(sig.shift(-1).fillna(0)))
sigc = pd.DataFrame(0.0, index=idx, columns=r.columns)
for c in r.columns:
    for y in yrs.unique():
        mask = yrs != y; mbym = r[c][mask].groupby(smonth[mask]).mean()
        sigc.loc[yrs == y, c] = smonth[yrs == y].map(np.sign(mbym)).values
rep("month_season_LOYO_perccy", sigc.shift(-1).fillna(0)/7)
pd.DataFrame(LOG, columns=["name","Sh","gross","IS","OOS","t","turn"]).to_csv(sys.argv[1]+"/screen5.csv", index=False)
