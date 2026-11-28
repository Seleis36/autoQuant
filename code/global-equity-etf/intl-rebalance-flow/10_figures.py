"""Figures: equity/drawdown of strategy.py net; day profile of the EFA hedged spread."""
import os, sys, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from lib import load, month_end_positions, roll_beta
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "..", "alphas", "global-equity-etf", "intl-rebalance-flow")
BLUE, ORANGE, INK, INK2 = "#257de0", "#f47230", "#191919", "#666666"
plt.rcParams.update({"axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
net = pd.read_parquet(os.path.join(HERE, "nets_09.parquet"))["irf"].loc["2002-01-01":]
eq = (1 + net).cumprod(); dd = eq / eq.cummax() - 1
fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
ax[0].plot(eq.index, eq.values, color=BLUE, lw=2)
ax[0].axvline(pd.Timestamp("2013-01-01"), color=INK2, lw=1, ls="--")
ax[0].text(pd.Timestamp("2013-03-01"), eq.max() * 0.985, "out-of-sample →", color=INK2)
ax[0].set_ylabel("growth of 1 (net, EFA 2 bp / SPY 1 bp)")
ax[0].set_title("intl-rebalance-flow — long EFA / short β·SPY on the last session, sized by MTD US−EFA gap", color=INK, loc="left")
ax[0].grid(axis="y", color="#e6e6e6", lw=0.8)
ax[1].fill_between(dd.index, dd.values * 100, 0, color=BLUE, alpha=0.35, lw=0)
ax[1].set_ylabel("drawdown %"); ax[1].grid(axis="y", color="#e6e6e6", lw=0.8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "equity_drawdown.png"), dpi=130); plt.close(fig)

C, R = load(); idx = C.index; pe = month_end_positions(idx)
rel = R.SPY - R.EFA; bt = roll_beta(R.EFA, R.SPY); hed = R.EFA - bt.shift(1) * R.SPY
vol = hed.rolling(252, min_periods=126).std()
labs = list(range(-6, 4)); vals = {}
for pn, (a_, b_) in {"2002 → 2012 (IS)": ("2002-01-01", "2012-12-31"), "2013 → 2026 (OOS)": ("2013-01-01", "2026-12-31")}.items():
    out = []
    for j in labs:
        xs, ys = [], []
        for a, b in zip(pe[:-1], pe[1:]):
            if not (pd.Timestamp(a_) <= idx[b] <= pd.Timestamp(b_)): continue
            end = b + j - 1 if j <= 0 else b
            if end - a < 4 or b + j >= len(idx) or not np.isfinite(vol.iloc[end]): continue
            xs.append(rel.iloc[a + 1:end + 1].sum() / (vol.iloc[end] * np.sqrt(end - a))); ys.append(hed.iloc[b + j])
        xs, ys = np.array(xs), np.array(ys); ok = np.isfinite(xs) & np.isfinite(ys); X = xs[ok] - xs[ok].mean()
        out.append((X * ys[ok]).sum() / (X ** 2).sum() * 1e4)
    vals[pn] = out
x = np.arange(len(labs)); wdt = 0.38
fig, ax = plt.subplots(figsize=(10, 4.2))
for i, (pn, v) in enumerate(vals.items()):
    ax.bar(x + (i - 0.5) * wdt, v, wdt - 0.04, color=[BLUE, ORANGE][i], label=pn)
ax.axhline(0, color=INK2, lw=0.8)
ax.set_xticks(x); ax.set_xticklabels([("L" if j == 0 else (f"L{j}" if j < 0 else f"next month +{j}")) for j in labs])
ax.set_ylabel("bp of EFA − β·SPY return\nper unit of MTD US−EFA z")
ax.set_title("US out-performance over the month → EFA beats SPY on the last session only, then gives back", color=INK, loc="left")
ax.legend(frameon=False); ax.grid(axis="y", color="#e6e6e6", lw=0.8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "day_profile.png"), dpi=130); plt.close(fig)
print("ok")
