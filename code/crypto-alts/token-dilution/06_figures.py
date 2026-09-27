"""Figures for alphas/crypto-alts/token-dilution/."""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
import numpy as np, pandas as pd
import figstyle as F
import matplotlib.pyplot as plt
import study as S
F.setup()
OUT = os.path.join(_HERE, "..", "..", "..", "alphas", "crypto-alts", "token-dilution")
R = pd.read_parquet(os.path.join(_HERE, "robust_03_nets.parquet")).loc["2018-03-08":]
net = R["BASE dil12w|h30|bn"]
pd.DataFrame({"net": net}).to_parquet(os.path.join(OUT, "backtest_series.parquet"))

fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.4), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
eq = np.log1p(net).cumsum()
a1.plot(eq.index, eq.values, color=F.SERIES[0], lw=2)
ens = np.log1p(R["ensemble 4/12/26/52w"]).cumsum()
a1.plot(ens.index, ens.values, color=F.SERIES[1], lw=1.3)
F.end_labels(a1, [(eq.index[-1], eq.iloc[-1], "  12-week dilution (spec)", F.SERIES[0]),
                  (ens.index[-1], ens.iloc[-1], "  4/12/26/52-week ensemble", F.SERIES[1])])
a1.axvline(pd.Timestamp(S.OOS[0]), color=F.AXIS, lw=1, ls="--"); a1.text(pd.Timestamp(S.OOS[0]), eq.max() * 0.95, " OOS →", color=F.MUTED, fontsize=9)
a1.set_title("Token dilution: short high 12-week supply growth, long low, BTC-beta-hedged (net 10 bp)")
a1.set_ylabel("cumulative log return"); a1.set_xlim(right=a1.get_xlim()[1] + 420)
dd = (1 + net).cumprod(); dd = dd / dd.cummax() - 1
a2.fill_between(dd.index, dd.values * 100, 0, color=F.SERIES[0], alpha=0.25, lw=0)
a2.plot(dd.index, dd.values * 100, color=F.SERIES[0], lw=1); a2.set_ylabel("drawdown %")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "01_equity_drawdown.png"), dpi=130); plt.close(fig)

ic = pd.read_csv(os.path.join(_HERE, "ic_01.csv")).set_index(["feat", "h"])
fig, ax = plt.subplots(figsize=(10, 4))
feats = ["dil4w", "dil12w", "dil26w", "dil52w"]
hs = [7, 14, 30, 60]; wbar = 0.1
for j, (split, col) in enumerate((("IS", F.SERIES[0]), ("OOS", F.SERIES[1]))):
    for i, f in enumerate(feats):
        vals = [ic.loc[(f, h), f"IC_{split}"] for h in hs]
        xs = np.arange(len(hs)) + (i - 1.5) * 0.2 + (j - 0.5) * wbar
        ax.bar(xs, vals, width=wbar * 0.9, color=col, label=split if i == 0 else None)
        if j == 0:
            for x_, h in zip(xs, hs):
                pass
ax.set_xticks(np.arange(len(hs))); ax.set_xticklabels([f"{h}-day forward return\n(bars: 4 / 12 / 26 / 52-week dilution)" for h in hs], fontsize=8)
ax.axhline(0, color=F.AXIS, lw=1); ax.set_ylabel("mean daily rank IC")
ax.set_title("Dilution IC is negative in both halves at every window and horizon"); ax.legend(loc="lower left")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "02_ic_by_horizon.png"), dpi=130); plt.close(fig)

yr = S.yearly(net).loc[2018:]
fig, ax = plt.subplots(figsize=(10, 3.6))
ax.bar(yr.index, yr.values, width=0.6, color=F.SERIES[0])
for x_, v in zip(yr.index, yr.values):
    ax.annotate(f"{v:+.2f}", (x_, v), xytext=(0, 4 if v >= 0 else -12), textcoords="offset points", ha="center", fontsize=8, color=F.INK2)
ax.axhline(0, color=F.AXIS, lw=1); ax.set_xticks(yr.index); ax.set_xticklabels([str(y) if y < 2026 else "2026 YTD" for y in yr.index])
ax.set_title("Token dilution: Sharpe by calendar year")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "03_yearly.png"), dpi=130); plt.close(fig)
print("ok")
