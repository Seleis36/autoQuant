"""Event-time profile of S&P 500 additions and (non-acquisition) deletions, 2010-2026:
mean cumulative sector-residual return from bar -15 to +20 around the effective date."""
import os, runpy
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "..", "past_research", "us-large-cap", "index-reconstitution", "figures")
g = runpy.run_path(os.path.join(HERE, "event_study.py"), run_name="es")
E, C, dates = g["E"], g["C"], g["dates"]
K = np.arange(-15, 21)
fig, ax = plt.subplots(figsize=(9, 4.5))
for (side, kind), lab in {("add", None): "additions (N=%d)", ("del", "cap"): "deletions, not acquisition-driven (N=%d)"}.items():
    e = E[(E.side == side) & ((E.kind == kind) if kind else True)]
    e = e[e.ri + 20 < len(dates)]
    base = C[e.ri.values - 16, e.ci.values]
    prof = [np.nanmean((C[e.ri.values + k, e.ci.values] - base) * 1e4) for k in K]
    ax.plot(K, prof, marker="o", ms=3, label=lab % len(e))
ax.axvline(-1, color="k", ls=":", lw=0.8); ax.axvline(0, color="k", ls="--", lw=0.8); ax.axhline(0, color="k", lw=0.5)
ax.set_xlabel("bars vs effective date (0 = first session in/out of the index; index funds trade at close of -1)")
ax.set_ylabel("cumulative sector-residual bp (from bar -16)"); ax.legend()
ax.set_title("S&P 500 index changes 2010-2026: run-up, then post-inclusion reversal")
plt.tight_layout(); plt.savefig(os.path.join(OUT, "01_event_profile.png"), dpi=110)
