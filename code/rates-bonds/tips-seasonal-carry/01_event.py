"""tips-seasonal-carry -- is the known TIPS inflation accrual priced?

TIPS reference CPI on day k of month M interpolates linearly from CPI_NSA(M-3) (on the 1st) to
CPI_NSA(M-2) (on the 1st of M+1). So the accrual earned by a TIPS holder over month M is
    a(M) = CPI_NSA(M-2) / CPI_NSA(M-3) - 1,
fully known once CPI(M-2) is published (about mid-month M-1), i.e. before month M starts.
The NSA CPI has a large seasonal (Jan-May prints high, Oct-Dec low/negative), so a(M) swings
by ~0.6-0.8 %/month through the year while the nominal alternative's carry does not.

Test: monthly TIPS-ETF excess over a hedge of nominal Treasuries, x(M) = r_tips(M) - b * r_nom(M)
(b = trailing 252-day OLS beta ending at M-1's last close), against a(M) and against its
seasonal part a(M) - mean(a over the prior 12 months). If the market fully prices known carry
into real yields, the slope is ~0; if not, it is ~1.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, fred  # noqa: E402

pd.set_option("display.width", 200)


def accrual_monthly():
    cpi = fred("CPIAUCNS")
    cpi.index = cpi.index.to_period("M")
    a = cpi.shift(2) / cpi.shift(3) - 1          # indexed by month M
    a.index = a.index  # PeriodIndex M
    # extend one month ahead: a(M+1) uses CPI(M-1) and CPI(M-2) -- known mid-M
    last = cpi.index.max()
    nxt = pd.Series({last + 1: cpi[last - 1] / cpi[last - 2] - 1, last + 2: cpi[last] / cpi[last - 1] - 1})
    return pd.concat([a, nxt]).dropna()


def main():
    pairs = [("TIP", "IEF"), ("TIP", "IEI"), ("SCHP", "IEI"), ("STIP", "SHY"), ("VTIP", "VGSH"),
             ("STIP", "VGSH"), ("LTPZ", "TLT")]
    tick = sorted({t for p in pairs for t in p})
    px = etf_close(tick)
    r = px.pct_change()
    a = accrual_monthly()
    mret = (1 + r).groupby(r.index.to_period("M")).prod() - 1
    rows = []
    for tp, nm in pairs:
        d = r[[tp, nm]].dropna()
        # trailing daily beta at each month-end
        cov = d[tp].rolling(252).cov(d[nm]); var = d[nm].rolling(252).var()
        beta = (cov / var).groupby(d.index.to_period("M")).last().shift(1)
        mm = mret[[tp, nm]].dropna()
        x = (mm[tp] - beta.reindex(mm.index) * mm[nm]).dropna()
        df = pd.DataFrame({"x": x, "a": a.reindex(x.index)}).dropna()
        df["a_seas"] = df["a"] - a.rolling(12).mean().shift(1).reindex(df.index)
        df = df.dropna()
        for lab, sub in (("all", df), ("<=2017", df.loc[:"2017"]), (">=2018", df.loc["2018":])):
            if len(sub) < 24:
                continue
            X = np.c_[np.ones(len(sub)), sub["a_seas"]]
            coef, *_ = np.linalg.lstsq(X, sub["x"].values, rcond=None)
            res = sub["x"].values - X @ coef
            se = np.sqrt(res.var(ddof=2) / ((sub["a_seas"] - sub["a_seas"].mean()) ** 2).sum())
            rows.append(dict(pair=f"{tp}-{nm}", sample=lab, n=len(sub), start=str(sub.index[0]),
                             slope=coef[1], t=coef[1] / se, corr=sub["x"].corr(sub["a_seas"]),
                             x_vol_m=sub["x"].std() * 100, a_seas_sd=sub["a_seas"].std() * 100))
    out = pd.DataFrame(rows)
    print("slope of monthly hedged TIPS excess on the seasonal part of the KNOWN accrual")
    print(out.round(3).to_string(index=False))

    # seasonal profile: mean known accrual and mean hedged excess by calendar month
    tp, nm = "STIP", "SHY"
    d = r[[tp, nm]].dropna()
    cov = d[tp].rolling(252).cov(d[nm]); var = d[nm].rolling(252).var()
    beta = (cov / var).groupby(d.index.to_period("M")).last().shift(1)
    mm = mret[[tp, nm]].dropna()
    x = (mm[tp] - beta.reindex(mm.index) * mm[nm]).dropna()
    prof = pd.DataFrame({"a": a.reindex(x.index), "x_STIP_SHY": x})
    prof["month"] = prof.index.month
    print("\nby calendar month (bp): known accrual a(M) vs hedged STIP-SHY excess")
    print((prof.groupby("month").mean() * 1e4).round(1).T.to_string())


if __name__ == "__main__":
    main()
