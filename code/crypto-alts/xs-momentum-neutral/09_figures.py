"""Figures for the alpha spec. Static PNGs; palette = dataviz reference slots 1-3, validated."""
from common import *
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

OUT = os.path.join(HERE, "..", "..", "..", "alphas", "crypto-alts", "xs-momentum-neutral")
S = pd.read_parquet(os.path.join(OUT, "backtest_series.parquet"))
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
                     "axes.spines.right": False, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "font.size": 10})

def shade_bears(ax):
    for s, e, _ in bear_windows():
        ax.axvspan(pd.Timestamp(s), pd.Timestamp(e), color="#d9d8d3", alpha=0.45, lw=0)

net = S["net_10bp"]; eq = (1 + net).cumprod()
btc = S["btc_close"] / S["btc_close"].iloc[0]
oos = pd.Timestamp(OOS[0])

# 1. equity (log) vs BTC, bear phases shaded
fig, ax = plt.subplots(figsize=(11, 5))
shade_bears(ax)
ax.plot(eq.index, eq, color=BLUE, lw=2, label="xs-momentum-neutral (net 10 bp)")
ax.plot(btc.index, btc, color=ORANGE, lw=2, label="BTC-USD buy & hold")
ax.axvline(oos, color=INK2, lw=1, ls="--"); ax.text(oos, ax.get_ylim()[1] * 0.9 if False else 1.05, "  OOS →", color=INK2, va="bottom")
ax.set_yscale("log"); ax.set_title("Growth of $1 — regime-hedged betting-against-beta on liquid alts (grey = BTC bear phases)", loc="left")
ax.text(eq.index[-1], eq.iloc[-1], f"  {eq.iloc[-1]:.1f}x", color=BLUE, va="center")
ax.text(btc.index[-1], btc.iloc[-1], f"  {btc.iloc[-1]:.1f}x", color=ORANGE, va="center")
ax.legend(loc="upper left", frameon=False); fig.tight_layout(); fig.savefig(os.path.join(OUT, "01_equity.png"), dpi=130); plt.close(fig)

# 2. drawdown
dd = eq / eq.cummax() - 1
fig, ax = plt.subplots(figsize=(11, 3.2))
shade_bears(ax); ax.fill_between(dd.index, dd, 0, color=BLUE, alpha=0.35, lw=0); ax.plot(dd.index, dd, color=BLUE, lw=1.5)
ax.axvline(oos, color=INK2, lw=1, ls="--")
ax.set_title(f"Drawdown (max {dd.min():.0%})", loc="left"); ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
fig.tight_layout(); fig.savefig(os.path.join(OUT, "02_drawdown.png"), dpi=130); plt.close(fig)

# 3. rolling 1y Sharpe
rs = net.rolling(365).mean() / net.rolling(365).std() * np.sqrt(ANN)
fig, ax = plt.subplots(figsize=(11, 3.2))
shade_bears(ax); ax.plot(rs.index, rs, color=BLUE, lw=2); ax.axhline(1.0, color=INK2, lw=1, ls=":"); ax.axhline(0, color=INK2, lw=0.8)
ax.axvline(oos, color=INK2, lw=1, ls="--"); ax.set_title("Rolling 1-year Sharpe (dotted = 1.0)", loc="left")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "03_rolling_sharpe.png"), dpi=130); plt.close(fig)

# 4. exposure: net exposure and regime
fig, ax = plt.subplots(figsize=(11, 3.6))
shade_bears(ax)
ax.plot(S.index, S["net_exposure"].rolling(14).mean(), color=AQUA, lw=2, label="net $ exposure (14d avg)")
ax.plot(S.index, S["gross_exposure"], color=BLUE, lw=1.2, label="gross exposure")
b = S["bull_regime"].fillna(0).astype(int); edges = b.diff().fillna(b.iloc[0])
starts = b.index[edges == 1]; ends = list(b.index[edges == -1]) + [b.index[-1]]
for st_, en_ in zip(starts, ends[:len(starts)]):
    ax.axvspan(st_, en_, ymin=0.0, ymax=0.06, color=ORANGE, alpha=0.8, lw=0)
ax.plot([], [], color=ORANGE, lw=6, alpha=0.8, label="bull regime strip (BTC > SMA50)")
ax.set_ylim(-0.08, 1.12)
ax.set_title("Exposure and hedge regime (net long in bull, negative-beta in bear)", loc="left")
ax.legend(loc="upper center", frameon=False, ncol=3, bbox_to_anchor=(0.5, -0.12)); fig.tight_layout(); fig.savefig(os.path.join(OUT, "04_exposure.png"), dpi=130); plt.close(fig)

# 5. Sharpe by bear window (bar) and by year
bs = bear_stats(net); labels = [i.split(" ")[0] for i in bs.index]
fig, axes = plt.subplots(1, 2, figsize=(12, 3.8), gridspec_kw={"width_ratios": [1.1, 1]})
ax = axes[0]; ax.set_axisbelow(True); vals = bs["Sharpe"].values
ax.bar(range(len(vals)), vals, color=[ORANGE if l.startswith("bear") else (INK2 if l.startswith("non") else BLUE) for l in labels], width=0.6)
ax.set_xticks(range(len(vals))); ax.set_xticklabels(["all bears"] + [l[:7] for l in labels[1:-1]] + ["non-bear"], rotation=0)
for i, v in enumerate(vals): ax.text(i, v + 0.05, f"{v:.2f}", ha="center", color=INK2, fontsize=9)
ax.axhline(0, color=INK2, lw=0.8); ax.set_title("Sharpe inside ex-post BTC bear phases (10 bp)", loc="left")
ax = axes[1]; ax.set_axisbelow(True); yr = yearly(net.loc["2018":])
ax.bar(yr.index.astype(str), yr["Sharpe"], color=BLUE, width=0.6); ax.axhline(0, color=INK2, lw=0.8)
for i, v in enumerate(yr["Sharpe"]): ax.text(i, v + 0.05 if v >= 0 else v - 0.25, f"{v:.1f}", ha="center", color=INK2, fontsize=9)
ax.set_title("Sharpe by calendar year", loc="left")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "05_bear_and_yearly.png"), dpi=130); plt.close(fig)
print("figures written to", OUT)
