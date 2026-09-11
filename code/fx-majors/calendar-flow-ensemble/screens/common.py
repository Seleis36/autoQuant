import sys, os, numpy as np, pandas as pd
sys.path.insert(0, "code/shared"); sys.path.insert(0, "code/fx-majors/shared")
from research_lib import perf_stats
from fx_data import load_fx_usd_per_ccy, load_closes
ANN=252
fx = load_fx_usd_per_ccy().dropna(); fx = fx[fx.index >= "2010-01-04"]
r = np.log(fx).diff(); alive = r.abs().sum(axis=1) > 0; fx = fx[alive]; r = r[alive].fillna(0)
idx = r.index; lp = np.log(fx)
# session date covered by the row stamped S: previous business day (Mon row -> Fri session)
session = pd.Series(idx - pd.tseries.offsets.BDay(1), index=idx)
def bt(W, rr=None, cost_bp=2.0, name="s"):
    rr = r if rr is None else rr
    W = W.reindex(rr.index).fillna(0.0); We = W.shift(1).fillna(0.0)
    turn = (We - We.shift(1).fillna(0.0)).abs().sum(axis=1)
    gross = (We*rr).sum(axis=1); net = gross - turn*cost_bp/1e4
    st = perf_stats(net, ann=ANN, name=name); st["Turn"] = turn.sum()/(len(turn)/ANN)
    st["GrossSharpe"] = perf_stats(gross, ann=ANN)["Sharpe"]; st["Gross"] = We.abs().sum(axis=1).mean()
    return net, st
def vs(net): return {k: round(perf_stats(net.loc[a:b], ann=ANN)["Sharpe"],2) for k,(a,b) in {"IS":("2010","2019"),"OOS":("2020","2027")}.items()}
LOG=[]
def rep(name, W, cb=2.0, quiet=False):
    net, st = bt(W, r, cb, name); v = vs(net); LOG.append((name, round(st["Sharpe"],2), round(st["GrossSharpe"],2), v["IS"], v["OOS"], round(st["t_NW"],1), round(st["Turn"])))
    if not quiet: print(f"{name:44s} Sh {st['Sharpe']:5.2f} gross {st['GrossSharpe']:5.2f} IS {v['IS']:5.2f} OOS {v['OOS']:5.2f} t {st['t_NW']:4.1f} turn {st['Turn']:5.0f}")
    return net
def basket(sig): return pd.DataFrame(np.repeat(np.asarray(sig)[:,None]/7, 7, axis=1), index=idx, columns=r.columns)
def macro_lagged(tickers):
    m = load_closes(tickers)
    # row stamped D closes 00:00 UTC D; macro close stamped D-1 (21:00 UTC) precedes it => use value stamped <= D-1
    return m.reindex(idx.union(m.index)).ffill().shift(1).reindex(idx)
