"""Which drift predicts the last-session return: US vs intl (this idea), US vs bonds (HMM),
or the plain SPY month-to-date return?  Outcomes: SPY, the INTL basket, the hedged spread,
all on day L, signal through L-1. Multivariate OLS with each drift z-scored by its own
trailing daily vol x sqrt(n)."""
import sys, os
import numpy as np, pandas as pd
from lib import load, spreads, month_end_positions, SPL
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import data as D

C, R = load()
B = D.load_panel(["TLT", "IEF"], start="1998-12-01").pct_change()
S = spreads(R)
idx = S.index; pe = month_end_positions(idx)
drifts = {"US-INTL": S["spy"] - S["intl"], "US-TLT": S["spy"] - B["TLT"], "US-IEF": S["spy"] - B["IEF"],
          "US": S["spy"], "INTL": S["intl"]}
vols = {k: v.rolling(252, min_periods=126).std().shift(1) for k, v in drifts.items()}

def zsig(k=1, anchor=0):
    rows = []
    for a, b in zip(pe[:-1], pe[1:]):
        p = b - anchor; end = p - k
        if end - (a + 1) < 3: continue
        r = {"day": idx[p]}
        for n, s in drifts.items():
            r[n] = s.iloc[a + 1:end + 1].sum() / (vols[n].iloc[end] * np.sqrt(end - a))
        rows.append(r)
    return pd.DataFrame(rows).set_index("day")

def ols(y, X):
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    if len(d) < 30: return None
    Xm = np.column_stack([np.ones(len(d)), d[X.columns].values])
    bta, *_ = np.linalg.lstsq(Xm, d["y"].values, rcond=None)
    res = d["y"].values - Xm @ bta
    s2 = res @ res / (len(d) - Xm.shape[1])
    se = np.sqrt(np.diag(s2 * np.linalg.inv(Xm.T @ Xm)))
    return pd.Series(bta[1:] * 1e4, X.columns).round(1).astype(str) + " (" + pd.Series(bta[1:] / se[1:], X.columns).round(2).astype(str) + ")"

Z = zsig(1)
print("corr of drifts:\n", Z.corr().round(2))
outs = {"SPY": S["spy"], "INTL": S["intl"], "hedged": S["hedged"], "dollar": S["dollar"]}
periods = dict(SPL); periods.update({"2002-12": ("2002-07-01", "2012-12-31"), "2020-26": ("2020-01-01", "2026-12-31")})
for on, y in outs.items():
    print(f"\n==== outcome {on} on day L (bp per z, t)")
    yy = y.reindex(Z.index)
    for spec in [["US-INTL"], ["US-TLT"], ["US"], ["US-INTL", "US-TLT"], ["US-INTL", "US"], ["INTL", "US"]]:
        line = []
        for pn, (a, b) in periods.items():
            r = ols(yy.loc[a:b], Z.loc[a:b, spec])
            line.append(f"{pn}: " + ("n/a" if r is None else " ".join(r.values)))
        print(f"  {'+'.join(spec):16s} | " + " | ".join(line))
