"""Figures for the report: turnover/decay curve (screen2), equity curves of the best variants."""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from panel import load_panel
from xs_lib import *
from research_lib import load_series
FIG = os.path.join(HERE, "..", "..", "..", "past_research", "us-large-cap", "industry-residual-reversal", "figures")
s2 = pd.read_csv(os.path.join(HERE, "screen2_results.csv"))
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
for (combo, w), g in s2.groupby(["combo", "w"]):
    if combo in ("rev5_sec", "rev5+rev21", "all6") and w in ("decile", "linear"):
        ax[0].plot(g.hold, g.GrossSh, "o-", label=f"{combo}/{w} gross"); ax[0].plot(g.hold, g.Net, "x--", label=f"{combo}/{w} net 5bp")
ax[0].set_xlabel("holding tranche (days)"); ax[0].set_ylabel("Sharpe"); ax[0].axhline(1.5, c="r", lw=.7, ls=":"); ax[0].axhline(0, c="k", lw=.5); ax[0].legend(fontsize=6); ax[0].set_title("Reversal: gross vs net Sharpe by holding period"); ax[0].grid(alpha=.3)
ax[1].scatter(s2.Turn, s2.GrossSh - s2.Net, s=12); ax[1].set_xlabel("one-way turnover (book/yr)"); ax[1].set_ylabel("Sharpe lost to 5bp cost"); ax[1].set_title("Cost drag vs turnover (all variants)"); ax[1].grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "01_turnover_decay.png"), dpi=110)

P = load_panel(); C, M = P["close"], P["member"]; sec = P["sector"].fillna("UNK")
ret = C.pct_change(); mask = M & C.notna().rolling(60).sum().ge(55) & C.notna()
def cum(n): return (C / C.shift(n) - 1)
def sres(x): return group_demean(x, sec, mask)
Z = lambda s: zscore_xs(s, mask)
vix = load_series("^VIX")["Close"].reindex(C.index).ffill()
sig = (Z(-sres(cum(5))) + Z(-sres(cum(21)))) / 2
w_lin = smooth_weights(linear_weights(rank_xs(sig, mask), mask), 3)
w_dec = decile_weights(Z(-sres(cum(5))), mask, 0.1)
curves = {}
for lab, w, cb in [("decile rev5 hold1 gross", w_dec, 0), ("decile rev5 hold1 net5bp", w_dec, 5), ("linear rev5+21 hold3 gross", w_lin, 0),
                   ("linear rev5+21 hold3 net5bp", w_lin, 5), ("linear rev5+21 hold3, VIX>25 gate, net5bp", w_lin.mul((vix > 25).astype(float), axis=0), 5)]:
    net, st = xs_backtest(w, ret, cost_bps=cb); curves[lab] = net
fig, ax = plt.subplots(figsize=(9, 4.5))
for k, s in curves.items(): ax.plot((1 + s).cumprod(), label=k, lw=1.1)
ax.axvline(pd.Timestamp("2018-01-01"), c="k", ls=":", lw=.8); ax.set_title("Sector-residual reversal, dollar-neutral: growth of $1"); ax.legend(fontsize=7); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "02_equity.png"), dpi=110)
# yearly gross Sharpe of decile rev5 (where does reversal pay?)
g = curves["decile rev5 hold1 gross"]; ys = g.groupby(g.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(252))
vy = vix.groupby(vix.index.year).mean()
fig, ax = plt.subplots(figsize=(8, 3.8)); ax.bar(ys.index, ys.values, color="#4a7"); ax2 = ax.twinx(); ax2.plot(vy.index, vy.values, "k.-", lw=.8); ax2.set_ylabel("avg VIX")
ax.set_title("Gross Sharpe by year, decile rev5 (bars) vs average VIX (line)"); ax.grid(alpha=.3); fig.tight_layout(); fig.savefig(os.path.join(FIG, "03_yearly_gross_vs_vix.png"), dpi=110)
print(ys.round(2).to_string())
