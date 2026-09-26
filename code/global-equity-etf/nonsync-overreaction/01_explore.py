"""Exploratory: does a country ETF's next-day return (hedged on SPY) load on today's SPY move?
Levy & Lieberman (2013): during non-synchronous hours country ETFs over-react to the S&P 500.
If so, r_{i,t+1} - b_i r_SPY,t+1 should load NEGATIVELY on r_SPY,t for Asian ETFs, less so for
Europe and not at all for the synchronous Americas (EWC, EWZ) -- a built-in control group."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data as D
import statsmodels.api as sm

C = D.load_panel(D.UNIVERSE, "Close", start="2003-01-01")
O = D.load_panel(D.UNIVERSE, "Open", start="2003-01-01")
r = C.pct_change()
roc = C / O - 1                    # US-session (intraday) return
rco = O / C.shift() - 1            # overnight gap (contains the local session for Asia)
spy = r["SPY"]
rows = []
for t in [c for c in D.UNIVERSE if c != "SPY"]:
    for per, (a, b) in {"IS": ("2003", "2012"), "OOS": ("2013", "2026")}.items():
        df = pd.DataFrame({"y": r[t].shift(-1), "spy_next": spy.shift(-1), "spy": spy,
                           "spy_oc": roc["SPY"], "own_oc": roc[t], "own_co": rco[t]}).loc[a:b].dropna()
        # hedged next-day return: beta on contemporaneous SPY estimated within the window
        X = sm.add_constant(df[["spy_next", "spy"]])
        m = sm.OLS(df["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
        X2 = sm.add_constant(df[["spy_next", "spy_oc", "own_oc", "own_co"]])
        m2 = sm.OLS(df["y"], X2).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
        rows.append({"etf": t, "sess": D.SESSION.get(t), "per": per, "n": len(df),
                     "beta_next": m.params["spy_next"], "b_spy_lag": m.params["spy"], "t": m.tvalues["spy"],
                     "b_spyoc": m2.params["spy_oc"], "t_spyoc": m2.tvalues["spy_oc"],
                     "b_ownoc": m2.params["own_oc"], "t_ownoc": m2.tvalues["own_oc"],
                     "b_ownco": m2.params["own_co"], "t_ownco": m2.tvalues["own_co"]})
out = pd.DataFrame(rows).set_index(["etf", "per"]).round(3)
print(out.to_string())
