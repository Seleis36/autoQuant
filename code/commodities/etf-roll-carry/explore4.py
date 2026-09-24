"""Step 4: where does carry P&L come from (per-asset contribution, static-tilt control), and does
inverse-vol weighting + portfolio vol targeting help?"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from factors import *
from research_lib import backtest_xs, quantile_weights, fmt, split_stats, perf_stats

fut, etf = load_panel()
mask = etf.notna() & fut.notna() & etf.shift(260).notna()
f = build(fut, etf, mask)
r = etf.pct_change()
vol = r.ewm(halflife=40, min_periods=40).std() * np.sqrt(ANN)

def monthly(w):
    me = w.index.to_series().groupby(w.index.to_period("M")).transform("max") == w.index
    return w.where(me).ffill().fillna(0)

def ivol(w):
    """Keep sign/leg membership, weight each name by 1/vol, each leg gross 0.5."""
    x = (np.sign(w) / vol).where(w != 0).fillna(0)
    L = x.clip(lower=0); S = x.clip(upper=0)
    return (L.div(L.sum(1).replace(0, np.nan), axis=0) * 0.5 - S.div(S.sum(1).replace(0, np.nan), axis=0) * 0.5).fillna(0)

def voltarget(w, target=0.10, hl=40, cap=3.0):
    """Scale the whole book to a target vol using the book's trailing realised vol (past only)."""
    pr = (w.shift(1) * r.fillna(0)).sum(1)
    pv = pr.ewm(halflife=hl, min_periods=60).std() * np.sqrt(ANN)
    return w.mul((target / pv).clip(upper=cap).fillna(0), axis=0)

SPL = {"IS": ("2011-01-01", "2018-12-31"), "OOS": ("2019-01-01", "2026-12-31")}
def row(name, w):
    net, st = backtest_xs(w, etf, 10, ANN, name)
    ss = split_stats(net.loc["2011":], SPL, ann=ANN)
    return pd.Series({"Sharpe": st.Sharpe, "CAGR": st.CAGR, "Vol": st.Vol, "MaxDD": st.MaxDD,
                      "SR_IS": ss.loc["IS", "Sharpe"], "SR_OOS": ss.loc["OOS", "Sharpe"],
                      "Turn": st.Turnover_ann, "Gross": st.AvgGross}, name=name), net

w_c = monthly(quantile_weights(f["carry"], mask, q=0.375))
print("carry [q]: avg weight per asset and P&L contribution (ann %):")
contrib = (w_c.shift(1) * r).mean() * ANN * 100
print(pd.DataFrame({"avg_w": w_c.mean().round(2), "pct_long": (w_c > 0).mean().round(2),
                    "pct_short": (w_c < 0).mean().round(2), "contrib%": contrib.round(2)}).to_string())

# static control: expanding-mean carry rank (slow, knows only the past) -> a near-static tilt
rows = []
rows.append(row("carry q", w_c)[0])
stat = f["carry"].expanding(252).mean()
rows.append(row("carry expanding-mean (static tilt)", monthly(quantile_weights(stat, mask, q=0.375)))[0])
dev = f["carry"] - stat
rows.append(row("carry minus own mean (timing only)", monthly(quantile_weights(dev, mask, q=0.375)))[0])
comp = (f["carry"] + f["mom"] + f["hp"] + f["skew"]) / 4
for nm, s in [("carry", f["carry"]), ("c+m", (f["carry"] + f["mom"]) / 2), ("composite4", comp),
              ("carry+skew", (f["carry"] + f["skew"]) / 2), ("carry+spec", (f["carry"] + f["spec"]) / 2)]:
    w = monthly(ivol(quantile_weights(s, mask, q=0.375)))
    rows.append(row(f"{nm} ivol", w)[0])
    rows.append(row(f"{nm} ivol+VT10", voltarget(w))[0])
print(fmt(pd.DataFrame(rows)).to_string())
