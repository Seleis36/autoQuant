"""Screen realized-moment features vs forward BTC returns (1, 3, 7 days).

Sampling: non-overlapping every h days for the IC (lags = 1 in NW), IS <= 2022, OOS 2023+.
Two statistics per feature: raw rank IC, and a partial IC after regressing the ranked
feature on the ranked same-window return (so RSJ/RSK are not just past return in disguise).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily  # noqa: E402
import research_lib as rl  # noqa: E402
from features import daily_moments, window_features  # noqa: E402


def ranks(x):
    r = x.rank()
    return (r - r.mean()) / r.std()


def stats(x, y, ctrl=None):
    m = x.notna() & y.notna() & (ctrl.notna() if ctrl is not None else True)
    x, y = ranks(x[m]), ranks(y[m])
    if ctrl is not None:
        c = ranks(ctrl[m])
        beta = (x * c).mean() / (c * c).mean()
        x = x - beta * c
        x = x / x.std()
    p = (x * y).values
    return p.mean(), rl.newey_west_t(p, lags=1), len(p)


def main():
    d = btc_daily()
    dm = daily_moments().reindex(d.index)
    close = d.Close
    feats = pd.concat([window_features(dm, L) for L in (1, 3, 7, 14)], axis=1)
    rows = []
    for h in (1, 3, 7):
        fwd = close.shift(-h) / close - 1
        samp = feats.index[::h]
        for c in feats.columns:
            L = c.split("_")[-1]
            ctrl = feats[f"ret_{L}"] if not c.startswith("ret_") else None
            r = {"feat": c, "h": h}
            for k, (a, b) in {"IS": ("2017-09-01", "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
                x = feats.loc[samp, c].loc[a:b]
                y = fwd.loc[samp].loc[a:b]
                r[f"IC_{k}"], r[f"t_{k}"], _ = stats(x, y)
                if ctrl is not None:
                    r[f"pIC_{k}"], r[f"pt_{k}"], _ = stats(x, y, ctrl.loc[samp].loc[a:b])
            rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(HERE, "exp01_screen.csv"), index=False)
    pd.set_option("display.width", 220)
    for h in (1, 3, 7):
        print(f"\n=== h={h} ===")
        print(res[res.h == h].round(3).to_string(index=False))
    for h in (1, 3, 7):
        s = res[res.h == h]
        print(h, "IS->OOS spearman of t:", round(s.t_IS.corr(s.t_OOS, method="spearman"), 2),
              " partial:", round(s.pt_IS.corr(s.pt_OOS, method="spearman"), 2))


if __name__ == "__main__":
    main()
