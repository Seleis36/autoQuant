"""Grid: momentum lookback x skip x weighting on the PIT alt universe. Dollar-neutral."""
from common import *
import itertools

D = load(n_top=15)
c, mask, btc, ret = D["c_alt"], D["mask"], D["btc"], D["ret"]
print("universe size by year:\n", mask.sum(axis=1).groupby(mask.index.year).mean().round(1).to_string())

rows = []
for lb, skip, wtype, hold in itertools.product([7, 14, 21, 30, 60, 90, 180], [0, 1, 3, 7],
                                                ["q30", "lin"], [1, 3, 7]):
    if skip >= lb:
        continue
    mom = c.shift(skip) / c.shift(lb) - 1
    if wtype == "q30":
        w = rl.quantile_weights(mom, mask, q=0.3, gross=1.0)
    else:
        w = rl.linear_weights(rl.rank_xs(mom, mask), mask, gross=1.0)
    if hold > 1:
        w = w.rolling(hold, min_periods=1).mean()
    net, st = rl.backtest_xs(w, c, cost_bps=COST, ann=ANN)
    sp = rl.split_stats(net, SPLITS, ann=ANN)
    rg = regime_table(net, btc)
    rows.append(dict(lb=lb, skip=skip, w=wtype, hold=hold,
                     full=sp.loc["full", "Sharpe"], IS=sp.loc["IS", "Sharpe"], OOS=sp.loc["OOS", "Sharpe"],
                     bull=rg.loc["bull", "Sharpe"], bear=rg.loc["bear", "Sharpe"],
                     cagr=sp.loc["full", "CAGR"], mdd=sp.loc["full", "MaxDD"], turn=st["Turnover_ann"]))
df = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(df.sort_values("full", ascending=False).head(25).round(2).to_string())
print("\nmedian by lookback:\n", df.groupby("lb")[["full", "IS", "OOS", "bull", "bear"]].median().round(2))
print("\nmedian by skip:\n", df.groupby("skip")[["full", "IS", "OOS", "bull", "bear"]].median().round(2))
print("\nmedian by hold:\n", df.groupby("hold")[["full", "IS", "OOS", "bull", "bear"]].median().round(2))
print("\nmedian by w:\n", df.groupby("w")[["full", "IS", "OOS", "bull", "bear"]].median().round(2))
df.to_csv(os.path.join(HERE, "grid_01.csv"), index=False)
