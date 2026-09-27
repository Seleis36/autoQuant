"""Event study around PREDICTED ex-dividend dates (Hartzmark & Solomon 2013 "dividend month
premium"; price pressure before the ex-date).

Predicted ex-date = an ex-date observed one year earlier + 364 days (same weekday), known a
year in advance -- the event exists whether or not the dividend is later paid. Returns are
total-return (the cache is dividend-adjusted), sector-residual, simple, in bp. Also the
monthly HS definition: month m is a "dividend month" if the stock had an ex-date in month m-12.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from common import sector_map
from panel import load_panel
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import DATA_DIR

P = load_panel()
close = P["close"]; dates = close.index; tix = list(close.columns)
ret = close.pct_change(fill_method=None)
mem = P["member"]; sec = sector_map(P)
r = ret.where(mem)
res = r.copy()
for s, cols in sec.groupby(sec).groups.items():
    cols = [c for c in cols if c in r.columns]
    res[cols] = r[cols].sub(r[cols].mean(axis=1), axis=0)
C = res.fillna(0.0).cumsum().values

A = pd.read_parquet(os.path.join(DATA_DIR, "SP500_actions.parquet"))
dv = A[(A.dividend > 0) & A.ticker.isin(tix)].copy()
dv["pred"] = dv.date + pd.Timedelta(days=364)
ev = dv[(dv.pred >= "2010-03-01") & (dv.pred <= dates[-1])].copy()
ev["ri"] = dates.searchsorted(ev.pred.values)          # first session on/after predicted date
ev["ci"] = pd.Index(tix).get_indexer(ev.ticker)
ev = ev[(ev.ri > 40) & (ev.ri < len(dates) - 15)]
ev = ev[mem.values[ev.ri.values - 20, ev.ci.values]]
# did the dividend actually come within +-10 days of prediction?
act = {t: g.date.values for t, g in dv.groupby("ticker")}
ev["hit"] = [np.any(np.abs((act[t] - p) / np.timedelta64(1, "D")) <= 10) for t, p in zip(ev.ticker, ev.pred.values)]
print(len(ev), "predicted events; hit rate", ev.hit.mean().round(3))

# daily event-time profile: residual return on bar k relative to predicted date (k = -30..+10)
K = range(-30, 11)
prof = {}
for k in K:
    i = ev.ri.values + k
    prof[k] = (C[i, ev.ci.values] - C[i - 1, ev.ci.values]) * 1e4
prof = pd.DataFrame(prof, index=ev.index)
m = prof.mean(); t = prof.mean() / prof.std() * np.sqrt(len(prof))
print(pd.DataFrame({"bp": m, "t": t}).T.round(2).to_string())
win = {"[-20,-1]": range(-20, 0), "[-10,-1]": range(-10, 0), "[-5,-1]": range(-5, 0), "[-3,-1]": range(-3, 0),
       "[0,0]": [0], "[0,+5]": range(0, 6), "[-20,+5]": range(-20, 6)}
rows = []
for name, ks in win.items():
    x = prof[list(ks)].sum(axis=1)
    rows.append({"window": name, "bp": x.mean(), "t": x.mean() / x.std() * np.sqrt(len(x)),
                 "IS": x[ev.pred < "2018"].mean(), "OOS": x[ev.pred >= "2018"].mean(),
                 "hit_only": x[ev.hit].mean(), "miss_only": x[~ev.hit].mean()})
d = pd.DataFrame(rows).set_index("window")
print(d.round(2).to_string())
d.round(3).to_csv(os.path.join(HERE, "event_study_results.csv"))
prof.mean().to_csv(os.path.join(HERE, "event_profile.csv"))
ev.to_parquet("/tmp/div_events.parquet")
