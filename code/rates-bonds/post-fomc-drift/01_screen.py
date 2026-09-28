"""post-fomc-drift -- do Treasury yields keep drifting after Fed policy moves?

Brooks, Katz & Lustig (NBER w25127, 2018): after a fed funds target *increase*, bond-fund
investors sell gradually for weeks, arbitrageurs absorb the supply slowly, and longer Treasury
yields drift up after the announcement ("post-FOMC announcement drift").

Events
  A. target changes: FRED DFEDTAR (to 2008-12-15) spliced with DFEDTARU (upper bound, 2008-12-16+);
     event date = first date the new target is in the series (the decision day or the next day).
     Pre-1994 the Fed did not announce decisions, so 1985-1993 is shown but is NOT the IS window.
  B. market surprise on scheduled FOMC statement days (1994+): the 2y CMT yield change on the
     statement day (DGS2 is published the next day -> entry is lagged one extra day).
Position: hike / yield-up -> SHORT duration, cut / yield-down -> LONG, for H trading days,
entered at the close of the event day (A) or the day after (B). Overlapping events are summed
and clipped to [-1, 1]. Variants: all events | hikes only | cuts only; B also with a
|dy2| >= 5 bp threshold. Instruments: synthetic 2y/5y/10y excess (1982+), and SHY/IEF/TLT
excess (2002+). Cost 2 bp/side.
Split fixed in advance: IS 1994-2009, OOS 2010-2026 (pre-1994 = "early", reported only).
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, cmt_returns, fred, ANN  # noqa: E402

pd.set_option("display.width", 220)
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
FOMC_CSV = os.path.join(ROOT, "code", "rates-bonds", "treasury-flow-calendar", "calendar_snapshots", "fomc.csv")
COST = 2e-4


def target_events():
    t = pd.concat([fred("DFEDTAR"), fred("DFEDTARU")]).sort_index()
    t = t[~t.index.duplicated(keep="last")]
    ch = t.diff()
    ev = ch[(ch != 0) & ch.notna()]
    return ev          # index = first date with new target, value = change (pp)


def fomc_surprise_events():
    d = pd.to_datetime(pd.read_csv(FOMC_CSV)["date"])
    d = d[d >= "1994-01-01"]
    y2 = fred("DGS2").dropna()
    dy = y2.diff()
    idx = y2.index
    pos = idx.searchsorted(d.values)          # statement day or next trading day
    ok = pos < len(idx)
    days = idx[pos[ok]]
    return dy.reindex(days)                    # pp change on the statement day


def rets():
    bill = fred("DGS3MO") / 100 / ANN
    syn = cmt_returns(maturities=(2, 5, 10), excess=True)
    px = etf_close(["SHY", "IEF", "TLT"])
    etf = px.pct_change().sub(bill.reindex(px.index).ffill().shift(1), axis=0)
    out = {f"syn{k}": syn[k] for k in (2, 5, 10)}
    out.update({k: etf[k] for k in etf})
    return out


def event_book(ev_sign, ret, H, lag=0):
    """ev_sign: Series date -> +1/-1 (desired duration position). Position starts at the close
    of the event day + `lag` trading days and is held H trading days."""
    r = ret.dropna()
    idx = r.index
    w = pd.Series(0.0, index=idx)
    for d, s in ev_sign.items():
        p = idx.searchsorted(d)
        if p >= len(idx):
            continue
        a = p + lag
        w.iloc[a:a + H] += s
    w = w.clip(-1, 1)
    we = w.shift(1).fillna(0)
    return we * r - we.diff().abs().fillna(0) * COST, we


def sh(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(ANN) if len(x) > 250 and x.std() > 0 else np.nan


def main():
    R = rets()
    tev = target_events()
    sev = fomc_surprise_events()
    print(f"target events: {len(tev)} (1994-2009: {len(tev['1994':'2009'])}, 2010+: {len(tev['2010':])})")
    print(f"scheduled FOMC days 1994+: {len(sev)}")
    rows = []
    variants = {
        "tgt_all": -np.sign(tev), "tgt_hikes": -np.sign(tev[tev > 0]), "tgt_cuts": -np.sign(tev[tev < 0]),
        "sur_all": -np.sign(sev[sev != 0]), "sur_5bp": -np.sign(sev[sev.abs() >= 0.05]),
        "sur_up5": -np.sign(sev[sev >= 0.05]), "sur_dn5": -np.sign(sev[sev <= -0.05]),
    }
    for vname, evs in variants.items():
        lag = 1 if vname.startswith("sur") else 0
        for H in (5, 10, 20, 40, 60):
            for inst, r in R.items():
                net, we = event_book(evs.dropna(), r, H, lag)
                rows.append(dict(var=vname, H=H, inst=inst, early=sh(net.loc["1985":"1993"]),
                                 IS=sh(net.loc["1994":"2009"]), OOS=sh(net.loc["2010":]),
                                 OOS_ann_ret=net.loc["2010":].mean() * ANN * 100,
                                 expo_IS=we.loc["1994":"2009"].abs().mean(), expo_OOS=we.loc["2010":].abs().mean()))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(_HERE, "01_screen.csv"), index=False)
    for inst in ("syn10", "IEF", "TLT", "syn2", "SHY"):
        print(f"\n=== {inst} ===")
        print(t[t.inst == inst].drop(columns="inst").round(2).to_string(index=False))


if __name__ == "__main__":
    main()
