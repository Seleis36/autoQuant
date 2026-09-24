"""Step 2: correct sign (carry = ETF return - =F return, >0 in backwardation), skip-gap test
to separate true roll yield from end-point ETF/futures basis noise, XS vs TS, vol scaling."""
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
vol = retE.ewm(halflife=40, min_periods=40).std() * np.sqrt(ANN)

def carry(k, s=0):
    c = ((le - le.shift(k)) - (lf - lf.shift(k))) * ANN / k
    return c.shift(s)

def monthly(w):
    me = w.index.to_series().groupby(w.index.to_period("M")).transform("max") == w.index
    return w.where(me).ffill()

mask = etf.notna() & fut.notna() & etf.shift(260).notna() & vol.notna()
SPL = {"IS": ("2011-01-01", "2018-12-31"), "OOS": ("2019-01-01", "2026-12-31")}

def row(name, w, cost=10):
    net, st = backtest_xs(w, etf, cost, ANN, name)
    ss = split_stats(net.loc["2011":], SPL, ann=ANN)
    return pd.Series({"Sharpe": st.Sharpe, "CAGR": st.CAGR, "MaxDD": st.MaxDD, "SR_IS": ss.loc["IS", "Sharpe"],
                      "SR_OOS": ss.loc["OOS", "Sharpe"], "Turn": st.Turnover_ann, "Gross": st.AvgGross,
                      "Net": st.AvgNet}, name=name)

rows = []
for k in [21, 63, 126, 252]:
    for s in [0, 1, 5, 21]:
        c = carry(k, s)
        rows.append(row(f"XS k={k} skip={s} D", quantile_weights(c, mask, q=0.375)))
        rows.append(row(f"XS k={k} skip={s} M", monthly(quantile_weights(c, mask, q=0.375))))
        # time-series: sign of carry, inverse-vol, 10% vol per asset / n
        n = mask.sum(axis=1)
        ts = np.sign(c).where(mask) * (0.10 / vol) / np.sqrt(n.values[:, None]).clip(1)
        rows.append(row(f"TS k={k} skip={s} M", monthly(ts.fillna(0))))
print(fmt(pd.DataFrame(rows)).to_string())
