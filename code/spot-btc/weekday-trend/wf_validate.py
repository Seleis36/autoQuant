"""Walk-forward + robustness validation of the final strategy.

Strategy (default params):
    weight_t = trend * momentum * vol_scalar * skip_thu_gate
where
    trend       = 1{close_t > SMA(200)}
    momentum    = 1{return_20 > 0}
    vol_scalar  = clip(0.40 / EWMA_vol_20, 0, 1.0)
    skip_thu    = 0 if (t+1).dayofweek == 3 else 1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import numpy as np
import pandas as pd
from research_lib import load_btc, backtest, perf_stats, ewm_vol, split_stats, fmt, newey_west_t, deflated_sharpe

btc = load_btc()
c = btc["Close"]
r = c.pct_change()

def weights(T=200, M=20, target=0.4, hl=20, cap=1.0, skip_dow=(3,)):
    trend = (c > c.rolling(T).mean()).astype(float)
    mom = (c.pct_change(M) > 0).astype(float)
    v = ewm_vol(r, halflife=hl)
    scale = (target / v).clip(0, cap).fillna(0)
    next_dow = (c.index + pd.Timedelta(days=1)).dayofweek
    gate = pd.Series([0.0 if d in skip_dow else 1.0 for d in next_dow], index=c.index)
    return (trend * mom * scale * gate).fillna(0)

# 1. Full-sample stats
w = weights()
net, stats = backtest(w, c, cost_bps=10.0, name="weekday-trend")
print("=== Full-sample (2015-01-01 -> 2026-09-06), 10bp/side ===")
print(fmt(pd.DataFrame([stats]).T.T))

# 2. IS/OOS split
IS = ("2015-01-01", "2021-12-31")
OOS = ("2022-01-01", "2026-09-06")
print("\n=== IS / OOS ===")
print(fmt(split_stats(net, {"IS": IS, "OOS": OOS})))

# 3. Cost sensitivity
print("\n=== Cost sensitivity ===")
for bps in [1.0, 3.0, 5.0, 10.0, 20.0, 30.0]:
    _, s = backtest(w, c, cost_bps=bps)
    print(f"cost={bps:>4.1f} bp/side: Sharpe={s.Sharpe:.2f} CAGR={s.CAGR*100:.1f}%")

# 4. Parameter neighborhood robustness
print("\n=== Parameter neighborhood (min-split IS/OOS) ===")
grid = []
for T in [100, 150, 200, 250]:
    for M in [10, 20, 40]:
        for tv in [0.30, 0.40, 0.50]:
            for hl in [10, 20, 30]:
                w2 = weights(T=T, M=M, target=tv, hl=hl)
                n2, s2 = backtest(w2, c, cost_bps=10.0)
                s_is = perf_stats(n2.loc[IS[0]:IS[1]]).Sharpe
                s_oos = perf_stats(n2.loc[OOS[0]:OOS[1]]).Sharpe
                grid.append((T, M, tv, hl, s2.Sharpe, s_is, s_oos))
gdf = pd.DataFrame(grid, columns=["T", "M", "tv", "hl", "Full", "IS", "OOS"])
gdf["min"] = gdf[["IS", "OOS"]].min(axis=1)
print(f"Median full={gdf.Full.median():.2f}  IS={gdf.IS.median():.2f}  OOS={gdf.OOS.median():.2f}")
print(f"Frac. Full>1.3: {(gdf.Full>1.3).mean()*100:.0f}%  Frac. OOS>0.9: {(gdf.OOS>0.9).mean()*100:.0f}%")
print(f"Frac. IS AND OOS > 1.0: {((gdf.IS>1.0) & (gdf.OOS>1.0)).mean()*100:.0f}%")

# 5. Walk-forward: retrain over 3-yr rolling window, apply next 1-yr
print("\n=== Walk-forward validation ===")
param_grid = []
for T in [100, 150, 200]:
    for M in [10, 20, 40]:
        for tv in [0.30, 0.40, 0.50]:
            param_grid.append(dict(T=T, M=M, target=tv, hl=20, cap=1.0, skip_dow=(3,)))

wf_start = pd.Timestamp("2018-01-01")
train_yrs = 3
step_yrs = 1
pieces = []
picks = []
dates = pd.date_range(wf_start, "2026-09-01", freq=pd.DateOffset(years=step_yrs))
for i in range(len(dates) - 1):
    test_start = dates[i]
    test_end = dates[i + 1]
    train_end = test_start
    train_start = train_end - pd.DateOffset(years=train_yrs)

    best_sh, best_p, best_net = -np.inf, None, None
    for p in param_grid:
        w_p = weights(**p)
        n_p, _ = backtest(w_p, c, cost_bps=10.0)
        sh = perf_stats(n_p.loc[train_start:train_end]).Sharpe
        if sh > best_sh:
            best_sh, best_p, best_net = sh, p, n_p
    pieces.append(best_net.loc[test_start:test_end])
    picks.append((test_start.date(), best_p, best_sh))

wf_net = pd.concat(pieces).dropna()
wf_stats = perf_stats(wf_net, name="walk-forward")
print(f"WF (train {train_yrs}yr, step {step_yrs}yr, {len(param_grid)} candidates)")
print(fmt(pd.DataFrame([wf_stats]).T.T))
print("Picks per test period:")
for p in picks:
    print(f"  {p[0]}: train_Sh={p[2]:.2f}  params={p[1]}")

# 6. Bootstrap of Sharpe
print("\n=== Bootstrap 95% CI on full-sample Sharpe (block bootstrap, 2000 iters) ===")
rng = np.random.default_rng(42)
rets = net.dropna().values
block = 21
nboot = 2000
sharpes = []
n_blocks = int(np.ceil(len(rets) / block))
for _ in range(nboot):
    idxs = rng.integers(0, len(rets) - block, size=n_blocks)
    sample = np.concatenate([rets[i:i+block] for i in idxs])[:len(rets)]
    sd = sample.std()
    if sd > 0:
        sharpes.append(sample.mean() / sd * np.sqrt(365))
sharpes = np.array(sharpes)
print(f"Median Sharpe: {np.median(sharpes):.2f}")
print(f"95% CI: [{np.percentile(sharpes,2.5):.2f}, {np.percentile(sharpes,97.5):.2f}]")
print(f"P(Sharpe > 1): {(sharpes > 1).mean()*100:.1f}%")
print(f"P(Sharpe > 1.5): {(sharpes > 1.5).mean()*100:.1f}%")

# 7. Deflated Sharpe
n_trials = len(gdf)
dsr = deflated_sharpe(stats.Sharpe, len(net), n_trials=n_trials, skew=stats.Skew, kurt=stats.Kurt+3)
print(f"\nDeflated Sharpe P(true SR > 0) over {n_trials} trials: {dsr:.3f}")

# 8. Regime breakdown
print("\n=== Yearly stats ===")
years = sorted(set(net.index.year))
rows = []
for y in years:
    seg = net[net.index.year == y]
    if len(seg) < 100:
        continue
    s = perf_stats(seg)
    rows.append((y, s.Sharpe, s.CAGR, s.MaxDD, s.AvgExposure if "AvgExposure" in s.index else np.nan))
print(pd.DataFrame(rows, columns=["yr", "Sharpe", "CAGR", "MDD", "Expo"]).round(2).to_string(index=False))

# 9. Save equity curve for plotting
outdir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "alphas", "spot-btc", "weekday-trend")
os.makedirs(outdir, exist_ok=True)
eq_df = pd.DataFrame({"strategy": (1 + net).cumprod(),
                      "buy_and_hold": c / c.iloc[0]})
eq_df.to_csv(os.path.join(outdir, "equity.csv"))
print(f"\nEquity curve saved to {outdir}/equity.csv")

# 10. Plot
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    axes[0].semilogy((1 + net).cumprod(), label="weekday-trend", lw=1.5)
    axes[0].semilogy(c / c.iloc[0], label="Buy & hold BTC", lw=1, alpha=0.7)
    axes[0].legend(); axes[0].set_title("weekday-trend equity curve (log scale, 10bp/side)")
    axes[0].axvline(pd.Timestamp("2022-01-01"), color="gray", ls="--", alpha=0.5, label="OOS")
    axes[0].grid(alpha=0.3)
    dd = (1 + net).cumprod() / (1 + net).cumprod().cummax() - 1
    axes[1].fill_between(dd.index, dd.values, 0, color="red", alpha=0.3)
    axes[1].set_title("Drawdown"); axes[1].grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "equity.png"), dpi=110)
    print(f"Plot saved to {outdir}/equity.png")
except Exception as e:
    print(f"Plot failed: {e}")
