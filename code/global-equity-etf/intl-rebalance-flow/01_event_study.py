"""Event study: does the period-to-date US-minus-international return predict the hedged
international-minus-SPY spread on the sessions around the month-end?

For each month m (last session L_m at position p):
  S_m(k) = sum of daily (r_SPY - r_INTL) from p_{m-1}+1 .. p-k    (known at close p-k)
  y_j    = hedged spread return on session p+j, j = -k+1 .. +10
Slope of y_j on S_m (z-scored by trailing spread vol x sqrt(n)), OLS t across months.
Rebalancing predicts slope > 0 (US out-ran -> intl bought -> spread up) near j = 0..+2.
Placebo: the same thing anchored 10 sessions before the month-end.
"""
import numpy as np, pandas as pd
from lib import load, spreads, month_end_positions, SPL

C, R = load()
S = spreads(R)
h = S["hedged"]; d = S["dollar"]
rel_us = S["spy"] - S["intl"]          # US minus intl, dollar
vol = h.rolling(252, min_periods=126).std().shift(1)
idx = h.index
pe = month_end_positions(idx)

def build(k=3, anchor_shift=0, horizon=10, which="hedged"):
    y_src = (h if which == "hedged" else d).values
    rows = []
    for a, b in zip(pe[:-1], pe[1:]):
        p = b - anchor_shift
        start = a + 1
        end = p - k
        if end - start < 3 or p + horizon >= len(idx):
            continue
        sig = rel_us.iloc[start:end + 1].sum()
        z = sig / (vol.iloc[end] * np.sqrt(end - start + 1))
        if not np.isfinite(z):
            continue
        row = {"date": idx[b], "S": sig, "Z": z, "q": idx[b].month in (3, 6, 9, 12)}
        for j in range(-k + 1, horizon + 1):
            row[j] = y_src[p + j]
        rows.append(row)
    return pd.DataFrame(rows).set_index("date")

def slopes(df, cols, x="Z"):
    out = {}
    for j in cols:
        sub = df[[x, j]].dropna()
        X = sub[x] - sub[x].mean()
        bta = (X * sub[j]).sum() / (X ** 2).sum()
        res = sub[j] - sub[j].mean() - bta * X
        se = np.sqrt((res ** 2).sum() / (len(sub) - 2) / (X ** 2).sum())
        out[j] = (bta * 1e4, bta / se)
    return out

pd.set_option("display.width", 200)
for which in ["hedged", "dollar"]:
  for k in [1, 3]:
    for anchor, lab in [(0, "MONTH-END"), (10, "PLACEBO L-10")]:
        df = build(k, anchor, which=which)
        cols = [c for c in df.columns if isinstance(c, (int, np.integer))]
        print(f"\n=== {which} | signal through L-{k} | {lab} | months={len(df)}")
        tab = {}
        for name, (a, b) in SPL.items():
            sub = df.loc[a:b]
            sl = slopes(sub, cols)
            tab[name + "_bp"] = {j: v[0] for j, v in sl.items()}
            tab[name + "_t"] = {j: v[1] for j, v in sl.items()}
        q = slopes(df[df.q], cols); nq = slopes(df[~df.q], cols)
        tab["QEND_t"] = {j: v[1] for j, v in q.items()}
        tab["NONQ_t"] = {j: v[1] for j, v in nq.items()}
        print(pd.DataFrame(tab).round(2).T.to_string())
        # cumulative windows
        for w0, w1 in [(-k + 1, 0), (-k + 1, 1), (0, 2), (1, 3), (1, 5), (4, 10)]:
            cs = df[list(range(w0, w1 + 1))].sum(axis=1)
            tmp = pd.DataFrame({"Z": df.Z, "y": cs})
            r = {n: slopes(tmp.loc[a:b], ["y"])["y"] for n, (a, b) in SPL.items()}
            print(f"  window [{w0:+d},{w1:+d}]  " + "  ".join(f"{n}: {v[0]:6.1f}bp t={v[1]:5.2f}" for n, v in r.items()))
