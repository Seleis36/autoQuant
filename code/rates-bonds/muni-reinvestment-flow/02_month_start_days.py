"""muni-reinvestment-flow -- where in the month-start window does the return sit?
Mean daily total return (bp, t) by trading day of month 1..5 and 'rest', for muni ETFs and,
as controls, Treasury / credit ETFs that go ex-dividend on the same day. Raw (not hedged)
and hedged (muni - trailing beta x IEF/SHY). IS 2008-2016 / OOS 2017-2026."""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from importlib import import_module
from rb_data import etf_close
s1 = import_module("01_screen")
X, B, r = s1.premia()
px = etf_close(["SHY", "IEF", "TLT", "LQD", "HYG", "AGG"])
R = pd.concat([r[["MUB", "TFI", "SHM", "ITM", "HYD"]], px.pct_change(),
               X.add_suffix("_h")], axis=1).loc["2008":]
idx = R.index
s = pd.Series(np.arange(len(idx)), index=idx); per = idx.to_period("M")
fwd = s - s.groupby(per).transform("min") + 1
bwd = s - s.groupby(per).transform("max") - 1
buckets = {f"d{k}": fwd == k for k in (1, 2, 3, 4, 5)}
buckets["last3"] = bwd >= -3
buckets["rest"] = (fwd > 5) & (bwd < -3)
rows = []
for sp, (a, b) in {"IS": ("2008", "2016"), "OOS": ("2017", "2026")}.items():
    for c in R.columns:
        for k, m in buckets.items():
            x = R[c].loc[a:b][m.loc[a:b].values].dropna()
            rows.append(dict(inst=c, split=sp, bucket=k, bp=x.mean() * 1e4, t=x.mean() / x.std() * np.sqrt(len(x))))
t = pd.DataFrame(rows)
p = t.pivot_table(index="inst", columns=["split", "bucket"], values="bp").round(1)
q = t.pivot_table(index="inst", columns=["split", "bucket"], values="t").round(1)
order = [(sp, k) for sp in ("IS", "OOS") for k in buckets]
print("bp/day"); print(p[order].to_string())
print("\nt-stat"); print(q[order].to_string())
