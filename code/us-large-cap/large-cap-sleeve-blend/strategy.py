"""large-cap-sleeve-blend -- target weights of the 4-sleeve S&P 500 market-neutral book.

    import sys; sys.path.insert(0, "code/us-large-cap/large-cap-sleeve-blend")
    from strategy import blend_weights, panel_inputs
    X = panel_inputs()             # {"close", "member", "sector", "rsp"} from the flat daily cache
    W = blend_weights(X)           # DataFrame dates x tickers, target weights at each close

W = sum_k MULT[k] * W_k, each sleeve built by its own idea's strategy.py with its defaults:
    RM   residual-momentum      residual 12-1 momentum, sector-neutral, beta-hedged, vol-managed (10 %)
    QVC  quality-value-composite IS-selected 5-sleeve fundamental blend (EDGAR XBRL, PIT)
    TXT  filing-text-changes    YoY Jaccard similarity of 10-K/10-Q text, quintile, beta-hedged
    REC  index-reconstitution   short S&P 500 additions at the effective-day close for 5 bars, sector-hedged
MULT = inverse IS (2011-17) vol weights x a leverage that puts the blend at 10 % IS vol; nothing is
fitted on 2018+ (calibrate.py). Rebalancing: RM/QVC/TXT books at the last NYSE session of each
month (their beta hedges and RM's vol scale per their own rules), REC on event days.

Data the live book must refresh before each close (all write to data/ or code/us-large-cap/shared/):
    python code/us-large-cap/shared/fetch_sp500_changes.py         # constituents, changes, PIT spans
    python code/us-large-cap/shared/fetch_universe.py <tickers> --refresh   # prices (or live_lib.daily)
    python code/us-large-cap/shared/fetch_actions.py               # splits/dividends (market cap)
    python code/us-large-cap/shared/fetch_xbrl.py --refresh        # fundamentals (companyfacts)
    python code/us-large-cap/shared/fetch_filing_text.py --update  # 10-K/10-Q similarity, new filings only
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(U, "shared")); sys.path.insert(0, os.path.join(U, "quality-value-composite"))
from modload import load

MULT = {"RM": 0.457, "QVC": 2.478, "TXT": 2.664, "REC": 1.211}

_rm = load(os.path.join(U, "residual-momentum", "strategy.py"))
_qvc = load(os.path.join(U, "quality-value-composite", "strategy.py"))
_txt = load(os.path.join(U, "filing-text-changes", "strategy.py"))
_rec = load(os.path.join(U, "index-reconstitution", "strategy.py"))
panel_inputs = _rm._panel_inputs


def sleeve_weights(X, start="2011-01-01"):
    return {"RM": _rm.residual_momentum_weights(X).loc[start:],
            "QVC": _qvc.qvc_weights(X, start=start),
            "TXT": _txt.text_weights(X, start=start),
            "REC": _rec.recon_weights(X, start=start)}


def blend_weights(X, mult=MULT, start="2011-01-01", return_sleeves=False):
    S = sleeve_weights(X, start)
    cols = sorted(set().union(*[S[k].columns for k in mult]))
    idx = S["RM"].index
    W = sum(S[k].reindex(index=idx, columns=cols).fillna(0.0) * v for k, v in mult.items())
    return (W, S) if return_sleeves else W


if __name__ == "__main__":
    from xs_lib import xs_backtest
    from common import splits_row
    X = panel_inputs()
    W = blend_weights(X)
    ret = X["close"].pct_change(fill_method=None).reindex(columns=W.columns).loc[W.index[0]:]
    net, st = xs_backtest(W, ret, cost_bps=5.0)
    print("blend 5 bp:", {k: round(v, 3) for k, v in splits_row(net, st).items()},
          "avg gross %.2f max gross %.2f" % (st["AvgGross"], W.abs().sum(axis=1).max()))
    print("latest target gross %.2f, net %.3f, names %d" % (W.iloc[-1].abs().sum(), W.iloc[-1].sum(), (W.iloc[-1] != 0).sum()))
