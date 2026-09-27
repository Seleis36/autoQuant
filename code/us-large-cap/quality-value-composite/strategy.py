"""quality-value-composite -- target weights of the IS-selected 5-sleeve fundamental blend.

    from strategy import qvc_weights
    W = qvc_weights(X)      # X = {"close", "member", "sector"} wide panels (see residual-momentum/strategy.py:_panel_inputs)

Needs data/SP500_xbrl_facts.parquet and data/SP500_actions.parquet (refresh with
code/us-large-cap/shared/fetch_xbrl.py --refresh and fetch_actions.py). Fundamentals enter at the
close of the first session after their EDGAR filing date (xbrl.py).

Sleeves (composite of sector-neutral z-scores -> sector-neutral z again -> book), each
rebalanced at the last NYSE session of the month and held; every sleeve is beta-hedged DAILY
with the EW member basket (252-bar beta to the EW member market), as backtested:
    QUAL_qmj      quintile   0.212
    PAYOUT        linear     0.258
    QUAL_prof     linear     0.265
    ALL_FUND_MOM  quintile   0.265     (weights = inverse IS 2011-17 vol, fixed; screen3_blend.py)
Unlevered the blend runs at ~2.6 % vol; scale it with `gross_mult`.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from signals import build_signals
from common import sector_z, book_weights
from trading_calendar import month_end_sessions

COMPOS = {
    "QUAL_prof": ["gpa", "roa", "roe", "cfoa", "accruals"],
    "QUAL_qmj": ["gpa", "roa", "roe", "cfoa", "accruals", "lev", "lowvol", "issuance", "shy"],
    "PAYOUT": ["shy", "issuance"],
    "INVEST": ["agrowth", "issuance", "accruals"],
    "ALL_FUND_MOM": ["gpa", "roa", "roe", "cfoa", "accruals", "lev", "agrowth", "issuance", "d_roa",
                     "ep", "cfp", "bm", "sp", "fcfp", "shy", "mom12_1"],
}
SLEEVES = {"QUAL_qmj": ("quintile", 0.212), "PAYOUT": ("linear", 0.258), "QUAL_prof": ("linear", 0.265),
           "ALL_FUND_MOM": ("quintile", 0.265)}


def qvc_weights(X, F=None, gross_mult=1.0, start="2011-01-01", sleeves=SLEEVES, return_sleeves=False):
    close, member, sector = X["close"], X["member"].fillna(False).astype(bool), X["sector"]
    sector = sector.reindex(close.columns).fillna("UNK")
    S, aux = build_signals(close, F)
    base = member & aux["mcap"].notna()
    Z = {}
    for k in set(sum((COMPOS[c] for c in sleeves), [])):
        m = base & S[k].notna()
        Z[k] = sector_z(S[k], sector, m)
    ret = close.pct_change(fill_method=None)
    mret = ret.where(member).mean(axis=1)
    beta = ret.rolling(252, min_periods=200).cov(mret).div(mret.rolling(252, min_periods=200).var(), axis=0)
    mw = member.astype(float); mw = mw.div(mw.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    rebal = month_end_sessions(close.index)
    out = {}
    for name, (kind, wt) in sleeves.items():
        names = COMPOS[name]
        zs = [Z[n] for n in names]
        stack = sum(z.fillna(0.0) for z in zs); cnt = sum(z.notna().astype(float) for z in zs)
        c = (stack / cnt.replace(0, np.nan)).where(cnt >= max(2, len(names) // 2))
        mask = base & c.notna()
        c = sector_z(c, sector, mask)
        w = book_weights(c, mask, kind=kind).reindex(rebal).reindex(close.index).ffill().fillna(0.0)
        bw = (w * beta.fillna(1.0)).sum(axis=1)
        out[name] = (w - mw.mul(bw, axis=0)).loc[start:]
    W = sum(out[n] * sleeves[n][1] for n in out) * gross_mult
    return (W, out) if return_sleeves else W


if __name__ == "__main__":
    from modload import load
    _panel_inputs = load(os.path.join(HERE, "..", "residual-momentum", "strategy.py"))._panel_inputs
    from xs_lib import xs_backtest
    from common import splits_row
    X = _panel_inputs()
    W, parts = qvc_weights(X, return_sleeves=True)
    ret = X["close"].pct_change(fill_method=None).loc[W.index[0]:]
    net, st = xs_backtest(W, ret, cost_bps=5.0)
    print("QVC blend (weight-level, 5 bp):", {k: round(v, 3) for k, v in splits_row(net, st).items()}, "avg gross", round(st["AvgGross"], 2))
    R = sum(xs_backtest(parts[n], ret, cost_bps=5.0)[0] * SLEEVES[n][1] for n in parts)
    print("QVC blend (return-level, as researched):", {k: round(v, 3) for k, v in splits_row(R).items()})
