"""Exp 15 - Better volatility forecasting from hourly data -> better vol targeting.
Daily close-to-close vol is a noisy estimator; realized vol from 24 hourly returns is
far more efficient. Test whether it improves the risk-managed daily strategy."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import *
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 60)

H = pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h.parquet"))
hclose = H["Close"]; hr = hclose.pct_change()
dclose = hclose.resample("1D").last(); dret = dclose.pct_change()
dhi = H["High"].resample("1D").max(); dlo = H["Low"].resample("1D").min()
dop = H["Open"].resample("1D").first()

# --- competing daily vol forecasts (all use only data up to the close of day t)
RV   = (hr**2).resample("1D").sum()                       # realized variance from hourly
V = {
 "cc_ewm20":   ewm_vol(dret, 20),
 "cc_roll30":  dret.rolling(30).std()*np.sqrt(365),
 "rv_ewm20":   np.sqrt(RV.ewm(halflife=20, min_periods=20).mean()*365),
 "rv_ewm10":   np.sqrt(RV.ewm(halflife=10, min_periods=10).mean()*365),
 "rv_ewm5":    np.sqrt(RV.ewm(halflife=5,  min_periods=5).mean()*365),
 "parkinson20":(np.sqrt((np.log(dhi/dlo)**2).rolling(20).mean()/(4*np.log(2)))*np.sqrt(365)),
 "har_rv":     None,
}
# HAR-RV (Corsi 2009): daily / weekly / monthly realized-vol components, expanding-window fit
rv_d = np.sqrt(RV*365); rv_w = np.sqrt(RV.rolling(7).mean()*365); rv_m = np.sqrt(RV.rolling(30).mean()*365)
X = pd.concat([rv_d, rv_w, rv_m], axis=1); X.columns = ["d","w","m"]
y = np.sqrt(RV.shift(-1)*365)
har = pd.Series(index=dclose.index, dtype=float)
Xy = pd.concat([X, y.rename("y")], axis=1).dropna()
for i in range(400, len(Xy)):                 # strictly expanding, no lookahead
    tr = Xy.iloc[:i]
    A = np.c_[np.ones(len(tr)), tr[["d","w","m"]].values]
    coef, *_ = np.linalg.lstsq(A, tr["y"].values, rcond=None)
    har.loc[Xy.index[i]] = float(np.r_[1, Xy[["d","w","m"]].iloc[i].values] @ coef)
V["har_rv"] = har

print("=== vol forecast quality: predicting NEXT-day realized vol (from hourly RV) ===")
tgt = np.sqrt(RV.shift(-1)*365)
rows = {}
for k, v in V.items():
    z = pd.concat([v.rename("f"), tgt.rename("y")], axis=1).dropna()
    z = z.loc["2018-01-01":]
    rows[k] = {"corr": z.f.corr(z.y), "rank_corr": z.f.corr(z.y, method="spearman"),
               "RMSE": np.sqrt(((z.f-z.y)**2).mean()), "QLIKE": (np.log(z.f**2)+ (z.y**2)/(z.f**2)).mean(),
               "n": len(z)}
print(pd.DataFrame(rows).T.round(4).to_string())

# --- does a better vol forecast improve the strategy?
G = lambda t: load_series(t)["Close"].reindex(dclose.index).ffill()
S_trend = pd.concat([(dclose > dclose.rolling(n).mean()).astype(float) for n in [20,50,100,150,200]], axis=1).mean(axis=1)
MAC = {"HYG": (G("HYG"),+1), "LQD": (G("LQD"),+1), "DXY": (G("DX-Y.NYB"),-1), "SPX": (G("^GSPC"),+1)}
def ens_ma(s, sign, lbs=[50,100,150,200,250]):
    m = pd.concat([(s > s.rolling(n).mean()).astype(float) for n in lbs], axis=1).mean(axis=1)
    return m if sign>0 else 1.0-m
S_macro = pd.concat([ens_ma(s,sg) for s,sg in MAC.values()], axis=1).mean(axis=1)
regime = (S_trend*S_macro).clip(0,1)

print("\n=== strategy Sharpe using each vol forecast (regime x volscalar, 10bp/side daily) ===")
rows = {}
for k, v in V.items():
    sc = (0.35/v).clip(0,1).fillna(0.0)
    net, st = backtest(regime*sc, dclose, cost_bps=10, name=k)
    rows[k] = {"CAGR%": st["CAGR"]*100, "Vol%": st["Vol"]*100, "SR": st["Sharpe"],
               "MaxDD%": st["MaxDD"]*100, "Calmar": st["Calmar"], "Turn": st["Turnover_ann"],
               "SR_IS": perf_stats(net.loc[:"2021-12-31"])["Sharpe"],
               "SR_OOS": perf_stats(net.loc["2022-01-01":])["Sharpe"],
               "SR_ETF": perf_stats(net.loc["2024-01-11":])["Sharpe"]}
rows["no vol scaling"] = (lambda n,s: {"CAGR%": s["CAGR"]*100,"Vol%": s["Vol"]*100,"SR": s["Sharpe"],
    "MaxDD%": s["MaxDD"]*100,"Calmar": s["Calmar"],"Turn": s["Turnover_ann"],
    "SR_IS": perf_stats(n.loc[:"2021-12-31"])["Sharpe"],"SR_OOS": perf_stats(n.loc["2022-01-01":])["Sharpe"],
    "SR_ETF": perf_stats(n.loc["2024-01-11":])["Sharpe"]})(*backtest(regime, dclose, cost_bps=10))
print(pd.DataFrame(rows).T.round(2).to_string())

# --- intraday crash circuit breaker: does reacting within the day help?
print("\n=== intraday drawdown circuit-breaker (uses hourly path, acts next bar) ===")
best_v = V["rv_ewm10"]
sc = (0.35/best_v).clip(0,1).fillna(0.0)
base = regime*sc
intraday_dd = (dclose/ H["Low"].resample("1D").min() ).rsub(1)   # not used directly; illustrative
rows = {}
for thr in [None, 0.06, 0.08, 0.10, 0.12]:
    if thr is None:
        w = base
    else:
        # if the worst 24h rolling move was < -thr as of yesterday's close, halve exposure for 3 days
        shock = (dclose/dclose.rolling(2).min()-1).lt(-999)     # placeholder
        worst = dret.rolling(3).min()
        flag = (worst < -thr).rolling(3).max().fillna(0)
        w = base * (1 - 0.5*flag)
    net, st = backtest(w, dclose, cost_bps=10, name=str(thr))
    rows[f"thr={thr}"] = {"SR": st["Sharpe"], "CAGR%": st["CAGR"]*100, "MaxDD%": st["MaxDD"]*100,
        "Calmar": st["Calmar"],
        "SR_IS": perf_stats(net.loc[:"2021-12-31"])["Sharpe"],
        "SR_OOS": perf_stats(net.loc["2022-01-01":])["Sharpe"]}
print(pd.DataFrame(rows).T.round(2).to_string())
