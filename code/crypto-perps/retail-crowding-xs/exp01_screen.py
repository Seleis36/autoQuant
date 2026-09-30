"""exp01 — feature screen: is the retail long/short account ratio a cross-sectional signal?

Feature: x = log(count_long_short_ratio), the head-count ratio dominated by small accounts.
Normalisations (pre-declared):
  raw     x                                     (includes each coin's fixed effect)
  dm90    x - mean_90d(x)                       (own-history demeaned)
  z90     (x - mean_90d) / std_90d
  exmed   x - expanding median(x)               (the spot-btc perp-crowding rule)
  chg7    x - x.shift(7)
Both signs (contrarian = short high), q30 long/short, beta-neutral, hold 1 day or 7-day
tranches. ICs at 1/7/14 days are printed for each normalisation (contrarian sign).
"""
import numpy as np
import pandas as pd

from common import (load, btc_beta, beta_neutral, quantile_ls, tranche, evaluate, ic_table,
                    IS, OOS)

close, vol, met, mask = load()
beta = btc_beta(close)
x = np.log(met["count_long_short_ratio"])


def norms(x):
    m90 = x.rolling(90, min_periods=60).mean()
    s90 = x.rolling(90, min_periods=60).std()
    return {
        "raw": x,
        "dm90": x - m90,
        "z90": (x - m90) / s90,
        "exmed": x - x.expanding(min_periods=60).median(),
        "chg7": x - x.shift(7),
    }


rows, ics = [], []
for nname, f in norms(x).items():
    ic = ic_table(-f, close, mask)
    for per, (a, b) in {"IS": IS, "OOS": OOS}.items():
        seg = ic.loc[a:b]
        ics.append({"feat": nname, "per": per,
                    **{f"IC{h}": seg[h].mean() for h in seg},
                    **{f"t{h}": seg[h].mean() / seg[h].std() * np.sqrt(seg[h].notna().sum() / h) for h in seg}})
    for sign in (+1, -1):
        for h in (1, 7):
            w = tranche(beta_neutral(quantile_ls(sign * f, mask), beta), h)
            name = f"{'-' if sign < 0 else '+'}{nname}_h{h}"
            _, row = evaluate(w, close, name)
            rows.append(row)

pd.set_option("display.width", 200)
print("contrarian ICs (signal = -feature), t uses non-overlapping-equivalent n")
print(pd.DataFrame(ics).round(3).to_string(index=False))
res = pd.DataFrame(rows)
print(res.round(2).to_string(index=False))
res.to_csv("exp01_results.csv", index=False)
print("universe size:", mask.sum(axis=1).loc[IS[0]:].describe().round(1).to_dict())
