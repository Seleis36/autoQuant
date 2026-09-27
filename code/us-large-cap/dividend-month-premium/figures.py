"""Event-time profile around predicted ex-dividend dates (sector-residual bp, cumulative)."""
import os
import pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "..", "past_research", "us-large-cap", "dividend-month-premium", "figures")
p = pd.read_csv(os.path.join(HERE, "event_profile.csv"), index_col=0).iloc[:, 0]
fig, ax = plt.subplots(figsize=(9, 4))
ax.plot(p.index, p.cumsum().values, marker="o", ms=3)
ax.axvline(0, color="k", ls="--", lw=0.8); ax.axhline(0, color="k", lw=0.5)
ax.set_xlabel("bars relative to predicted ex-date (last year's ex-date + 364 d)")
ax.set_ylabel("cumulative sector-residual bp"); ax.set_title("S&P 500 payers, 22,288 predicted ex-dates 2010-2026")
plt.tight_layout(); plt.savefig(os.path.join(OUT, "01_event_profile.png"), dpi=110)
