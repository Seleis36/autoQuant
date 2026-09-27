"""Figures: purchase-event residual return by year (event-weighted vs one-per-ticker-week) and
the cumulative net return of the best cross-sectional insider book."""
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "..", "past_research", "us-large-cap", "insider-opportunistic-buys", "figures")
E = pd.read_parquet("/tmp/insider_events.parquet")
X = E[(E.code == "P") & ~E.is_10pct_only].copy(); X["yr"] = X.entry.dt.year
X["wk"] = X.entry.dt.to_period("W")
D = X.sort_values("entry").drop_duplicates(["ticker", "wk"])
a = X.groupby("yr").h21.mean(); b = D.groupby("yr").h21.mean()
fig, ax = plt.subplots(figsize=(10, 4))
ax.bar(a.index - 0.2, a.values, 0.4, label="all purchase events (event-weighted)")
ax.bar(b.index + 0.2, b.values, 0.4, label="one per ticker-week")
ax.axhline(0, color="k", lw=0.6); ax.set_ylabel("sector-residual bp, bars +1..+21")
ax.set_title("Insider purchases, S&P 500 members: the average is 2010's 3,024 clustered events"); ax.legend()
plt.tight_layout(); plt.savefig(os.path.join(OUT, "01_purchase_event_by_year.png"), dpi=110)
