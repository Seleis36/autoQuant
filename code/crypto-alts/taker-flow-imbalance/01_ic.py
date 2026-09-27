"""IC screen: Binance taker-buy share features vs forward XS-demeaned returns.

Signal from Binance bar D (covers D 00:00 -> D+1 00:00 UTC) is known at the yfinance close D.
Forward return h = close(D+h)/close(D) - 1 on yfinance prices (what the book trades).
"""
from common import *

d = S.load()
c, mask, ret = d["c_alt"], d["mask"], d["ret"]
f = load_flow(list(c.columns))
qv = f["QuoteVolume"].reindex(c.index)
tq = f["TakerBuyQuote"].reindex(c.index)
nt = f["Trades"].reindex(c.index)
has = qv.notna() & (qv > 0)
m = mask & has.reindex(columns=c.columns, fill_value=False)
print("universe names/day (with Binance):", m.sum(axis=1).loc["2018-03":].describe().round(1).to_dict())
print("coverage by year:", m.sum(axis=1).groupby(m.index.year).mean().round(1).to_dict())

btc_ret = d["btc"].pct_change()
beta = S.ewm_beta(ret, btc_ret, 60)

feats = {}
for k in (1, 3, 7, 14, 30, 60):
    tbr = tq.rolling(k, min_periods=k).sum() / qv.rolling(k, min_periods=k).sum() - 0.5
    feats[f"tbr{k}"] = tbr
    mu = tbr.rolling(180, min_periods=60).mean().shift(k)
    sd = tbr.rolling(180, min_periods=60).std().shift(k)
    feats[f"tbrz{k}"] = (tbr - mu) / sd                        # vs own history
    feats[f"tbrdm{k}"] = tbr - tbr.rolling(180, min_periods=60).mean().shift(k)
    r = c.pct_change(k)
    # cross-sectional residual of flow on same-window return
    z = S.xs_zscore(feats[f"tbrdm{k}"], m); rz = S.xs_zscore(r, m)
    b = (z * rz).sum(axis=1) / (rz ** 2).sum(axis=1)
    feats[f"flowres{k}"] = z - rz.mul(b, axis=0)
    feats[f"ret{k}"] = r                                      # control: plain momentum/reversal
    ats = (qv / nt)
    feats[f"ats{k}"] = np.log(ats.rolling(k).mean() / ats.rolling(180, min_periods=60).mean().shift(k))

rows = []
for h in (1, 3, 7, 14, 30):
    fwd = c.shift(-h) / c - 1
    fwd = fwd.sub(fwd.where(m).mean(axis=1), axis=0)
    for name, sig in feats.items():
        r = ic_table(sig, fwd, m)
        r.update(feat=name, h=h)
        rows.append(r)
res = pd.DataFrame(rows).set_index(["feat", "h"]).round(3)
pd.set_option("display.width", 200, "display.max_rows", 500)
print(res)
res.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ic_01.csv"))
