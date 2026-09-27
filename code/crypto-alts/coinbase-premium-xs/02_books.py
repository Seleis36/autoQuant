"""Costed books: long high / short low XS Coinbase premium (k-day mean level), BTC-beta-hedged,
linear-rank weights, tranche hold; flat on days with < 6 names priced on both venues."""
from common import *
d = S.load(); c, m = d["c_alt"], d["mask"]
bab = S.bab_reference()
beta = S.ewm_beta(d["ret"], d["btc"].pct_change(), 60)
raw, xs, ov = premium_panel(["BTC-USD", "ETH-USD"] + list(c.columns), c.index)
prem = xs.reindex(columns=c.columns)
mm = m & prem.notna()
mm = mm & (mm.sum(axis=1) >= 6).values[:, None]
rows, nets = [], {}
for k in (1, 3, 7, 14, 30):
    lvl = prem.rolling(k, min_periods=max(1, k // 2)).mean()
    for demean in (False, True):
        s = lvl - prem.rolling(180, min_periods=60).mean().shift(k) if demean else lvl
        for hold in (3, 7, 14):
            w = rl.linear_weights(rl.rank_xs(s, mm), mm)
            w = w.assign(**{"BTC-USD": -(w * beta).sum(axis=1)})
            w = S.tranche(w, hold)
            net, st = S.bt(w, d["close"])
            name = f"lvl{k}|{'dm' if demean else 'raw'}|h{hold}"
            r = S.row(net, name); r.update(turn=st["Turnover_ann"], rho_bab=net.corr(bab),
                                           s2020=S.sharpe(net.loc["2020":"2022"]))
            rows.append(r); nets[name] = net
res = pd.DataFrame(rows).set_index("name")
pd.set_option("display.width", 250)
print(res.round(2).to_string()); res.to_csv("books_02.csv"); pd.DataFrame(nets).to_parquet("books_02_nets.parquet")
print("N", len(res), "median", res[["full", "IS", "OOS", "s2020", "rho_bab"]].median().round(2).to_dict())
