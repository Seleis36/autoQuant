"""upshock-continuation 02: selection-free ensemble, gating, vol scaling, and combination
with the live eth-trend-filter.

E = mean over the full 45-cell grid (k in {1,2,4,8,12}, Z in {2,2.5,3}, H in {12,24,48}) of the
hold indicators -> a weight in [0,1] that grows with the number/recency of up-shocks.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import rl
from ethdata import bars, bt, row, to_daily, trend_filter_weights_daily

h = bars("ETHUSDT", "1h"); c = h["Close"]
lr = np.log(c).diff(); sig = lr.ewm(halflife=168, min_periods=168).std()
sma40d = c.rolling(960, min_periods=960).mean()
up = (c > sma40d).astype(float)


def hold_weights(ev, H):
    ev = ev.fillna(False).astype(int)
    grp = ev.cumsum(); since = ev.groupby(grp).cumcount()
    return ((grp > 0) & (since < H)).astype(float)


cells = []
for k in [1, 2, 4, 8, 12]:
    z = np.log(c / c.shift(k)) / (sig.shift(k) * np.sqrt(k))
    for Z in [2.0, 2.5, 3.0]:
        for H in [12, 24, 48]:
            cells.append(hold_weights(z > Z, H))
E = pd.concat(cells, axis=1).mean(axis=1)
E_any = (pd.concat(cells, axis=1).max(axis=1))

# vol scalar on hourly returns, annualised with 8760 (target 0.5 like the trend filter)
vs = rl.vol_target_scalar(c.pct_change(), target=0.5, halflife=24 * 20, cap=1.0, ann=24 * 365)

d = c.resample("1D").last()
w_tf = trend_filter_weights_daily(d).shift(1, freq="D").reindex(c.index, method="ffill").fillna(0)

variants = {
    "trend_filter (live)": w_tf,
    "E (mean of 45)": E,
    "E_any (in any cell)": E_any,
    "E x vs": E * vs,
    "E_any x vs": E_any * vs,
    "E x uptrend": E * up,
    "E_any x uptrend x vs": E_any * up * vs,
    "E scaled to max 1 (E/E.q99)": (E / E.quantile(0.99)).clip(upper=1),
    "max(w_tf, E_any x vs)": np.maximum(w_tf, E_any * vs),
    "min(1, w_tf + E x vs)": (w_tf + E * vs).clip(upper=1),
    "w_tf x (1 + E) capped 1": (w_tf * (1 + E)).clip(upper=1),
    "0.5 w_tf + 0.5 E_any x vs": 0.5 * w_tf + 0.5 * E_any * vs,
}
rows, nets = [], {}
for name, w in variants.items():
    net, s = bt(w, c)
    nets[name] = net
    rows.append(row(to_daily(net), ann=365, extra=dict(
        v=name, AvgExp=s["AvgExposure"], TIM=s["TimeInMkt"], Turn=s["Turnover_ann"])))
df = pd.DataFrame(rows).set_index("v")
base = nets["trend_filter (live)"]
df["rho_tf"] = [np.corrcoef(nets[n], base)[0, 1] for n in df.index]
pd.set_option("display.width", 250)
print(df[["Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "AvgExp", "TIM", "Turn", "rho_tf"]].round(2).to_string())

# yearly Sharpe for the key variants
print()
yr = {}
for n in ["trend_filter (live)", "E_any x vs", "max(w_tf, E_any x vs)", "0.5 w_tf + 0.5 E_any x vs"]:
    nd = to_daily(nets[n])
    yr[n] = nd.groupby(nd.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(365))
print(pd.DataFrame(yr).round(2).to_string())
