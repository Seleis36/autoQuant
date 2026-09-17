"""Clean parametrisation robustness grid + walk-forward selection."""
from common import *
from strategy import alt_bab_weights
import itertools

p = load_panel(); close_all = clean_close(p["Close"]); vol_all = p["Volume"].reindex(columns=close_all.columns)
alts = [t for t in ALTS if t in close_all]
c, v, btc = close_all[alts], vol_all[alts], close_all["BTC-USD"]

def evaluate(w, cost=COST):
    net, st = rl.backtest_xs(w, c, cost_bps=cost, ann=ANN)
    sp = rl.split_stats(net, SPLITS, ann=ANN); bs = bear_stats(net)
    return net, dict(full=sp.loc["full","Sharpe"], IS=sp.loc["IS","Sharpe"], OOS=sp.loc["OOS","Sharpe"],
                     xbear=bs.loc["bear_pooled","Sharpe"], xnon=bs.loc["non_bear","Sharpe"],
                     minwin=bs.iloc[1:6]["Sharpe"].min(), cagr=sp.loc["full","CAGR"], mdd=sp.loc["full","MaxDD"],
                     turn=st["Turnover_ann"], netexp=st["AvgNet"])

rows = {}; nets = {}
grid = list(itertools.product([15, 20, 25], [30, 60, 90], [0.25, 0.3, 0.4], [50, 100], [7, 14, 21]))
for ntop, hl, q, sma, hold in grid:
    w = alt_bab_weights(c, v, btc, n_top=ntop, beta_halflife=hl, q=q, regime_sma=sma, hold=hold)
    nets[(ntop, hl, q, sma, hold)], rows[(ntop, hl, q, sma, hold)] = evaluate(w)
df = pd.DataFrame(rows).T; df.index.names = ["ntop", "hl", "q", "sma", "hold"]
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print("n configs:", len(df))
print(df.describe().round(2).to_string())
print("\ntop 15:\n", df.sort_values("full", ascending=False).head(15).round(2).to_string())
for k in df.index.names:
    print(f"\nmedian by {k}:\n", df.groupby(level=k)[["full","IS","OOS","xbear","xnon","minwin","mdd","turn"]].median().round(2).to_string())
print("\nP(full>=1):", (df.full >= 1).mean().round(2), " P(OOS>=1):", (df.OOS >= 1).mean().round(2),
      " P(xbear>0):", (df.xbear > 0).mean().round(2), " P(all 5 windows>0):", (df.minwin > 0).mean().round(2))
df.to_csv(os.path.join(HERE, "robust_06.csv"))

# ---- walk-forward: pick best-full-Sharpe config on expanding window, apply next calendar year
N = pd.DataFrame(nets)
wf = []
for yr in range(2021, 2027):
    train = N.loc[:f"{yr-1}-12-31"]
    sh = train.mean() / train.std() * np.sqrt(ANN)
    best = sh.idxmax()
    seg = N.loc[f"{yr}-01-01":f"{yr}-12-31", best]
    wf.append(seg); print(f"WF {yr}: picked {best}  IS-Sharpe {sh.max():.2f}  realised {seg.mean()/seg.std()*np.sqrt(ANN):.2f}")
wf = pd.concat(wf)
print("walk-forward stitched 2021-2026:", rl.perf_stats(wf, ann=ANN)[["Sharpe","CAGR","MaxDD"]].round(3).to_dict())
print(bear_stats(wf).round(2).to_string())
# median-config (selection-free) reference
med = N.median(axis=1); print("\nequal-weight of ALL configs:", rl.perf_stats(N.mean(axis=1), ann=ANN)[["Sharpe","CAGR","MaxDD"]].round(3).to_dict())
print(rl.split_stats(N.mean(axis=1), SPLITS, ann=ANN)[["Sharpe","CAGR","MaxDD"]].round(2).to_string())
print(bear_stats(N.mean(axis=1)).round(2).to_string())
