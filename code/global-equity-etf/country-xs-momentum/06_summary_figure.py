"""Aggregate all variant results into one summary bar chart + equity curve of best variant."""
import os, sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import perf_stats

sys.path.insert(0, HERE)
from importlib import import_module
_bt = import_module("02_backtest")
_v = import_module("03_variants")
_r = import_module("04_residual_and_ensemble")

load_prices = _bt.load_prices
vol_target_scale = _bt.vol_target_scale
backtest = _bt.backtest

ANN = 252
OUT = os.path.join(os.path.dirname(HERE), "..", "..", "past_research",
                   "global-equity-etf", "country-xs-momentum")
os.makedirs(OUT, exist_ok=True)

px = load_prices()
all_dates = px.index
split_ix = int(len(all_dates) * 0.6)
split = all_dates[split_ix]

def _ss(net):
    is_ = perf_stats(net.loc[:split], ann=ANN)["Sharpe"]
    oos = perf_stats(net.loc[split:], ann=ANN)["Sharpe"]
    full = perf_stats(net, ann=ANN)["Sharpe"]
    return full, is_, oos

results = {}

# XS mom variants
for lb, sk in [(126, 5), (252, 21), (63, 5)]:
    w = _bt.xs_momentum_weights(px, lookback=lb, skip=sk, top_k=3, bot_k=3)
    w_v = vol_target_scale(w, px, target_vol=0.10)
    net, st = backtest(w_v, px, cost_bps=5.0)
    results[f"XS_mom_{lb}_{sk}_L3S3"] = _ss(net)

# TS mom
w = _bt.ts_momentum_weights(px, fast=32, slow=128)
w_v = vol_target_scale(w, px, target_vol=0.10)
net, _ = backtest(w_v, px, cost_bps=5.0)
results["TS_mom_32_128"] = _ss(net)

# Reversal
w = _bt.st_reversal_weights(px, lookback=5, top_k=3, bot_k=3)
w_v = vol_target_scale(w, px, target_vol=0.10)
net, _ = backtest(w_v, px, cost_bps=5.0)
results["ST_rev_5d"] = _ss(net)

# Long-only trend-gated
for lb in [63, 126]:
    w = _v.long_only_top_k(px, lookback=lb, skip=5, top_k=3, trend_gate_ma=200)
    w_v = vol_target_scale(w, px, target_vol=0.15)
    net, _ = backtest(w_v, px, cost_bps=5.0)
    results[f"LO_top3_{lb}_trendgate"] = _ss(net)

# Rel strength
w = _v.rel_strength_xs(px, lookback=126, skip=5, top_k=3, bot_k=3)
w_v = vol_target_scale(w, px, target_vol=0.10)
net, _ = backtest(w_v, px, cost_bps=5.0)
results["RS_xs_126_5"] = _ss(net)

# Low vol
w = _v.low_vol_tilt(px, vol_win=63, top_k=3, bot_k=3)
w_v = vol_target_scale(w, px, target_vol=0.10)
net, _ = backtest(w_v, px, cost_bps=5.0)
results["LowVol_63d"] = _ss(net)

# Residual XS
w = _r.residual_xs_mom(px, lookback=126, skip=5, top_k=3, bot_k=3)
w_v = vol_target_scale(w, px, target_vol=0.10)
net, _ = backtest(w_v, px, cost_bps=5.0)
results["Resid_xs_126_5"] = _ss(net)

# Residual TS
w = _r.residual_ts_mom(px, fast=32, slow=128)
w_v = vol_target_scale(w, px, target_vol=0.10)
net, _ = backtest(w_v, px, cost_bps=5.0)
results["Resid_ts_32_128"] = _ss(net)

# SPY BH benchmark
r = px["SPY"].pct_change().fillna(0.0)
results["SPY_BH"] = _ss(r)

# Best variant net for equity curve
w_best = _v.long_only_top_k(px, lookback=126, skip=5, top_k=3, trend_gate_ma=200)
w_best_v = vol_target_scale(w_best, px, target_vol=0.15)
net_best, st_best = backtest(w_best_v, px, cost_bps=5.0, name="LO_top3_126_trendgate")

# Save summary
df = pd.DataFrame(results, index=["Full", "IS", "OOS"]).T.round(3)
df.to_csv(os.path.join(OUT, "variants_summary.csv"))
print(df)

# Bar chart
fig, ax = plt.subplots(figsize=(11, 5))
df_sorted = df.sort_values("OOS", ascending=False)
x = np.arange(len(df_sorted))
w = 0.28
ax.bar(x - w, df_sorted["Full"], w, label="Full-sample")
ax.bar(x, df_sorted["IS"], w, label="In-sample")
ax.bar(x + w, df_sorted["OOS"], w, label="Out-of-sample")
ax.axhline(2.0, color="crimson", linestyle="--", label="Target Sharpe = 2.0")
ax.axhline(0.0, color="k", linewidth=0.5)
ax.set_xticks(x)
ax.set_xticklabels(df_sorted.index, rotation=45, ha="right")
ax.set_ylabel("Sharpe")
ax.set_title("Global-equity-ETF cross-sectional strategies — Sharpe by regime (5 bp costs)")
ax.legend()
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "variants_sharpe_bar.png"), dpi=110)
plt.close(fig)

# Equity curve of best variant + SPY
fig, ax = plt.subplots(figsize=(11, 5))
eq_best = (1 + net_best).cumprod()
eq_spy = (1 + r).cumprod()
ax.plot(eq_best.index, eq_best, label="Long-only top3 126d trend-gate (best XS variant)")
ax.plot(eq_spy.index, eq_spy, label="SPY buy-and-hold")
ax.axvline(split, color="grey", linestyle="--", label="IS/OOS split")
ax.set_yscale("log")
ax.set_ylabel("Equity (log)")
ax.set_title("Best cross-sectional variant vs SPY (5 bp costs)")
ax.legend()
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "best_variant_equity.png"), dpi=110)
plt.close(fig)

print(f"\nWrote figures + CSV to {OUT}")
print(f"\nBest variant stats:\n{st_best.round(3)}")
