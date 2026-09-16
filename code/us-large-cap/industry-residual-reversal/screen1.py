"""Screen 1: which short-horizon cross-sectional signals carry an edge in S&P 500 names?
Rank IC + costed decile L/S backtest (daily rebalance, 5 bp/side), FULL/IS/OOS."""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
from panel import load_panel
from xs_lib import *

P = load_panel()
C, O, V, M = P["close"], P["open"], P["volume"], P["member"]
sec = P["sector"].fillna("UNK")
ret = C.pct_change()
logret = np.log(C).diff()
# universe: member & has price & has 60d history; sector known
hist_ok = C.notna().rolling(60).sum().ge(55)
mask = M & hist_ok & C.notna()
print("avg names/day", mask.sum(axis=1).mean())

mkt = ret.where(mask).mean(axis=1)                      # equal-weight universe return
fwd1 = ret.shift(-1)
fwd5 = (C.shift(-5) / C - 1)

def cum(n): return (C / C.shift(n) - 1)
def sector_resid(x): return group_demean(x, sec, mask)
# beta-residual (60d beta to EW market)
cov = logret.rolling(60).cov(mkt) if False else None
def beta_resid(n):
    r = logret; m = np.log1p(mkt)
    beta = r.rolling(120).cov(m).div(m.rolling(120).var(), axis=0)
    resid = r - beta.shift(1).mul(m, axis=0)
    return resid.rolling(n).sum()

on = np.log(O / C.shift(1))      # overnight log return
intra = np.log(C / O)            # intraday log return
vol20 = logret.rolling(20).std()
dvol = (C * V)
volratio = np.log(V / V.rolling(20).mean().shift(1))

signals = {
    "rev1_raw": -cum(1), "rev5_raw": -cum(5), "rev21_raw": -cum(21),
    "rev1_sec": -sector_resid(cum(1)), "rev5_sec": -sector_resid(cum(5)), "rev21_sec": -sector_resid(cum(21)),
    "rev5_beta": -beta_resid(5), "rev21_beta": -beta_resid(21),
    "rev5_sec_volscaled": -sector_resid(cum(5)).div(vol20 * np.sqrt(5)),
    "overnight5": on.rolling(5).sum(), "intraday5_rev": -intra.rolling(5).sum(),
    "overnight1": on, "intraday1_rev": -intra,
    "mom12_1": C.shift(21) / C.shift(252) - 1, "mom6_1": C.shift(21) / C.shift(126) - 1,
    "lowvol": -vol20, "lowmax5": -ret.rolling(21).max(),
    "volratio5_low": -volratio.rolling(5).mean(),
    "rev5_sec_lowvol_cond": (-sector_resid(cum(5))).where(volratio.rolling(5).mean() < 0),
    "rev5_sec_highvol_cond": (-sector_resid(cum(5))).where(volratio.rolling(5).mean() > 0),
}
rows = []
for k, s in signals.items():
    s = s.where(mask)
    ic1 = ic_series(s, fwd1, mask); ic5 = ic_series(s, fwd5, mask)
    w = decile_weights(s, mask, q=0.1)
    net, st = xs_backtest(w, ret, cost_bps=5.0, name=k)
    sp = split_perf(net, SPLITS)
    g, _ = xs_backtest(w, ret, cost_bps=0.0)
    rows.append({"signal": k, "IC1": ic1.mean(), "IC1_t": ic_summary(ic1)["IC_t"], "IC5": ic5.mean(), "IC5_t": ic_summary(ic5)["IC_t"],
                 "GrossSh": st["GrossSharpe"], "NetSh5bp": st["Sharpe"], "IS": sp.loc["IS", "Sharpe"], "OOS": sp.loc["OOS", "Sharpe"],
                 "Turn": st["Turnover_ann"], "Names": st["AvgNames"], "Vol": st["Vol"]})
    print(rows[-1], flush=True)
df = pd.DataFrame(rows).set_index("signal").round(3)
print(df.to_string())
df.to_csv(os.path.join(HERE, "screen1_results.csv"))
