"""S&P 500 additions and deletions 2010-2026 (Wikipedia 'Selected changes' table, with reasons):
sector-residual (vs EW sector members) and market-residual returns around the effective date.

Timing: bar 0 = first session ON/AFTER the effective date (changes take effect before the open);
index funds trade at the close of bar -1. The announcement (typically 3-10 sessions earlier)
is not in the data, so only windows starting at the close of bar -1 or later are tradeable.
"""
import os, sys, re
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from common import sector_map
from panel import load_panel
from universe import _yf

P = load_panel()
close = P["close"]; dates = close.index; tix = list(close.columns)
ret = close.pct_change(fill_method=None)
# outside membership windows the panel's bad-data mask does not apply: recycled tickers and
# mis-adjusted bars produce +50,000 bp "returns". Mask any |daily return| > 40 % (bar and the
# next), and drop tickers with >= 3 such bars (recycled symbols).
bad = ret.abs() > 0.4
ret = ret.where(~(bad | bad.shift(1, fill_value=False)))
BAD_TICKERS = set(bad.sum()[bad.sum() >= 3].index)
mem = P["member"]; sec = sector_map(P)
# residual vs EW of sector members (the stock itself excluded only when it is a member: fine)
r = ret
res = r.copy()
for s, cols in sec.groupby(sec).groups.items():
    cols = [c for c in cols if c in r.columns]
    sm = r[cols].where(mem[cols]).mean(axis=1)
    res[cols] = r[cols].sub(sm, axis=0)
mk = r.where(mem).mean(axis=1)
C = res.fillna(0.0).cumsum().values
Cm = r.sub(mk, axis=0).fillna(0.0).cumsum().values
raw = pd.read_csv(os.path.join(HERE, "..", "shared", "sp500_changes_raw.csv"), header=[0, 1])
raw.columns = ["date", "add", "add_name", "rem", "rem_name", "reason", "refs"]
raw["date"] = pd.to_datetime(raw.date, errors="coerce")
raw = raw.dropna(subset=["date"])
raw = raw[raw.date >= "2010-01-01"]
ev = []
for _, x in raw.iterrows():
    reason = str(x.reason).lower()
    kind = "acq" if re.search(r"acquir|merg|spun|spin|purchase|bought", reason) else "cap"
    if isinstance(x["add"], str) and x["add"].strip():
        ev.append((x.date, _yf(x["add"].strip()), "add", kind))
    if isinstance(x["rem"], str) and x["rem"].strip():
        ev.append((x.date, _yf(x["rem"].strip()), "del", kind))
E = pd.DataFrame(ev, columns=["eff", "ticker", "side", "kind"])
E = E[E.ticker.isin(tix) & ~E.ticker.isin(BAD_TICKERS)].copy()
E["ri"] = dates.searchsorted(E.eff.values)
E["ci"] = pd.Index(tix).get_indexer(E.ticker)
E = E[(E.ri > 25) & (E.ri < len(dates) - 1)]
# priced around the event?
E = E[[np.isfinite(close.values[i - 1, c]) and np.isfinite(close.values[min(i + 5, len(dates) - 1), c]) for i, c in zip(E.ri, E.ci)]]
print(E.groupby(["side", "kind"]).size())


def win(a, b, CC=C):
    """cumulative residual from close of bar a to close of bar b (bp); NaN if beyond data."""
    ia = E.ri.values + a; ib = E.ri.values + b
    ok = ib < len(dates)
    v = np.full(len(E), np.nan)
    v[ok] = (CC[ib[ok], E.ci.values[ok]] - CC[ia[ok], E.ci.values[ok]]) * 1e4
    return v


W = {"pre [-10,-1]": (-11, -1), "[-5,-1]": (-6, -1), "day0 [0]": (-1, 0), "post [1,5]": (0, 5),
     "trade [0,5] from close -1": (-1, 5), "trade [0,20]": (-1, 20), "trade [0,60]": (-1, 60),
     "trade [0,120]": (-1, 120), "[+5,+60]": (5, 60)}
rows = []
for (side, kind), g in list(E.groupby(["side", "kind"])) + [(("add", "all"), E[E.side == "add"]), (("del", "all"), E[E.side == "del"])]:
    idx = E.index.get_indexer(g.index)
    for wn, (a, b) in W.items():
        v = win(a, b)[idx]; vm = win(a, b, Cm)[idx]
        v = v[np.isfinite(v)]; vm = vm[np.isfinite(vm)]
        yrs = g.eff.dt.year.values
        rows.append({"side": side, "kind": kind, "window": wn, "N": len(v), "sector_res_bp": v.mean(),
                     "t": v.mean() / v.std() * np.sqrt(len(v)) if len(v) > 2 else np.nan,
                     "mkt_res_bp": vm.mean(), "median": np.median(v) if len(v) else np.nan})
d = pd.DataFrame(rows).set_index(["side", "kind", "window"])
pd.set_option("display.width", 200)
print(d.round(1).to_string())
d.round(2).to_csv(os.path.join(HERE, "event_study_results.csv"))
E.to_parquet("/tmp/recon_events.parquet")
# IS / OOS for the tradeable windows
for side in ("add", "del"):
    g = E[E.side == side]; idx = E.index.get_indexer(g.index)
    for wn in ("trade [0,20]", "trade [0,60]", "trade [0,120]"):
        a, b = W[wn]; v = win(a, b)[idx]
        print(side, wn, "IS %.0f (N %d)  OOS %.0f (N %d)" % (np.nanmean(v[g.eff.values < np.datetime64("2018-01-01")]), (g.eff < "2018").sum(),
                                                         np.nanmean(v[g.eff.values >= np.datetime64("2018-01-01")]), (g.eff >= "2018").sum()))
