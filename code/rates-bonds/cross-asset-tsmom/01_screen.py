"""cross-asset-tsmom -- Pitkaejaervi, Suominen & Vaittinen (JFE 2020) on US duration.

Their finding (20 countries, 1980-2016): past bond returns predict bond returns positively
(time-series momentum), past EQUITY returns predict bond returns NEGATIVELY; the combined
"cross-asset TSMOM" signal beats plain TSMOM by ~45 % in Sharpe. Mechanism: slow-moving
capital -- after an equity rally investors rotate out of bonds (and growth/rate expectations
rise); after an equity crash they rotate in.

Setup
  bond   = synthetic 10y constant-maturity par bond, excess of the 3m bill (1982+, FRED CMT);
           OOS also IEF / TLT excess (2002+ spliced).
  equity = S&P 500 price index (^GSPC, 1960+ spliced) minus the 3m bill.
  Signals at each month-end (last trading day), for lookback L in {1, 3, 6, 12} months:
     b_L = sign(bond excess return over L months)          (own TSMOM)
     e_L = -sign(equity excess return over L months)       (cross-asset, negative)
     x_L = (b_L + e_L) / 2                                 (PSV combined)
  Position: signal x vol-scale, vol-scale = 10 % / (EWMA-60d realised vol of the bond, annualised),
  capped at 3x, set at month-end and held for the month. Cost 2 bp/side.
Split fixed in advance: IS 1985-01 -> 2009-12 (synthetic only), OOS 2010-01 -> 2026-09.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, cmt_returns, fred, ANN  # noqa: E402

pd.set_option("display.width", 220)
COST = 2e-4


def spx():
    parts = []
    for f in ("IDX_GSPC_d_long", "IDX_GSPC_d_pre2010", "IDX_GSPC_d"):
        d = pd.read_parquet(os.path.join(os.path.dirname(os.path.dirname(_HERE)), "..", "data", f + ".parquet"))["Close"]
        d.index = pd.to_datetime(d.index).tz_localize(None)
        parts.append(d)
    s = parts[0]
    for p in parts[1:]:
        ov = s.index.intersection(p.index)
        k = p.loc[ov[-1]] / s.loc[ov[-1]]
        s = pd.concat([s[s.index < ov[-1]] * k, p[p.index >= ov[-1]]])
    return s[~s.index.duplicated(keep="last")].sort_index()


def data():
    bill = (fred("DGS3MO") / 100 / ANN)
    syn = cmt_returns(maturities=(2, 5, 10), excess=True)
    px = etf_close(["IEF", "TLT"])
    etf = px.pct_change().sub(bill.reindex(px.index).ffill().shift(1), axis=0)
    eq = spx().pct_change()
    eq_x = eq - bill.reindex(eq.index).ffill().shift(1)
    return syn, etf, eq_x.dropna()


def month_end_mask(idx):
    s = pd.Series(idx, index=idx)
    return s.groupby(idx.to_period("M")).transform("max").eq(s).values


def book(sig_m, bond_ret, cost=COST, target=0.10, cap=3.0):
    """sig_m: signal at month-ends (index = month-end dates, any calendar); applied from next day."""
    r = bond_ret.dropna()
    vol = r.ewm(span=60, min_periods=40).std() * np.sqrt(ANN)
    lev = (target / vol).clip(upper=cap)
    me = month_end_mask(r.index)
    s = sig_m.reindex(r.index[me], method="ffill")         # signal known at this month-end close
    w = pd.Series(np.nan, index=r.index)
    w[me] = (s * lev[me]).values
    w = w.ffill().fillna(0)
    we = w.shift(1).fillna(0)
    return we * r - we.diff().abs().fillna(0) * cost, we


def cum(r, idx_me, L):
    """L-month cumulative (log-sum) return at month-ends."""
    lr = np.log1p(r.fillna(0))
    c = lr.cumsum()
    m = c.groupby(c.index.to_period("M")).last()
    return (m - m.shift(L))


def sh(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(ANN) if len(x) > 250 and x.std() > 0 else np.nan


def main():
    syn, etf, eq = data()
    rows = []
    for L in (1, 3, 6, 12):
        bsig_syn = np.sign(cum(syn[10], None, L))
        esig = -np.sign(cum(eq, None, L))
        for name, bond, bsig in (("syn10", syn[10], bsig_syn),
                                 ("IEF", etf["IEF"], np.sign(cum(etf["IEF"], None, L))),
                                 ("TLT", etf["TLT"], np.sign(cum(etf["TLT"], None, L)))):
            # month-end period index -> map to last trading date of that month in bond calendar
            me_dates = bond.dropna().groupby(bond.dropna().index.to_period("M")).apply(lambda s: s.index.max())
            for sname, sig in (("own", bsig), ("eq", esig), ("combo", (bsig + esig) / 2)):
                sg = sig.reindex(me_dates.index)
                sg.index = me_dates.values
                net, we = book(sg.dropna(), bond)
                rows.append(dict(inst=name, L=L, sig=sname, IS=sh(net.loc["1985":"2009"]),
                                 OOS=sh(net.loc["2010":]), OOS18=sh(net.loc["2018":]),
                                 FULL=sh(net.loc["1985":]), lev=we.abs().mean()))
        # buy-and-hold vol-scaled benchmark
    for name, bond in (("syn10", syn[10]), ("IEF", etf["IEF"])):
        me_dates = bond.dropna().groupby(bond.dropna().index.to_period("M")).apply(lambda s: s.index.max())
        net, we = book(pd.Series(1.0, index=me_dates.values), bond)
        rows.append(dict(inst=name, L=0, sig="long", IS=sh(net.loc["1985":"2009"]), OOS=sh(net.loc["2010":]),
                         OOS18=sh(net.loc["2018":]), FULL=sh(net.loc["1985":]), lev=we.abs().mean()))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(_HERE, "01_screen.csv"), index=False)
    print(t.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
