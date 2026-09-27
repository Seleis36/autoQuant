"""Costed dilution books + controls. Short high k-week circulating-supply growth / long low,
linear-rank weights, dollar-neutral (dn) or BTC-beta-hedged (bn), overlapping tranches."""
from common import *
import json
d = S.load(); c, m = d["c_alt"], d["mask"]
idmap, W = supply_panels(c)
circ = W["circulatingSupply"].where(W["circulatingSupply"] > 0).reindex(columns=c.columns)
mcap = W["marketCap"].reindex(columns=c.columns)
mm = m & circ.notna()
bab = S.bab_reference()
beta = S.ewm_beta(d["ret"], d["btc"].pct_change(), 60)


def dil(wk):
    return np.log(circ / circ.shift(7 * wk)).clip(-1, 2)


def book(sig, hold, hedge):
    w = rl.linear_weights(rl.rank_xs(sig, mm), mm)
    if hedge == "bn":
        w = w.assign(**{"BTC-USD": -(w * beta).sum(axis=1)})
    return S.tranche(w, hold)


rows, nets = [], {}
def run(sig, name, hold, hedge):
    net, st = S.bt(book(sig, hold, hedge), d["close"])
    r = S.row(net, name); r.update(turn=st["Turnover_ann"], rho_bab=net.corr(bab), gross=st["AvgGross"])
    rows.append(r); nets[name] = net

for wk in (4, 12, 26, 52):
    for hold in (7, 14, 30):
        for hedge in ("dn", "bn"):
            run(-dil(wk), f"dil{wk}w|h{hold}|{hedge}", hold, hedge)
# controls with the same construction
for hold in (14, 30):
    run(np.log(mcap), f"ctrl_size_big|h{hold}|bn", hold, "bn")
    run(-beta, f"ctrl_lowbeta|h{hold}|bn", hold, "bn")
res = pd.DataFrame(rows).set_index("name")
pd.set_option("display.width", 250)
print(res.round(2).to_string()); res.to_csv("books_02.csv"); pd.DataFrame(nets).to_parquet("books_02_nets.parquet")
dres = res[res.index.str.startswith("dil")]
print("dilution N", len(dres), "median", dres[["full", "IS", "OOS", "bear", "rho_bab"]].median().round(2).to_dict())
N = pd.DataFrame(nets)
print(N[["dil12w|h14|bn", "dil12w|h30|bn", "ctrl_size_big|h30|bn", "ctrl_lowbeta|h30|bn"]].corr().round(2).to_string())
