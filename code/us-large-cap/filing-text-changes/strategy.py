"""filing-text-changes -- target weights of the text-similarity sleeve.

    from strategy import text_weights
    W = text_weights(X)        # X = {"close", "member", "sector"}

Signal: Jaccard similarity (word sets) between a firm's latest 10-K/10-Q and the same form for
the period one year earlier (data/SP500_filing_similarity.parquet; refresh incrementally with
`python code/us-large-cap/shared/fetch_filing_text.py --update`). Usable from the first session
after the filing date; expires 200 days after the period end. Higher similarity ("non-changer")
= long. Sector-neutral z, quintile dollar-neutral book (gross 1), set at the last NYSE session
of each month, beta-hedged DAILY with the EW member basket. Unlevered vol ~2.3 %.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from common import sector_z, book_weights
from xbrl import Fundamentals
from trading_calendar import month_end_sessions
from research_lib import DATA_DIR

SIM = os.path.join(DATA_DIR, "SP500_filing_similarity.parquet")


def text_weights(X, sim=None, metric="jac", max_age_days=200, kind="quintile", start="2011-01-01", gross_mult=1.0):
    close, member, sector = X["close"], X["member"].fillna(False).astype(bool), X["sector"]
    sector = sector.reindex(close.columns).fillna("UNK")
    tix = list(close.columns); dates = close.index
    S = pd.read_parquet(SIM) if sim is None else sim
    S = S[S.ticker.isin(tix)].dropna(subset=["cos"])
    long = S[["ticker", "report_date", "filing_date", metric]].rename(
        columns={"report_date": "end", "filing_date": "avail", metric: "val"}).dropna()
    sig = Fundamentals.daily(long, dates, tix, max_age_days=max_age_days)
    mask = member & close.notna() & sig.notna()
    z = sector_z(sig, sector, mask)
    rebal = month_end_sessions(dates)
    w = book_weights(z, mask, kind=kind).reindex(rebal).reindex(dates).ffill().fillna(0.0)
    ret = close.pct_change(fill_method=None)
    M = ret.where(member).mean(axis=1)
    beta = ret.rolling(252, min_periods=200).cov(M).div(M.rolling(252, min_periods=200).var(), axis=0)
    mw = member.astype(float); mw = mw.div(mw.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    bw = (w * beta.fillna(1.0)).sum(axis=1)
    return ((w - mw.mul(bw, axis=0)) * gross_mult).loc[start:]


if __name__ == "__main__":
    from modload import load
    _panel_inputs = load(os.path.join(HERE, "..", "residual-momentum", "strategy.py"))._panel_inputs
    from xs_lib import xs_backtest
    from common import splits_row
    X = _panel_inputs()
    W = text_weights(X)
    net, st = xs_backtest(W, X["close"].pct_change(fill_method=None).loc[W.index[0]:], cost_bps=5.0)
    print("text sleeve 5 bp:", {k: round(v, 3) for k, v in splits_row(net, st).items()}, "avg gross", round(st["AvgGross"], 2))
