"""tips-seasonal-carry, round 2 -- inflation carry and inflation momentum as breakeven timers.

Round 1 showed the *seasonal* part of the known accrual is ~80-90 % priced. Re-framing: does the
breakeven under-react to the *level* of realised/known inflation (inflation carry, cf. KMPV
"Carry" 2018 for inflation swaps) or to its trend (inflation momentum)?

Traded object: hedged TIPS excess x = r_TIPS - b * r_nominal, b = trailing 252d beta at M-1
(as in round 1). Monthly re-set at the last close of M-1, held through M.

Signals, all known at the last close of month M-1 (CPI(M-2) published mid M-1; T5YIE/T10YIE
daily market data):
  s_carry1 = 12 * a(M) - BEI                 next month's known accrual, annualised, minus breakeven
  s_carry3 = 4 * sum a(M-2..M) - BEI         3 known months
  s_yoy    = CPI(M-2)/CPI(M-14) - 1 - BEI    known YoY inflation minus breakeven
  s_mom6   = YoY(M-2) - YoY(M-8)             6-month change in YoY inflation (momentum)
  s_bei_mom= BEI(M-1) - BEI(M-4)             3-month breakeven trend (price momentum control)
Books: sign(s) and clip(z,-1,1) of s with z over the trailing 60 months (z needs 36 months).
Split fixed in advance: IS 2004-2015, OOS 2016-2026 (TIP-IEF / TIP-IEI); STIP/VTIP/SCHP pairs
start 2011-13 and are reported as a second instrument, not as a selection set.
Cost: 3 bp per side on each leg (hedged pair ~ (1 + b) x notional turnover).
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, fred  # noqa: E402

pd.set_option("display.width", 220)
COST = 3e-4


def monthly_frame():
    cpi = fred("CPIAUCNS"); cpi.index = cpi.index.to_period("M")
    idx = pd.period_range("2003-01", pd.Timestamp.today().to_period("M"), freq="M")
    c = cpi.reindex(idx.union(cpi.index))
    a = (c.shift(2) / c.shift(3) - 1).reindex(idx)                    # accrual in month M
    yoy_known = (c.shift(2) / c.shift(14) - 1).reindex(idx)           # known at start of M
    bei = {}
    for sid in ("T5YIE", "T10YIE"):
        b = fred(sid) / 100
        bei[sid] = b.groupby(b.index.to_period("M")).last().shift(1).reindex(idx)   # at end of M-1
    f = pd.DataFrame({"a": a, "yoy": yoy_known, "bei5": bei["T5YIE"], "bei10": bei["T10YIE"]})
    return f


def signals(f, bei="bei5"):
    s = pd.DataFrame(index=f.index)
    s["carry1"] = 12 * f.a - f[bei]
    s["carry3"] = 4 * f.a.rolling(3).sum() - f[bei]
    s["yoy_gap"] = f.yoy - f[bei]
    s["mom6"] = f.yoy - f.yoy.shift(6)
    s["bei_mom3"] = f[bei] - f[bei].shift(3)
    return s


def hedged(tp, nm, r):
    d = r[[tp, nm]].dropna()
    cov = d[tp].rolling(252).cov(d[nm]); var = d[nm].rolling(252).var()
    beta = (cov / var).groupby(d.index.to_period("M")).last().shift(1)
    mret = (1 + d).groupby(d.index.to_period("M")).prod() - 1
    x = (mret[tp] - beta.reindex(mret.index) * mret[nm])
    return x.dropna(), beta.reindex(x.index)


def run_book(sig, x, beta, mode):
    if mode == "sign":
        w = np.sign(sig)
    else:
        zz = (sig - sig.rolling(60, min_periods=36).mean()) / sig.rolling(60, min_periods=36).std()
        w = zz.clip(-1, 1)
    w = w.reindex(x.index)
    turn = w.diff().abs().fillna(w.abs()) * (1 + beta.abs())
    net = (w * x - turn * COST).dropna()
    return net


def sh(n):
    return n.mean() / n.std() * np.sqrt(12) if len(n) > 24 and n.std() > 0 else np.nan


def main():
    f = monthly_frame()
    pairs = [("TIP", "IEF"), ("TIP", "IEI"), ("SCHP", "IEI"), ("STIP", "SHY"), ("VTIP", "VGSH")]
    px = etf_close(sorted({t for p in pairs for t in p}))
    r = px.pct_change()
    rows = []
    for bei in ("bei5", "bei10"):
        s = signals(f, bei)
        for tp, nm in pairs:
            x, beta = hedged(tp, nm, r)
            for col in s.columns:
                for mode in ("sign", "z"):
                    n = run_book(s[col], x, beta, mode)
                    rows.append(dict(bei=bei, pair=f"{tp}-{nm}", sig=col, mode=mode,
                                     IS=sh(n.loc[:"2015"]), OOS=sh(n.loc["2016":]), FULL=sh(n),
                                     ex_2021_22=sh(n[(n.index.year < 2021) | (n.index.year > 2022)]),
                                     start=str(n.index[0]) if len(n) else ""))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(_HERE, "02_inflation_carry.csv"), index=False)
    print(t[t.bei == "bei5"].round(2).to_string(index=False))
    print("\n(bei10 variants in 02_inflation_carry.csv)")
    print(t[t.bei == "bei10"].groupby("sig")[["IS", "OOS", "FULL"]].median().round(2))


if __name__ == "__main__":
    main()
