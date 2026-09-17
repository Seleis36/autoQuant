"""Reversal, BTC lead-lag, residual momentum, BAB variants, universe size, blends."""
from common import *

rows = {}
def rec(name, w, close, btc, cost=COST):
    net, st = rl.backtest_xs(w, close, cost_bps=cost, ann=ANN)
    sp = rl.split_stats(net, SPLITS, ann=ANN); rg = regime_table(net, btc)
    rows[name] = dict(full=sp.loc["full","Sharpe"], IS=sp.loc["IS","Sharpe"], OOS=sp.loc["OOS","Sharpe"],
                      bull=rg.loc["bull","Sharpe"], bear=rg.loc["bear","Sharpe"],
                      cagr=sp.loc["full","CAGR"], mdd=sp.loc["full","MaxDD"], turn=st["Turnover_ann"], gross=st["AvgGross"])
    return net

nets = {}
for ntop in [10, 15, 20, 30]:
    D = load(n_top=ntop)
    c, mask, btc, ret = D["c_alt"], D["mask"], D["btc"], D["ret"]
    btc_ret = btc.pct_change()
    n = mask.sum(axis=1).replace(0, np.nan)
    ew = mask.astype(float).div(n, axis=0)
    vol = ret.ewm(halflife=20, min_periods=20).std() * np.sqrt(ANN)
    tag = f"n{ntop}"

    # reversal
    for lb in [1, 2, 3, 5, 7]:
        for hold in [1, 3, 5]:
            rv = -(c / c.shift(lb) - 1)
            w = rl.linear_weights(rl.rank_xs(rv, mask), mask).rolling(hold, min_periods=1).mean()
            rec(f"{tag}_rev{lb}_h{hold}", w, c, btc)
    # BTC lead-lag: basket direction = sign of BTC's last 1/2/3-day return
    for lb in [1, 2, 3, 5]:
        s = np.sign(btc / btc.shift(lb) - 1)
        rec(f"{tag}_btclead{lb}_LS", ew.mul(s, axis=0), c, btc)
    # cross-sectional lag: alts whose 1d ret lagged BTC's (residual) -> catch up next day
    beta60 = ret.rolling(60).cov(btc_ret).div(btc_ret.rolling(60).var(), axis=0)
    resid1 = ret - beta60 * btc_ret.values[:, None]
    for hold in [1, 3]:
        w = rl.linear_weights(-rl.rank_xs(resid1, mask), mask).rolling(hold, min_periods=1).mean()
        rec(f"{tag}_residrev1_h{hold}", w, c, btc)
    # residual momentum (idiosyncratic 14/30d)
    for lb in [14, 30, 60]:
        rmom = resid1.rolling(lb).sum()
        w = rl.linear_weights(rl.rank_xs(rmom, mask), mask).rolling(7, min_periods=1).mean()
        rec(f"{tag}_residmom{lb}_h7", w, c, btc)
    # BAB variants
    for lb in [60, 90]:
        beta = ret.rolling(lb).cov(btc_ret).div(btc_ret.rolling(lb).var(), axis=0)
        w = rl.linear_weights(-rl.rank_xs(beta, mask), mask).rolling(7, min_periods=1).mean()
        nets[f"{tag}_bab{lb}_h7"] = rec(f"{tag}_bab{lb}_h7", w, c, btc)
        w = rl.quantile_weights(-beta, mask, q=0.3).rolling(7, min_periods=1).mean()
        rec(f"{tag}_bab{lb}_q30_h7", w, c, btc)
        # Frazzini-Pedersen beta-neutral: scale legs so beta_long*wl = beta_short*ws
        wl = rl.quantile_weights(-beta, mask, q=0.3, long_only=True)
        ws = rl.quantile_weights(beta, mask, q=0.3, long_only=True)
        bl = (wl * beta).sum(axis=1); bs = (ws * beta).sum(axis=1)
        w = (wl.div(bl.replace(0, np.nan), axis=0) - ws.div(bs.replace(0, np.nan), axis=0)).fillna(0.0)
        w = w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0).rolling(7, min_periods=1).mean()
        rec(f"{tag}_bab{lb}_betaneutral_h7", w, c, btc)
        # vol-scaled BAB
        w = (-rl.rank_xs(beta, mask) / vol).where(mask)
        w = w.sub(w.mean(axis=1), axis=0); w = w.div(w.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        rec(f"{tag}_bab{lb}_volsc_h7", w.rolling(7, min_periods=1).mean(), c, btc)
    # long-only trend 14d + BAB blend
    sgn = (c / c.shift(14) - 1 > 0).astype(float).where(mask)
    wl = (sgn * (0.5 / vol)).where(mask).fillna(0.0)
    wl = wl.div(wl.abs().sum(axis=1).clip(lower=1.0), axis=0)
    nets[f"{tag}_trendL14"] = rec(f"{tag}_trendL14", wl, c, btc)
    beta = ret.rolling(60).cov(btc_ret).div(btc_ret.rolling(60).var(), axis=0)
    wb = rl.linear_weights(-rl.rank_xs(beta, mask), mask).rolling(7, min_periods=1).mean()
    rec(f"{tag}_blend_trendL14_bab60", 0.5 * wl + 0.5 * wb, c, btc)
    rec(f"{tag}_blend_trendL14_bab60_g1.5", 0.75 * wl + 0.75 * wb, c, btc)

df = pd.DataFrame(rows).T
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 500)
print(df.round(2).to_string())
df.to_csv(os.path.join(HERE, "more_03.csv"))
N = pd.DataFrame(nets); print("\ncorr:\n", N.corr().round(2))
