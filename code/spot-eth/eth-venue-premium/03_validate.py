"""eth-venue-premium 03: final validation of strategy.target_weight (the deployable function).

(1) research_lib backtest vs vectorbt cross-check
(2) truncation lookahead test: weights recomputed on data cut at t must equal full-sample weights at t
(3) headline stats, yearly table, exposure/turnover
(4) Thursday-skip stacked variant (from session-momentum) -- reported, not adopted
(5) figures + equity csv into alphas/spot-eth/eth-venue-premium/
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import pandas as pd
from ethdata import rl, bars, bt, row, to_daily, trend_filter_weights_daily, _ROOT
from fetch_coinbase import load as cb_load
from strategy import target_weight

OUT = os.path.join(_ROOT, "alphas", "spot-eth", "eth-venue-premium")
bn = bars("ETHUSDT", "1h")["Close"]
cb = cb_load("ETH-USD")["Close"]
w = target_weight(bn, cb)
net, s = bt(w, bn)
nd = to_daily(net)

# (1) vectorbt cross-check
import vectorbt as vbt
# vectorbt fills an order placed at bar t at close_t, so the position over (t, t+1] is size[t]: pass w
# unshifted. targetpercent re-trades price drift every bar, so it pays slightly more fees than rl.
pf = vbt.Portfolio.from_orders(bn, size=w.fillna(0), size_type="targetpercent", fees=0.001,
                               freq="1h", init_cash=1e6)
vr = pf.returns()
print("(1) research_lib daily Sharpe:", round(rl.perf_stats(nd, ann=365)["Sharpe"], 3),
      " vectorbt daily Sharpe:", round(rl.perf_stats(to_daily(vr), ann=365)["Sharpe"], 3),
      " total return rl/vbt:", round((1 + net).prod() - 1, 2), round(pf.total_return(), 2))

# (2) truncation test at 12 random timestamps
rng = np.random.default_rng(1)
ts = rng.choice(bn.index[5000:], 12, replace=False)
bad = 0
for t in ts:
    wt = target_weight(bn.loc[:t], cb.loc[:t]).iloc[-1]
    if abs(wt - w.loc[t]) > 1e-9:
        bad += 1; print("   MISMATCH", t, wt, w.loc[t])
print(f"(2) truncation test: {len(ts) - bad}/{len(ts)} identical")

# (3) headline
print("(3) headline:", {k: round(float(v), 3) for k, v in row(nd, ann=365).items()})
st = rl.perf_stats(nd, ann=365)
print("    Sortino", round(st["Sortino"], 2), "Calmar", round(st["Calmar"], 2), "t_NW", round(st["t_NW"], 2),
      "Turnover/yr", round(s["Turnover_ann"], 1), "AvgExp", round(s["AvgExposure"], 3), "TIM", round(s["TimeInMkt"], 3))
yr = pd.DataFrame({
    "Sharpe": nd.groupby(nd.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(365)),
    "Return": nd.groupby(nd.index.year).apply(lambda x: (1 + x).prod() - 1),
    "MaxDD": nd.groupby(nd.index.year).apply(lambda x: ((1 + x).cumprod() / (1 + x).cumprod().cummax() - 1).min()),
})
d = bn.resample("1D").last()
w_live = trend_filter_weights_daily(d).shift(1, freq="D").reindex(bn.index, method="ffill").fillna(0)
live = to_daily(bt(w_live, bn)[0])
yr["live_TF_Sharpe"] = live.groupby(live.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(365))
print(yr.round(3).to_string())
print("    corr with live eth-trend-filter (daily):", round(nd.corr(live), 2))

# (4) Thursday skip stacked
flat = pd.Series(bn.index.dayofweek == 3, index=bn.index).astype(float).shift(-1).fillna(0)
n4 = to_daily(bt(w * (1 - flat), bn)[0])
print("(4) + Thursday skip:", {k: round(float(v), 2) for k, v in row(n4, ann=365).items() if k in ("Sh_Full", "Sh_IS", "Sh_OOS", "MDD")})

# (5) figures
os.makedirs(OUT, exist_ok=True)
eq = pd.DataFrame({"eth-venue-premium": (1 + nd).cumprod(), "eth-trend-filter (live)": (1 + live).cumprod(),
                   "ETH buy & hold": d.reindex(nd.index) / d.reindex(nd.index).iloc[0]})
eq.to_csv(os.path.join(OUT, "equity.csv"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
for col, c_ in zip(eq.columns, ["#1f5fa8", "#8c8c8c", "#d0d0d0"]):
    ax[0].plot(eq.index, eq[col], label=col, color=c_, lw=1.4 if col.startswith("eth-venue") else 1.0)
ax[0].set_yscale("log"); ax[0].legend(frameon=False); ax[0].set_ylabel("growth of 1 (log)")
ax[0].axvline(pd.Timestamp("2024-01-01"), color="k", lw=0.6, ls=":"); ax[0].text(pd.Timestamp("2024-01-15"), ax[0].get_ylim()[0] * 1.5, "OOS", fontsize=8)
ax[0].set_title("eth-venue-premium — spot ETH long/flat, 10 bp/side")
dd = eq["eth-venue-premium"] / eq["eth-venue-premium"].cummax() - 1
ax[1].fill_between(dd.index, dd, 0, color="#1f5fa8", alpha=0.4); ax[1].set_ylabel("drawdown")
for a in ax: a.spines[["top", "right"]].set_visible(False)
plt.tight_layout(); plt.savefig(os.path.join(OUT, "equity.png"), dpi=130)
print("figures written to", OUT)
