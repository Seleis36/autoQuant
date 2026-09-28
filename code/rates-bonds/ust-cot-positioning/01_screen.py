"""ust-cot-positioning -- screen: does CFTC positioning in Treasury futures predict duration returns?

Splits fixed before any number was computed:
  legacy (non-commercial / commercial, 1986+):  IS 1990-2009 on synthetic 10y CMT excess returns,
                                               OOS 2010-2026 on IEF (and synthetic 10y for comparison)
  tff (dealer / asset manager / lev funds, 2006-06+): IS 2006-06 -> 2017, OOS 2018 -> 2026 on IEF

Signals, per trader group, built on the weekly report grid:
  lvl_z  = z(net share of OI, trailing 156 reports)
  chg_z  = z(4-report change in net share, trailing 156 reports)
for the aggregate across 2y/5y/10y/bond (mean net share) and per tenor.
Reported: Spearman IC vs forward 1/4/13-week excess returns, and a weekly-rebalanced
linear book w = clip(sign * z / 2, -1, 1) at 2 bp/side. `sign` is +1 (follow) in the
tables; the contrarian book is the negative of it.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, cmt_returns, ANN  # noqa: E402
from fetch_cot_ust import fetch_legacy, fetch_tff, net_share, report_avail, on_daily_rows  # noqa: E402

pd.set_option("display.width", 200)
TEN = ["2y", "5y", "10y", "bond"]
WIN, MINP, DH = 156, 52, 4


def z(x, win=WIN, minp=MINP):
    return (x - x.rolling(win, min_periods=minp).mean()) / x.rolling(win, min_periods=minp).std()


def build_signals():
    lg, tf = fetch_legacy(), fetch_tff()
    sig = {}
    for rep, df, groups in (("legacy", lg, ("nc", "c", "nr")), ("tff", tf, ("lev", "am", "dealer", "oth"))):
        av = report_avail(df)
        for g in groups:
            ns = net_share(df, g, TEN)
            ns = ns[ns.index >= "1988-01-01"] if rep == "legacy" else ns
            agg = ns.mean(axis=1, skipna=True)
            for name, s in (("agg", agg), *[(t, ns[t]) for t in TEN]):
                sig[(rep, g, name, "lvl")] = (z(s), av)
                sig[(rep, g, name, "chg")] = (z(s.diff(DH)), av)
    return sig


def main():
    px = etf_close(["IEF", "TLT", "SHY"])
    syn = cmt_returns(maturities=(2, 5, 10), excess=True)
    cash = syn  # noqa
    ief = px["IEF"].pct_change()
    # excess return of IEF over the 3m bill (bill from DGS3MO)
    from rb_data import fred
    bill = (fred("DGS3MO") / 100 / ANN).reindex(ief.index).ffill().shift(1)
    ief_x = (ief - bill).dropna()
    r10 = syn[10]
    sig = build_signals()

    rows = []
    for key, (s, av) in sig.items():
        rep, g, ten, kind = key
        for inst, ret in (("syn10", r10), ("IEF", ief_x)):
            ret = ret.dropna()
            d = on_daily_rows(s.to_frame("s"), ret.index, av)["s"]
            # forward cumulative returns over h trading days starting the NEXT bar
            for h in (5, 20, 65):
                fwd = ret[::-1].rolling(h).sum()[::-1].shift(-1)
                # weekly sampling (Mondays / first bar of week) to limit overlap
                wk = d.groupby(d.index.to_period("W")).head(1).index
                x = pd.concat([d.reindex(wk), fwd.reindex(wk)], axis=1).dropna()
                if rep == "legacy":
                    splits = {"IS": ("1990", "2009"), "OOS": ("2010", "2026")}
                else:
                    splits = {"IS": ("2006", "2017"), "OOS": ("2018", "2026")}
                for sp, (a, b) in splits.items():
                    xx = x.loc[a:b]
                    if len(xx) < 60:
                        continue
                    ic = xx.iloc[:, 0].corr(xx.iloc[:, 1], method="spearman")
                    rows.append(dict(rep=rep, grp=g, tenor=ten, kind=kind, inst=inst, h=h, split=sp,
                                     ic=ic, n=len(xx)))
    ic = pd.DataFrame(rows)
    ic.to_csv(os.path.join(_HERE, "01_screen_ic.csv"), index=False)

    # Book: weekly rebalanced linear follow-signal on the aggregate, 2bp/side
    brow = []
    for key, (s, av) in sig.items():
        rep, g, ten, kind = key
        if ten != "agg":
            continue
        for inst, ret in (("syn10", r10), ("IEF", ief_x)):
            ret = ret.dropna()
            d = on_daily_rows(s.to_frame("s"), ret.index, av)["s"]
            w = (d / 2).clip(-1, 1)
            # hold within the week: only change on first bar of each week
            first = ~d.index.to_period("W").duplicated()
            w = w.where(first).ffill().fillna(0)
            we = w.shift(1).fillna(0)
            net = we * ret - (we.diff().abs().fillna(0)) * 2e-4
            splits = ({"IS": ("1990", "2009"), "OOS": ("2010", "2026")} if rep == "legacy"
                      else {"IS": ("2006", "2017"), "OOS": ("2018", "2026")})
            for sp, (a, b) in splits.items():
                n = net.loc[a:b]
                if len(n) < 250:
                    continue
                brow.append(dict(rep=rep, grp=g, kind=kind, inst=inst, split=sp,
                                 sharpe_follow=n.mean() / n.std() * np.sqrt(ANN)))
    bk = pd.DataFrame(brow)
    bk.to_csv(os.path.join(_HERE, "01_screen_books.csv"), index=False)

    print("=== IC (Spearman, weekly samples) — aggregate across tenors ===")
    t = ic[ic.tenor == "agg"].pivot_table(index=["rep", "grp", "kind", "inst"], columns=["split", "h"], values="ic")
    print(t.round(3).to_string())
    print("\n=== IC per tenor, h=20, instrument syn10 (legacy) / IEF (tff) ===")
    t2 = ic[(ic.tenor != "agg") & (ic.h == 20) & (((ic.rep == "legacy") & (ic.inst == "syn10")) | ((ic.rep == "tff") & (ic.inst == "IEF")))]
    print(t2.pivot_table(index=["rep", "grp", "kind", "tenor"], columns="split", values="ic").round(3).to_string())
    print("\n=== Linear FOLLOW book Sharpe (contrarian = minus), aggregate, 2bp/side ===")
    print(bk.pivot_table(index=["rep", "grp", "kind", "inst"], columns="split", values="sharpe_follow").round(2).to_string())


if __name__ == "__main__":
    main()
