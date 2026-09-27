"""IC screen 2: trade-size / activity features and Fama-MacBeth partials vs price controls.

ats in USD per trade mechanically embeds the price level (coin-unit trade sizes are sticky),
so it is split into base-unit trade size and price-vs-own-history. All features are
log(k-day mean / 180-day mean ending k days earlier): own-history normalised, past data only.
"""
from common import *

d = S.load()
c, mask = d["c_alt"], d["mask"]
f = load_flow(list(c.columns))
f["Volume"] = V.panel(V.binance_daily, list(c.columns), "Volume")
qv = f["QuoteVolume"].reindex(c.index); nt = f["Trades"].reindex(c.index)
vb = f["Volume"].reindex(c.index); tq = f["TakerBuyQuote"].reindex(c.index)
yv = d["v_alt"]
m = mask & (qv > 0).reindex(columns=c.columns, fill_value=False)


def rel(x, k, base=180):
    return np.log(x.rolling(k, min_periods=k).mean() / x.rolling(base, min_periods=base // 3).mean().shift(k))


feats = {}
for k in (3, 7, 14, 30, 60):
    feats[f"ats_usd{k}"] = rel(qv / nt, k)
    feats[f"ats_base{k}"] = rel(vb / nt, k)
    feats[f"trades{k}"] = rel(nt, k)
    feats[f"qvol{k}"] = rel(qv, k)
    feats[f"yvol{k}"] = rel(yv, k)
    feats[f"binshare{k}"] = rel(qv / yv, k)
    feats[f"pma{k}"] = rel(c, k)                 # price vs its own 180d mean
    feats[f"ret{k}"] = c.pct_change(k)

rows = []
for h in (7, 14, 30):
    fwd = c.shift(-h) / c - 1
    fwd = fwd.sub(fwd.where(m).mean(axis=1), axis=0)
    for name, sig in feats.items():
        r = ic_table(sig, fwd, m); r.update(feat=name, h=h); rows.append(r)
res = pd.DataFrame(rows).set_index(["feat", "h"]).round(3)
pd.set_option("display.width", 200, "display.max_rows", 500)
print(res.to_string())
res.to_csv("ic_02.csv")


# Fama-MacBeth: fwd rank on ranks of [feature, pma, ret] -> partial slope t-stats
def fmb(y, xs, m, lags=21):
    Y = y.where(m).rank(axis=1, pct=True)
    X = [x.where(m).rank(axis=1, pct=True) for x in xs]
    out = []
    for dt in Y.index:
        yy = Y.loc[dt]
        XX = pd.concat([x.loc[dt] for x in X], axis=1)
        ok = yy.notna() & XX.notna().all(axis=1)
        if ok.sum() < 10:
            continue
        A = np.column_stack([np.ones(ok.sum()), XX[ok].values - 0.5])
        b = np.linalg.lstsq(A, yy[ok].values - 0.5, rcond=None)[0]
        out.append(pd.Series(b[1:], name=dt))
    B = pd.DataFrame(out)
    res = {}
    for k, (a, bb) in S.SPLITS.items():
        seg = B.loc[a:bb]
        res[k] = [f"{seg[i].mean():+.3f} (t {rl.newey_west_t(seg[i].values, lags):+.1f})" for i in seg.columns]
    return pd.DataFrame(res)

print("\nFama-MacBeth partials (rank on rank), h=14, every 7th day")
fwd = c.shift(-14) / c - 1
sub = fwd.index[::7]
for k in (14, 30, 60):
    for name in (f"ats_usd{k}", f"ats_base{k}", f"trades{k}", f"qvol{k}", f"binshare{k}"):
        t = fmb(fwd.loc[sub], [feats[name].loc[sub], feats[f"pma{k}"].loc[sub], feats[f"ret{k}"].loc[sub]], m.loc[sub], lags=3)
        t.index = [name, f"pma{k}", f"ret{k}"]
        print(t.to_string(header=(name == f"ats_usd{k}")))
