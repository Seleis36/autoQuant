"""exp04 -- figures for the report/spec: equity (log), drawdown, funding vs basis decomposition, yearly Sharpe."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from carry_lib import *
OUT = os.path.join(ROOT, "alphas", "crypto-perps", "funding-carry"); os.makedirs(OUT, exist_ok=True)
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"; INK, INK2, SURF = "#0b0b0b", "#52514e", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e6e5e1", "grid.linewidth": 0.6, "font.size": 10})
d = pd.read_parquet(os.path.join(os.path.dirname(os.path.abspath(__file__)), "exp03_daily.parquet"))
L = 1.0; cf = 1/(1+1/L)
eq = (1 + d["port"]*cf).cumprod(); eqb = (1 + d["BTCUSDT"]*cf).cumprod(); eqe = (1 + d["ETHUSDT"]*cf).cumprod()

fig, ax = plt.subplots(figsize=(10, 4.2))
ax.plot(eq.index, eq, color=C1, lw=2, label="BTC+ETH carry (L=1)")
ax.plot(eqb.index, eqb, color=C2, lw=1.2, label="BTC only")
ax.plot(eqe.index, eqe, color=C3, lw=1.2, label="ETH only")
ax.set_title("Funding carry: long spot / short perp, always on, net of 20 bp per switch", loc="left")
ax.set_ylabel("Growth of 1 (return on capital, L=1)"); ax.legend(frameon=False, loc="upper left")
for s, e in [(eq, C1), (eqb, C2), (eqe, C3)]:
    ax.annotate(f"{s.iloc[-1]:.2f}", (s.index[-1], s.iloc[-1]), xytext=(4, 0), textcoords="offset points", color=INK2, fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "equity.png"), dpi=150); plt.close(fig)

dd = eq / eq.cummax() - 1
fig, ax = plt.subplots(figsize=(10, 2.6))
ax.fill_between(dd.index, dd*100, 0, color=C1, alpha=0.35, lw=0); ax.plot(dd.index, dd*100, color=C1, lw=1)
ax.set_title("Drawdown, % of capital (L=1)", loc="left"); ax.set_ylabel("%")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "drawdown.png"), dpi=150); plt.close(fig)

# yearly Sharpe and return, BTC+ETH
g = d["port"]*cf
yr = g.groupby(g.index.year).agg(sharpe=lambda x: x.mean()/x.std()*np.sqrt(365), ret=lambda x: ((1+x).prod()-1)*100)
fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
axes[0].bar(yr.index.astype(str), yr["sharpe"], color=C1, width=0.6); axes[0].axhline(3, color=C2, lw=1.2, ls="--"); axes[0].set_title("Sharpe by calendar year (dashed = 3.0)", loc="left")
axes[1].bar(yr.index.astype(str), yr["ret"], color=C1, width=0.6); axes[1].set_title("Return on capital by year, % (L=1)", loc="left")
for ax in axes: ax.grid(axis="x", visible=False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "yearly.png"), dpi=150); plt.close(fig)

# funding vs basis decomposition, BTC, monthly
df = load_pair("BTCUSDT", start="2020-01-01"); r = leg_returns(df)
fund = (df["f"]*df["P"]/df["S"].shift(1)).fillna(0); basis = r - fund
m = pd.DataFrame({"funding": fund.resample("MS").sum()*100, "basis change": basis.resample("MS").sum()*100})
fig, ax = plt.subplots(figsize=(10, 3.4))
ax.bar(m.index, m["funding"], width=20, color=C1, label="funding received")
ax.bar(m.index, m["basis change"], width=20, color=C2, label="basis mark-to-market")
ax.set_title("BTC: monthly return on one-leg notional, % -- funding vs basis", loc="left"); ax.legend(frameon=False); ax.grid(axis="x", visible=False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "decomposition.png"), dpi=150); plt.close(fig)
print("figures written to", OUT)
