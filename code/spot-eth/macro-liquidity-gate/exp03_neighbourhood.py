"""exp03 — selection-free view of "macro state as a gate on the ETH trend filter".

exp02 found one strong cell (TF AND fast60 > 0.5: 1.42 / 1.35 / 1.55) among four fast variants.
Before believing it: the whole family, reported as a distribution.
  * momentum horizon k in {10, 20, 40, 60, 90, 120, 180, 250} days
  * state = mean of sign-momentum over the five series (HYG, LQD, SPX +; DXY, VIX -)
  * form: TF x state, TF AND state > 0.5, TF AND state >= 0.6
  * plus each series alone at each k (TF AND own state)
and the lift over TF_live in IS (<= 2023) and OOS (2024+), with the IS -> OOS rank correlation.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from exp01_replicate import ek, rl  # noqa: E402

pd.set_option("display.width", 260)
eth = ek.daily()["Close"]
base = ek.baselines(eth)
tf = base["TF_live"]
START = "2018-06-01"
FAST = {"HYG": +1, "LQD": +1, "^GSPC": +1, "DX-Y.NYB": -1, "^VIX": -1}
KS = (10, 20, 40, 60, 90, 120, 180, 250)


def sh3(w):
    n = ek.bt(w, eth, start=START)[0]
    f = lambda x: x.mean() / x.std() * np.sqrt(365)
    return f(n), f(n.loc[:"2023-12-31"]), f(n.loc["2024-01-01":])


def state(k, tickers=FAST):
    parts = []
    for t, sgn in tickers.items():
        s = rl.load_series(t)["Close"]
        m = (np.sign(s / s.shift(k) - 1) * sgn > 0).astype(float).where(s.shift(k).notna())
        parts.append(m.reindex(eth.index, method="ffill"))
    return pd.concat(parts, axis=1).mean(axis=1)


t0 = sh3(tf)
print(f"TF_live: {t0[0]:.2f} / {t0[1]:.2f} / {t0[2]:.2f}")
rows = []
for k in KS:
    s = state(k)
    for form, w in (("x state", tf * s), ("AND > 0.5", tf * (s > 0.5)), ("AND >= 0.6", tf * (s >= 0.6))):
        a = sh3(w)
        rows.append({"k": k, "form": form, "series": "all5", "full": a[0], "IS": a[1], "OOS": a[2]})
    for t, sgn in FAST.items():
        a = sh3(tf * state(k, {t: sgn}))
        rows.append({"k": k, "form": "AND own", "series": t, "full": a[0], "IS": a[1], "OOS": a[2]})
R = pd.DataFrame(rows)
R["lift_IS"], R["lift_OOS"], R["lift_full"] = R["IS"] - t0[1], R["OOS"] - t0[2], R["full"] - t0[0]
comp = R[R.series == "all5"]
print("\ncomposite family (8 horizons x 3 forms = 24 cells): Sharpe full / IS / OOS")
print(comp.pivot(index="k", columns="form", values="full").round(2).to_string())
print("OOS:"); print(comp.pivot(index="k", columns="form", values="OOS").round(2).to_string())
print("IS:"); print(comp.pivot(index="k", columns="form", values="IS").round(2).to_string())
for nm, d in (("composite (24)", comp), ("single series (40)", R[R.series != "all5"]), ("all (64)", R)):
    print(f"\n{nm}: lift over TF  median full {d.lift_full.median():+.2f}, IS {d.lift_IS.median():+.2f}, OOS {d.lift_OOS.median():+.2f}; "
          f"share with lift > 0: IS {np.mean(d.lift_IS > 0):.2f}, OOS {np.mean(d.lift_OOS > 0):.2f}, both {np.mean((d.lift_IS > 0) & (d.lift_OOS > 0)):.2f}; "
          f"IS->OOS Spearman {d.IS.corr(d.OOS, method='spearman'):+.2f}; best full {d.full.max():.2f}")
print("\nsingle series, TF AND own momentum sign: OOS Sharpe by k")
print(R[R.series != "all5"].pivot(index="k", columns="series", values="OOS").round(2).to_string())
print("IS:"); print(R[R.series != "all5"].pivot(index="k", columns="series", values="IS").round(2).to_string())

# IS-selected member of the composite family, and yearly walk-forward selection
best_is = comp.sort_values("IS", ascending=False).iloc[0]
print(f"\nIS-best composite cell: k={best_is.k} {best_is.form}: IS {best_is.IS:.2f} -> OOS {best_is.OOS:.2f} (TF {t0[2]:.2f})")
cells = {}
for k in KS:
    s = state(k)
    cells[(k, "x")] = tf * s
    cells[(k, "and")] = tf * (s > 0.5)
    cells[(k, "and6")] = tf * (s >= 0.6)
nets = {c: ek.bt(w, eth, start=START)[0] for c, w in cells.items()}
wf = []
for y in range(2021, 2027):
    tr = {c: n.loc[:f"{y - 1}-12-31"] for c, n in nets.items()}
    pick = max(tr, key=lambda c: tr[c].mean() / tr[c].std())
    wf.append(nets[pick].loc[f"{y}-01-01":f"{y}-12-31"])
    print(f"  {y}: picked k={pick[0]} {pick[1]}")
wf = pd.concat(wf)
nt = ek.bt(tf, eth, start=START)[0].loc[wf.index[0]:]
f = lambda x: x.mean() / x.std() * np.sqrt(365)
print(f"walk-forward (expanding, yearly re-selection, 2021+): {f(wf):.2f} vs TF_live {f(nt):.2f}; 2024+: {f(wf.loc['2024-01-01':]):.2f} vs {f(nt.loc['2024-01-01':]):.2f}")
R.to_csv(os.path.join(HERE, "exp03_family.csv"), index=False)
