"""Figures for the alpha spec: ETF-era equity/drawdown/rolling Sharpe, and the 1980-2026 backcast."""
import sys
sys.path.insert(0, "../shared")
import numpy as np, pandas as pd, warnings, matplotlib
warnings.filterwarnings("ignore")
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 10, "legend.frameon": False})
OUT = "../../../alphas/global-equity-etf/intl-relative-trend/"

nets = pd.read_parquet("nets_03.parquet")
spec = nets["SPEC blend50 (5bp)"]; start = spec.ne(0).idxmax()
N = nets.loc[start:, ["SPEC blend50 (5bp)", "AGG only", "DIV only"]]
eq = (1 + N).cumprod()
fig, ax = plt.subplots(3, 1, figsize=(10, 9), gridspec_kw={"height_ratios": [3, 1.3, 1.3]}, sharex=True)
for c, col, lw in [("SPEC blend50 (5bp)", BLUE, 2.0), ("AGG only", ORANGE, 1.4), ("DIV only", AQUA, 1.4)]:
    ax[0].plot(eq.index, eq[c], color=col, lw=lw, label={"SPEC blend50 (5bp)": "Spec: 50/50 blend", "AGG only": "AGG sleeve only", "DIV only": "DIV sleeve only"}[c])
ax[0].set_yscale("log"); ax[0].set_ylabel("Growth of $1 (log), net 5 bp/side")
ax[0].axvline(pd.Timestamp("2013-01-01"), color=INK2, lw=1, ls="--")
ax[0].text(pd.Timestamp("2013-03-01"), eq.values.min() * 1.05, "OOS from 2013", color=INK2, fontsize=9)
ax[0].legend(loc="upper left")
ax[0].set_title("intl-relative-trend — country ETFs vs SPY, slow relative trend (market-neutral, 10% vol target)", fontsize=11, loc="left")
dd = eq["SPEC blend50 (5bp)"] / eq["SPEC blend50 (5bp)"].cummax() - 1
ax[1].fill_between(dd.index, dd * 100, 0, color=BLUE, alpha=0.35, lw=0); ax[1].plot(dd.index, dd * 100, color=BLUE, lw=1)
ax[1].set_ylabel("Drawdown, spec (%)")
s = N["SPEC blend50 (5bp)"]
rs = s.rolling(756).mean() / s.rolling(756).std() * np.sqrt(252)
ax[2].plot(rs.index, rs, color=BLUE, lw=1.6); ax[2].axhline(0, color=INK2, lw=0.8)
ax[2].set_ylabel("Rolling 3y Sharpe")
fig.tight_layout(); fig.savefig(OUT + "equity_drawdown.png", dpi=130); plt.close(fig)

# long history (monthly index data) -- recompute via the 02 script's objects
ns = {}
exec(open("02_long_history.py").read(), ns)
bl = ns["bl"]
eqb = (1 + bl).cumprod()
fig, ax = plt.subplots(figsize=(10, 4.2))
ax.plot(eqb.index, eqb, color=BLUE, lw=2, label="50/50 blend, slow (6/12/24m), 10 bp/side")
for a, b, lab in [("1980", "2000-12-31", "pre-sample 1980-2000: SR 0.52"), ("2001", "2012-12-31", "IS 2001-12: 0.58"), ("2013", "2026-12-31", "OOS 2013-26: 0.59")]:
    ax.axvspan(pd.Timestamp(a), pd.Timestamp(b), color=GRID, alpha=0.35 if lab.startswith("IS") else 0.0, lw=0)
    ax.text(pd.Timestamp(a) + pd.Timedelta(days=200), eqb.max() * 0.93, lab, color=INK2, fontsize=9)
ax.set_yscale("log"); ax.set_ylabel("Growth of $1 (log)")
ax.set_title("Independent backcast: USD-converted local indices (JP, UK, CA, AU, HK, DE from 1999) vs S&P 500, monthly", fontsize=10, loc="left")
ax.legend(loc="lower right")
fig.tight_layout(); fig.savefig(OUT + "long_history_backcast.png", dpi=130); plt.close(fig)
print("saved")
