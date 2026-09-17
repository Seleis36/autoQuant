"""Final config evaluation: stats, splits, bear windows, yearly, cost & short-funding sensitivity,
block bootstrap, deflated Sharpe, walk-forward, BTC beta. Writes backtest_series.parquet."""
from common import *
from strategy import alt_bab_weights
import itertools, json

p = load_panel(); close_all = clean_close(p["Close"]); vol_all = p["Volume"].reindex(columns=close_all.columns)
alts = [t for t in ALTS if t in close_all]
c, v, btc = close_all[alts], vol_all[alts], close_all["BTC-USD"]
ret = c.pct_change(); btc_ret = btc.pct_change()
START = "2018-03-08"                       # first day the PIT universe is populated
w = alt_bab_weights(c, v, btc)             # spec defaults
w = w.loc[START:]; cc = c.loc[START:]
out = {}

net, st = rl.backtest_xs(w, cc, cost_bps=COST, ann=ANN, name="xs-momentum-neutral")
gross_ret, _ = rl.backtest_xs(w, cc, cost_bps=0.0, ann=ANN)
pd.set_option("display.width", 250)
print("=== full-sample stats @10bp ===\n", rl.fmt(pd.DataFrame(st).T).T.to_string())
print("\n=== splits ===\n", rl.fmt(rl.split_stats(net, SPLITS, ann=ANN)).to_string())
print("\n=== ex-post BTC bear windows ===\n", rl.fmt(bear_stats(net)).to_string())
print("\n=== yearly ===\n", yearly(net.loc["2018":]).round(2).to_string())
print("\n=== BTC-SMA200 regime ===\n", rl.fmt(regime_table(net, btc)).to_string())

# exposure / beta
w_eff = w.shift(1).fillna(0.0)
expo = pd.DataFrame({"gross": w_eff.abs().sum(axis=1), "net": w_eff.sum(axis=1),
                     "long": w_eff.clip(lower=0).sum(axis=1), "short": -w_eff.clip(upper=0).sum(axis=1)})
bull = (btc > btc.rolling(50).mean()).reindex(w.index)
print("\nexposure (mean):", expo.mean().round(3).to_dict(), " max gross:", round(expo.gross.max(), 3))
print("time in bull regime:", round(bull.mean(), 3))
x = btc_ret.reindex(net.index).fillna(0)
for nm, m in (("all", net.index == net.index), ("bull", bull.values), ("bear", ~bull.values)):
    print(f"beta to BTC [{nm}]: {np.cov(x[m], net[m])[0,1]/x[m].var():.3f}  corr {np.corrcoef(x[m], net[m])[0,1]:.3f}")
eth_ret = close_all["ETH-USD"].pct_change().reindex(net.index).fillna(0)
print("corr to ETH:", round(np.corrcoef(eth_ret, net)[0, 1], 3))
n_names = (w_eff.abs() > 0).sum(axis=1); print("names held: mean", round(n_names.mean(), 1), "min", n_names[n_names > 0].min())
print("max single-name |weight|:", round(w_eff.abs().max().max(), 3))

# cost sensitivity
print("\n=== cost sensitivity (bp/side) ===")
for cb in [0, 5, 10, 15, 20, 30]:
    n_, s_ = rl.backtest_xs(w, cc, cost_bps=cb, ann=ANN)
    sp = rl.split_stats(n_, SPLITS, ann=ANN)
    print(f"{cb:>3}bp: full {sp.loc['full','Sharpe']:.2f}  IS {sp.loc['IS','Sharpe']:.2f}  OOS {sp.loc['OOS','Sharpe']:.2f}  CAGR {sp.loc['full','CAGR']:.1%}  bear {bear_stats(n_).loc['bear_pooled','Sharpe']:.2f}")
# short-leg carry drag (perp funding / borrow), annualised on short notional
print("\n=== short-leg carry drag (annualised % of short notional) ===")
for drag in [0, 5, 10, 20]:
    n_ = net - expo["short"] * drag / 100 / ANN
    sp = rl.split_stats(n_, SPLITS, ann=ANN)
    print(f"{drag:>3}%: full {sp.loc['full','Sharpe']:.2f}  OOS {sp.loc['OOS','Sharpe']:.2f}  CAGR {sp.loc['full','CAGR']:.1%}")

# block bootstrap
rng = np.random.default_rng(0); r = net.values; n = len(r); B = 30; draws = []
for _ in range(2000):
    idx = np.concatenate([np.arange(s, s + B) for s in rng.integers(0, n - B, n // B + 1)])[:n]
    x_ = r[idx]; draws.append(x_.mean() / x_.std() * np.sqrt(ANN))
draws = np.array(draws)
print(f"\nblock bootstrap (30d, 2000): mean {draws.mean():.2f}  5-95% [{np.percentile(draws,5):.2f}, {np.percentile(draws,95):.2f}]  P(Sh>1)={np.mean(draws>1):.1%}  P(Sh>0)={np.mean(draws>0):.1%}")
# deflated Sharpe for several assumed effective trial counts
for nt in [10, 50, 200, 1000]:
    print(f"DSR (n_trials={nt}): {rl.deflated_sharpe(st['Sharpe'], len(net), nt, skew=st['Skew'], kurt=st['Kurt']+3):.3f}")

# walk-forward over the final-family grid (switch mode), yearly re-selection, expanding window
grid = list(itertools.product([15, 20, 25], [30, 60, 90], [0.25, 0.3, 0.4], [50, 100], [7, 14, 21]))
N = {}
for g in grid:
    wg = alt_bab_weights(c, v, btc, n_top=g[0], beta_halflife=g[1], q=g[2], regime_sma=g[3], hold=g[4]).loc[START:]
    N[g] = rl.backtest_xs(wg, cc, cost_bps=COST, ann=ANN)[0]
N = pd.DataFrame(N)
wf = []
for yr in range(2021, 2027):
    train = N.loc[:f"{yr-1}-12-31"]; sh = train.mean() / train.std() * np.sqrt(ANN); best = sh.idxmax()
    seg = N.loc[f"{yr}-01-01":f"{yr}-12-31", best]; wf.append(seg)
    print(f"WF {yr}: picked {best}  train Sharpe {sh.max():.2f}  realised {seg.mean()/seg.std()*np.sqrt(ANN):.2f}")
wf = pd.concat(wf)
print("walk-forward stitched 2021-2026 Sharpe:", round(wf.mean() / wf.std() * np.sqrt(ANN), 2))
avg = N.mean(axis=1)
print("equal-weight of all 162 configs:", rl.fmt(rl.split_stats(avg, SPLITS, ann=ANN)[["Sharpe","CAGR","MaxDD"]]).to_string())
print("grid distribution (full/IS/OOS/bear):", N.apply(lambda s: s.mean()/s.std()*np.sqrt(ANN)).describe().round(2).to_dict())

# save series
series = pd.DataFrame({"net_10bp": net, "gross_0bp": gross_ret, "btc_close": btc.reindex(net.index),
                       "gross_exposure": expo.gross, "net_exposure": expo.net, "bull_regime": bull.astype(float)})
series.to_parquet(os.path.join(HERE, "..", "..", "..", "alphas", "crypto-alts", "xs-momentum-neutral", "backtest_series.parquet"))
w.to_parquet(os.path.join(HERE, "weights_final.parquet"))
N.to_parquet(os.path.join(HERE, "grid_nets.parquet"))
