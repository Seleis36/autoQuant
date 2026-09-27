"""Figures for residual-momentum: spec equity (10 % vol, net 5 bp) vs raw 12-1 momentum, and
yearly Sharpe."""
import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "..", "past_research", "us-large-cap", "residual-momentum", "figures")
spec = pd.read_parquet(os.path.join(HERE, "nets_0_spec10.parquet"))["rm10"]
s1 = pd.read_parquet(os.path.join(HERE, "nets_0_screen1.parquet"))
raw = s1["raw_12_1|linear|beta"]; raw = raw * (0.10 / (raw.loc[:"2017"].std() * np.sqrt(252)))
res = s1["resid_MS_12_1_t|linear|beta"]; res = res * (0.10 / (res.loc[:"2017"].std() * np.sqrt(252)))
fig, ax = plt.subplots(2, 1, figsize=(10, 8))
ax[0].plot(spec.cumsum(), label="SPEC: residual 12-1 t-stat, beta-hedged, vol-managed (0.63 / IS 0.61 / OOS 0.63)", color="C3")
ax[0].plot(res.cumsum(), label="residual 12-1, beta-hedged, no vol management (0.49)", color="C1", lw=0.9)
ax[0].plot(raw.cumsum(), label="raw 12-1 momentum, beta-hedged (0.19)", color="C7", lw=0.9)
ax[0].axvline(pd.Timestamp("2018-01-01"), color="k", ls="--", lw=0.8)
ax[0].set_title("S&P 500 sector-neutral momentum books, 10 % vol (IS), net 5 bp -- cumulative return"); ax[0].legend(fontsize=8)
yr = spec.groupby(spec.index.year).agg(lambda x: x.mean() / x.std() * np.sqrt(252))
ax[1].bar(yr.index, yr.values, color=["C2" if v > 0 else "C3" for v in yr.values]); ax[1].axhline(0, color="k", lw=0.6)
ax[1].set_title("SPEC yearly Sharpe")
plt.tight_layout(); plt.savefig(os.path.join(OUT, "01_equity_yearly.png"), dpi=110)
import shutil; shutil.copy(os.path.join(OUT, "01_equity_yearly.png"),
                           os.path.join(HERE, "..", "..", "..", "alphas", "us-large-cap", "residual-momentum", "equity_yearly.png"))
