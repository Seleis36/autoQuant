"""exp05 — implementation sensitivity (not selection): when in the day the ratio is sampled,
the metrics-history eligibility rule the live REST feed can satisfy, and one pre-declared
composite with the top-trader position ratio.

  cutoff 23 (base) / 20 / 12 h; daily mean of stamps instead of the last stamp
  min_metric_days 60 (base) / 30 / 7   (REST serves 30 days; the archive files are on disk)
  composite: rank(-log global account ratio) + rank(-log top-trader position ratio)
"""
import numpy as np
import pandas as pd

import common as cm
from common import btc_beta, beta_neutral, quantile_ls, tranche, evaluate
import metrics_panel as mp
import funding_panel as fp

close, vol, met, mask = cm.load()
beta = btc_beta(close)
inv = {v: k for k, v in fp.PERP_OF.items()}
rows = []


def run(sig, m, name):
    w = tranche(beta_neutral(quantile_ls(sig, m), beta), 7)
    _, row = evaluate(w, close, name)
    rows.append(row)


def ratio(cutoff=23, how="last"):
    d = mp.daily_metrics(list(fp.PERP_OF.values()), cutoff_hour=cutoff, how=how)["count_long_short_ratio"]
    return d.rename(columns=inv).reindex(index=close.index, columns=close.columns)


def mask_for(r, min_days):
    med = vol.rolling(90, min_periods=45).median()
    hist = close.notna().cumsum()
    elig = (hist >= 120) & (med >= 1e6) & close.notna() & (r.notna().cumsum() >= min_days) & r.notna()
    return (med.where(elig).rank(axis=1, ascending=False) <= 20) & elig


x = np.log(met["count_long_short_ratio"])
run(-x, mask, "base (last stamp < 23:00, 60d)")
for c in (20, 12):
    r = ratio(cutoff=c)
    run(-np.log(r), mask_for(r, 60), f"last stamp < {c}:00")
r = ratio(how="mean")
run(-np.log(r), mask_for(r, 60), "daily mean of stamps")
for md in (30, 7):
    run(-x, mask_for(met["count_long_short_ratio"], md), f"min_metric_days {md}")
pos = np.log(met["sum_toptrader_long_short_ratio"])
comp = (-x).where(mask).rank(axis=1, pct=True) + (-pos).where(mask).rank(axis=1, pct=True)
run(comp, mask, "composite acc + toptrader pos")
pd.set_option("display.width", 200)
res = pd.DataFrame(rows)
print(res.round(2).to_string(index=False))
res.to_csv("exp05_results.csv", index=False)
