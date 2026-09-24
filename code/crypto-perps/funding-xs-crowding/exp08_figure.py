"""Equity curves of the funding sleeve, plain BAB and the 50/50 combo (exp06 nets)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

n = pd.read_parquet("exp06_nets.parquet").loc["2020-09-01":]
cols = {"fund_ens_n20_lag0_c10": ("Funding sleeve (this idea)", "#2a6fdb"),
        "bab_n20_lag0_c10": ("Beta-neutral BAB (reference)", "#9aa3ad"),
        "combo_n20_lag0_c10": ("50/50 combo", "#e07a1f")}
fig, ax = plt.subplots(figsize=(10, 5))
for k, (lab, col) in cols.items():
    ax.plot(np.log((1 + n[k]).cumprod()), label=lab, color=col, lw=1.6)
ax.axvline(pd.Timestamp("2023-01-01"), color="k", ls="--", lw=0.8)
ax.text(pd.Timestamp("2023-01-15"), ax.get_ylim()[1] * 0.92, "OOS →", fontsize=9)
ax.set_ylabel("log cumulative return (net 10 bp/side)")
ax.set_title("funding-xs-crowding: contrarian XS funding sleeve vs BAB")
ax.spines[["top", "right"]].set_visible(False)
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig("../../../past_research/crypto-perps/funding-xs-crowding/equity.png", dpi=120)
