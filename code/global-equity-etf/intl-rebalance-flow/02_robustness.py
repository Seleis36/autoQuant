"""Robustness of the day-0 (last session of the month) effect.

Signal Z_m: period-to-date (SPY - INTL basket) return through the close of L-1, z-scored by
trailing hedged-spread vol x sqrt(n). Outcome: return on day L of various spreads.
"""
import sys, os
import numpy as np, pandas as pd
from lib import load, spreads, month_end_positions, SPL, roll_beta, COUNTRIES
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import data as D

C, R = load()
X = D.load_panel(["DBEF", "HEFA", "DXJ", "HEDJ", "VEU", "FXE", "FXY", "UUP"], start="1998-12-01")
RX = X.pct_change()
S = spreads(R)
rel_us = S["spy"] - S["intl"]
vol = S["hedged"].rolling(252, min_periods=126).std().shift(1)
idx = S.index
pe = month_end_positions(idx)

def signal(k=1, anchor=0, period="M"):
    rows = []
    for a, b in zip(pe[:-1], pe[1:]):
        p = b - anchor
        end = p - k
        if end - (a + 1) < 3 or p >= len(idx):
            continue
        z = rel_us.iloc[a + 1:end + 1].sum() / (vol.iloc[end] * np.sqrt(end - a))
        if np.isfinite(z):
            rows.append((idx[p], idx[b], z))
    return pd.DataFrame(rows, columns=["day", "me", "Z"]).set_index("day")

def slope(x, y):
    sub = pd.concat([x, y], axis=1).dropna()
    if len(sub) < 20: return np.nan, np.nan, len(sub)
    X_ = sub.iloc[:, 0] - sub.iloc[:, 0].mean(); Y = sub.iloc[:, 1]
    b = (X_ * Y).sum() / (X_ ** 2).sum()
    res = Y - Y.mean() - b * X_
    se = np.sqrt((res ** 2).sum() / (len(sub) - 2) / (X_ ** 2).sum())
    return b * 1e4, b / se, len(sub)

sig = signal(1)
# ---- outcomes on day L
beta = lambda y: roll_beta(y, R["SPY"]).shift(1)
out = {"basket_hedged": S["hedged"], "basket_dollar": S["dollar"]}
for t in COUNTRIES + ["EFA", "EEM"]:
    out[t + "_h"] = R[t] - beta(R[t]) * R["SPY"]
for t in ["DBEF", "HEFA", "DXJ", "HEDJ", "VEU"]:
    out[t + "_h"] = RX[t] - roll_beta(RX[t], R["SPY"]).shift(1) * R["SPY"]
out["EFA-DBEF (fx part)"] = R["EFA"] - RX["DBEF"]
out["EWJ-DXJ (~fx part)"] = R["EWJ"] - RX["DXJ"]
out["FXE"] = RX["FXE"]; out["FXY"] = RX["FXY"]; out["-UUP"] = -RX["UUP"]
out["SPY"] = R["SPY"]; out["INTL"] = S["intl"]

rows = {}
for k_, y in out.items():
    yy = y.reindex(sig.index)
    r = {}
    for n, (a, b) in SPL.items():
        bp, t, nn = slope(sig.Z.loc[a:b], yy.loc[a:b])
        r[n + "_bp"] = bp; r[n + "_t"] = t; r[n + "_n"] = nn
    rows[k_] = r
pd.set_option("display.width", 220)
print("=== day-L slope on Z (signal through L-1), bp per unit Z")
print(pd.DataFrame(rows).T.round(2).to_string())

# ---- by sub-period and quarter-end split
print("\n=== basket_dollar day-L slope by sub-period")
y = out["basket_dollar"].reindex(sig.index)
for a, b in [("1999", "2005"), ("2006", "2012"), ("2013", "2019"), ("2020", "2026")]:
    s = sig.loc[a:b]; q = s.index.month.isin([3, 6, 9, 12])
    print(a, b, "all", np.round(slope(s.Z, y.loc[a:b])[:2], 2), " qend", np.round(slope(s.Z[q], y.loc[a:b][q])[:2], 2),
          " nonq", np.round(slope(s.Z[~q], y.loc[a:b][~q])[:2], 2))

# ---- placebo distribution: anchor the "month-end" 3..15 sessions earlier
print("\n=== placebo: day-(L-a) slope (signal through L-a-1)")
for a_ in range(0, 16):
    s = signal(1, a_)
    yy = out["basket_dollar"].reindex(s.index)
    r = [slope(s.Z.loc[a:b], yy.loc[a:b])[1] for n, (a, b) in SPL.items()]
    print(f"anchor L-{a_:2d}: t FULL {r[0]:5.2f} IS {r[1]:5.2f} OOS {r[2]:5.2f}")

# ---- day-L slope next month start? and sign-based mean
print("\n=== sign-based day-L mean of basket_dollar * sign(Z) (bp)")
for n, (a, b) in SPL.items():
    s = sig.loc[a:b]; yy = y.loc[a:b]
    m = (np.sign(s.Z) * yy) * 1e4
    print(n, f"mean {m.mean():.1f}bp  t {m.mean() / m.std() * np.sqrt(len(m)):.2f}  n {len(m)}; |Z|>1: "
          f"{m[s.Z.abs() > 1].mean():.1f}bp n={int((s.Z.abs() > 1).sum())}")
