"""Equity and drawdown: trend-flow-blend vs the deployed global-etf-sleeve-blend (net)."""
import os, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "..", "alphas", "global-equity-etf", "trend-flow-blend")
BLUE, ORANGE, INK, INK2 = "#257de0", "#f47230", "#191919", "#666666"
plt.rcParams.update({"axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
n = pd.read_parquet(os.path.join(HERE, "nets_02.parquet")).loc["2003-03-01":]
fig, ax = plt.subplots(2, 1, figsize=(10, 6.2), sharex=True, gridspec_kw={"height_ratios": [3, 1.2]})
for col, colr, lab in [("tfb", BLUE, "trend-flow-blend (4 sleeves)"), ("old", ORANGE, "deployed global-etf-sleeve-blend (2 sleeves)")]:
    eq = (1 + n[col]).cumprod(); dd = eq / eq.cummax() - 1
    ax[0].plot(eq.index, eq.values, color=colr, lw=2, label=lab)
    ax[1].plot(dd.index, dd.values * 100, color=colr, lw=1.5)
    ax[0].text(eq.index[-1], eq.iloc[-1], f" {lab.split(' (')[0]}", color=INK, va="center", fontsize=9)
ax[0].axvline(pd.Timestamp("2013-01-01"), color=INK2, lw=1, ls="--")
ax[0].text(pd.Timestamp("2013-03-01"), ax[0].get_ylim()[1] * 0.93, "out-of-sample →", color=INK2)
ax[0].set_yscale("log"); ax[0].set_ylabel("growth of 1, net (log)")
ax[0].set_title("trend-flow-blend vs the deployed blend, net of costs (5 bp countries / 2 bp EFA / 1 bp SPY)", color=INK, loc="left")
ax[0].legend(frameon=False, loc="upper left"); ax[0].grid(axis="y", color="#e6e6e6", lw=0.8)
ax[1].set_ylabel("drawdown %"); ax[1].grid(axis="y", color="#e6e6e6", lw=0.8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "equity_drawdown.png"), dpi=130); plt.close(fig); print("ok")
