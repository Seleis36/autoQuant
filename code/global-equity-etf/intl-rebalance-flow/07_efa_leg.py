"""Re-framing: the same day-L spread trade with a single liquid international leg (EFA, VEU)
instead of the 9-name basket, so the round trip costs 2 bp/side + 1 bp SPY rather than 5 + 1.
Signal unchanged (MTD SPY - INTL basket, through L-1). Also the signal built from the leg
itself (MTD SPY - EFA)."""
import sys, os
import numpy as np, pandas as pd
from lib import load, spreads, month_end_positions, SPL, run_book, stats, roll_beta
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import data as D

C, R = load()
X = D.load_panel(["VEU"], start="1998-12-01"); C = C.join(X); R = C.pct_change()
S = spreads(R)
idx = S.index; pe = month_end_positions(idx)

def book(leg, sig_src, qend=False, cost=2.0):
    rel = S["spy"] - (S["intl"] if sig_src == "basket" else R[leg])
    hed = R[leg] - roll_beta(R[leg], R["SPY"]).shift(1) * R["SPY"]
    vol = hed.rolling(252, min_periods=126).std().shift(1)
    b_t = roll_beta(R[leg], R["SPY"])                # known at close t
    pos = pd.Series(0.0, index=idx)
    for a, b in zip(pe[:-1], pe[1:]):
        if qend and idx[b].month not in (3, 6, 9, 12): continue
        end = b - 1
        if end - a < 4 or not np.isfinite(vol.iloc[end]): continue
        z = rel.iloc[a + 1:end + 1].sum() / (vol.iloc[end] * np.sqrt(end - a))
        if np.isfinite(z): pos.iloc[b - 1] = np.clip(z, -2, 2) / 2 * 4.0
    w = pd.DataFrame({leg: pos, "SPY": -pos * b_t.fillna(1.0)})
    net, gross, turn, We = run_book(w, C, cost=cost)
    st = stats(net, turn=turn, We=We)
    g = gross.loc["2002-01":]; st["gross_FULL"] = g.mean() / g.std() * np.sqrt(252)
    go = gross.loc["2013":]; st["gross_OOS"] = go.mean() / go.std() * np.sqrt(252)
    return st

rows = {}
for leg in ["EFA", "VEU", "EEM"]:
    for src in ["basket", "leg"]:
        for q in [False, True]:
            rows[f"{leg} sig={src} {'qend' if q else 'all'}"] = book(leg, src, q, cost=2.0 if leg != "EEM" else 3.0)
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).T.round(3).to_string())
