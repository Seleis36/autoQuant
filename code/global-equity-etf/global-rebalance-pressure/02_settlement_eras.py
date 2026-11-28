"""Mechanism test: if calendar rebalancers trade so that their trades SETTLE by the month-end,
the pressure day should sit at L - (settlement lag): T+5 before 1995-06-07, T+3 until
2017-09-05, T+2 until 2024-05-28, T+1 after. Slope of the next-session equity return on the
calendar-fund drift, by days left in the month of the earned session and by settlement era.
ETF era: SPY/IEF drift -> SPY and EFA. Backcast: S&P/syn10 drift -> S&P (pre-2002 bonds)."""
import numpy as np, pandas as pd
from grp_lib import load_etf, load_back, drift_z, days_left, month_end_flags, slope_t

ERAS = {"T+5 1980-95.06": ("1980-01-01", "1995-06-06"), "T+3 1995.06-2017.08": ("1995-06-07", "2017-09-04"),
        "T+3 ETF 2002.08-2017.08": ("2002-08-01", "2017-09-04"),
        "T+2 2017.09-2024.05": ("2017-09-05", "2024-05-27"), "T+1 2024.05-": ("2024-05-28", "2026-12-31")}

def table(z, y, me, eras):
    dl = days_left(z.index, me)
    df = pd.DataFrame({"z": z, "y": y.shift(-1), "dl": dl.shift(-1)}).dropna()
    out = {}
    for en, (a, b) in eras.items():
        d = df.loc[a:b]
        for k in range(0, 7):
            g = d[d.dl == k]
            out.setdefault(en, {})[f"L-{k}"] = "%6.1f(%5.2f)" % slope_t(g.z.values, g.y.values)
        g = d[d.dl >= 7]
        out[en]["mid(>=7)"] = "%6.1f(%5.2f)" % slope_t(g.z.values, g.y.values)
        out[en]["months"] = int((d.dl == 0).sum())
    return pd.DataFrame(out).T

pd.set_option("display.width", 220)
Bk = load_back(); meb = month_end_flags(Bk.index); zb = drift_z(Bk.EQ, Bk.BD, meb)
print("=== S&P 500 / syn10 (index data), next-session S&P return")
print(table(zb, Bk.EQ, meb, {k: v for k, v in ERAS.items() if "ETF" not in k}).to_string())
C, R = load_etf(); me = month_end_flags(R.index); z = drift_z(R.SPY, R.IEF, me)
for on in ["SPY", "EFA", "BASKET"]:
    print(f"\n=== ETF: SPY/IEF drift -> {on}")
    print(table(z, R[on], me, {k: v for k, v in ERAS.items() if k.startswith(("T+3 ETF", "T+2", "T+1"))}).to_string())
