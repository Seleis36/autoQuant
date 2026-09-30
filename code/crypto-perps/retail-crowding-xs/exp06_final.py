"""exp06 — the spec, run through strategy.target_weights with its defaults; headline table,
yearly table, figures for alphas/crypto-perps/retail-crowding-xs/."""
import os
import sys
import numpy as np
import pandas as pd

from common import load, IS, OOS, FULL, ROOT
import research_lib as rl
import strategy as S

sys.path.insert(0, os.path.join(ROOT, "code", "crypto-alts", "shared"))
import figstyle as fs  # noqa: E402

OUT = os.path.join(ROOT, "alphas", "crypto-perps", "retail-crowding-xs")
os.makedirs(OUT, exist_ok=True)

close, vol, met, mask = load(start="2020-01-01")   # full price history: no warm-up edge effects
w = S.target_weights(close, vol, met["count_long_short_ratio"]).loc["2021-12-01":]
close = close.loc["2021-12-01":]
ref = pd.read_parquet("exp04_weights.parquet")
print("max |w - exp04 w|:", float((w - ref.reindex_like(w)).abs().max().max()))

net, st = rl.backtest_xs(w, close, cost_bps=10.0, name="retail-crowding-xs")
net = net.loc[FULL[0]:]
tab = {}
for k, (a, b) in {"Full 2022-03→2026-09": FULL, "IS 2022-03→2023-12": IS, "OOS 2024-01→2026-09": OOS}.items():
    s = rl.perf_stats(net.loc[a:b])
    tab[k] = s[["Sharpe", "CAGR", "Vol", "MaxDD", "Sortino", "Calmar", "HitRate", "t_NW"]]
tab = pd.DataFrame(tab).T
print(tab.round(3).to_string())
we = w.shift(1).loc[FULL[0]:]
print("turnover/yr", round(st["Turnover_ann"], 1), "| avg gross", round(we.abs().sum(axis=1).mean(), 3),
      "| max gross", round(we.abs().sum(axis=1).max(), 3), "| avg net", round(we.sum(axis=1).mean(), 3),
      "| avg names long/short", round((we > 0).sum(axis=1).mean(), 1), round((we < 0).sum(axis=1).mean(), 1))
for c in (5, 20, 30):
    n2, _ = rl.backtest_xs(w, close, cost_bps=c)
    print(f"cost {c}bp: SR full {rl.perf_stats(n2.loc[FULL[0]:])['Sharpe']:.2f}"
          f" OOS {rl.perf_stats(n2.loc[OOS[0]:])['Sharpe']:.2f}")
yr = net.groupby(net.index.year).agg(ret=lambda r: (1 + r).prod() - 1,
                                     sharpe=lambda r: r.mean() / r.std() * np.sqrt(365))
print(yr.round(3).to_string())
tab.to_csv("exp06_headline.csv")
net.to_frame("net").to_parquet("exp06_net.parquet")

# figures
fs.setup()
import matplotlib.pyplot as plt  # noqa: E402
eq = (1 + net).cumprod()
dd = eq / eq.cummax() - 1
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 5.2), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
ax.plot(eq.index, eq.values, color=fs.SERIES[0], lw=1.8)
ax.axvline(pd.Timestamp(OOS[0]), color=fs.MUTED, lw=0.8, ls="--")
ax.annotate("out-of-sample →", (pd.Timestamp(OOS[0]), eq.max()), xytext=(6, 0), textcoords="offset points",
            fontsize=9, color=fs.INK2, va="top")
ax.set_title("retail-crowding-xs — growth of $1, net of 10 bp/side")
ax.set_ylabel("equity")
ax2.fill_between(dd.index, dd.values, 0, color=fs.SERIES[0], alpha=0.35, lw=0)
ax2.set_ylabel("drawdown")
ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
fig.tight_layout()
fig.savefig(os.path.join(OUT, "equity.png"), dpi=130)

fig, ax = plt.subplots(figsize=(7, 3.2))
ax.bar([str(y) for y in yr.index], yr["sharpe"].values, color=fs.SERIES[0], width=0.6)
for i, v in enumerate(yr["sharpe"].values):
    ax.annotate(f"{v:.2f}", (i, v), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=9, color=fs.INK2)
ax.axhline(0, color=fs.AXIS, lw=0.8)
ax.set_title("Sharpe by calendar year (2022 from March, 2026 to September)")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "yearly_sharpe.png"), dpi=130)
print("figures ->", OUT)
