"""Figures for alphas/crypto-alts/alt-sleeve-blend/."""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
import numpy as np, pandas as pd
import figstyle as F
import matplotlib.pyplot as plt
import study as S
F.setup()
OUT = os.path.join(_HERE, "..", "..", "..", "alphas", "crypto-alts", "alt-sleeve-blend")
B = pd.read_parquet(os.path.join(_HERE, "blend_01_nets.parquet")).loc["2018-03-08":]
ser = pd.read_parquet(os.path.join(OUT, "backtest_series.parquet")).loc["2018-03-08":]
blend = ser["net"]
# scale single sleeves to the blend's full-sample vol so curves are comparable
names = {"bab+dilution+volume+funding": "Blend (4 sleeves, lev 2)", "bab": "BAB (live)", "dilution": "Token dilution",
         "volume": "Abnormal volume", "funding": "Funding crowding"}
curves = {"Blend (4 sleeves, lev 2)": blend}
for k in ("bab", "dilution", "volume", "funding"):
    x = B[k]; curves[names[k]] = x * blend.std() / x[x != 0].std()

fig, ax = plt.subplots(figsize=(10, 5.2))
labels = []
for i, (nm, x) in enumerate(curves.items()):
    eq = np.log1p(x).cumsum()
    ax.plot(eq.index, eq.values, color=F.SERIES[i], lw=2.2 if i == 0 else 1.4, label=nm)
    labels.append((eq.index[-1], eq.iloc[-1], "  " + nm, F.SERIES[i]))
F.end_labels(ax, labels)
ax.axvline(pd.Timestamp(S.OOS[0]), color=F.AXIS, lw=1, ls="--"); ax.text(pd.Timestamp(S.OOS[0]), ax.get_ylim()[1] * 0.95, " OOS →", color=F.MUTED, fontsize=9)
ax.set_title("Cumulative log return, net of 10 bp/side (sleeves scaled to the blend's volatility)")
ax.set_ylabel("cumulative log return"); ax.legend(loc="upper left", fontsize=9)
ax.set_xlim(right=ax.get_xlim()[1] + 300)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "01_equity.png"), dpi=130); plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 3.6))
for i, (nm, x) in enumerate(list(curves.items())[:2]):
    eq = (1 + x).cumprod(); dd = eq / eq.cummax() - 1
    ax.plot(dd.index, dd.values * 100, color=F.SERIES[i], lw=1.6, label=f"{nm} (max {dd.min():.0%})")
ax.set_title("Drawdown (%), BAB scaled to the blend's volatility"); ax.set_ylabel("%"); ax.legend(loc="lower left", fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "02_drawdown.png"), dpi=130); plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 3.8))
for i, (nm, x) in enumerate(list(curves.items())[:2]):
    rs = x.rolling(365).mean() / x.rolling(365).std() * np.sqrt(365)
    ax.plot(rs.index, rs.values, color=F.SERIES[i], lw=1.6, label=nm)
ax.axhline(0, color=F.AXIS, lw=1); ax.set_title("Rolling 365-day Sharpe"); ax.legend(loc="upper left", fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "03_rolling_sharpe.png"), dpi=130); plt.close(fig)

yr = pd.DataFrame({nm: S.yearly(x) for nm, x in list(curves.items())}).loc[2018:]
fig, ax = plt.subplots(figsize=(10, 4.2))
wbar = 0.16
for i, nm in enumerate(yr.columns):
    ax.bar(yr.index + (i - 2) * wbar, yr[nm].values, width=wbar * 0.88, color=F.SERIES[i], label=nm)
ax.axhline(0, color=F.AXIS, lw=1); ax.set_xticks(yr.index); ax.set_xticklabels([str(y) if y < 2026 else "2026 YTD" for y in yr.index])
ax.set_title("Sharpe by calendar year"); ax.legend(ncol=5, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1))
fig.tight_layout(); fig.savefig(os.path.join(OUT, "04_yearly.png"), dpi=130); plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 3.6))
ax.plot(ser.index, ser["gross"], color=F.SERIES[0], lw=1.2, label="gross exposure Σ|w|")
ax.plot(ser.index, ser["net_exposure"], color=F.SERIES[1], lw=1.2, label="net exposure Σw")
ax.axhline(0, color=F.AXIS, lw=1); ax.set_title("Exposure at leverage 2.0"); ax.legend(loc="upper left", fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "05_exposure.png"), dpi=130); plt.close(fig)
print("figures written")
