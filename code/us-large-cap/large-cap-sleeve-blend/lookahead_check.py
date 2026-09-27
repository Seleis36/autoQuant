"""Truncation test for the blend: recompute the weights with every input cut at date d and
compare the weights ON d with the full-sample weights. Mid-month and month-end dates.

Two inputs are rebuilt the way a live run on date d would have seen them:
  * prices: the cache is split- and dividend-adjusted to its LAST date; a download on d is
    adjusted to d. Dividing each ticker by its dividend factor at d and multiplying by the split
    ratios after d (constants per ticker, returns unchanged) reproduces that, so the market-cap
    reconstruction in QVC sees the prices a live run on d would have seen;
  * the fundamentals / filing-text / changes tables are cut at filing (or effective) date <= d.
Any remaining |dw| means the signal reads the future."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import strategy as B
from xbrl import Fundamentals

X = B.panel_inputs()
F_full = Fundamentals()
divF = F_full.div_factor(X["close"])
S_txt = pd.read_parquet(B._txt.SIM)
CH = B._rec.load_changes()
full, parts = B.blend_weights(X, return_sleeves=True)
rows = []
for d in ["2015-07-15", "2019-03-29", "2020-12-22", "2021-11-10", "2024-08-30", "2026-08-19", "2026-09-10"]:
    d = X["close"].index[X["close"].index.get_indexer([pd.Timestamp(d)], method="ffill")[0]]
    sf = F_full.split_factor_after(pd.DatetimeIndex([d]), list(X["close"].columns)).iloc[0]
    Xt = {"close": X["close"].loc[:d] / divF.loc[d] * sf, "member": X["member"].loc[:d], "sector": X["sector"],
          "rsp": X["rsp"].loc[:d]}
    Ft = Fundamentals(); Ft.facts = Ft.facts[Ft.facts.filed <= d]
    act = Ft.actions[Ft.actions.date <= d].copy()          # Yahoo dividends are on TODAY's share basis:
    act["dividend"] = act.dividend * act.ticker.map(sf).fillna(1.0).values   # on d's basis they are x later splits
    Ft.actions = act
    Wt = {"RM": B._rm.residual_momentum_weights(Xt).loc["2011-01-01":],
          "QVC": B._qvc.qvc_weights(Xt, F=Ft),
          "TXT": B._txt.text_weights(Xt, sim=S_txt[S_txt.filing_date <= d]),
          "REC": B._rec.recon_weights(Xt, changes=CH[CH.eff <= d + pd.Timedelta(days=10)])}
    for k in Wt:
        a = parts[k].loc[d].reindex(Wt[k].columns).fillna(0.0); b = Wt[k].loc[d]
        rows.append({"date": d.date(), "sleeve": k, "max_abs_dw": float((a - b).abs().max()), "gross": float(b.abs().sum())})
out = pd.DataFrame(rows)
print(out.to_string(index=False))
out.to_csv(os.path.join(HERE, "lookahead_check_out.csv"), index=False)
