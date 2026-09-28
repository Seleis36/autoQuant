"""auction-demand-signal -- do Treasury auction demand metrics predict the next days' returns?

Two competing mechanisms, both from dealer-inventory theory:
  * inventory overhang: a weak auction leaves primary dealers holding more paper than they
    wanted; they distribute it over the following days -> continued underperformance;
  * liquidity provision: the weak auction clears at a concession; the concession is paid back
    as inventory is placed -> recovery (Lou-Yan-Zhang's post-auction rebound, conditional).
The sign is therefore chosen on IS only.

Metrics per auction (results public ~13:00 ET, i.e. before the 16:00 close of the auction day),
each z-scored against the trailing 12 auctions of the same tenor (min 6):
  dealer   = primary_dealer_accepted / competitive_accepted     (high = weak)
  indirect = indirect_accepted / competitive_accepted           (high = strong)
  btc      = bid_to_cover                                       (high = strong)
  disp     = high_yield - median_yield  (bp)                    (high = weak, wide bid spread)
  weak     = mean(z_dealer, -z_indirect, -z_btc, z_disp)
Targets: excess return of the auctioned maturity (synthetic CMT par bond; ETF check in 02)
over [t+1, t+h] for h in 1, 2, 3, 5, 10 (t = auction day close), and the auction-day return
itself (t-1 close -> t close, not tradable, for context).
Nominal coupons only (2y 3y 5y 7y 10y 20y 30y), 2008-04 onward (investor classes).
Split fixed in advance: IS 2008-04 -> 2016, OOS 2017 -> 2026.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import cmt_returns  # noqa: E402
from fetch_auctions import fetch  # noqa: E402

pd.set_option("display.width", 220)
MAP = {"2y": 2, "3y": 2, "5y": 5, "7y": 5, "10y": 10, "20y": 30, "30y": 30}


def auction_signals():
    a = fetch()
    a = a[a.tenor.isin(MAP) & ~a.tips & (a.auction_date >= "2006-01-01")].copy()
    a["dealer"] = a.primary_dealer_accepted / a.competitive_accepted
    a["indirect"] = a.indirect_accepted / a.competitive_accepted
    a["btc"] = a.bid_to_cover
    a["disp"] = (a.high_yield - a.median_yield) * 100
    for m in ("dealer", "indirect", "btc", "disp"):
        g = a.groupby("tenor")[m]
        mu = g.transform(lambda s: s.shift(1).rolling(12, min_periods=6).mean())
        sd = g.transform(lambda s: s.shift(1).rolling(12, min_periods=6).std())
        a[f"z_{m}"] = (a[m] - mu) / sd
    a["weak"] = pd.concat([a.z_dealer, -a.z_indirect, -a.z_btc, a.z_disp], axis=1).mean(axis=1, skipna=False)
    return a[a.auction_date >= "2008-04-01"]


def main():
    a = auction_signals()
    R = cmt_returns(maturities=(2, 5, 10, 30), excess=True)
    idx = R.index
    rows = []
    for _, ev in a.iterrows():
        p = idx.searchsorted(ev.auction_date)
        if p >= len(idx) - 11 or idx[p] != ev.auction_date:
            continue
        r = R[MAP[ev.tenor]].values
        out = dict(date=ev.auction_date, tenor=ev.tenor, day0=r[p])
        for h in (1, 2, 3, 5, 10):
            out[f"f{h}"] = np.nansum(r[p + 1:p + 1 + h])
        for m in ("z_dealer", "z_indirect", "z_btc", "z_disp", "weak"):
            out[m] = ev[m]
        rows.append(out)
    e = pd.DataFrame(rows).dropna(subset=["weak"])
    e.to_csv(os.path.join(_HERE, "01_events.csv"), index=False)
    print(f"events with all metrics: {len(e)}  (IS {len(e[e.date < '2017'])}, OOS {len(e[e.date >= '2017'])})")
    res = []
    for sp, sub in (("IS", e[e.date < "2017"]), ("OOS", e[e.date >= "2017"])):
        for m in ("z_dealer", "z_indirect", "z_btc", "z_disp", "weak"):
            for tgt in ("day0", "f1", "f2", "f3", "f5", "f10"):
                c = sub[m].corr(sub[tgt], method="spearman")
                res.append(dict(split=sp, metric=m, target=tgt, ic=c, t=c * np.sqrt(len(sub))))
    r = pd.DataFrame(res)
    print("\nSpearman IC of metric vs return of the auctioned maturity (positive = metric high -> bond up)")
    print(r.pivot_table(index=["metric", "target"], columns="split", values="ic").round(3).to_string())
    # by tenor for the composite, f5
    print("\ncomposite 'weak' IC vs f1 / f5 by tenor")
    rr = []
    for sp, sub in (("IS", e[e.date < "2017"]), ("OOS", e[e.date >= "2017"])):
        for ten, g in sub.groupby("tenor"):
            rr.append(dict(split=sp, tenor=ten, n=len(g), f1=g.weak.corr(g.f1, method="spearman"),
                           f5=g.weak.corr(g.f5, method="spearman"), day0=g.weak.corr(g.day0, method="spearman")))
    print(pd.DataFrame(rr).pivot_table(index="tenor", columns="split", values=["n", "day0", "f1", "f5"]).round(2).to_string())
    # quintile profile of weak vs f5 (bp)
    e["q"] = e.groupby(e.date.dt.year >= 2017)["weak"].transform(lambda s: pd.qcut(s, 5, labels=False))
    e["split"] = np.where(e.date >= "2017", "OOS", "IS")
    print("\nmean return (bp) by 'weak' quintile (0 = strongest demand)")
    print((e.groupby(["split", "q"])[["day0", "f1", "f2", "f5", "f10"]].mean() * 1e4).round(1).to_string())


if __name__ == "__main__":
    main()
