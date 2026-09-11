import sys, os, numpy as np, pandas as pd
sys.path.insert(0, "code/shared"); sys.path.insert(0, "code/fx-majors/shared")
from research_lib import perf_stats
from fx_data import load_fx_usd_per_ccy, load_closes
from fomc_dates import fomc_days
ANN=252
fx = load_fx_usd_per_ccy().dropna(); fx = fx[fx.index >= "2010-01-04"]
r = np.log(fx).diff(); alive = r.abs().sum(axis=1) > 0; fx = fx[alive]; r = r[alive].fillna(0)
etf = load_closes(["FXE","FXB","FXY","FXA","FXC","FXF","UUP","SPY"])
etf_map = {"EUR":"FXE","GBP":"FXB","JPY":"FXY","AUD":"FXA","CAD":"FXC","CHF":"FXF"}
re = np.log(etf).diff()
# alignment check: corr of same-day returns, and lead/lag
for c,e in etf_map.items():
    a = r[c].reindex(re.index).dropna(); b = re[e].reindex(a.index)
    print(c, "corr same-day", round(a.corr(b),3), "fx(t) vs etf(t+1)", round(a.corr(b.shift(-1)),3), "fx(t+1) vs etf(t)", round(a.shift(-1).corr(b),3))

def bt(W, r, cost_bp=2.0, name="s"):
    W = W.reindex(r.index).fillna(0.0); We = W.shift(1).fillna(0.0)
    turn = (We - We.shift(1).fillna(0.0)).abs().sum(axis=1)
    gross = (We*r).sum(axis=1); net = gross - turn*cost_bp/1e4
    st = perf_stats(net, ann=ANN, name=name); st["Turn"] = turn.sum()/(len(turn)/ANN)
    st["GrossSharpe"] = perf_stats(gross, ann=ANN)["Sharpe"]; st["Vol"] = net.std()*np.sqrt(ANN)
    return net, st
def by_year(net): return (net.groupby(net.index.year).apply(lambda x: x.mean()/x.std()*np.sqrt(ANN))).round(2).to_dict()

# 1-day XS reversal on Yahoo FX
m = r; rk = -(m.rank(axis=1) - 4); W = rk.div(rk.abs().sum(axis=1), axis=0)
for cb in [0, 2, 5]:
    net, st = bt(W, r, cost_bp=cb, name="XSrev1"); print("XSrev1 yahoo cost", cb, "Sharpe", round(st["Sharpe"],2), "vol", round(st["Vol"],3), "turn", round(st["Turn"]))
net,_ = bt(W, r, 2); print(by_year(net))
# same signal, dollar-neutral demeaned (not rank)
dm = -(r.sub(r.mean(axis=1), axis=0)); W2 = dm.div(dm.abs().sum(axis=1), axis=0)
net, st = bt(W2, r, 2, "XSrev1_dm"); print("demeaned version", round(st["Sharpe"],2))
# time-series 1-day reversal (not dollar neutral)
W3 = -np.sign(r)/7; net, st = bt(W3, r, 2, "TSrev1"); print("TS reversal 1d", round(st["Sharpe"],2), round(st["GrossSharpe"],2))

# --- ETF cross-check: signal from ETF own returns, trade ETF (6 ccys)
re6 = re[list(etf_map.values())].dropna(); re6 = re6[re6.abs().sum(axis=1)>0]
rk = -(re6.rank(axis=1) - 3.5); W = rk.div(rk.abs().sum(axis=1), axis=0)
net, st = bt(W, re6, 2, "XSrev1_ETF"); print("XSrev1 ETF-on-ETF", round(st["Sharpe"],2), by_year(net))
# signal from yahoo FX (6 ccys), traded on ETF next-day returns
r6 = r[list(etf_map.keys())]; rk = -(r6.rank(axis=1) - 3.5); W = rk.div(rk.abs().sum(axis=1), axis=0); W.columns = list(etf_map.values())
net, st = bt(W, re6, 2, "XSrev1_FXsig_ETFtrade"); print("XSrev1 FX-signal ETF-trade", round(st["Sharpe"],2), by_year(net))
# signal from ETF, traded on yahoo FX
rk = -(re6.rank(axis=1) - 3.5); W = rk.div(rk.abs().sum(axis=1), axis=0); W.columns = list(etf_map.keys())
net, st = bt(W, r6, 2, "XSrev1_ETFsig_FXtrade"); print("XSrev1 ETF-signal FX-trade", round(st["Sharpe"],2), by_year(net))

# --- FOMC days: short USD basket over the FOMC bar. Which bar? test held over bar t=FOMC day and bar t+1.
fd = fomc_days()
idx = r.index
for lag,label in [(0,"hold over FOMC-day bar"),(1,"hold over day after"),(-1,"hold over day before")]:
    tgt = pd.Series(0.0, index=idx)
    for d in fd:
        pos = idx.searchsorted(d)  # bar index of FOMC day (or next available)
        p = pos + lag
        if 0 <= p < len(idx): tgt.iloc[p] = 1.0
    # weight set at close of previous bar
    W = pd.DataFrame(np.repeat(tgt.shift(-1).fillna(0).values[:,None]/7, 7, axis=1), index=idx, columns=r.columns)
    net, st = bt(W, r, 2, "FOMC"); print(label, "Sharpe", round(st["Sharpe"],2), "mean bp/day-in-mkt", round(net[net!=0].mean()*1e4,1), "n", int((net!=0).sum()), by_year(net))
