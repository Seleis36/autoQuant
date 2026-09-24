"""exp03 — the uncompressed basis: premium-index features, cross-sectional.

Funding is premium + clamp(0.01% - premium, +-0.05%), so a small premium maps to exactly
0.01% and the information is lost. The premium index keeps it. Same grid discipline as
exp01: both signs, k in {1,3,7,14,30}, h in {1,7}, plus z-scored and change features;
dollar-neutral q30 and beta-neutral q30.
"""
import itertools
import numpy as np
import pandas as pd
import common as c
import funding_panel as fp
import research_lib as rl
from exp02_refine import beta_neutral, beta  # noqa: E402  (re-runs exp02 once; cheap enough)

close, vol, fund, mask = c.load()
prem = fp.daily_premium(close.columns).reindex(close.index)
prem = prem.reindex(columns=close.columns)
pmask = mask & prem.notna()

F = {}
for k in (1, 3, 7, 14, 30):
    F[f"prem_{k}"] = prem.rolling(k, min_periods=max(1, int(k * 0.7))).mean()
F["prem_chg_3_30"] = F["prem_3"] - F["prem_30"]
mu = prem.rolling(90, min_periods=60).mean()
sd = prem.rolling(90, min_periods=60).std()
F["prem_z7_90"] = (F["prem_7"] - mu) / sd
# premium relative to the cross-section median (removes the common leg)
F["prem_rel_7"] = F["prem_7"].sub(F["prem_7"].where(pmask).median(axis=1), axis=0)

rows = []
for (fname, f), sign, h, neu in itertools.product(F.items(), (+1, -1), (1, 7), ("dollar", "beta")):
    w = rl.quantile_weights(sign * f, pmask, q=0.3)
    if neu == "beta":
        w = beta_neutral(w, beta)
    w = c.tranche(w, h)
    _, row = c.evaluate(w, close, f"{'+' if sign > 0 else '-'}{fname}_h{h}_{neu}")
    rows.append(row)
res = pd.DataFrame(rows).set_index("name")
res.to_csv("exp03_results.csv")
pd.set_option("display.width", 200)
print(rl.fmt(res).to_string())
