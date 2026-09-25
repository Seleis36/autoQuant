"""Equity / drawdown figure for the blend spec vs its two sleeves (same scaling as in the spec)."""
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.grid": True, "grid.color": GRID,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 10, "legend.frameon": False})
N = pd.read_parquet("nets_02.parquet")
N = N.loc[N["BLEND spec 5bp"].ne(0).idxmax():]
cols = [("BLEND spec 5bp", BLUE, 2.0, "Blend (spec), net 5 bp"), ("trend sleeve only (x0.67)", ORANGE, 1.3, "intl-relative-trend sleeve (x0.67)"),
        ("FOMC sleeve only (x0.87)", AQUA, 1.3, "FOMC sleeve (x0.87)")]
eq = (1 + N[[c[0] for c in cols]]).cumprod()
fig, ax = plt.subplots(2, 1, figsize=(10, 6.8), gridspec_kw={"height_ratios": [3, 1.2]}, sharex=True)
for c, col, lw, lab in cols:
    ax[0].plot(eq.index, eq[c], color=col, lw=lw, label=lab)
ax[0].set_yscale("log"); ax[0].set_ylabel("Growth of $1 (log)")
ax[0].axvline(pd.Timestamp("2013-01-01"), color=INK2, lw=1, ls="--")
ax[0].text(pd.Timestamp("2013-03-01"), 0.95, "OOS from 2013", color=INK2, fontsize=9)
ax[0].legend(loc="upper left")
ax[0].set_title("global-etf-sleeve-blend — Sharpe 0.81 full / 0.77 IS / 0.86 OOS, corr to SPY 0.10", fontsize=11, loc="left")
dd = eq["BLEND spec 5bp"] / eq["BLEND spec 5bp"].cummax() - 1
ax[1].fill_between(dd.index, dd * 100, 0, color=BLUE, alpha=0.35, lw=0); ax[1].plot(dd.index, dd * 100, color=BLUE, lw=1)
ax[1].set_ylabel("Drawdown, blend (%)")
fig.tight_layout(); fig.savefig("../../../alphas/global-equity-etf/global-etf-sleeve-blend/equity_drawdown.png", dpi=130)
print("saved")
