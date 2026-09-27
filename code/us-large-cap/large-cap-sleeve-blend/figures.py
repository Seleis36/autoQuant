"""Blend figures: cumulative net return of the 4-sleeve blend (weight-level, 5 bp) and its
sleeves at their blend multipliers; yearly Sharpe."""
import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "..", "past_research", "us-large-cap", "large-cap-sleeve-blend", "figures")
ALPHA = os.path.join(HERE, "..", "..", "..", "alphas", "us-large-cap", "large-cap-sleeve-blend")
sys.path.insert(0, HERE)
MULT = {"RM": 0.457, "QVC": 2.478, "TXT": 2.664, "REC": 1.211}
b = pd.read_parquet(os.path.join(HERE, "nets_0_blend_weightlevel.parquet"))["blend"]
S = pd.read_parquet(os.path.join(HERE, "nets_0_sleeves.parquet"))
fig, ax = plt.subplots(2, 1, figsize=(10, 8))
ax[0].plot(b.cumsum(), color="k", lw=1.6, label="blend (1.03 / IS 1.57 / OOS 0.81)")
for k, c in zip(MULT, ["C3", "C0", "C2", "C1"]):
    ax[0].plot((S[k] * MULT[k]).cumsum(), color=c, lw=0.9, label=f"{k} x{MULT[k]}")
ax[0].axvline(pd.Timestamp("2018-01-01"), color="k", ls="--", lw=0.8)
ax[0].set_title("S&P 500 market-neutral sleeve blend, net 5 bp, cumulative return (sum)"); ax[0].legend(fontsize=8)
yr = b.groupby(b.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(252))
ax[1].bar(yr.index, yr.values, color=["C2" if v > 0 else "C3" for v in yr.values]); ax[1].axhline(0, color="k", lw=0.6)
ax[1].set_title("blend yearly Sharpe")
plt.tight_layout()
os.makedirs(OUT, exist_ok=True); os.makedirs(ALPHA, exist_ok=True)
plt.savefig(os.path.join(OUT, "01_blend_equity_yearly.png"), dpi=110)
plt.savefig(os.path.join(ALPHA, "blend_equity_yearly.png"), dpi=110)
