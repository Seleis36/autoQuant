"""eth-btc-relative-momentum 01: time-series momentum on the ETH/BTC ratio, traded as a
dollar-neutral pair (long ETH / short BTC when the ratio trends up, the reverse when down).

Daily Binance closes at 00:00 UTC (bar D = [D, D+1)). Weight known at the close of D, applied to
D+1 (research_lib.backtest_xs shifts). 10 bp per side on each leg's |dw|.
Pair sized to a 20% annual vol target on the ratio (EWM halflife 20d), gross capped at 2 (1 per leg).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import rl, bars, row, trend_filter_weights_daily, IS_END, OOS_START

e = bars("ETHUSDT", "1h").resample("1D")["Close"].last()
b = bars("BTCUSDT", "1h").resample("1D")["Close"].last()
px = pd.concat({"ETH": e, "BTC": b}, axis=1).dropna()
lr_ratio = np.log(px.ETH / px.BTC)
rr = lr_ratio.diff()
vol_r = rr.ewm(halflife=20, min_periods=20).std() * np.sqrt(365)
scale = (0.20 / vol_r).clip(upper=1.0).fillna(0)

tf_w = trend_filter_weights_daily(px.ETH)
tf, _ = rl.backtest(tf_w, px.ETH, cost_bps=10)


def pair_bt(s, name):
    """s: signed pair exposure in [-1, 1] (per leg)."""
    W = pd.DataFrame({"ETH": s, "BTC": -s})
    net, st = rl.backtest_xs(W, px, cost_bps=10, ann=365, name=name)
    return net, st


rows, nets = [], {}
sigs = {}
for L in [3, 7, 14, 30, 60, 90, 120, 180]:
    sigs[f"sign{L}"] = np.sign(lr_ratio - lr_ratio.shift(L))
for f_, s_ in [(4, 16), (8, 32), (16, 64), (32, 128)]:
    m = lr_ratio.ewm(halflife=f_).mean() - lr_ratio.ewm(halflife=s_).mean()
    sigs[f"macd{f_}/{s_}"] = np.tanh(m / (rr.rolling(63).std() * np.sqrt(s_)))
sigs["ens_sign_7-180"] = pd.concat([sigs[f"sign{L}"] for L in [7, 14, 30, 60, 90, 120, 180]], axis=1).mean(axis=1)
sigs["ens_macd"] = pd.concat([sigs[k] for k in sigs if k.startswith("macd")], axis=1).mean(axis=1)
sigs["ens_sign_30-180"] = pd.concat([sigs[f"sign{L}"] for L in [30, 60, 90, 120, 180]], axis=1).mean(axis=1)
sigs["ens_sign_3-14"] = pd.concat([sigs[f"sign{L}"] for L in [3, 7, 14]], axis=1).mean(axis=1)

for k, s in sigs.items():
    for sized in ["raw", "vt20"]:
        pos = s.fillna(0) * (scale if sized == "vt20" else 1.0)
        net, st = pair_bt(pos, k)
        net = net.loc["2017-12-01":]
        nets[(k, sized)] = net
        rows.append(row(net, ann=365, extra=dict(sig=k, sized=sized, Turn=st["Turnover_ann"],
                                                  gross=st["AvgGross"], rho_tf=net.corr(tf.loc[net.index]),
                                                  rho_eth=net.corr(px.ETH.pct_change().loc[net.index]))))
df = pd.DataFrame(rows)
pd.set_option("display.width", 220, "display.max_rows", 100)
print(df[["sig", "sized", "Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Vol", "Turn", "gross", "rho_tf", "rho_eth"]]
      .round(2).to_string(index=False))
print("median by sizing:", df.groupby("sized")[["Sh_Full", "Sh_IS", "Sh_OOS"]].median().round(2).to_dict())
df.to_csv(os.path.join(os.path.dirname(__file__), "01_ratio_tsmom.csv"), index=False)

# yearly for the ensemble
n = nets[("ens_sign_7-180", "vt20")]
print(n.groupby(n.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(365)).round(2).to_dict())
# ratio buy&hold reference
print("ratio drift (ETH/BTC log) per year:", lr_ratio.resample("YE").last().diff().round(2).to_dict())
