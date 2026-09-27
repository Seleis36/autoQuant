"""Post-hoc diagnostic of the sign-flipped (contrarian) own-history premium book: yearly Sharpe,
per-coin contribution, and whether it is a Coinbase-listing artefact (exclude each coin's first
365 days on Coinbase, a rule that treats every coin the same)."""
from common import *
d = S.load(); c, m = d["c_alt"], d["mask"]
beta = S.ewm_beta(d["ret"], d["btc"].pct_change(), 60)
raw, xs, ov = premium_panel(["BTC-USD", "ETH-USD"] + list(c.columns), c.index)
prem = xs.reindex(columns=c.columns)
first = prem.apply(lambda s: s.first_valid_index())
age = pd.DataFrame({t: (c.index - first[t]).days if first[t] is not None else np.nan for t in c.columns}, index=c.index)
out = []
for excl in (0, 180, 365):
    mm = m & prem.notna() & (age >= excl)
    mm = mm & (mm.sum(axis=1) >= 6).values[:, None]
    for k in (3, 7):
        s = -(prem.rolling(k, min_periods=1).mean() - prem.rolling(180, min_periods=60).mean().shift(k))
        w = rl.linear_weights(rl.rank_xs(s, mm), mm)
        wb = w.assign(**{"BTC-USD": -(w * beta).sum(axis=1)})
        w7 = S.tranche(wb, 7)
        net, st = S.bt(w7, d["close"])
        r = S.row(net, f"contra lvl{k} h7 excl_first{excl}d"); r["turn"] = st["Turnover_ann"]; out.append(r)
        if excl == 0 and k == 3:
            print("yearly:", S.yearly(net).round(2).to_dict())
            contrib = (w7.shift(1) * d["close"][w7.columns].pct_change()).fillna(0)
            print("top/bottom coin contributions (sum of daily P&L):")
            cs = contrib.sum().sort_values(); print(pd.concat([cs.head(6), cs.tail(6)]).round(3).to_dict())
            print("2021 contributions:", contrib.loc["2021"].sum().sort_values().round(3).iloc[[0,1,2,-3,-2,-1]].to_dict())
print(pd.DataFrame(out).set_index("name").round(2).to_string())
