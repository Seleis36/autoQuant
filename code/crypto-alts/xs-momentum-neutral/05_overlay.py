"""Dollar-neutral BAB + regime-timed long basket overlay. Leg decomposition. Per-window."""
from common import *
import itertools
exec(open(os.path.join(HERE, "04_bab.py")).read().split("rows = {}")[0])   # beta_matrix, bab_weights

rows = {}
def rec(name, w, close, btc, cost=COST):
    net, st = rl.backtest_xs(w, close, cost_bps=cost, ann=ANN)
    sp = rl.split_stats(net, SPLITS, ann=ANN); rg = regime_table(net, btc); bs = bear_stats(net)
    rows[name] = dict(full=sp.loc["full","Sharpe"], IS=sp.loc["IS","Sharpe"], OOS=sp.loc["OOS","Sharpe"],
                      xbear=bs.loc["bear_pooled","Sharpe"], xnon=bs.loc["non_bear","Sharpe"],
                      b18=bs.iloc[1]["Sharpe"], b19=bs.iloc[2]["Sharpe"], b21=bs.iloc[3]["Sharpe"],
                      b22=bs.iloc[4]["Sharpe"], b25=bs.iloc[5]["Sharpe"],
                      cagr=sp.loc["full","CAGR"], mdd=sp.loc["full","MaxDD"], turn=st["Turnover_ann"],
                      gross=st["AvgGross"], netexp=st["AvgNet"])
    return net

D = load(n_top=20); c, mask, btc, ret = D["c_alt"], D["mask"], D["btc"], D["ret"]
btc_ret = btc.pct_change()
n = mask.sum(axis=1).replace(0, np.nan); ew = mask.astype(float).div(n, axis=0)
basket = (1 + (ew.shift(1) * ret).sum(axis=1)).cumprod()

# --- leg decomposition of the dn book (ewm60, h14)
beta = beta_matrix(ret, btc_ret, 60, "ewm")
wdn = bab_weights(beta, mask, "dn").rolling(14, min_periods=1).mean()
rec("dn_full", wdn, c, btc)
rec("dn_longleg", wdn.clip(lower=0), c, btc)
rec("dn_shortleg", wdn.clip(upper=0), c, btc)
rec("ew_basket", ew, c, btc)
rec("bn_ewm60_h14", bab_weights(beta, mask, "bn").rolling(14, min_periods=1).mean(), c, btc)
# strategy beta to BTC by regime
net_dn, _ = rl.backtest_xs(wdn, c, cost_bps=COST, ann=ANN)
bm = bear_mask(net_dn.index)
for nm, m in (("bear", bm), ("non", ~bm)):
    x = btc_ret.reindex(net_dn.index)[m]; y = net_dn[m]
    print(f"dn beta to BTC in {nm}: {np.cov(x.fillna(0), y)[0,1]/x.var():.3f}")
x = (ew.shift(1) * ret).sum(axis=1); print("dn beta to EW basket:", round(np.cov(x, net_dn)[0,1]/x.var(), 3))

# --- overlays
regimes = {}
for lb in [50, 100, 200]:
    regimes[f"btcsma{lb}"] = (btc > btc.rolling(lb).mean()).astype(float)
    regimes[f"basksma{lb}"] = (basket > basket.rolling(lb).mean()).astype(float)
for lb in [30, 60, 90]:
    regimes[f"btcmom{lb}"] = (btc > btc.shift(lb)).astype(float)

for (rname, reg), k, mode in itertools.product(regimes.items(), [0.2, 0.35, 0.5], ["L0", "LS"]):
    tilt = reg if mode == "L0" else (2 * reg - 1)
    w = wdn + k * ew.mul(tilt, axis=0)
    rec(f"dn+{k}ew_{rname}_{mode}", w, c, btc)
# regime-switched hedge: bn in bull, dn in bear
wbn = bab_weights(beta, mask, "bn").rolling(14, min_periods=1).mean()
for rname, reg in regimes.items():
    w = wbn.mul(reg, axis=0) + wdn.mul(1 - reg, axis=0)
    rec(f"switch_bn/dn_{rname}", w, c, btc)
# pure long-only trend overlay reference
for rname, reg in regimes.items():
    rec(f"ew_{rname}_L0", 0.35 * ew.mul(reg, axis=0), c, btc)

df = pd.DataFrame(rows).T
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print(df.round(2).to_string())
df.to_csv(os.path.join(HERE, "overlay_05.csv"))
