"""fomc-front-end-reversal -- books: FOMC-day fade vs generic front-end fade, split by policy regime.

Books (2 bp/side, positions on the 2y / SHY, +1 = long duration):
  fomc_fade : after statement day t, position = +sign(dy2_t) (yield up -> buy) for H days,
              entered at the close of t (lag 0 -- research only on CMT; live would use SHY's own
              day-t return) or t+1 (lag 1).
  all_fade  : every day, position = +sign(dy2_t) held 1 day (generic short-term reversal), and
              only on days with |dy2| >= 5 bp.
Regime split of 2010-2026: ZLB (fed funds upper target <= 0.25 %) vs not.
Instruments: syn2 (CMT par-bond excess return), SHY excess.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from importlib import import_module  # noqa: E402
from rb_data import etf_close, cmt_returns, fred, ANN  # noqa: E402
ev = import_module("01_event_study")

pd.set_option("display.width", 220)
COST = 2e-4


def sh(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(ANN) if len(x) > 100 and x.std() > 0 else np.nan


def main():
    y2 = fred("DGS2").dropna() * 100
    dy = y2.diff()
    idx = y2.index
    fomc = ev.ev_days("fomc", idx)
    bill = fred("DGS3MO") / 100 / ANN
    syn2 = cmt_returns(maturities=(2,), excess=True)[2]
    px = etf_close(["SHY"])
    shy = (px["SHY"].pct_change() - bill.reindex(px.index).ffill().shift(1)).dropna()
    tgt = pd.concat([fred("DFEDTAR"), fred("DFEDTARU")]).sort_index()
    tgt = tgt[~tgt.index.duplicated(keep="last")]
    zlb = (tgt <= 0.25)
    rows = []
    for inst, r in (("syn2", syn2), ("SHY", shy)):
        r = r.dropna()
        d = dy.reindex(r.index)
        z = zlb.reindex(r.index, method="ffill").fillna(False).astype(bool)
        books = {}
        for lag in (0, 1):
            for H in (1, 2, 3, 5, 10):
                w = pd.Series(0.0, index=r.index)
                pos = r.index.get_indexer(fomc)
                for p in pos[pos >= 0]:
                    s = np.sign(d.iloc[p])
                    w.iloc[p + lag:p + lag + H] += s
                books[f"fomc_fade_lag{lag}_H{H}"] = w.clip(-1, 1)
        books["all_fade_1d"] = np.sign(d).fillna(0)
        books["all_fade_1d_5bp"] = np.sign(d).where(d.abs() >= 5, 0).fillna(0)
        books["nonfomc_fade_1d"] = np.sign(d).where(~r.index.isin(fomc), 0).fillna(0)
        for name, w in books.items():
            we = w.shift(1).fillna(0)
            net = we * r - we.diff().abs().fillna(0) * COST
            gross = we * r
            rows.append(dict(inst=inst, book=name,
                             IS=sh(net.loc["1994":"2009"]), OOS=sh(net.loc["2010":]),
                             OOS_zlb=sh(net.loc["2010":][z.loc["2010":]]),
                             OOS_nonzlb=sh(net.loc["2010":][~z.loc["2010":]]),
                             y2022_26=sh(net.loc["2022":]),
                             OOS_gross=sh(gross.loc["2010":]),
                             expo=we.loc["2010":].abs().mean(),
                             OOS_ret_pct=net.loc["2010":].mean() * ANN * 100))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(_HERE, "02_books.csv"), index=False)
    print(t.round(2).to_string(index=False))
    print(f"\nZLB share of 2010-2026 days: {zlb.reindex(syn2.loc['2010':].index, method='ffill').mean():.2f}")


if __name__ == "__main__":
    main()
