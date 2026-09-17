"""Betting-against-beta deep dive: beta window, hold, hedge construction, universe, costs,
ex-post bear windows, leg decomposition."""
from common import *
import itertools

def beta_matrix(ret, mkt_ret, lb, kind="ols"):
    if kind == "ols":
        return ret.rolling(lb).cov(mkt_ret).div(mkt_ret.rolling(lb).var(), axis=0)
    if kind == "ewm":
        cov = ret.ewm(halflife=lb, min_periods=lb).cov(mkt_ret)
        var = mkt_ret.ewm(halflife=lb, min_periods=lb).var()
        return cov.div(var, axis=0)
    if kind == "fp":   # Frazzini-Pedersen: corr over lb, vols over lb/2 (crypto-scaled)
        corr = ret.rolling(lb).corr(mkt_ret)
        sv = ret.rolling(max(lb // 2, 10)).std(); mv = mkt_ret.rolling(max(lb // 2, 10)).std()
        return corr * sv.div(mv, axis=0)


def bab_weights(beta, mask, hedge="dn", q=0.3, shrink=0.0):
    """dn: dollar-neutral rank-linear. bn: beta-neutral quantile legs (Frazzini-Pedersen).
    bn_full: beta-neutral rank-linear (legs scaled to equal beta exposure)."""
    b = beta.where(mask)
    if shrink:
        b = shrink * 1.0 + (1 - shrink) * b
    if hedge == "dn":
        return rl.linear_weights(-rl.rank_xs(b, mask), mask, gross=1.0)
    if hedge == "dn_q":
        return rl.quantile_weights(-b, mask, q=q, gross=1.0)
    if hedge in ("bn", "bn_full"):
        if hedge == "bn":
            wl = rl.quantile_weights(-b, mask, q=q, long_only=True)
            ws = rl.quantile_weights(b, mask, q=q, long_only=True)
        else:
            r = rl.rank_xs(-b, mask)
            wl = r.clip(lower=0); wl = wl.div(wl.sum(axis=1).replace(0, np.nan), axis=0)
            ws = (-r).clip(lower=0); ws = ws.div(ws.sum(axis=1).replace(0, np.nan), axis=0)
        bl = (wl * b).sum(axis=1); bs = (ws * b).sum(axis=1)
        w = (wl.div(bl.replace(0, np.nan), axis=0) - ws.div(bs.replace(0, np.nan), axis=0)).fillna(0.0)
        return w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


rows = {}
def rec(name, w, close, btc, cost=COST, keep=False):
    net, st = rl.backtest_xs(w, close, cost_bps=cost, ann=ANN)
    sp = rl.split_stats(net, SPLITS, ann=ANN); rg = regime_table(net, btc); bs = bear_stats(net)
    rows[name] = dict(full=sp.loc["full","Sharpe"], IS=sp.loc["IS","Sharpe"], OOS=sp.loc["OOS","Sharpe"],
                      bullS=rg.loc["bull","Sharpe"], bearS=rg.loc["bear","Sharpe"],
                      xbear=bs.loc["bear_pooled","Sharpe"], xnon=bs.loc["non_bear","Sharpe"],
                      cagr=sp.loc["full","CAGR"], mdd=sp.loc["full","MaxDD"], turn=st["Turnover_ann"],
                      gross=st["AvgGross"], netexp=st["AvgNet"])
    return net

panels = {n: load(n_top=n) for n in [15, 20, 25]}
nets = {}
for ntop, lb, kind, hedge, hold in itertools.product([15, 20, 25], [30, 60, 90, 120], ["ols", "ewm", "fp"],
                                                     ["dn", "bn"], [3, 7, 14]):
    D = panels[ntop]; c, mask, btc, ret = D["c_alt"], D["mask"], D["btc"], D["ret"]
    beta = beta_matrix(ret, btc.pct_change(), lb, kind)
    w = bab_weights(beta, mask, hedge).rolling(hold, min_periods=1).mean()
    nets[(ntop, lb, kind, hedge, hold)] = rec(f"n{ntop}_b{lb}{kind}_{hedge}_h{hold}", w, c, btc)

df = pd.DataFrame(rows).T
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print(df.round(2).sort_values("full", ascending=False).head(40).to_string())
for k in ["ntop", "lb", "kind", "hedge", "hold"]:
    pass
idx = pd.MultiIndex.from_tuples(list(nets.keys()), names=["ntop", "lb", "kind", "hedge", "hold"])
df.index = idx
print("\nmedians by hedge:\n", df.groupby("hedge")[["full","IS","OOS","xbear","xnon","mdd","netexp"]].median().round(2))
print("\nmedians by kind:\n", df.groupby(["hedge","kind"])[["full","IS","OOS","xbear","xnon"]].median().round(2))
print("\nmedians by lb:\n", df.groupby(["hedge","lb"])[["full","IS","OOS","xbear","xnon"]].median().round(2))
print("\nmedians by hold:\n", df.groupby(["hedge","hold"])[["full","IS","OOS","xbear","xnon","turn"]].median().round(2))
print("\nmedians by ntop:\n", df.groupby(["hedge","ntop"])[["full","IS","OOS","xbear","xnon"]].median().round(2))
df.to_csv(os.path.join(HERE, "bab_04.csv"))
