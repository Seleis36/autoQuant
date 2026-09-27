"""Event study: sector-residual cumulative returns after insider purchases / sales, entry at the
close of the first trading day after the filing date. Simple (not log) residuals, bp.
Splits by role, CMP routine/opportunistic, size, clustering and prior return. IS <= 2017."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from events import load_events
from panel import load_panel
from common import sector_map

P = load_panel()
close = P["close"]; dates = close.index
ret = close.pct_change(fill_method=None)
mem = P["member"]
sec = sector_map(P)
r = ret.where(mem)
res = r.copy()
for s, cols in sec.groupby(sec).groups.items():
    cols = [c for c in cols if c in r.columns]
    res[cols] = r[cols].sub(r[cols].mean(axis=1), axis=0)
cum = res.fillna(0.0).cumsum()
cum_raw = ret.fillna(0.0).cumsum()

E = load_events(dates)
E = E[E.entry >= "2010-01-01"]
tix = {t: i for i, t in enumerate(close.columns)}
E = E[E.ticker.isin(tix)]
E["ci"] = E.ticker.map(tix); E["ri"] = dates.get_indexer(E.entry)
E = E[mem.values[E.ri.values, E.ci.values]]           # member at entry
H = [5, 21, 63, 126]
C = cum.values
for h in H:
    j = np.minimum(E.ri.values + h, len(dates) - 1)
    ok = (E.ri.values + h) < len(dates)
    E[f"h{h}"] = np.where(ok, C[j, E.ci.values] - C[E.ri.values, E.ci.values], np.nan) * 1e4
# pre-event residual return (formation, 21d before the trade date's entry)
j0 = np.maximum(E.ri.values - 21, 0)
E["pre21"] = (C[E.ri.values, E.ci.values] - C[j0, E.ci.values]) * 1e4
# cluster: >= 2 distinct insiders same ticker & code within 30 days before (incl.) the filing
E = E.sort_values("filing_date")
E["n_ins_30d"] = 0
for (t, c), g in E.groupby(["ticker", "code"]):
    fd = g.filing_date.values; own = g.owner_cik.values
    n = [len(set(own[(fd <= fd[i]) & (fd > fd[i] - np.timedelta64(30, "D"))])) for i in range(len(g))]
    E.loc[g.index, "n_ins_30d"] = n


def summ(x, name):
    row = {"subset": name, "N": len(x), "N/yr": len(x) / 16.7}
    for h in (5, 21):
        row[f"IS_h{h}"] = x.loc[x.entry < "2018", f"h{h}"].mean(); row[f"OOS_h{h}"] = x.loc[x.entry >= "2018", f"h{h}"].mean()
    for h in H:
        v = x[f"h{h}"].dropna()
        row[f"h{h}"] = v.mean(); row[f"t{h}"] = v.mean() / v.std() * np.sqrt(len(v)) if len(v) > 2 else np.nan
    row["IS_h63"] = x.loc[x.entry < "2018", "h63"].mean(); row["OOS_h63"] = x.loc[x.entry >= "2018", "h63"].mean()
    return row


rows = []
for code in ("P", "S"):
    X = E[(E.code == code) & ~E.is_10pct_only]
    rows.append(summ(X, f"{code} all (ex 10%-only)"))
    rows.append(summ(X[X.cls == "opportunistic"], f"{code} opportunistic"))
    rows.append(summ(X[X.cls == "routine"], f"{code} routine"))
    rows.append(summ(X[X.cls == "unclassified"], f"{code} unclassified"))
    rows.append(summ(X[X.is_officer], f"{code} officer"))
    rows.append(summ(X[X.is_ceo | X.is_cfo], f"{code} CEO/CFO"))
    rows.append(summ(X[X.is_director & ~X.is_officer], f"{code} director only"))
    rows.append(summ(X[X.val >= 1e6], f"{code} >= $1M"))
    rows.append(summ(X[(X.val >= 1e5) & (X.val < 1e6)], f"{code} $100k-1M"))
    rows.append(summ(X[X.val < 1e5], f"{code} < $100k"))
    rows.append(summ(X[X.n_ins_30d >= 2], f"{code} cluster >=2 insiders/30d"))
    rows.append(summ(X[X.n_ins_30d >= 3], f"{code} cluster >=3 insiders/30d"))
    rows.append(summ(X[X.pre21 < -500], f"{code} after 21d resid < -5%"))
    rows.append(summ(X[X.pre21 > 500], f"{code} after 21d resid > +5%"))
    rows.append(summ(X[X.frac_holdings > 0.2], f"{code} > 20% of holdings"))
    rows.append(summ(E[(E.code == code) & E.is_10pct_only], f"{code} 10%-owner only"))
d = pd.DataFrame(rows).set_index("subset")
pd.set_option("display.width", 220)
print(d.round(1).to_string())
d.round(2).to_csv(os.path.join(HERE, "event_study_results.csv"))
E.to_parquet("/tmp/insider_events.parquet")
