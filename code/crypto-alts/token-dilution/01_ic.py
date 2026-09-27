"""Map yfinance alts to CMC ids, build dilution / overhang / age / size signals, IC screen."""
from common import *
d = S.load(); c, m = d["c_alt"], d["mask"]
idmap, W = supply_panels(c)
print(f"mapped {len(idmap)}/{c.shape[1]}; unmapped: {sorted(set(c.columns) - set(idmap))}")
circ = W["circulatingSupply"].where(W["circulatingSupply"] > 0)
tot = W["totalSupply"].where(W["totalSupply"] > 0)
mx = W["maxSupply"].where(W["maxSupply"] > 0)
mcap = W["marketCap"]
added = W["dateAdded"]
mm = m & circ.reindex(columns=c.columns).notna()
print("in-universe names with supply / day by year:", mm.sum(axis=1).groupby(mm.index.year).mean().round(1).to_dict())
feats = {}
for wk in (4, 12, 26, 52):
    g = np.log(circ / circ.shift(7 * wk)).clip(-1, 2)
    feats[f"dil{wk}w"] = g.reindex(columns=c.columns)
feats["overhang_total"] = np.log(tot.clip(lower=circ) / circ).reindex(columns=c.columns)
feats["overhang_max"] = np.log(mx.fillna(tot).clip(lower=circ) / circ).reindex(columns=c.columns)
first_add = pd.to_datetime(added.bfill().iloc[-1])      # dateAdded is a static CMC attribute
age = pd.DataFrame({t: (c.index - first_add[t]).days for t in added.columns}, index=c.index)
feats["age"] = age.reindex(columns=c.columns)
feats["logmcap"] = np.log(mcap).reindex(columns=c.columns)
# sanity print for a few names
for t in ("SOL-USD", "AVAX-USD", "XRP-USD", "BNB-USD", "DOT-USD"):
    if t in circ:
        s = circ[t].dropna()
        print(t, idmap.get(t), f"circ {s.iloc[0]:.3g} ({s.index[0].date()}) -> {s.iloc[-1]:.3g}", f"dil52 now {feats['dil52w'][t].dropna().iloc[-1]:.2f}")
rows = []
for h in (7, 14, 30, 60):
    fwd = c.shift(-h) / c - 1
    fwd = fwd.sub(fwd.where(mm).mean(axis=1), axis=0)
    for nme, s in feats.items():
        r = ic_table(s, fwd, mm); r.update(feat=nme, h=h); rows.append(r)
res = pd.DataFrame(rows).set_index(["feat", "h"])
pd.set_option("display.width", 250, "display.max_rows", 200)
print(res.round(3).to_string()); res.to_csv("ic_01.csv")
import json; json.dump(idmap, open("idmap.json", "w"), indent=0)
