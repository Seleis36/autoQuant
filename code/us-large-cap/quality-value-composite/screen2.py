"""Screen 2: literature composites (fixed a priori, equal-weight of sector-neutral z's),
quintile vs linear, raw vs beta-hedged, plus 3-month overlapping rebalance to cut turnover."""
import os, sys, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import *

S, P, aux = pickle.load(open("/tmp/qvc_signals.pkl", "rb"))
Z = pickle.load(open("/tmp/qvc_Z.pkl", "rb"))
close = P["close"]; ret = close.pct_change(fill_method=None)
sec = sector_map(P)
base = P["member"] & aux["mcap"].notna()
rebal = month_ends(close.index); rebal = rebal[rebal >= "2010-12-31"]

COMPOS = {
    "QUAL_prof": ["gpa", "roa", "roe", "cfoa", "accruals"],                    # QMJ profitability
    "QUAL_qmj": ["gpa", "roa", "roe", "cfoa", "accruals", "lev", "lowvol", "issuance", "shy"],
    "VALUE": ["ep", "cfp", "bm", "sp", "fcfp"],
    "PAYOUT": ["shy", "issuance"],
    "INVEST": ["agrowth", "issuance", "accruals"],                           # Hou-Xue-Zhang / Sloan
    "QV": ["gpa", "roa", "cfoa", "accruals", "ep", "cfp", "bm", "sp", "fcfp"],
    "ALL_FUND": ["gpa", "roa", "roe", "cfoa", "accruals", "lev", "agrowth", "issuance", "d_roa",
                 "ep", "cfp", "bm", "sp", "fcfp", "shy"],
    "ALL_FUND_MOM": ["gpa", "roa", "roe", "cfoa", "accruals", "lev", "agrowth", "issuance", "d_roa",
                     "ep", "cfp", "bm", "sp", "fcfp", "shy", "mom12_1"],
}

# 252d beta to the equal-weight member market for the beta-hedged variant
mret = ret.where(P["member"]).mean(axis=1)
beta = ret.rolling(252, min_periods=200).cov(mret).div(mret.rolling(252, min_periods=200).var(), axis=0)


def composite(names):
    zs = [Z[n] for n in names]
    stack = sum(z.fillna(0.0) for z in zs)
    cnt = sum(z.notna().astype(float) for z in zs)
    return (stack / cnt.replace(0, np.nan)).where(cnt >= max(2, len(names) // 2))


def main():
    rows = []
    for cname, names in COMPOS.items():
        c = composite(names)
        mask = base & c.notna()
        c = sector_z(c, sec, mask)
        for kind in ("quintile", "linear"):
            net, st, w = run_book(c, mask, ret, rebal, kind=kind, name=cname)
            r = splits_row(net, st); r.update({"compo": cname, "kind": kind, "variant": "raw"}); rows.append(r)
            # beta hedge: offset the book's ex-ante beta with the EW member market (cost on hedge incl.)
            bw = (w * beta.reindex_like(w).fillna(1.0)).sum(axis=1)
            mw = P["member"].astype(float); mw = mw.div(mw.sum(axis=1), axis=0).loc[w.index]
            wh = w - mw.mul(bw, axis=0)
            net_h, st_h = xs_backtest(wh, ret.loc[w.index[0]:], cost_bps=5.0, name=cname)
            r = splits_row(net_h, st_h); r.update({"compo": cname, "kind": kind, "variant": "beta_hedged"}); rows.append(r)
        # 3-tranche (quarterly overlapping) holding
        w1 = book_weights(c, mask, kind="linear")
        w3 = hold_monthly(w1, rebal).rolling(63, min_periods=1).mean().loc["2011-01-01":]
        net3, st3 = xs_backtest(w3, ret.loc["2011-01-01":], cost_bps=5.0, name=cname)
        r = splits_row(net3, st3); r.update({"compo": cname, "kind": "linear", "variant": "3m_tranche"}); rows.append(r)

    res = pd.DataFrame(rows).set_index(["compo", "kind", "variant"])
    pd.set_option("display.width", 200)
    print(res.round(3).to_string())
    res.round(4).to_csv(os.path.join(HERE, "screen2_results.csv"))


if __name__ == "__main__":
    main()
