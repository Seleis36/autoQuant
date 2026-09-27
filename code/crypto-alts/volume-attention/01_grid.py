"""Grid of abnormal-volume books. Selection rule fixed before running: pick on IS Sharpe only.
Short high abnormal volume / long low, dollar-neutral linear-rank weights, tranche hold."""
from common import *

d = S.load(); c, v, m = d["c_alt"], d["v_alt"], d["mask"]
btc = d["btc"]; bab = S.bab_reference()
beta = S.ewm_beta(d["ret"], btc.pct_change(), 60)

rows, nets = [], {}
for k in (7, 14, 30, 60, 90):
    for base in (180, 365):
        av = abn_volume(v, k, base)
        for hold in (7, 14, 30):
            for hedge in ("dn", "bn"):
                w = rl.linear_weights(-rl.rank_xs(av, m), m)
                if hedge == "bn":          # add a BTC leg so the book's EWM beta is 0
                    wb = -(w * beta).sum(axis=1)
                    w = w.assign(**{"BTC-USD": wb})
                w = S.tranche(w, hold)
                net, st = S.bt(w, d["close"])
                name = f"k{k}|b{base}|h{hold}|{hedge}"
                r = S.row(net, name); r.update(turn=st["Turnover_ann"], rho_bab=net.corr(bab))
                rows.append(r); nets[name] = net
res = pd.DataFrame(rows).set_index("name")
pd.set_option("display.width", 250, "display.max_rows", 500)
print(res.round(2).to_string())
res.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "grid_01.csv"))
pd.DataFrame(nets).to_parquet(os.path.join(os.path.dirname(os.path.abspath(__file__)), "grid_01_nets.parquet"))
print("\nN", len(res), "median:", res[["full", "IS", "OOS", "bear", "rho_bab"]].median().round(2).to_dict())
best = res["IS"].idxmax(); print("IS-selected:", best, res.loc[best, ["full", "IS", "OOS"]].round(2).to_dict())
