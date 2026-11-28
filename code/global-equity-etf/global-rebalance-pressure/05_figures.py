"""Figures for the alpha spec: equity/drawdown of strategy.py net, and the day profile."""
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from grp_lib import load_etf, drift_z, days_left, month_end_flags, slope_t
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "..", "alphas", "global-equity-etf", "global-rebalance-pressure")
BLUE, ORANGE, INK, INK2 = "#257de0", "#f47230", "#191919", "#666666"
plt.rcParams.update({"axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
net = pd.read_parquet(os.path.join(HERE, "nets_04.parquet"))["grp"].loc["2002-08-01":]
eq = (1 + net).cumprod(); dd = eq / eq.cummax() - 1
fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
ax[0].plot(eq.index, eq.values, color=BLUE, lw=2)
ax[0].axvline(pd.Timestamp("2013-01-01"), color=INK2, lw=1, ls="--")
ax[0].text(pd.Timestamp("2013-03-01"), eq.max() * 0.97, "out-of-sample →", color=INK2)
ax[0].set_ylabel("growth of 1 (net, 1/2 bp)")
ax[0].set_title("global-rebalance-pressure — net equity, gross ≤ 1 (spec)", color=INK, loc="left")
ax[0].grid(axis="y", color="#e6e6e6", lw=0.8)
ax[1].fill_between(dd.index, dd.values * 100, 0, color=BLUE, alpha=0.35, lw=0)
ax[1].set_ylabel("drawdown %"); ax[1].grid(axis="y", color="#e6e6e6", lw=0.8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "equity_drawdown.png"), dpi=130); plt.close(fig)

C, R = load_etf(); me = month_end_flags(R.index); z = drift_z(R.SPY, R.IEF, me)
dl = days_left(R.index, me)
df = pd.DataFrame({"z": z, "y": R.SPY.shift(-1), "dl": dl.shift(-1)}).dropna()
labs = list(range(8, -1, -1))
vals = {}
for pn, (a, b) in {"2002-08 → 2012 (IS)": ("2002-08-01", "2012-12-31"), "2013 → 2026 (OOS)": ("2013-01-01", "2026-12-31")}.items():
    d = df.loc[a:b]
    vals[pn] = [slope_t(d[d.dl == k].z.values, d[d.dl == k].y.values)[0] for k in labs] + \
               [slope_t(d[d.dl >= 9].z.values, d[d.dl >= 9].y.values)[0]]
x = np.arange(len(labs) + 1); wdt = 0.38
fig, ax = plt.subplots(figsize=(10, 4.2))
for i, (pn, v) in enumerate(vals.items()):
    ax.bar(x + (i - 0.5) * wdt, v, wdt - 0.04, color=[BLUE, ORANGE][i], label=pn)
ax.axhline(0, color=INK2, lw=0.8)
ax.set_xticks(x); ax.set_xticklabels([f"L-{k}" for k in labs] + ["mid-month\n(≥ 9 left)"])
ax.set_ylabel("bp of next-session SPY return\nper unit of stock-bond drift z")
ax.set_title("Month-to-date stock-minus-bond drift predicts SPY falling only in the last four sessions", color=INK, loc="left")
ax.legend(frameon=False); ax.grid(axis="y", color="#e6e6e6", lw=0.8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "day_profile.png"), dpi=130); plt.close(fig)
print("ok")
