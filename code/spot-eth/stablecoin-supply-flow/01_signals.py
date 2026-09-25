"""stablecoin-supply-flow 01: does stablecoin net issuance predict spot ETH?

Supply S = USDT + USDC + BUSD + DAI circulating (CoinMetrics SplyCur, stamped at the day it covers).
Timing: ETH daily bar D = Binance [D, D+1), close at D+1 00:00 UTC; the weight set at that close
uses supply stamped D-1 (one extra day of lag: always published by then).

Signals (all lagged as above):
  g_n   = log(S_t / S_{t-n}), n in {1, 7, 14, 30, 60}
  gz_n  = (g_n - rolling-365d mean) / rolling-365d std   (growth relative to its own recent norm)
  ssr   = log(ETH mcap / S)  -> z over 365d (stablecoin supply ratio: low = dry powder)
Tests: predictive IC vs forward 1/7/30d ETH returns (IS/OOS), and long/flat strategies.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import rl, bars, row, trend_filter_weights_daily, IS_END, OOS_START
from coinmetrics import load

eth = bars("ETHUSDT", "1h").resample("1D").agg({"Close": "last"})["Close"].dropna()
S = sum(load(a, ["SplyCur"])["SplyCur"].fillna(0) for a in ["usdt", "usdc", "busd", "dai"])
S = S.reindex(eth.index).ffill().shift(1)            # value stamped D-1 used at bar D's close
mcap = load("eth", ["CapMrktCurUSD"])["CapMrktCurUSD"].reindex(eth.index).ffill().shift(1)

sigs = {}
for n in [1, 7, 14, 30, 60]:
    g = np.log(S / S.shift(n))
    sigs[f"g{n}"] = g
    sigs[f"gz{n}"] = (g - g.rolling(365, min_periods=180).mean()) / g.rolling(365, min_periods=180).std()
ssr = np.log(mcap / S)
sigs["ssr_z"] = -(ssr - ssr.rolling(365, min_periods=180).mean()) / ssr.rolling(365, min_periods=180).std()
sigs = pd.DataFrame(sigs)

r = eth.pct_change()
rows = []
for hzn in [1, 7, 30]:
    fwd = np.log(eth.shift(-hzn) / eth)
    for s in sigs:
        rr = dict(sig=s, h=hzn)
        for part, (a, b) in {"IS": ("2018-06-01", IS_END), "OOS": (OOS_START, None)}.items():
            x = pd.concat([sigs[s], fwd], axis=1).loc[a:b].dropna()
            rr[f"IC_{part}"] = x.iloc[:, 0].corr(x.iloc[:, 1], method="spearman")
        rows.append(rr)
ic = pd.DataFrame(rows).round(3)
pd.set_option("display.width", 200, "display.max_rows", 200)
print(ic.pivot(index="sig", columns="h", values=["IC_IS", "IC_OOS"]).to_string())

# long/flat strategies: long when signal > threshold, sized by the trend-filter vol scalar
vs = rl.vol_target_scalar(r, target=0.5, halflife=20, cap=1.0)
w_tf = trend_filter_weights_daily(eth)
net_tf, _ = rl.backtest(w_tf, eth, cost_bps=10)
print("\ntrend filter:", {k: round(float(v), 2) for k, v in row(net_tf.loc["2018-06-01":], ann=365).items()})
net_bh, _ = rl.backtest(vs, eth, cost_bps=10)
print("vol-scaled B&H:", {k: round(float(v), 2) for k, v in row(net_bh.loc["2018-06-01":], ann=365).items()})
out = []
for s in sigs:
    for thr in ([0.0] if s.startswith("g") and not s.startswith("gz") else [-0.5, 0.0, 0.5]):
        gate = (sigs[s] > thr).astype(float)
        for sized in ["vs", "vs x trend"]:
            w = gate * vs if sized == "vs" else gate * w_tf
            net, st = rl.backtest(w, eth, cost_bps=10)
            net = net.loc["2018-06-01":]
            out.append(row(net, ann=365, extra=dict(sig=s, thr=thr, sized=sized, TIM=st["TimeInMkt"],
                                                     Turn=st["Turnover_ann"], rho_tf=net.corr(net_tf.loc["2018-06-01":]))))
df = pd.DataFrame(out)
print(df[["sig", "thr", "sized", "Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "TIM", "Turn", "rho_tf"]]
      .round(2).sort_values("Sh_Full", ascending=False).to_string(index=False))
df.to_csv(os.path.join(os.path.dirname(__file__), "01_signals.csv"), index=False)
