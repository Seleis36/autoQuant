"""Step 3: single factors and pre-registered composite (carry+mom+hp+skew), monthly XS long/short."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from factors import *
from research_lib import backtest_xs, quantile_weights, linear_weights, fmt, split_stats

fut, etf = load_panel()
mask = etf.notna() & fut.notna() & etf.shift(260).notna()
f = build(fut, etf, mask)
f["COMPOSITE(c+m+hp+sk)"] = (f["carry"] + f["mom"] + f["hp"] + f["skew"]) / 4
f["c+m"] = (f["carry"] + f["mom"]) / 2

def monthly(w):
    me = w.index.to_series().groupby(w.index.to_period("M")).transform("max") == w.index
    return w.where(me).ffill().fillna(0)

SPL = {"IS": ("2011-01-01", "2018-12-31"), "OOS": ("2019-01-01", "2026-12-31")}
rows = []
for name, s in f.items():
    for kind in ["q", "lin"]:
        w = quantile_weights(s, mask, q=0.375) if kind == "q" else linear_weights(s, mask)
        net, st = backtest_xs(monthly(w), etf, 10, ANN, name)
        ss = split_stats(net.loc["2011":], SPL, ann=ANN)
        rows.append(pd.Series({"Sharpe": st.Sharpe, "CAGR": st.CAGR, "MaxDD": st.MaxDD,
                               "SR_IS": ss.loc["IS", "Sharpe"], "SR_OOS": ss.loc["OOS", "Sharpe"],
                               "Turn": st.Turnover_ann}, name=f"{name} [{kind}]"))
print(fmt(pd.DataFrame(rows)).to_string())
print(pd.DataFrame({k: v.stack() for k, v in f.items() if "+" not in k}).corr().round(2))
