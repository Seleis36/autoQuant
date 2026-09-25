"""exchange-netflow 01: do ETH exchange flows (CoinMetrics community) predict spot ETH?

Hypothesis: coins moving onto exchanges are about to be sold (distribution); coins leaving are
being accumulated / staked. Bullish = net OUTflow.
Timing: value stamped D-1 used for the weight set at the D+1 00:00 close of bar D (as in the
stablecoin study). PIT caveat: CoinMetrics re-tags exchange addresses, so today's vintage of these
series is not what was knowable at the time; any positive result is an upper bound.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import rl, bars, row, trend_filter_weights_daily, IS_END, OOS_START
from coinmetrics import load

eth = bars("ETHUSDT", "1h").resample("1D").agg({"Close": "last"})["Close"].dropna()
m = load("eth").reindex(eth.index).shift(1)
inflow, outflow, sply, spx = m.FlowInExNtv, m.FlowOutExNtv, m.SplyCur, m.SplyExNtv


def z365(x):
    return (x - x.rolling(365, min_periods=180).mean()) / x.rolling(365, min_periods=180).std()


sigs = {}
for n in [1, 3, 7, 14, 30]:
    nf = (inflow - outflow).rolling(n).sum() / sply * 1e4       # bp of supply
    sigs[f"-nf{n}_z"] = -z365(nf)
    sigs[f"-dSx{n}_z"] = -z365(np.log(spx / spx.shift(n)))
    sigs[f"-in{n}_z"] = -z365(np.log(inflow.rolling(n).sum()))  # inflow spike (bearish) -> negated
    sigs[f"out/in{n}_z"] = z365(np.log(outflow.rolling(n).sum() / inflow.rolling(n).sum()))
sigs = pd.DataFrame(sigs)

rows = []
for hzn in [1, 7, 30]:
    fwd = np.log(eth.shift(-hzn) / eth)
    for s in sigs:
        rr = dict(sig=s, h=hzn)
        for part, (a, b) in {"IS": ("2018-06-01", IS_END), "OOS": (OOS_START, None)}.items():
            x = pd.concat([sigs[s], fwd], axis=1).loc[a:b].dropna()
            rr[f"IC_{part}"] = x.iloc[:, 0].corr(x.iloc[:, 1], method="spearman")
        rows.append(rr)
ic = pd.DataFrame(rows)
pd.set_option("display.width", 200, "display.max_rows", 200)
print(ic.pivot(index="sig", columns="h", values=["IC_IS", "IC_OOS"]).round(3).to_string())

r = eth.pct_change()
vs = rl.vol_target_scalar(r, target=0.5, halflife=20, cap=1.0)
w_tf = trend_filter_weights_daily(eth)
A = "2018-06-01"
tf, _ = rl.backtest(w_tf, eth, cost_bps=10)
out = []
for s in sigs:
    for thr in [-0.5, 0.0, 0.5]:
        gate = (sigs[s] > thr).astype(float)
        for sized, w in [("vs", gate * vs), ("tf x gate", gate * w_tf)]:
            net, st = rl.backtest(w, eth, cost_bps=10)
            out.append(row(net.loc[A:], ann=365, extra=dict(sig=s, thr=thr, sized=sized, TIM=st["TimeInMkt"],
                                                         Turn=st["Turnover_ann"], rho_tf=net.loc[A:].corr(tf.loc[A:]))))
df = pd.DataFrame(out)
print("\nTF ref:", {k: round(float(v), 2) for k, v in row(tf.loc[A:], ann=365).items() if k.startswith("Sh")})
print(df[["sig", "thr", "sized", "Sh_Full", "Sh_IS", "Sh_OOS", "MDD", "TIM", "Turn", "rho_tf"]]
      .round(2).sort_values("Sh_Full", ascending=False).head(25).to_string(index=False))
print("N", len(df), "median", df.groupby("sized")[["Sh_Full", "Sh_IS", "Sh_OOS"]].median().round(2).to_dict())
df.to_csv(os.path.join(os.path.dirname(__file__), "01_flows.csv"), index=False)
