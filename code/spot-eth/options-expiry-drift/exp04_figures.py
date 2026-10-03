"""exp04 — figures for the alpha spec (written to alphas/spot-eth/options-expiry-drift/).

fig1_path.png    mean cumulative ETH return from T-24h to T+8h: month-end expiry vs other Fridays vs Tuesday
fig2_equity.png  net equity of the sleeve (10 bp/side)
fig3_yearly.png  net return per calendar year
"""
import importlib.util
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import common as c
from common import ek

OUT = os.path.join(c.REPO, "alphas", "spot-eth", "options-expiry-drift")
os.makedirs(OUT, exist_ok=True)
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"      # validated categorical slots 1-3 (light)
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
                     "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
                     "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True})
H, D = pd.Timedelta(hours=1), pd.Timedelta(days=1)

# ---------------------------------------------------------------- fig 1: path around the expiry
p = c.price_at("ETHUSDT", start="2019-11-01")
end = p.index.max() - 1 * D
ex = c.expiries(end)
groups = [("Month-end expiry (last Friday)", ex.index[ex != "weekly"], BLUE),
          ("Other Fridays", ex.index[ex == "weekly"], ORANGE),
          ("Tuesdays (placebo)", c.placebo_times(end), AQUA)]
hours = np.arange(-24, 9)
fig, ax = plt.subplots(figsize=(9, 4.8))
ax.axvspan(-8, 0, color="#efeeea", zorder=0)
ax.set_ylim(-58, 72)
ax.text(-4, 70, "short window\n00:00–08:00 UTC", ha="center", va="top", color=INK2, fontsize=9)
ax.axhline(0, color=INK2, lw=0.8)
ends = []
for name, t, col in groups:
    cum = [0.0] + [c.window_ret(p, t, -24 * H, k * H).mean() * 1e4 for k in hours[1:]]
    ax.plot(hours, cum, color=col, lw=2, label=f"{name} (n = {len(t)})", solid_capstyle="round")
    ends.append((cum[-1], name, col))
for (y, name, col), dy in zip(ends, (0, 0, 0)):
    ax.plot([8], [y], "o", ms=5, color=col)
    ax.annotate(f"{name.split(' (')[0]}  {y:+.0f} bp", (8, y), xytext=(8, 0), textcoords="offset points", va="center", color=INK, fontsize=9)
ax.set_xlim(-24, 8)
ax.set_xticks(range(-24, 9, 4))
ax.set_xticklabels([f"T{h:+d}h" if h else "T" for h in range(-24, 9, 4)])
ax.set_ylabel("mean cumulative log return since T−24h (bp)")
ax.set_title("ETH falls into the month-end option expiry, and only then", loc="left", fontsize=12, color=INK, pad=14)
ax.text(0, 1.015, "Binance ETHUSDT, 2020-01 → 2026-09, 1-minute bars; T = 08:00 UTC, the Deribit settlement", transform=ax.transAxes, color=INK2, fontsize=9)
fig.legend(*ax.get_legend_handles_labels(), frameon=False, loc="lower left", bbox_to_anchor=(0.08, 0.0), ncol=3, fontsize=9)
fig.subplots_adjust(right=0.74, left=0.09, top=0.87, bottom=0.17)
fig.savefig(os.path.join(OUT, "fig1_path.png"), dpi=150)
plt.close(fig)

# ---------------------------------------------------------------- fig 2 & 3: the sleeve
spec = importlib.util.spec_from_file_location("strategy", os.path.join(c.HERE, "strategy.py"))
st = importlib.util.module_from_spec(spec); spec.loader.exec_module(st)
h = ek.ed.bars("ETHUSDT", "1h", start="2019-11-01")["Close"]
net = ek.ed.to_daily(ek.ed.bt(st.target_weight(h), h)[0]).loc[c.START:]
eq = (1 + net).cumprod()

fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(eq.index, eq.to_numpy(), color=BLUE, lw=2)
ax.axvline(pd.Timestamp(c.OOS_START), color=INK2, lw=0.8, ls=(0, (4, 3)))
ax.text(pd.Timestamp(c.OOS_START), eq.min(), " out of sample →", color=INK2, fontsize=9, va="bottom")
ax.plot([eq.index[-1]], [eq.iloc[-1]], "o", ms=5, color=BLUE)
ax.annotate(f"{eq.iloc[-1]:.2f}", (eq.index[-1], eq.iloc[-1]), xytext=(8, 0), textcoords="offset points", va="center", fontsize=9)
ax.set_ylabel("equity (start = 1)")
ax.set_title("Pre-expiry short: net equity at 10 bp per side", loc="left", fontsize=12, pad=14)
ax.text(0, 1.015, "Short 1× ETH 00:00–08:00 UTC on the last Friday of each month; 81 events, in the market 1.1% of the time",
        transform=ax.transAxes, color=INK2, fontsize=9)
fig.subplots_adjust(right=0.93, left=0.09, top=0.87, bottom=0.1)
fig.savefig(os.path.join(OUT, "fig2_equity.png"), dpi=150)
plt.close(fig)

yr = net.groupby(net.index.year).agg(lambda s: (1 + s).prod() - 1) * 100
fig, ax = plt.subplots(figsize=(7, 3.8))
bars = ax.bar(yr.index.astype(str), yr.to_numpy(), color=BLUE, width=0.55)
ax.axhline(0, color=INK2, lw=0.8)
for b, v in zip(bars, yr.to_numpy()):
    ax.annotate(f"{v:+.1f}%", (b.get_x() + b.get_width() / 2, v), xytext=(0, 4 if v >= 0 else -12),
                textcoords="offset points", ha="center", fontsize=9, color=INK)
ax.set_ylabel("net return (%)")
ax.grid(axis="x", visible=False)
ax.set_title("Net return by calendar year", loc="left", fontsize=12, pad=14)
ax.text(0, 1.015, "10 bp per side; 2026 through September", transform=ax.transAxes, color=INK2, fontsize=9)
ax.set_ylim(min(yr.min() - 2.5, -7), yr.max() + 2.5)
fig.subplots_adjust(left=0.11, right=0.97, top=0.85, bottom=0.1)
fig.savefig(os.path.join(OUT, "fig3_yearly.png"), dpi=150)
plt.close(fig)
print("written:", sorted(os.listdir(OUT)))
print(yr.round(1).to_dict(), round(float(eq.iloc[-1]), 3))

# BTC class split, for the report
pb = c.price_at("BTCUSDT", start="2019-11-01")
for k in ("quarterly", "monthly"):
    for sym, pp in (("ETH", p), ("BTC", pb)):
        x = c.window_ret(pp, ex.index[ex == k], -8 * H, 0 * H).dropna()
        print(f"{sym} {k}: full {x.mean() * 1e4:+.0f} bp (t {x.mean() / x.std() * np.sqrt(len(x)):+.1f}, n {len(x)}, share<0 {np.mean(x < 0):.2f})")
