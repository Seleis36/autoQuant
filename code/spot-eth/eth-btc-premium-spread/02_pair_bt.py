"""eth-btc-premium-spread 02: costed dollar-neutral ETH/BTC pair driven by the premium spread
s = z_e - z_b with a symmetric hysteresis (long ETH/short BTC after s > +a, flat after s < +b, and
mirror for shorts). Hourly, 10 bp per side per leg, vol-targeted 20% on the ratio, sim book."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "eth-venue-premium"))
import numpy as np, pandas as pd
from ethdata import rl, bars, row, to_daily
from fetch_coinbase import load as cb_load
be = bars("ETHUSDT", "1h")["Close"]; bb = bars("BTCUSDT", "1h")["Close"].reindex(be.index).ffill()
ce = cb_load("ETH-USD")["Close"].reindex(be.index); cbb = cb_load("BTC-USD")["Close"].reindex(be.index)
z = lambda p, w=720: (p - p.rolling(w, min_periods=w // 2).mean()) / p.rolling(w, min_periods=w // 2).std()
s = (z(ce / be - 1) - z(cbb / bb - 1))
lr = np.log(be / bb); sc = (0.2 / (lr.diff().ewm(halflife=480).std() * np.sqrt(8760))).clip(upper=1).fillna(0)
px = pd.DataFrame({"ETH": be, "BTC": bb})
def hyst(x, a, b):
    out = np.zeros(len(x)); st = 0.0
    for i, v in enumerate(x.to_numpy(float)):
        if not np.isnan(v):
            if st == 0 and v > a: st = 1.0
            elif st == 0 and v < -a: st = -1.0
            elif st == 1 and v < b: st = 0.0
            elif st == -1 and v > -b: st = 0.0
        out[i] = st
    return pd.Series(out, index=x.index)
rows = []
for a in [1.0, 1.5, 2.0, 3.0]:
    for b in [0.0, 0.5]:
        pos = hyst(s, a, b) * sc
        net, st = rl.backtest_xs(pd.DataFrame({"ETH": pos, "BTC": -pos}), px, cost_bps=10, ann=8760)
        rows.append(row(to_daily(net).loc["2017-10-01":], ann=365, extra=dict(enter=a, exit=b, Turn=st["Turnover_ann"])))
        g, _ = rl.backtest_xs(pd.DataFrame({"ETH": pos, "BTC": -pos}), px, cost_bps=0, ann=8760)
        rows[-1]["gross_Sh_Full"] = rl.perf_stats(to_daily(g).loc["2017-10-01":], ann=365)["Sharpe"]
pd.set_option("display.width", 200)
print(pd.DataFrame(rows)[["enter", "exit", "gross_Sh_Full", "Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Turn"]].round(2).to_string(index=False))
