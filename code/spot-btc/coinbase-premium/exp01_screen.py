"""exp01 -- single-feature screen of the exogenous-flow panel.

Protocol fixed BEFORE running:
  * IS  = rows <= 2022-12-31 ; OOS = rows >= 2023-01-01. Never re-picked.
  * Selection statistic is IS-only: rank-IC of feature vs next-day return, NW t-stat of the
    quintile long-short spread. OOS columns are shown for information; a feature is a
    'survivor' if |t_IS| >= 2.0 AND the OOS spread has the same sign.
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared"))
from research_lib import newey_west_t, ANN
from features import build_panel

IS_END, OOS_START = "2022-12-31", "2023-01-01"
panel = build_panel()
panel.to_parquet(os.path.join(HERE, "panel.parquet"))
feats = [c for c in panel.columns if c not in ("close", "ret", "ret_fwd", "cb_close")]

def qspread(x, y):
    """Return (Q5-Q1 mean spread in bp, Sharpe of the spread-day series, NW t, IC)."""
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(df) < 200:
        return np.nan, np.nan, np.nan, np.nan, len(df)
    q = pd.qcut(df["x"].rank(method="first"), 5, labels=False)
    top, bot = df["y"][q == 4], df["y"][q == 0]
    # long-top / short-bottom daily series (each day belongs to one quintile) -> sign-weighted
    s = pd.Series(0.0, index=df.index); s[q == 4] = df["y"][q == 4]; s[q == 0] = -df["y"][q == 0]
    ic = df["x"].corr(df["y"], method="spearman")
    return (top.mean() - bot.mean()) * 1e4, s.mean() / s.std() * np.sqrt(ANN), newey_west_t(s.values, 10), ic, len(df)

rows = []
for f in feats:
    a = panel.loc[:IS_END]; b = panel.loc[OOS_START:]
    sp_is, sh_is, t_is, ic_is, n_is = qspread(a[f], a["ret_fwd"])
    sp_os, sh_os, t_os, ic_os, n_os = qspread(b[f], b["ret_fwd"])
    rows.append(dict(feature=f, n_is=n_is, spread_is=sp_is, sh_is=sh_is, t_is=t_is, ic_is=ic_is,
                     n_os=n_os, spread_os=sp_os, sh_os=sh_os, t_os=t_os, ic_os=ic_os))
res = pd.DataFrame(rows).set_index("feature")
res["survivor"] = (res["t_is"].abs() >= 2.0) & (np.sign(res["spread_is"]) == np.sign(res["spread_os"]))
res = res.sort_values("t_is", key=lambda s: -s.abs())
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 200)
print(res.round(3).to_string())
res.to_csv(os.path.join(HERE, "exp01_screen.csv"))
print("\nSURVIVORS:", list(res.index[res["survivor"]]))
