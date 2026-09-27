"""Weight-level equal-risk blends. Pre-registered (before this script ran):
  * candidates: bab (live), dilution, volume (ensemble), funding (crypto-perps defaults);
  * inclusion: IS Sharpe (on the sleeve's active IS days) >= 0.3 and |rho to BAB| < 0.5;
  * risk weights k_s = 1 / sigma_s(IS active days); blend w = sum_s k_s w_s / sum_s k_s * N_s-normalised
    so the blend's alt-leg gross is comparable to one sleeve; costs on the NET blended turnover;
  * primary = all sleeves passing; every subset reported; walk-forward inclusion as a control."""
from common import *
import itertools
W, full = sleeve_weights()
cols = sorted(set().union(*[w.columns for w in W.values()]))
W = {k: w.reindex(columns=cols).fillna(0.0) for k, w in W.items()}
px = full.reindex(columns=cols)
nets, active = {}, {}
for k, w in W.items():
    nets[k], _ = rl.backtest_xs(w, px, 10, 365)
    active[k] = w.abs().sum(axis=1).shift(1) > 0
IS0, IS1 = "2018-03-08", S.IS[1]
sig = {k: nets[k].loc[IS0:IS1][active[k].loc[IS0:IS1]].std() for k in W}
isr = {k: S.sharpe(nets[k].loc[IS0:IS1][active[k].loc[IS0:IS1]]) for k in W}
rho = {k: nets[k].corr(nets["bab"]) for k in W}
print("IS sharpe (active days):", {k: round(v, 2) for k, v in isr.items()})
print("IS daily vol:", {k: round(v * np.sqrt(365), 3) for k, v in sig.items()}, " rho to BAB:", {k: round(v, 2) for k, v in rho.items()})
passing = [k for k in W if isr[k] >= 0.3 and abs(rho[k] if k != "bab" else 0) < 0.5]
print("passing inclusion rule:", passing)
print("return corr matrix:\n", pd.DataFrame(nets).loc["2018-03-08":].corr().round(2).to_string())


def blend(keys, scale_to_bab=False):
    k = pd.Series({s: 1.0 / sig[s] for s in keys})
    k = k / k.sum() * len(keys) / len(keys)        # weights sum to 1: each sleeve's risk share equal
    w = sum(W[s] * k[s] for s in keys)
    if scale_to_bab:                               # lever so blend IS vol = BAB IS vol
        n0, _ = rl.backtest_xs(w, px, 0, 365)
        w = w * (sig["bab"] / n0.loc[IS0:IS1].std())
    return w


rows, bnets = [], {}
for r in range(1, 5):
    for keys in itertools.combinations(["bab", "dilution", "volume", "funding"], r):
        w = blend(list(keys))
        net, st = rl.backtest_xs(w, px, 10, 365)
        name = "+".join(keys)
        row = S.row(net, name)
        g = w.abs().sum(axis=1).loc["2018-03-08":]
        row.update(turn=st["Turnover_ann"] * len(net) / len(net.loc["2018-03-08":]), gross_avg=g.mean(), gross_max=g.max(),
                   vol=net.loc["2018-03-08":].std() * np.sqrt(365), y2026=S.sharpe(net.loc["2026"]))
        rows.append(row); bnets[name] = net
res = pd.DataFrame(rows).set_index("name")
pd.set_option("display.width", 260)
print(res.round(2).to_string()); res.to_csv("blend_01.csv"); pd.DataFrame(bnets).to_parquet("blend_01_nets.parquet")

# primary, levered to BAB's IS vol
wp = blend(passing, scale_to_bab=True)
net, st = rl.backtest_xs(wp, px, 10, 365)
g = wp.abs().sum(axis=1).loc["2018-03-08":]
print("\nPRIMARY levered to BAB IS vol:", {k: round(v, 3) for k, v in S.row(net, "p").items() if k != "name"},
      "gross avg/max", round(g.mean(), 2), round(g.max(), 2))
print("yearly primary:", S.yearly(bnets["+".join(passing)]).loc[2018:].round(2).to_dict())
print("yearly BAB:", S.yearly(bnets["bab"]).loc[2018:].round(2).to_dict())

# walk-forward inclusion control: each year Y>=2021 include sleeves with expanding Sharpe >= 0.3
# (active days through Y-1), risk weights from expanding vol; stitch year by year.
parts = []
for Y in range(2021, 2027):
    end = f"{Y-1}-12-31"
    inc, kk = [], {}
    for s in W:
        x = nets[s].loc["2018-03-08":end][active[s].loc["2018-03-08":end]]
        if len(x) > 180 and S.sharpe(x) >= 0.3:
            inc.append(s); kk[s] = 1.0 / x.std()
    kk = pd.Series(kk); kk = kk / kk.sum()
    w = sum(W[s] * kk[s] for s in inc)
    n, _ = rl.backtest_xs(w, px, 10, 365)
    parts.append(n.loc[f"{Y}-01-01":f"{Y}-12-31"])
    print("WF", Y, "included", inc)
wf = pd.concat(parts)
print("walk-forward stitched 2021-26:", round(S.sharpe(wf), 2), " 2023-26:", round(S.sharpe(wf.loc["2023":]), 2),
      "| BAB same windows:", round(S.sharpe(bnets["bab"].loc["2021":]), 2), round(S.sharpe(bnets["bab"].loc["2023":]), 2))
