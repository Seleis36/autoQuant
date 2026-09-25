"""Event study: mean daily return (bp) by calendar bucket for SPY, the equal-weight sector
basket, and a cyclical-minus-defensive (high-minus-low beta) spread. IS 1999-2014 / OOS 2015+."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import data, sxlib as sx, cal

c = data.load_panel()
r = c.pct_change().loc["1999":]
S = data.SECTORS
f = cal.features(c.index).loc["1999":]
ew = r[S].mean(axis=1)
beta = sx.beta_to(c.pct_change()[S], c.pct_change()["SPY"], 126).shift(1).loc["1999":]
hi = r[S].where(beta.rank(axis=1, ascending=False) <= 3).mean(axis=1)
lo = r[S].where(beta.rank(axis=1) <= 3).mean(axis=1)
series = {"SPY": r["SPY"], "EW": ew, "HiMinusLoBeta": hi - lo}

def tab(key, grp):
    rows = []
    for nm, x in series.items():
        for seg, (a, b) in [("IS", sx.IS), ("OOS", sx.OOS)]:
            xx = x.loc[a:b]; g = grp.loc[a:b]
            m = xx.groupby(g).agg(["mean", "std", "count"])
            m["t"] = m["mean"] / (m["std"] / np.sqrt(m["count"]))
            for k_, row in m.iterrows():
                rows.append(dict(series=nm, seg=seg, bucket=k_, bp=row["mean"] * 1e4, t=row["t"], n=row["count"]))
    d = pd.DataFrame(rows)
    p = d.pivot_table(index="bucket", columns=["series", "seg"], values=["bp", "t"])
    print(f"\n=== {key}")
    print(p.round(1).to_string())

pd.set_option("display.width", 250)
tdb = f["tdom"].clip(-8, 8)
tab("trading day of month (-1 = last day, +1 = first)", tdb)
fo = f["fomc_off"]
week = pd.Series(np.where(f["to_fomc"] == -1, -1, np.floor((fo + 1) / 5)), index=f.index).clip(upper=7)
tab("FOMC cycle week (CMVJ: week0 = days -1..+3; -1 bucket = day before statement)", week)
tab("pre-holiday", f["pre_hol"].astype(int))
