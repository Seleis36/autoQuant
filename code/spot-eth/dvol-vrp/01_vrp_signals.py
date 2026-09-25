"""dvol-vrp 01: does ETH implied vol (Deribit DVOL) or the variance risk premium predict spot ETH?

Timing: ETH bar D (Binance [D, D+1)) closes at D+1 00:00 UTC; DVOL daily bar D's Close is the index
at the same instant. Realised vol uses 1h returns through that close. Weight applied to day D+1.
Signals:
  iv       = DVOL/100 (30d implied, annualised)
  rv30     = sqrt(365*24/720 * sum of last 720 squared 1h log-returns)   (trailing 30d realised)
  vrp      = iv - rv30             vrp_z = z-score over trailing 180d
  iv_z     = z of iv over 180d     div5 = 5d change in iv (vol shock)
  ivrv     = log(iv / rv30)
IS 2021-04 -> 2023-12, OOS 2024-01 -> 2026-09.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import pandas as pd
from ethdata import rl, bars, row, trend_filter_weights_daily, IS_END, OOS_START
from fetch_dvol import load

h = bars("ETHUSDT", "1h"); c = h["Close"]
lr1 = np.log(c).diff()
rv30_h = np.sqrt((lr1 ** 2).rolling(720, min_periods=600).sum() * (365 * 24 / 720))
eth = c.resample("1D").last().dropna()
rv30 = rv30_h.resample("1D").last().reindex(eth.index)
iv = (load("1d")["Close"] / 100).reindex(eth.index)
z = lambda x, n=180: (x - x.rolling(n, min_periods=90).mean()) / x.rolling(n, min_periods=90).std()
S = pd.DataFrame({
    "iv": iv, "iv_z": z(iv), "vrp": iv - rv30, "vrp_z": z(iv - rv30), "ivrv": np.log(iv / rv30),
    "-div5": -(iv - iv.shift(5)), "-div1": -(iv - iv.shift(1)), "-rv30_z": -z(rv30),
})
A = "2021-05-01"
rows = []
for hzn in [1, 7, 30]:
    fwd = np.log(eth.shift(-hzn) / eth)
    for s in S:
        rr = dict(sig=s, h=hzn)
        for p, (a, b) in {"IS": (A, IS_END), "OOS": (OOS_START, None)}.items():
            x = pd.concat([S[s], fwd], axis=1).loc[a:b].dropna()
            rr[f"IC_{p}"] = x.iloc[:, 0].corr(x.iloc[:, 1], method="spearman")
        rows.append(rr)
pd.set_option("display.width", 200, "display.max_rows", 200)
print(pd.DataFrame(rows).pivot(index="sig", columns="h", values=["IC_IS", "IC_OOS"]).round(3).to_string())

# quintile forward 7d returns by vrp_z and iv_z
for s in ["vrp_z", "iv_z", "ivrv"]:
    fwd7 = np.log(eth.shift(-7) / eth)
    out = {}
    for p, (a, b) in {"IS": (A, IS_END), "OOS": (OOS_START, None)}.items():
        x = pd.concat([S[s], fwd7], axis=1, keys=["s", "f"]).loc[a:b].dropna()
        out[p] = (x.groupby(pd.qcut(x.s, 5, labels=False)).f.mean() * 1e4).round(0)
    print(s, "fwd7 bp by quintile:", pd.DataFrame(out).T.to_string())

r = eth.pct_change()
vs = rl.vol_target_scalar(r, target=0.5, halflife=20, cap=1.0)
w_tf = trend_filter_weights_daily(eth)
tf, _ = rl.backtest(w_tf, eth, cost_bps=10)
bh, _ = rl.backtest(vs, eth, cost_bps=10)
print("\nTF:", {k: round(float(v), 2) for k, v in row(tf.loc[A:], ann=365).items() if k.startswith("Sh")},
      " vs-B&H:", {k: round(float(v), 2) for k, v in row(bh.loc[A:], ann=365).items() if k.startswith("Sh")})
out = []
for s in S:
    base = S[s] if s not in ("iv", "vrp", "ivrv") else z(S[s])
    for thr in [-0.5, 0.0, 0.5]:
        for side in ["hi", "lo"]:
            gate = (base > thr) if side == "hi" else (base < -thr)
            for sized, w in [("vs", gate.astype(float) * vs), ("tf", gate.astype(float) * w_tf)]:
                net, st = rl.backtest(w, eth, cost_bps=10); net = net.loc[A:]
                out.append(row(net, ann=365, extra=dict(sig=s, thr=thr, side=side, sized=sized, TIM=st["TimeInMkt"],
                                                         rho_tf=net.corr(tf.loc[A:]))))
df = pd.DataFrame(out)
print(df[["sig", "thr", "side", "sized", "Sh_Full", "Sh_IS", "Sh_OOS", "MDD", "TIM", "rho_tf"]]
      .round(2).sort_values("Sh_Full", ascending=False).head(20).to_string(index=False))
print("N", len(df), "median", df.groupby("sized")[["Sh_Full", "Sh_IS", "Sh_OOS"]].median().round(2).to_dict())
df.to_csv(os.path.join(os.path.dirname(__file__), "01_vrp_signals.csv"), index=False)
