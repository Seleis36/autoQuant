"""Step 1: does trailing roll yield (=F return minus ETF return) predict ETF returns cross-sectionally?"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import numpy as np, pandas as pd
from panel import load_panel
from research_lib import backtest_xs, quantile_weights, fmt, split_stats

ANN = 252
fut, etf = load_panel()
lf, le = np.log(fut.clip(lower=0.01)), np.log(etf)
retE = etf.pct_change()

def carry(k):
    return ((lf - lf.shift(k)) - (le - le.shift(k))) * ANN / k

c = carry(252)
print("mean annual roll yield (252d proxy), full sample:")
print((c.mean()).round(3).to_string())

def monthly(w):
    """Hold weights fixed between month-end rebalances."""
    me = w.index.to_series().groupby(w.index.to_period("M")).transform("max") == w.index
    return w.where(me).ffill()

mask = etf.notna() & fut.notna() & etf.shift(252).notna()
SPL = {"IS 2011-2018": ("2011-01-01", "2018-12-31"), "OOS 2019-2026": ("2019-01-01", "2026-12-31")}
rows = {}
ew = mask.astype(float).div(mask.sum(axis=1), axis=0).fillna(0)
rows["EW long ETFs"] = backtest_xs(ew, etf, 10, ANN, "ew")
for k in [21, 63, 126, 252]:
    s = carry(k)
    for q in [0.25, 0.375]:
        for reb in ["D", "M"]:
            w = quantile_weights(s, mask, q=q, gross=1.0)
            if reb == "M": w = monthly(w)
            rows[f"carry k={k} q={q} {reb}"] = backtest_xs(w, etf, 10, ANN, f"c{k}")
    # momentum on ETF (tradable) returns for comparison
    m = le - le.shift(k)
    w = monthly(quantile_weights(m, mask, q=0.375, gross=1.0))
    rows[f"xs-mom k={k} M"] = backtest_xs(w, etf, 10, ANN, f"m{k}")

tab = []
for name, (net, st) in rows.items():
    ss = split_stats(net.loc["2011":], SPL, ann=ANN)
    tab.append(pd.Series({"Sharpe": st.Sharpe, "CAGR": st.CAGR, "MaxDD": st.MaxDD,
                          "SR_IS": ss.loc["IS 2011-2018", "Sharpe"], "SR_OOS": ss.loc["OOS 2019-2026", "Sharpe"],
                          "Turn": st.Turnover_ann}, name=name))
print(fmt(pd.DataFrame(tab)).to_string())
