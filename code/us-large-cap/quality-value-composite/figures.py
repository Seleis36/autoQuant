"""Figure: cumulative net return of the IS-selected blend (levered to 10% IS vol) and its sleeves."""
import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import *
import screen3_blend as s3
OUT = os.path.join(HERE, "..", "..", "..", "past_research", "us-large-cap", "quality-value-composite", "figures")
fig, ax = plt.subplots(2, 1, figsize=(10, 8))
for k in s3.R:
    r = s3.R[k] * (0.10 / (s3.R[k].loc[:"2017"].std() * np.sqrt(252)))
    ax[0].plot(r.cumsum(), lw=1, label=k.replace("|", " "))
ax[0].axvline(pd.Timestamp("2018-01-01"), color="k", ls="--", lw=0.8)
ax[0].set_title("Sleeves, net 5 bp, each scaled to 10% IS vol (cumulative sum of returns)"); ax[0].legend(fontsize=7)
ax[1].plot(s3.net10.cumsum(), color="C3")
ax[1].axvline(pd.Timestamp("2018-01-01"), color="k", ls="--", lw=0.8)
_r = splits_row(s3.net10)
ax[1].set_title("IS-selected equal-risk blend, levered to 10%% IS vol, net 5 bp (%.2f / IS %.2f / OOS %.2f)" % (_r["FULL"], _r["IS"], _r["OOS"]))
plt.tight_layout(); plt.savefig(os.path.join(OUT, "01_blend_equity.png"), dpi=110)
