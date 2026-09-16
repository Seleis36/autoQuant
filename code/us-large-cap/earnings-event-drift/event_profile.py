"""Event-time profile of sector-residual returns around earnings, k in [-45,+45] trading bars."""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
from panel import load_panel
from xs_lib import *
from earnings import load_earnings, reaction_day_matrix

P = load_panel()
C, M = P["close"], P["member"]
sec = P["sector"].fillna("UNK")
ret = C.pct_change()
mask = M & C.notna()
E = load_earnings()
R = reaction_day_matrix(E, C.index, C.columns) & mask
res = group_demean(ret, sec, mask).where(mask)
rows = []
for k in range(-45, 46):
    x = res.shift(-k).where(R).stack().dropna()
    xi = x[x.index.get_level_values(0) < "2018-01-01"]; xo = x[x.index.get_level_values(0) >= "2018-01-01"]
    rows.append({"k": k, "mean_bp": x.mean() * 1e4, "t": x.mean() / x.std() * np.sqrt(len(x)), "IS_bp": xi.mean() * 1e4, "OOS_bp": xo.mean() * 1e4, "N": len(x)})
df = pd.DataFrame(rows).set_index("k")
df["cum_bp"] = df.mean_bp.cumsum(); df["cumIS"] = df.IS_bp.cumsum(); df["cumOOS"] = df.OOS_bp.cumsum()
pd.set_option("display.width", 200)
print(df.round(1).to_string())
df.to_csv(os.path.join(HERE, "event_profile.csv"))
# bucketed
for a, b in [(-45, -31), (-30, -21), (-20, -11), (-10, -6), (-5, -1), (0, 1), (2, 5), (6, 10), (11, 20), (21, 30), (31, 45)]:
    seg = df.loc[a:b]
    print(f"[{a:+d},{b:+d}] sum {seg.mean_bp.sum():+6.1f}bp IS {seg.IS_bp.sum():+6.1f} OOS {seg.OOS_bp.sum():+6.1f}  per-day t~{seg.t.mean():.1f}")
