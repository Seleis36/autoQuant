"""Costed books for the taker-flow family (10 bp/side, dollar-neutral linear-rank weights,
overlapping tranches). Every configuration run is written to books_03.csv."""
import warnings; warnings.filterwarnings("ignore")
from common import *

d = S.load()
c, mask = d["c_alt"], d["mask"]
f = load_flow(list(c.columns))
qv = f["QuoteVolume"].reindex(c.index); tq = f["TakerBuyQuote"].reindex(c.index)
m = mask & (qv > 0).reindex(columns=c.columns, fill_value=False)
btc = d["btc"]; bull = (btc > btc.rolling(50).mean())
bab = S.bab_reference()

def tbr(k):
    return tq.rolling(k, min_periods=k).sum() / qv.rolling(k, min_periods=k).sum() - 0.5

def dm(x, k):
    return x - x.rolling(180, min_periods=60).mean().shift(k)

sigs = {}
for k in (3, 7, 14, 30):
    t = tbr(k); r = c.pct_change(k)
    sigs[f"tbr{k}"] = t                                   # raw level (IS-strong)
    sigs[f"tbrdm{k}"] = dm(t, k)                          # vs own history
    z = S.xs_zscore(dm(t, k), m); rz = S.xs_zscore(r, m)
    b = (z * rz).sum(axis=1) / (rz ** 2).sum(axis=1)
    sigs[f"flowres{k}"] = z - rz.mul(b, axis=0)           # flow not explained by price
    b2 = (z * rz).sum(axis=1) / (z ** 2).sum(axis=1)
    sigs[f"unsupported_rev{k}"] = -(rz - z.mul(b2, axis=0))  # Llorente: fade returns flow does not support
    sigs[f"supported_mom{k}"] = rz * (z * rz > 0)         # returns with same-sign flow continue

rows, nets = [], {}
for name, s in sigs.items():
    for hold in (7, 14):
        w = S.tranche(rl.linear_weights(rl.rank_xs(s, m), m), hold)
        net, st = S.bt(w, c)
        r = S.row(net, f"{name}|h{hold}")
        r.update(turn=st["Turnover_ann"], rho_bab=net.corr(bab))
        rows.append(r); nets[f"{name}|h{hold}"] = net
res = pd.DataFrame(rows).set_index("name")
pd.set_option("display.width", 250, "display.max_rows", 500)
print(res.round(2).to_string())
res.to_csv("books_03.csv")
print("\nN configs:", len(res), " median full/IS/OOS:", res[["full", "IS", "OOS"]].median().round(2).to_dict())
