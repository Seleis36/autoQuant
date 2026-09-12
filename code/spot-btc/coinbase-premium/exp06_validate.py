"""exp06 -- validation of the locked candidate (strategy.py defaults), 10 bp/side, hourly bars.
  walk-forward re-selection, lookahead probe, block bootstrap, deflated Sharpe (N=400 trials),
  Bitstamp-based premium replication, randomised-premium placebo, vectorbt cross-check.
"""
import os, sys, warnings, itertools
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared"))
from research_lib import DATA_DIR, backtest, split_stats, deflated_sharpe, perf_stats
from strategy import target_weight, premium_zscore, hysteresis_state, HOURS_PER_YEAR as HANN
pd.set_option("display.width", 250)
IS_END, OOS_START = "2022-12-31", "2023-01-01"
def naive(df): return (df.tz_convert("UTC").tz_localize(None) if df.index.tz is not None else df).sort_index()
b = naive(pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h_flow.parquet")))
c = naive(pd.read_parquet(os.path.join(DATA_DIR, "COINBASE_BTCUSD_1h.parquet")))
idx = b.index.intersection(c.index); px, cx = b.loc[idx, "Close"], c.loc[idx, "Close"]
def rep(w, cost=10):
    net, st = backtest(w, px, cost_bps=cost, ann=HANN)
    sp = split_stats(net, {"IS": (None, IS_END), "OOS": (OOS_START, None)}, ann=HANN)
    return net, st, sp
w0 = target_weight(px, cx)
net0, st0, sp0 = rep(w0)
print("=== candidate: full", round(st0["Sharpe"], 3), "IS", round(sp0.loc["IS", "Sharpe"], 3), "OOS", round(sp0.loc["OOS", "Sharpe"], 3),
      "CAGR", round(st0["CAGR"], 3), "MaxDD", round(st0["MaxDD"], 3), "TO/yr", round(st0["Turnover_ann"], 1), "Expo", round(st0["AvgExposure"], 3),
      "tNW", round(st0["t_NW"], 2), "N", int(st0["N"]))
net0.to_frame("net").to_csv(os.path.join(HERE, "candidate_net_returns.csv"))

# ---- walk-forward: re-select (enter, exit, trend) each calendar year on all prior data
print("\n=== strict walk-forward (expanding train, 36 candidates, test years 2020-2026)")
grid = list(itertools.product((0.0, 0.5, 1.0, 1.5), (-1.5, -1.0, -0.5), (20 * 24, 50 * 24, 100 * 24)))
cache = {}
for g in grid:
    w = target_weight(px, cx, enter=g[0], exit_=g[1], trend_hours=g[2])
    cache[g] = backtest(w, px, cost_bps=10, ann=HANN)[0]
segs, picks = [], []
for Y in range(2020, 2027):
    tr = {g: n.loc[:f"{Y-1}-12-31"] for g, n in cache.items()}
    best = max(grid, key=lambda g: tr[g].mean() / tr[g].std())
    seg = cache[best].loc[f"{Y}-01-01":f"{Y}-12-31"]
    segs.append(seg); picks.append((Y, best, round(tr[best].mean() / tr[best].std() * np.sqrt(HANN), 2), round(seg.mean() / seg.std() * np.sqrt(HANN), 2)))
wf = pd.concat(segs); wfs = perf_stats(wf, ann=HANN)
for p in picks: print("  ", p)
print("walk-forward Sharpe", round(wfs["Sharpe"], 3), "CAGR", round(wfs["CAGR"], 3), "MaxDD", round(wfs["MaxDD"], 3), "tNW", round(wfs["t_NW"], 2))
print("grid summary (full-sample Sharpe over 36 cells): min/median/max",
      round(min(perf_stats(n, ann=HANN)["Sharpe"] for n in cache.values()), 2), round(np.median([perf_stats(n, ann=HANN)["Sharpe"] for n in cache.values()]), 2),
      round(max(perf_stats(n, ann=HANN)["Sharpe"] for n in cache.values()), 2))

# ---- lookahead probe
print("\n=== lookahead probe: Sharpe when weight is shifted by k bars (k>0 = ILLEGAL future weight; k<0 = legal extra lag)")
for k in (-2, -1, 0, 1, 2, 4, 12, 24):
    print(f"  shift {k:+d}: {backtest(w0.shift(-k).fillna(0), px, cost_bps=10, ann=HANN)[1]['Sharpe']:.3f}")

# ---- stationary block bootstrap on daily-aggregated net returns
print("\n=== block bootstrap (daily-aggregated returns, 21-day blocks, 2000 reps)")
d = (1 + net0).groupby(net0.index.floor("D")).prod() - 1
rng = np.random.default_rng(0); L = 21; n = len(d); vals = d.values
shs = []
for _ in range(2000):
    starts = rng.integers(0, n - L, size=n // L + 1)
    smp = np.concatenate([vals[s:s + L] for s in starts])[:n]
    shs.append(smp.mean() / smp.std() * np.sqrt(365))
shs = np.array(shs)
print("  median", round(np.median(shs), 2), "5-95%", np.round(np.percentile(shs, [5, 95]), 2), "P(Sh>1)", round((shs > 1).mean(), 3), "P(Sh>2)", round((shs > 2).mean(), 3))
print("  deflated Sharpe P(true SR>0) with 400 trials:", round(deflated_sharpe(d.mean() / d.std() * np.sqrt(365), len(d), 400, skew=d.skew(), kurt=d.kurtosis() + 3, ann=365), 3))

# ---- Bitstamp-based premium (Coinbase vs Bitstamp, both USD) as the signal, else identical
print("\n=== replication: premium computed vs Bitstamp BTC/USD instead of Binance (2019-11+)")
bs = naive(pd.read_parquet(os.path.join(DATA_DIR, "BITSTAMP_1h.parquet")))["Close"]
i2 = idx.intersection(bs.index)
z_bs = premium_zscore(bs.reindex(i2), cx.reindex(i2))
px2 = px.reindex(i2)
trend = (px2 > px2.rolling(1200).mean()).astype(float)
ewv = px2.pct_change().ewm(halflife=480, min_periods=480).std() * np.sqrt(HANN); scale = (0.40 / ewv).clip(0, 1).fillna(0)
w_bs = hysteresis_state(z_bs) * trend * scale
w_ref = target_weight(px2, cx.reindex(i2))
for nm, w in (("premium vs Bitstamp", w_bs), ("premium vs Binance (same window)", w_ref), ("trend x vol only (same window)", trend * scale)):
    n_, s_ = backtest(w, px2, cost_bps=10, ann=HANN); sp_ = split_stats(n_, {"IS": (None, IS_END), "OOS": (OOS_START, None)}, ann=HANN)
    print(f"  {nm:36s} full {s_['Sharpe']:.2f}  IS {sp_.loc['IS','Sharpe']:.2f}  OOS {sp_.loc['OOS','Sharpe']:.2f}")

# ---- placebo: block-shuffled premium z (keeps trend x vol, destroys premium timing)
print("\n=== placebo: premium z-score block-shuffled (30-day blocks), 200 draws")
z = premium_zscore(px, cx); trend = (px > px.rolling(1200).mean()).astype(float)
ewv = px.pct_change().ewm(halflife=480, min_periods=480).std() * np.sqrt(HANN); scale = (0.40 / ewv).clip(0, 1).fillna(0)
zv = z.values; B = 720; nb = len(zv) // B; rng = np.random.default_rng(1); pl = []
for _ in range(200):
    order = rng.permutation(nb)
    zs = np.concatenate([zv[o * B:(o + 1) * B] for o in order]); zs = np.concatenate([zs, zv[nb * B:]])
    w = hysteresis_state(pd.Series(zs, index=z.index)) * trend * scale
    pl.append(backtest(w, px, cost_bps=10, ann=HANN)[1]["Sharpe"])
pl = np.array(pl)
print("  placebo mean", round(pl.mean(), 2), "sd", round(pl.std(), 2), "max", round(pl.max(), 2), "| real", round(st0["Sharpe"], 2), "empirical p", round((pl >= st0["Sharpe"]).mean(), 3))

# ---- vectorbt cross-check
print("\n=== vectorbt cross-check (from_orders, targetpercent, fees 10bp)")
import vectorbt as vbt
w_shift = w0.shift(1).fillna(0)   # vbt executes at bar close; our weight at t applies to bar t+1's return
pf = vbt.Portfolio.from_orders(px, size=w_shift, size_type="targetpercent", fees=0.001, init_cash=1.0, freq="1h")
r = pf.returns()
print("  vbt Sharpe", round(r.mean() / r.std() * np.sqrt(HANN), 3), "custom", round(st0["Sharpe"], 3), "corr", round(r.corr(net0), 5),
      "vbt total return", round(pf.total_return(), 3), "custom", round((1 + net0).prod() - 1, 3))
