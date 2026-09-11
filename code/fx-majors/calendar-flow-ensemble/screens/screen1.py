import sys, os, numpy as np, pandas as pd
sys.path.insert(0, "code/shared"); sys.path.insert(0, "code/fx-majors/shared")
from research_lib import perf_stats, newey_west_t
from fx_data import load_fx_usd_per_ccy, load_closes
ANN=252
fx = load_fx_usd_per_ccy().dropna()
fx = fx[fx.index >= "2010-01-04"]
# drop weekends / holiday rows with zero moves across all pairs
r = np.log(fx).diff()
alive = (r.abs().sum(axis=1) > 0)
fx = fx[alive]; r = r[alive].fillna(0)
print("bars", len(fx), fx.index.min(), fx.index.max())
print("ann vol %:", (r.std()*np.sqrt(ANN)*100).round(1).to_dict())
print("drift Sharpe (long fx ccy vs USD):", (r.mean()/r.std()*np.sqrt(ANN)).round(2).to_dict())
# weekday pattern
dow = r.groupby(r.index.dayofweek).mean()*1e4
print("mean bp by weekday (Mon=0):\n", dow.round(1))
cnt = r.groupby(r.index.dayofweek).size(); print(cnt)

def bt(W, r, cost_bp=2.0, name="s"):
    """W: target weights (columns = ccys, +1 = long ccy/short USD) known at close t."""
    W = W.reindex(r.index).fillna(0.0)
    We = W.shift(1).fillna(0.0)
    turn = (We - We.shift(1).fillna(0.0)).abs().sum(axis=1)
    net = (We*r).sum(axis=1) - turn*cost_bp/1e4
    st = perf_stats(net, ann=ANN, name=name)
    st["Turn"] = turn.sum()/(len(turn)/ANN); st["Gross"] = We.abs().sum(axis=1).mean()
    return net, st

def vs(net, splits={"IS":("2010","2019"),"OOS":("2020","2027")}):
    return {k: round(perf_stats(net.loc[a:b], ann=ANN)["Sharpe"],2) for k,(a,b) in splits.items()}

res = {}
# --- basket "short USD" always (benchmark)
W = pd.DataFrame(1/7, index=r.index, columns=r.columns)
net, st = bt(W, r, name="shortUSD_basket"); res["shortUSD_basket"] = st; print("shortUSD", st["Sharpe"].round(2), vs(net))

# --- month-end / turn-of-month: position on last k trading days of month (held into next day)
idx = fx.index
mon = idx.to_period("M")
# trading-day rank from end of month: 0 = last bar of month
pos_from_end = pd.Series(idx, index=idx).groupby(mon).cumcount(ascending=False)
pos_from_start = pd.Series(idx, index=idx).groupby(mon).cumcount()
for k in [1,2,3]:
    for sgn,nm in [(1,"shortUSD"),(-1,"longUSD")]:
        # weight set at close t when t+1 is within last k days => t in last k+1..? Simpler: hold over next day's return when NEXT bar is in last k days of month
        nxt_from_end = pos_from_end.shift(-1)  # unknown for last bar; fine since we would know calendar
        # calendar-known: next bar's rank from end is (pos_from_end -1) if same month else it's the first day of next month
        rank_next = pos_from_end - 1
        gate = (rank_next >= 0) & (rank_next < k)
        W = pd.DataFrame(np.where(np.repeat(gate.values[:,None],7,axis=1), sgn/7, 0.0), index=idx, columns=r.columns)
        net, st = bt(W, r, name=f"{nm}_last{k}"); res[st.name]=st
        print(st.name, "Sh", st["Sharpe"].round(2), vs(net), "days/yr", round(gate.mean()*252))
    for sgn,nm in [(1,"shortUSD"),(-1,"longUSD")]:
        rank_next = pos_from_start + 1
        gate = (rank_next <= k) | (pos_from_end == 0)  # first k days of next month
        W = pd.DataFrame(np.where(np.repeat(gate.values[:,None],7,axis=1), sgn/7, 0.0), index=idx, columns=r.columns)
        net, st = bt(W, r, name=f"{nm}_first{k}"); res[st.name]=st
        print(st.name, "Sh", st["Sharpe"].round(2), vs(net))

# --- month-end equity rebalancing: sign = -(SPY MTD return) at last 2 days
spy = load_closes(["SPY","EFA"])["SPY"].reindex(idx).ffill()
mtd = spy / spy.groupby(mon).transform("first") - 1
for k in [1,2,3]:
    rank_next = pos_from_end - 1
    gate = (rank_next >= 0) & (rank_next < k)
    sig = -np.sign(mtd) * gate
    W = pd.DataFrame(np.repeat(sig.values[:,None]/7, 7, axis=1)*-1, index=idx, columns=r.columns)  # SPY up => sell USD => long fx ccy => +
    W = pd.DataFrame(np.repeat((np.sign(mtd)*gate).values[:,None]/7, 7, axis=1), index=idx, columns=r.columns)
    net, st = bt(W, r, name=f"MErebal_last{k}"); res[st.name]=st
    print(st.name, "Sh", st["Sharpe"].round(2), vs(net), "t", round(st["t_NW"],2))

# --- TS momentum (Baz MACD) basket, vol scaled
def macd(close, f, s):
    m = close.ewm(halflife=f).mean() - close.ewm(halflife=s).mean()
    q = m / close.rolling(63).std(ddof=1)
    return q / q.rolling(252).std(ddof=1)
vol = r.ewm(halflife=20, min_periods=20).std()*np.sqrt(ANN)
for f,s in [(8,24),(16,48),(32,96),(64,192)]:
    z = macd(fx, f, s).clip(-3,3)
    W = (z / 7 * (0.10/vol)).clip(-1,1)
    net, st = bt(W, r, name=f"TSMOM_{f}_{s}"); res[st.name]=st
    print(st.name, "Sh", st["Sharpe"].round(2), vs(net), "turn", round(st["Turn"],1))
for L in [21,63,126,252]:
    z = np.sign(np.log(fx).diff(L))
    W = (z / 7 * (0.10/vol)).clip(-1,1)
    net, st = bt(W, r, name=f"TSMOM_sign{L}"); res[st.name]=st
    print(st.name, "Sh", st["Sharpe"].round(2), vs(net), "turn", round(st["Turn"],1))

# --- XS short-term reversal / momentum across 7 ccys (dollar-neutral)
for L in [1,3,5,10,21,63,126,252]:
    m = np.log(fx).diff(L)
    rk = m.rank(axis=1) - 4  # -3..3
    W = rk.div(rk.abs().sum(axis=1), axis=0)
    net, st = bt(W, r, name=f"XSmom_{L}"); res[st.name]=st
    print(st.name, "Sh", st["Sharpe"].round(2), vs(net), "turn", round(st["Turn"],1))
pd.DataFrame(res).T.to_csv(os.path.join(os.environ["S"], "screen1.csv"))
