"""Data quality + baseline term-structure rules on VIXY/SVXY/UVXY (2011-2026)."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import research_lib as rl
ANN = 252
END = "2026-09-11"

def load(t):
    return rl.load_series(t).loc[:END]

vix, v3m, v9d, vvix = [load(t)["Close"] for t in ["^VIX", "^VIX3M", "^VIX9D", "^VVIX"]]
etp = {t: load(t)["Close"] for t in ["VIXY", "SVXY", "UVXY", "VXX", "SPY"]}
px = pd.DataFrame(etp)
print(px.describe().T[["count", "min", "max"]])
r = px.pct_change()
print("\nBiggest VIXY daily moves:\n", r["VIXY"].abs().nlargest(8))
print("\n2018-02-02..07:\n", r.loc["2018-02-02":"2018-02-07"].round(3))
print("\nSVXY/UVXY split checks (ratio SVXY ret vs VIXY ret) pre/post 2018-02-28:")
for a, b in [("2012", "2018-02-26"), ("2018-03-01", "2026")]:
    s = r.loc[a:b]
    print(a, b, "SVXY beta", round(np.polyfit(s.VIXY.dropna(), s.SVXY.dropna(), 1)[0], 3),
          "UVXY beta", round(np.polyfit(s.VIXY.dropna(), s.UVXY.dropna(), 1)[0], 3))

# ---------- baselines on VIXY (long/short), 5bp per side
idx = px["VIXY"].dropna().index
V = vix.reindex(idx).ffill(); V3 = v3m.reindex(idx).ffill()
ratio = V3 / V
rows = {}
def run(w, name, cost=5):
    net, st = rl.backtest(w, px["VIXY"].reindex(idx), cost_bps=cost, ann=ANN, name=name)
    rows[name] = st
    return net
run(pd.Series(-1.0, idx), "short VIXY always")
run(pd.Series(1.0, idx), "long VIXY always")
run(-np.sign(ratio - 1.0), "contango(VIX3M/VIX>1): -1/+1")
run(-(ratio > 1.0).astype(float), "contango: -1/0")
run(-np.sign(ratio - 1.0) * 0.5, "contango: -0.5/+0.5")
for th in [0.95, 1.0, 1.05, 1.1]:
    run(-(ratio > th).astype(float), f"short if ratio>{th}")
# VRP: VIX - realized vol (10d)
spyr = px["SPY"].reindex(idx).pct_change()
rv10 = spyr.rolling(10).std() * np.sqrt(252) * 100
vrp = V - rv10
run(-np.sign(vrp), "VRP sign(VIX-RV10): -1/+1")
run(-((vrp > 0) & (ratio > 1)).astype(float) + ((vrp < 0) & (ratio < 1)).astype(float), "VRP & contango agree")
print("\n", rl.fmt(pd.DataFrame(rows).T)[["Sharpe", "CAGR", "MaxDD", "Vol", "Turnover_ann", "AvgExposure", "t_NW", "Skew"]])
# Split
w = -np.sign(ratio - 1.0)
net, _ = rl.backtest(w, px["VIXY"].reindex(idx), cost_bps=5, ann=ANN)
print("\ncontango -1/+1 by year:\n", net.groupby(net.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(252)).round(2).to_string())
