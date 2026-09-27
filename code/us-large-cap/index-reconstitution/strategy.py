"""index-reconstitution -- target weights of the post-inclusion reversal sleeve.

    from strategy import recon_weights, load_changes
    W = recon_weights(X)            # X = {"close", "member", "sector"}; changes default: shared/sp500_changes_raw.csv

Leg B (deployable, default): every S&P 500 ADDITION is shorted at the close of its effective
session (bar 0 = first session on/after the Wikipedia "Effective Date"; index funds bought at the
close of bar -1), `size` of capital, hedged with the same notional of its sector's EW member
basket, and covered at the close of bar +H (H = 5). Everything is known at entry: the addition
and its effective date are public days before.

Leg A (research only, legA=True): long quarterly-rebalance additions from the close of the first
session after the first Friday of Mar/Jun/Sep/Dec to the close of bar -1. It assumes S&P's
first-Friday announcement schedule, which is not reliable for every year -> excluded by default.

Refresh the changes table with `python code/us-large-cap/shared/fetch_sp500_changes.py`.
"""
import os, re, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from universe import _yf

CHANGES = os.path.join(HERE, "..", "shared", "sp500_changes_raw.csv")


def load_changes(path=CHANGES):
    raw = pd.read_csv(path, header=[0, 1])
    raw.columns = ["date", "add", "add_name", "rem", "rem_name", "reason", "refs"]
    raw["date"] = pd.to_datetime(raw.date, errors="coerce")
    raw = raw.dropna(subset=["date"])
    adds = raw[raw["add"].astype(str).str.strip().ne("") & raw["add"].notna()]
    return pd.DataFrame({"eff": adds.date.values, "ticker": [_yf(str(t).strip()) for t in adds["add"]]})


def _nth_friday(y, m, n):
    d = pd.Timestamp(year=y, month=m, day=1)
    return d + pd.Timedelta(days=(4 - d.weekday()) % 7) + pd.Timedelta(weeks=n - 1)


def recon_weights(X, changes=None, H=5, size=0.25, legA=False, start="2011-01-01", max_abs_ret=0.4):
    close, member, sector = X["close"], X["member"].fillna(False).astype(bool), X["sector"]
    sector = sector.reindex(close.columns).fillna("UNK")
    dates = close.index; tix = pd.Index(close.columns)
    ch = load_changes() if changes is None else changes
    ch = ch[(ch.eff >= pd.Timestamp(start) - pd.Timedelta(days=40)) & ch.ticker.isin(tix)]
    # names whose price history is a recycled symbol (>= 3 bars with |r| > 40 %) are skipped
    r = close.pct_change(fill_method=None)
    bad = (r.abs() > max_abs_ret).sum()
    ch = ch[~ch.ticker.isin(bad[bad >= 3].index)]
    W = pd.DataFrame(0.0, index=dates, columns=tix)
    sw = {}
    for s, cols in sector.groupby(sector).groups.items():
        m = member[list(cols)].astype(float)
        sw[s] = (list(cols), m.div(m.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0))

    def put(a, b, t, sign):
        if b <= a or a < 0:
            return
        ci = tix.get_loc(t)
        W.iloc[a:b, ci] += sign * size
        cols, w_s = sw[sector[t]]
        W.loc[W.index[a:b], cols] = W.loc[W.index[a:b], cols].values - sign * size * w_s.iloc[a:b].values

    for eff, t in zip(ch.eff, ch.ticker):
        ri = dates.searchsorted(eff)
        if ri >= len(dates) or not np.isfinite(close[t].iloc[ri]):
            continue
        put(ri, min(ri + H, len(dates)), t, -1.0)                  # held closes ri..ri+H-1
        if legA and eff.month in (3, 6, 9, 12):
            f3 = _nth_friday(eff.year, eff.month, 3)
            if f3 < eff <= f3 + pd.Timedelta(days=4):
                ia = dates.searchsorted(_nth_friday(eff.year, eff.month, 1), side="right")
                put(ia, ri - 1, t, +1.0)
    return W.loc[start:]


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
    from modload import load
    _panel_inputs = load(os.path.join(HERE, "..", "residual-momentum", "strategy.py"))._panel_inputs
    from xs_lib import xs_backtest
    from common import splits_row
    X = _panel_inputs()
    ret = X["close"].pct_change(fill_method=None)     # raw: a real squeeze on a short must count
    for legA in (False, True):
        W = recon_weights(X, legA=legA)
        net, st = xs_backtest(W, ret.loc[W.index[0]:].fillna(0), cost_bps=5.0)
        print("legA" if legA else "legB only", {k: round(v, 3) for k, v in splits_row(net, st).items()},
              "days active %.2f" % (W.abs().sum(axis=1) > 0).mean())
