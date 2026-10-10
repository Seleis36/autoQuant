"""Figures for the alpha spec (written to alphas/rates-bonds/cef-discount-reversion/)."""
import os
import sys
import numpy as np
import pandas as pd
import cef_lib as cl
import strategy as S

sys.path.insert(0, os.path.join(cl.ROOT, "code", "rates-bonds", "shared"))
import plot_style as ps
import matplotlib.pyplot as plt

ps.apply()
OUT = os.path.join(cl.ROOT, "alphas", "rates-bonds", "cef-discount-reversion")
os.makedirs(OUT, exist_ok=True)
d = cl.load()
ret, group = d["ret"], d["group"]
w = S.target_weights(d["close"], d["nav"], d["volume"], group)
nets = {c: cl.xs_backtest(w, ret, c, lag=0)[0].loc["2004":] for c in (0.0, 10.0, 20.0)}
split = pd.Timestamp(cl.OOS[0])

# 1 -- equity curves, log scale
fig, ax = plt.subplots(figsize=(9.2, 4.6))
labels = {0.0: "gross", 10.0: "net, 10 bp per side", 20.0: "net, 20 bp per side"}
for (c, r), col in zip(nets.items(), (ps.SERIES[2], ps.SERIES[0], ps.SERIES[1])):
    eq = (1 + r).cumprod()
    ax.plot(eq.index, eq.values, color=col, label=labels[c])
    ps.end_label(ax, eq.index[-1], eq.iloc[-1], "%s  x%.1f" % (labels[c].split(",")[0] if c == 0 else "%d bp" % c, eq.iloc[-1]))
ax.set_yscale("log")
ax.set_yticks([1, 2, 4, 8, 16])
ax.set_yticklabels(["1", "2", "4", "8", "16"])
ax.axvline(split, color=ps.NEUTRAL, linewidth=1)
ax.text(split, ax.get_ylim()[0] * 1.08, "  out of sample from 2015", color=ps.INK2, fontsize=9, va="bottom")
ax.set_title("Bond CEF discount reversion: growth of 1, gross 1.0 cap, one-session skip", pad=22)
ps.subtitle(ax, "Dollar-neutral long/short, 2004-01 to 2026-10. Log scale.")
ax.legend(loc="upper left")
ax.set_xlim(nets[10.0].index[0], nets[10.0].index[-1] + pd.Timedelta(days=560))
fig.tight_layout()
fig.savefig(os.path.join(OUT, "equity_curve.png"))
plt.close(fig)

# 2 -- calendar-year net return at 10 bp
yr = nets[10.0].groupby(nets[10.0].index.year).apply(lambda x: (1 + x).prod() - 1) * 100
fig, ax = plt.subplots(figsize=(9.2, 4.0))
ax.bar(yr.index, yr.values, width=0.62, color=ps.SERIES[0])
ax.axhline(0, color=ps.NEUTRAL, linewidth=1)
ax.axvline(2014.5, color=ps.NEUTRAL, linewidth=1)
for y in (yr.idxmax(), yr.idxmin(), 2020, 2022, 2026):
    ax.annotate("%+.1f%%" % yr[y], xy=(y, yr[y]), xytext=(0, 4 if yr[y] >= 0 else -11), textcoords="offset points",
                ha="center", fontsize=9, color=ps.INK2)
ax.set_xticks(yr.index[::2])
ax.set_ylabel("net return, %")
ax.set_title("Calendar-year net return at 10 bp per side", pad=22)
ps.subtitle(ax, "Largest in stress years (2008-09, 2020, 2022); near zero in calm ones. 2026 is to 9 October.")
ax.text(2014.6, yr.max() * 0.9, " out of sample", color=ps.INK2, fontsize=9)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "annual_returns.png"))
plt.close(fig)

# 3 -- cost ladder and entry-delay decay (two panels, each one y-axis)
costs = [0, 5, 10, 15, 20, 25, 30, 40]
lad = pd.DataFrame({c: {k: cl.sharpe(cl.xs_backtest(w, ret, c, lag=0)[0], a, b) for k, (a, b) in (("IS 2004-14", cl.IS), ("OOS 2015-26", cl.OOS))} for c in costs}).T
lags = [0, 1, 2, 3, 4, 6, 9]
dec = pd.DataFrame({L: {k: cl.sharpe(cl.xs_backtest(w, ret, 10.0, lag=L)[0], a, b) for k, (a, b) in (("IS 2004-14", cl.IS), ("OOS 2015-26", cl.OOS))} for L in lags}).T
fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), sharey=True)
for ax, df, xl, ttl in ((axes[0], lad, "cost, bp per side", "Net Sharpe vs trading cost"),
                        (axes[1], dec, "extra sessions of entry delay (10 bp per side)", "Net Sharpe vs entry delay")):
    for col, colr in zip(df.columns, ps.SERIES[:2]):
        ax.plot(df.index, df[col], color=colr, marker="o", markersize=5, markeredgecolor=ps.SURFACE, markeredgewidth=1.5, label=col)
        ps.end_label(ax, df.index[-1], df[col].iloc[-1], "%s  %.1f" % (col.split()[0], df[col].iloc[-1]))
    ax.axhline(0, color=ps.NEUTRAL, linewidth=1)
    ax.set_xlabel(xl)
    ax.set_title(ttl)
    ax.set_xlim(df.index[0] - 0.5, df.index[-1] * 1.22 + 0.5)
axes[0].set_ylabel("annualised net Sharpe")
axes[0].legend(loc="upper right")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "cost_and_delay.png"))
plt.close(fig)
lad.round(2).to_csv("10_cost_ladder.csv")
dec.round(2).to_csv("10_delay_decay.csv")

# 4 -- event study: cheap-minus-rich quintile spread by horizon, 60d z-score signal
ic = pd.read_csv("02_signal_ic.csv")
z = ic[(ic.sig == "z60") & (ic.split.isin(["IS", "OOS"]))].pivot(index="h", columns="split", values="spread_bp")
fig, ax = plt.subplots(figsize=(6.4, 4.0))
for col, colr, lab in (("IS", ps.SERIES[0], "IS 2004-14"), ("OOS", ps.SERIES[1], "OOS 2015-26")):
    ax.plot(z.index, z[col], color=colr, marker="o", markersize=5, markeredgecolor=ps.SURFACE, markeredgewidth=1.5, label=lab)
    ps.end_label(ax, z.index[-1], z[col].iloc[-1], "%s  %.0f bp" % (col, z[col].iloc[-1]))
ax.set_xticks(z.index)
ax.set_xlim(0, 26)
ax.set_ylim(0, None)
ax.set_xlabel("holding horizon, sessions (entered one session after the signal)")
ax.set_ylabel("cheap minus rich quintile, bp")
ax.set_title("What the signal is worth before costs", pad=22)
ps.subtitle(ax, "60-session discount z-score, sorted within muni / taxable, liquid funds.")
ax.legend(loc="upper left")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "event_study.png"))
plt.close(fig)
print(lad.round(2).T.to_string()); print(dec.round(2).T.to_string())
