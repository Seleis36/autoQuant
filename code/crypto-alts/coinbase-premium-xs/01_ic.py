"""IC screen for the XS Coinbase premium: level (k-day mean), own-history z, change."""
from common import *
d = S.load(); c, m = d["c_alt"], d["mask"]
tick = ["BTC-USD", "ETH-USD"] + list(c.columns)
raw, xs, ov = premium_panel(tick, c.index)
prem = xs.reindex(columns=c.columns)
mm = m & prem.notna()
print("names/day with premium (in universe):", mm.sum(axis=1).groupby(mm.index.year).mean().round(1).to_dict())
print("XS premium distribution (bp):", (prem.where(mm).stack() * 1e4).describe(percentiles=[.05, .25, .5, .75, .95]).round(1).to_dict())
feats = {}
for k in (1, 3, 7, 14, 30):
    lvl = prem.rolling(k, min_periods=max(1, k // 2)).mean()
    feats[f"lvl{k}"] = lvl
    mu = prem.rolling(180, min_periods=60).mean().shift(k); sd = prem.rolling(180, min_periods=60).std().shift(k)
    feats[f"z{k}"] = (lvl - mu) / sd
    feats[f"chg{k}"] = prem - prem.shift(k)
rows = []
for h in (1, 3, 7, 14, 30):
    fwd = c.shift(-h) / c - 1
    fwd = fwd.sub(fwd.where(mm).mean(axis=1), axis=0)
    for nme, s in feats.items():
        r = ic_table(s, fwd, mm); r.update(feat=nme, h=h); rows.append(r)
res = pd.DataFrame(rows).set_index(["feat", "h"])
pd.set_option("display.width", 250, "display.max_rows", 200)
print(res.round(3).to_string()); res.to_csv("ic_01.csv")
