"""Diagnostics: is the raw taker-buy share a coin fixed effect? Rank persistence and
which coins carry the IS result."""
import warnings; warnings.filterwarnings("ignore")
from common import *
d = S.load(); c, mask = d["c_alt"], d["mask"]
f = load_flow(list(c.columns))
qv = f["QuoteVolume"].reindex(c.index); tq = f["TakerBuyQuote"].reindex(c.index)
m = mask & (qv > 0).reindex(columns=c.columns, fill_value=False)
t30 = tq.rolling(30).sum() / qv.rolling(30).sum() - 0.5
rk = t30.where(m).rank(axis=1, pct=True)
# autocorrelation of XS rank at 90/180/365 day lags
for L in (30, 90, 180, 365):
    a = rk.stack(); b = rk.shift(L).stack()
    j = pd.concat([a, b], axis=1).dropna()
    print(f"rank autocorr lag {L}: {j.corr().iloc[0,1]:.2f}")
# per-coin mean tbr (in-universe) IS vs OOS
tab = pd.DataFrame({"tbr_IS": t30.where(m).loc[S.IS[0]:S.IS[1]].mean(), "tbr_OOS": t30.where(m).loc[S.OOS[0]:].mean(),
                    "days_IS": m.loc[S.IS[0]:S.IS[1]].sum(), "days_OOS": m.loc[S.OOS[0]:].sum()})
print(tab[(tab.days_IS > 200) | (tab.days_OOS > 200)].sort_values("tbr_IS").round(4).to_string())
# a static-rank control: IS-average level used as a fixed signal (pure fixed-effect book)
fe = t30.where(m).loc[:"2020-12-31"].mean().reindex(c.columns)
w = S.tranche(rl.linear_weights(rl.rank_xs(pd.DataFrame(np.tile(fe.values, (len(c), 1)), index=c.index, columns=c.columns), m), m), 14)
net, st = S.bt(w, c)
print("fixed-effect (2018-20 avg tbr, frozen) book 2021+:", round(S.sharpe(net.loc["2021":]), 2), " 2021-22:", round(S.sharpe(net.loc["2021":"2022"]), 2), " OOS:", round(S.sharpe(net.loc["2023":]), 2))
