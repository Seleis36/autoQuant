"""muni-reinvestment-flow -- the month-start effect on 1990-2007 muni fund NAVs (untouched holdout).

Why NAVs. The ETF month-start effect (02) lives in 2017-2026 and is weak in 2008-2016, and the
ETFs start in 2007, so there is no untouched ETF sample left. Vanguard / T. Rowe muni mutual
funds have daily NAVs from 1980. They are daily-accrual funds: income accrues outside the
NAV and is paid on the last business day of the month, so the UNADJUSTED NAV is a pure price
series with nothing happening at month-start (verified below: no NAV drop on pay dates).

Pre-registered statistic (written before any holdout number was computed):
  hedged daily premium  p_t = r_NAV,t - b0 * r_T,t - b1 * r_T,t-1
  (r_T = synthetic 10y CMT *price* return; b0, b1 trailing 252-day OLS, lagged one day --
  the lagged term absorbs stale evaluated pricing). For each month m:
  D_m = sum of p over trading days 1..5  -  5 * mean(p over days 6..end of m).
  Report mean(D_m) in bp and its t-stat per window, averaged over the six funds
  (VWITX, VWLTX, VWSTX, VMLTX, VWAHX, PRTAX), and per fund.
Windows: 1990-1999, 2000-2007 (the holdout), 2008-2016, 2017-2026. The ETF result (02) is
2017-2026; the claim is only supported if 1990-2007 shows the same sign.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))

import rb_data  # noqa: E402
import curve_lib  # noqa: E402

pd.set_option("display.width", 220)
FUNDS = ["VWITX", "VWLTX", "VWSTX", "VMLTX", "VWAHX", "PRTAX"]
CACHE = os.path.join(rb_data.rl.DATA_DIR, "MUNI_FUNDS_nav_d.parquet")


def navs():
    if os.path.exists(CACHE):
        return pd.read_parquet(CACHE)
    import yfinance as yf
    cols = {}
    for t in FUNDS:
        h = yf.Ticker(t).history(period="max", auto_adjust=False, actions=True)
        h.index = h.index.tz_localize(None)
        cols[(t, "nav")] = h["Close"]
        cols[(t, "div")] = h["Dividends"]
    df = pd.DataFrame(cols)
    df.columns = [f"{a}_{b}" for a, b in df.columns]
    rb_data.rl._atomic_parquet(df, CACHE)
    return df


def tsy_price_returns(n=10):
    y = curve_lib.yields(maturities=(0.25, n), start="1982-01-01")
    yy = y[n]; dy = yy.diff()
    D = pd.Series(curve_lib.par_duration(yy.shift(1), n), index=yy.index)
    C = pd.Series(curve_lib.par_convexity(yy.shift(1), n), index=yy.index)
    return (-D * dy + 0.5 * C * dy ** 2).dropna()


def main():
    nv = navs()
    rt = tsy_price_returns(10)
    # 1. check: NAV change on dividend pay dates vs other days
    print("NAV (unadjusted) mean daily change, bp: dividend pay dates vs other days")
    for t in FUNDS:
        r = nv[f"{t}_nav"].pct_change()
        dv = nv[f"{t}_div"].fillna(0) > 0
        print(f"  {t}: pay dates {r[dv].mean()*1e4:6.2f}  others {r[~dv].mean()*1e4:6.2f}  "
              f"avg dividend/NAV {(nv[f'{t}_div'][dv] / nv[f'{t}_nav'].shift(1)[dv]).mean()*1e4:5.1f} bp")
    rows, fund_D = [], {}
    for t in FUNDS:
        r = nv[f"{t}_nav"].pct_change().dropna()
        r = r[(r.abs() < 0.05)]                      # drop data glitches
        idx = r.index.intersection(rt.index)
        r, x0 = r.reindex(idx), rt.reindex(idx)
        x1 = x0.shift(1)
        # trailing 252d 2-regressor OLS via rolling moments
        Z = pd.concat([r, x0, x1], axis=1, keys=["y", "a", "b"]).dropna()
        m = Z.rolling(252, min_periods=126)
        Saa, Sbb, Sab = m.cov().xs("a", level=1)["a"], m.cov().xs("b", level=1)["b"], m.cov().xs("a", level=1)["b"]
        Sya, Syb = m.cov().xs("a", level=1)["y"], m.cov().xs("b", level=1)["y"]
        det = Saa * Sbb - Sab ** 2
        b0 = ((Sya * Sbb - Syb * Sab) / det).shift(1)
        b1 = ((Syb * Saa - Sya * Sab) / det).shift(1)
        p = (Z.y - b0 * Z.a - b1 * Z.b).dropna()
        per = p.index.to_period("M")
        s = pd.Series(np.arange(len(p)), index=p.index)
        day = s - s.groupby(per).transform("min") + 1
        first = p[day <= 5].groupby(per[day <= 5]).sum()
        rest = p[day > 5].groupby(per[day > 5]).mean() * 5
        D = (first - rest).dropna()
        fund_D[t] = D
        for w, (a, b) in {"1990-99": ("1990", "1999"), "2000-07": ("2000", "2007"),
                          "2008-16": ("2008", "2016"), "2017-26": ("2017", "2026")}.items():
            d = D.loc[a:b]
            rows.append(dict(fund=t, window=w, D_bp=d.mean() * 1e4, t=d.mean() / d.std() * np.sqrt(len(d)),
                             first5_bp=first.loc[a:b].mean() * 1e4, rest5_bp=rest.loc[a:b].mean() * 1e4,
                             hit=(d > 0).mean(), n=len(d)))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(_HERE, "03_nav_holdout.csv"), index=False)
    print("\nper fund: D = first-5-days hedged price return minus 5 x average other day (bp/month)")
    print(t.round(2).to_string(index=False))
    avg = pd.DataFrame(fund_D).mean(axis=1)
    print("\nsix-fund average D_m")
    for w, (a, b) in {"1990-99": ("1990", "1999"), "2000-07": ("2000", "2007"), "1990-2007": ("1990", "2007"),
                      "2008-16": ("2008", "2016"), "2017-26": ("2017", "2026")}.items():
        d = avg.loc[a:b]
        print(f"  {w:9s} mean {d.mean()*1e4:6.2f} bp/month  t {d.mean()/d.std()*np.sqrt(len(d)):5.2f}  hit {(d>0).mean():.2f}  n {len(d)}")


if __name__ == "__main__":
    main()
