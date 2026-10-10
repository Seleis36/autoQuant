"""Mechanism check on the pre-ETF sample: muni mutual-fund NAVs (price-only, 1980+) against
the synthetic 10y Treasury return. NAVs are struck from evaluated prices, so a lag here is
expected; the point is that it is long-standing and of the size the ETFs inherit a part of.
This is evidence about WHY, not a backtest: a mutual-fund NAV cannot be traded on it.
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/seleis/autoQuant/code/rates-bonds/shared")
from rb_data import cmt_returns

nav = pd.read_parquet("/home/seleis/autoQuant/data/MUNI_FUNDS_nav_d.parquet")
nav.index = pd.to_datetime(nav.index)
r = nav[[c for c in nav if c.endswith("_nav")]].pct_change(fill_method=None)
r.columns = [c[:-4] for c in r.columns]
syn = cmt_returns(maturities=(10,))[10]
for a, b in (("1990", "1999"), ("2000", "2007"), ("2008", "2017"), ("2018", "2026")):
    out = []
    for f in ("VWITX", "VWLTX"):
        df = pd.concat([r[f]] + [syn.shift(j).rename(f"L{j}") for j in range(4)], axis=1).loc[a:b].dropna()
        X = np.column_stack([np.ones(len(df)), df.iloc[:, 1:].values])
        bta = np.linalg.lstsq(X, df.iloc[:, 0].values, rcond=None)[0]
        out.append("%s  same-day %.2f  lag1 %.2f  lag2 %.2f  lag3 %.2f" % (f, *bta[1:5]))
    print(a, "-", b, " | ".join(out))
