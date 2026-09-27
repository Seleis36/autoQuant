"""IC screen for the XS Upbit (Korea) premium. Pre-registered sign: NEGATIVE (retail froth)."""
from common import *
d = S.load(); c, m = d["c_alt"], d["mask"]
raw, xs, upq = premium_panel(["BTC-USD", "ETH-USD"] + list(c.columns), c.index)
prem = xs.reindex(columns=c.columns)
mm = m & prem.notna()
print("names/day with KR premium (in universe):", mm.sum(axis=1).groupby(mm.index.year).mean().round(1).to_dict())
print("XS premium (bp):", (prem.where(mm).stack() * 1e4).describe(percentiles=[.05, .5, .95]).round(1).to_dict())
print("market-wide kimchi (median raw, %):", (raw.median(axis=1) * 100).groupby(raw.index.year).mean().round(2).dropna().to_dict())
# Upbit volume share relative to Binance (retail concentration), own-history
bq = V.panel(V.binance_daily, list(c.columns), "QuoteVolume").reindex(c.index)
krw = V.panel(V.upbit_daily, ["BTC-USD"], "Close").reindex(c.index)["BTC-USD"] / V.panel(V.binance_daily, ["BTC-USD"], "Close").reindex(c.index)["BTC-USD"]
upusd = upq.reindex(columns=c.columns).div(krw, axis=0)          # KRW volume in ~USDT
share = np.log(upusd / bq)
feats = {}
for k in (1, 3, 7, 14, 30):
    lvl = prem.rolling(k, min_periods=max(1, k // 2)).mean()
    feats[f"lvl{k}"] = lvl
    feats[f"dm{k}"] = lvl - prem.rolling(180, min_periods=60).mean().shift(k)
    feats[f"chg{k}"] = prem - prem.shift(k)
    sh = share.rolling(k, min_periods=max(1, k // 2)).mean()
    feats[f"krshare_dm{k}"] = sh - share.rolling(180, min_periods=60).mean().shift(k)
rows = []
for h in (1, 3, 7, 14, 30):
    fwd = c.shift(-h) / c - 1
    fwd = fwd.sub(fwd.where(mm).mean(axis=1), axis=0)
    for nme, s in feats.items():
        r = ic_table(s, fwd, mm); r.update(feat=nme, h=h); rows.append(r)
res = pd.DataFrame(rows).set_index(["feat", "h"])
pd.set_option("display.width", 250, "display.max_rows", 200)
print(res.round(3).to_string()); res.to_csv("ic_01.csv")
