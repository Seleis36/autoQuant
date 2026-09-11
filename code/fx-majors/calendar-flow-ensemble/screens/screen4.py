import sys, os, numpy as np, pandas as pd, itertools
sys.path.insert(0, "code/shared"); sys.path.insert(0, "code/fx-majors/shared")
from research_lib import perf_stats
from fx_data import load_fx_usd_per_ccy, load_closes
ANN=252
fx = load_fx_usd_per_ccy().dropna(); fx = fx[fx.index >= "2010-01-04"]
r = np.log(fx).diff(); alive = r.abs().sum(axis=1) > 0; fx = fx[alive]; r = r[alive].fillna(0)
idx = r.index; lp = np.log(fx)
def bt(W, r, cost_bp=2.0, name="s"):
    W = W.reindex(r.index).fillna(0.0); We = W.shift(1).fillna(0.0)
    turn = (We - We.shift(1).fillna(0.0)).abs().sum(axis=1)
    gross = (We*r).sum(axis=1); net = gross - turn*cost_bp/1e4
    st = perf_stats(net, ann=ANN, name=name); st["Turn"] = turn.sum()/(len(turn)/ANN)
    st["GrossSharpe"] = perf_stats(gross, ann=ANN)["Sharpe"]
    return net, st
def vs(net): return {k: round(perf_stats(net.loc[a:b], ann=ANN)["Sharpe"],2) for k,(a,b) in {"IS":("2010","2019"),"OOS":("2020","2027")}.items()}
rows=[]
def rep(name, W, cb=2.0, quiet=False):
    net, st = bt(W, r, cb, name); rows.append((name, st["Sharpe"], st["GrossSharpe"], vs(net)["IS"], vs(net)["OOS"], st["t_NW"], st["Turn"]))
    if not quiet: print(f"{name:42s} Sh {st['Sharpe']:5.2f} gross {st['GrossSharpe']:5.2f} {vs(net)} t {st['t_NW']:4.1f} turn {st['Turn']:5.0f}")
    return net

print("== cross mean reversion: z-score of log(A/B) vs rolling mean; weight = -z/2 capped, on the cross (long A short B)")
crosses = [("AUD","NZD"),("EUR","CHF"),("EUR","GBP"),("AUD","CAD"),("NZD","CAD"),("CAD","CHF"),("GBP","CHF"),("EUR","JPY"),("AUD","JPY")]
for a,b in crosses:
    s = lp[a]-lp[b]
    for win in [20, 60]:
        z = (s - s.rolling(win).mean())/s.rolling(win).std()
        W = pd.DataFrame(0.0, index=idx, columns=r.columns); w = (-z/2).clip(-1,1); W[a] = w/2; W[b] = -w/2
        rep(f"xrev_{a}{b}_z{win}", W, quiet=True)
df = pd.DataFrame(rows, columns=["name","Sh","gross","IS","OOS","t","turn"]); print(df.sort_values("Sh", ascending=False).head(8).round(2).to_string(index=False)); rows.clear()
# portfolio of all cross reversions z60
W = pd.DataFrame(0.0, index=idx, columns=r.columns)
for a,b in crosses:
    s = lp[a]-lp[b]; z = (s - s.rolling(60).mean())/s.rolling(60).std(); w = (-z/2).clip(-1,1)/len(crosses)
    W[a] += w/2; W[b] -= w/2
rep("xrev_ALL_z60", W)
W = pd.DataFrame(0.0, index=idx, columns=r.columns)
for a,b in crosses:
    s = lp[a]-lp[b]; z = (s - s.rolling(20).mean())/s.rolling(20).std(); w = (-z/2).clip(-1,1)/len(crosses)
    W[a] += w/2; W[b] -= w/2
rep("xrev_ALL_z20", W)

print("== commodity / rates lead-lag (macro lagged one stamp)")
mac = load_closes(["USO","GLD","^TNX","TLT","HYG","SPY","^VIX"])
macL = mac.reindex(idx.union(mac.index)).ffill().shift(1).reindex(idx)
def single(ccy, sig, name):
    W = pd.DataFrame(0.0, index=idx, columns=r.columns); W[ccy] = sig; return rep(name, W)
for L in [1,5,21]:
    single("CAD", np.sign(np.log(macL["USO"]).diff(L)), f"oil{L}->CAD")
    single("AUD", np.sign(np.log(macL["GLD"]).diff(L)), f"gold{L}->AUD")
    single("CHF", np.sign(np.log(macL["GLD"]).diff(L)), f"gold{L}->CHF")
    tnx = macL["^TNX"].diff(L)
    rep(f"tnx{L}->longUSD", pd.DataFrame(np.repeat((-np.sign(tnx)).values[:,None]/7,7,axis=1), index=idx, columns=r.columns))
    single("JPY", -np.sign(tnx), f"tnx{L}->shortJPY")

print("== vol-regime conditional 1-5d basket / XS reversal, weekly rebalance to cut turnover")
vol = r.ewm(halflife=10).std()*np.sqrt(ANN)
bask = r.mean(axis=1); bvol = bask.ewm(halflife=10).std()*np.sqrt(ANN)
hi = (bvol > bvol.rolling(252).median()).astype(float)
for L in [1,3,5]:
    sig = -np.sign(bask.rolling(L).sum())
    rep(f"basket_rev{L}_hivol", pd.DataFrame(np.repeat((sig*hi).values[:,None]/7,7,axis=1), index=idx, columns=r.columns))
    rep(f"basket_rev{L}_lovol", pd.DataFrame(np.repeat((sig*(1-hi)).values[:,None]/7,7,axis=1), index=idx, columns=r.columns))
for L in [5, 10, 21]:
    m = lp.diff(L); rk = -(m.sub(m.mean(axis=1),axis=0)); W = rk.div(rk.abs().sum(axis=1), axis=0)
    Wk = W.where(idx.dayofweek == 4).ffill()   # rebalance Fridays only
    rep(f"XSrev{L}_weekly", Wk)
    rep(f"XSrev{L}_weekly_hivol", Wk.mul(hi, axis=0))
print("== large-move reversal: single ccy |ret| > 2 sigma yesterday -> fade")
z1 = r / (r.rolling(60).std())
for th in [1.5, 2.0, 2.5]:
    W = (-np.sign(z1)).where(z1.abs() > th, 0.0) / 7
    rep(f"fade_bigmove_{th}s", W)
    W = (np.sign(z1)).where(z1.abs() > th, 0.0) / 7
    rep(f"follow_bigmove_{th}s", W)
