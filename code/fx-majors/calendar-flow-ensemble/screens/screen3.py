import sys, os, numpy as np, pandas as pd
sys.path.insert(0, "code/shared"); sys.path.insert(0, "code/fx-majors/shared")
from research_lib import perf_stats
from fx_data import load_fx_usd_per_ccy, load_closes
ANN=252
fx = load_fx_usd_per_ccy().dropna(); fx = fx[fx.index >= "2010-01-04"]
r = np.log(fx).diff(); alive = r.abs().sum(axis=1) > 0; fx = fx[alive]; r = r[alive].fillna(0)
idx = r.index
mac = load_closes(["SPY","EFA","^VIX","DX-Y.NYB","TLT","GLD","USO","HYG","^TNX","^IRX"])
# CONSERVATIVE ALIGNMENT: macro stamped <= D-1 is usable for the weight set at FX stamp D.
macL = mac.reindex(idx.union(mac.index)).ffill().shift(1).reindex(idx)   # value of previous calendar row
def bt(W, r, cost_bp=2.0, name="s"):
    W = W.reindex(r.index).fillna(0.0); We = W.shift(1).fillna(0.0)
    turn = (We - We.shift(1).fillna(0.0)).abs().sum(axis=1)
    gross = (We*r).sum(axis=1); net = gross - turn*cost_bp/1e4
    st = perf_stats(net, ann=ANN, name=name); st["Turn"] = turn.sum()/(len(turn)/ANN)
    st["GrossSharpe"] = perf_stats(gross, ann=ANN)["Sharpe"]
    return net, st
def vs(net): return {k: round(perf_stats(net.loc[a:b], ann=ANN)["Sharpe"],2) for k,(a,b) in {"IS":("2010","2019"),"OOS":("2020","2027")}.items()}
def basket(sig): return pd.DataFrame(np.repeat(sig.values[:,None]/7, 7, axis=1), index=idx, columns=r.columns)
def rep(name, W, cb=2.0):
    net, st = bt(W, r, cb, name); print(f"{name:40s} Sh {st['Sharpe']:5.2f} gross {st['GrossSharpe']:5.2f} {vs(net)} t {st['t_NW']:4.1f} turn {st['Turn']:5.0f}"); return net

print("== weekday: weight set at FX-stamp D applies to bar D+1; sign -1 = long USD")
for dw in range(5):
    nxt = pd.Series(idx, index=idx).shift(-1)
    gate = pd.Series((idx.dayofweek == (dw-1)%5) if False else ((idx.dayofweek+1)%7 == dw), index=idx)  # weight when next bar's weekday==dw (approx: Fri->Mon handled via %7? no)
# simpler: use actual next bar's weekday
nxt_dow = pd.Series(idx.dayofweek, index=idx).shift(-1)
for dw in range(5):
    gate = (nxt_dow == dw).astype(float)
    rep(f"longUSD_when_next_bar_is_{dw}", basket(-gate))

print("== month-end equity rebalancing, lagged SPY MTD (sign: SPY up MTD -> short USD)")
mon = idx.to_period("M")
pos_from_end = pd.Series(idx, index=idx).groupby(mon).cumcount(ascending=False)
spyL = macL["SPY"]; efaL = macL["EFA"]
mtd = spyL / spyL.groupby(mon).transform("first") - 1
mtd_rel = np.log(spyL / spyL.groupby(mon).transform("first")) - np.log(efaL / efaL.groupby(mon).transform("first"))
for k in [1,2,3,4]:
    gate = ((pos_from_end - 1 >= 0) & (pos_from_end - 1 < k)).astype(float)
    rep(f"ME_spyMTD_last{k}", basket(np.sign(mtd)*gate))
    rep(f"ME_spyMTD_scaled_last{k}", basket((mtd/0.03).clip(-1,1)*gate))
    rep(f"ME_relMTD_last{k}", basket(np.sign(mtd_rel)*gate))
# also first days of month (unwind)
for k in [1,2]:
    pos_from_start = pd.Series(idx, index=idx).groupby(mon).cumcount()
    gate = ((pos_from_start + 1 <= k) | (pos_from_end == 0)).astype(float)
    mtd_prev = mtd.groupby(mon).transform("last").shift(1)  # crude
    rep(f"ME_unwind_first{k}", basket(-np.sign(mtd_prev)*gate))

print("== equity/VIX lead-lag to FX basket (lagged macro)")
spy_r = np.log(macL["SPY"]).diff(); vix_ch = np.log(macL["^VIX"]).diff(); dxy_r = np.log(macL["DX-Y.NYB"]).diff()
for L in [1,2,5]:
    rep(f"spy_ret{L}_sign_shortUSD", basket(np.sign(spy_r.rolling(L).sum())))
    rep(f"vix_ch{L}_sign_longUSD", basket(-np.sign(vix_ch.rolling(L).sum())))
    rep(f"dxy_ret{L}_sign_cont", basket(-np.sign(dxy_r.rolling(L).sum())))
# own basket 1-day reversal / continuation (basket-level)
bask_r = r.mean(axis=1)
for L in [1,2,3,5,10]:
    rep(f"basket_rev{L}", basket(-np.sign(bask_r.rolling(L).sum())))
# risk-on/off pairs: long JPY+CHF short AUD+NZD when VIX up
W = pd.DataFrame(0.0, index=idx, columns=r.columns)
for L in [1,5]:
    s = np.sign(vix_ch.rolling(L).sum())
    W2 = W.copy(); W2["JPY"] = s/4; W2["CHF"] = s/4; W2["AUD"] = -s/4; W2["NZD"] = -s/4
    rep(f"riskoff_pairs_vix{L}", W2)
    s = -np.sign(spy_r.rolling(L).sum())
    W2 = W.copy(); W2["JPY"] = s/4; W2["CHF"] = s/4; W2["AUD"] = -s/4; W2["NZD"] = -s/4
    rep(f"riskoff_pairs_spy{L}", W2)

print("== ETF-implied carry: log(ETF/spot) drift over 63d vs UUP/DXY")
etf = load_closes(["FXE","FXB","FXY","FXA","FXC","FXF","UUP"])
etfL = etf.reindex(idx.union(etf.index)).ffill().shift(1).reindex(idx)
spotL = fx.shift(1)  # spot at previous FX stamp ~ aligns with lagged ETF (both ~ day D-1)
m = {"EUR":"FXE","GBP":"FXB","JPY":"FXY","AUD":"FXA","CAD":"FXC","CHF":"FXF"}
carry = pd.DataFrame(index=idx)
for c,e in m.items():
    ratio = np.log(etfL[e]) - np.log(spotL[c])
    carry[c] = (ratio - ratio.shift(126)) * 2   # annualised implied (deposit rate - fee)
dxyL = macL["DX-Y.NYB"]; usd_ratio = np.log(etfL["UUP"]) - np.log(dxyL)
usd_c = (usd_ratio - usd_ratio.shift(126))*2
print(carry.tail(3).round(3)); print("usd", usd_c.tail(3).round(3))
carry_rel = carry.sub(usd_c, axis=0)
rk = carry_rel.rank(axis=1) - 3.5; W = rk.div(rk.abs().sum(axis=1), axis=0); W = W.reindex(columns=r.columns).fillna(0)
rep("ETFcarry_rank_LS", W)
sg = np.sign(carry_rel).reindex(columns=r.columns).fillna(0)/6
rep("ETFcarry_sign_basket", sg)
