"""ust-cot-positioning -- round 2, selection on IS only.

Legacy report (1988+): IS 1990-2009 on the synthetic 10y CMT excess return, OOS 2010-2026 on
IEF excess (and synthetic 10y). TFF: IS 2006-06 -> 2017, OOS 2018 -> 2026 on IEF.

Refinements, each a single a-priori variation of the round-1 signals:
  * DV01-weighted aggregation: net contracts x (duration x contract size) summed over
    2y/5y/10y/bond, divided by the same-weighted open interest -- a net *risk* share
    instead of an equal-weighted mean of four OI shares.
  * change horizon dh in {1, 2, 4, 8, 13} reports; z window in {52, 156, 260}.
  * extremes only: trade sign(z) when |z| > 1, flat otherwise.
  * holding: weekly re-set (as round 1).
The contrarian/follow direction is taken from the IS sign and then frozen.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, cmt_returns, fred, ANN  # noqa: E402
from fetch_cot_ust import fetch_legacy, fetch_tff, report_avail, on_daily_rows  # noqa: E402

pd.set_option("display.width", 220)
TEN = ["2y", "5y", "10y", "bond"]
# approximate contract DV01 weights: modified duration x notional ($k); 2y is $200k notional
DV01 = {"2y": 1.9 * 200, "5y": 4.2 * 100, "10y": 6.5 * 100, "bond": 15.0 * 100}


def z(x, win, minp=52):
    return (x - x.rolling(win, min_periods=minp).mean()) / x.rolling(win, min_periods=minp).std()


def dv01_share(df, grp):
    d = df[df.tenor.isin(TEN)].copy()
    wt = d.tenor.map(DV01)
    d["net"] = (d[f"{grp}_long"] - d[f"{grp}_short"]) * wt
    d["oiw"] = d["oi"] * wt
    g = d.groupby("date")[["net", "oiw"]].sum()
    return g["net"] / g["oiw"]


def book(sig_daily, ret, mode, cost=2e-4):
    if mode == "lin":
        w = (sig_daily / 2).clip(-1, 1)
    else:
        w = np.sign(sig_daily).where(sig_daily.abs() > 1, 0.0)
    first = ~sig_daily.index.to_period("W").duplicated()
    w = w.where(first).ffill().fillna(0)
    we = w.shift(1).fillna(0)
    return we * ret - we.diff().abs().fillna(0) * cost, we


def sh(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(ANN) if len(x) > 250 and x.std() > 0 else np.nan


def main():
    px = etf_close(["IEF"])
    bill = (fred("DGS3MO") / 100 / ANN)
    ief_x = (px["IEF"].pct_change() - bill.reindex(px.index).ffill().shift(1)).dropna()
    r10 = cmt_returns(maturities=(2, 5, 10), excess=True)[10].dropna()
    lg, tf = fetch_legacy(), fetch_tff()
    rows = []
    for rep, df, groups, isp, oosp in (
            ("legacy", lg[lg.date >= "1988-01-01"], ("nc", "c"), ("1990", "2009"), ("2010", "2026")),
            ("tff", tf, ("lev", "am", "dealer", "oth"), ("2006", "2017"), ("2018", "2026"))):
        av = report_avail(df)
        for g in groups:
            share = dv01_share(df, g)
            for kind in ("lvl", "chg"):
                for dh in ((None,) if kind == "lvl" else (1, 2, 4, 8, 13)):
                    for win in (52, 156, 260):
                        raw = share if kind == "lvl" else share.diff(dh)
                        s = z(raw, win, minp=min(52, win))
                        is_ret = r10 if rep == "legacy" else ief_x
                        d_is = on_daily_rows(s.to_frame("s"), is_ret.index, av)["s"]
                        for mode in ("lin", "ext"):
                            n_is, _ = book(d_is, is_ret, mode)
                            s_is = sh(n_is.loc[isp[0]:isp[1]])
                            sign = 1.0 if s_is > 0 else -1.0
                            out = dict(rep=rep, grp=g, kind=kind, dh=dh, win=win, mode=mode,
                                       dir="follow" if sign > 0 else "fade", IS=abs(s_is))
                            for nm, rr in (("OOS_syn10", r10), ("OOS_IEF", ief_x)):
                                d_o = on_daily_rows((sign * s).to_frame("s"), rr.index, av)["s"]
                                n_o, we = book(d_o, rr, mode)
                                out[nm] = sh(n_o.loc[oosp[0]:oosp[1]])
                            rows.append(out)
    t = pd.DataFrame(rows).sort_values(["rep", "IS"], ascending=[True, False])
    t.to_csv(os.path.join(_HERE, "02_refine.csv"), index=False)
    print(f"{len(t)} configurations")
    for rep in ("legacy", "tff"):
        tt = t[t.rep == rep]
        print(f"\n=== {rep}: top 15 by IS Sharpe (direction chosen on IS) ===")
        print(tt.head(15).round(2).to_string(index=False))
        print(f"IS-rank vs OOS_IEF Spearman: {tt.IS.corr(tt.OOS_IEF, method='spearman'):.2f}; "
              f"median OOS_IEF of top-10 IS: {tt.head(10).OOS_IEF.median():.2f}; of all: {tt.OOS_IEF.median():.2f}")


if __name__ == "__main__":
    main()
