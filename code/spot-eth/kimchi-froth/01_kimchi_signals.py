"""kimchi-froth 01: the Korean ETH premium as a retail-froth (contrarian) or retail-inflow (momentum) signal.

kp_D = Upbit KRW-ETH close_D / (Binance ETHUSDT close_D x USDKRW_{D-1 row}) - 1
Both closes are at D+1 00:00 UTC. The yfinance KRW=X row stamped D is the rate at ~00:00 UTC on D,
so using it at D+1 00:00 is 24 h stale -- conservative, and FX moves (<1%/day) are small next to kp.
Signals: kp level, kp z (365d), 7d change of kp, BTC kimchi premium, ETH-minus-BTC kp.
IS 2018-01 -> 2023-12 / OOS 2024-01 -> 2026-09. 10 bp per side.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
from ethdata import rl, bars, row, trend_filter_weights_daily, IS_END, OOS_START
from fetch_upbit import load as up

eth = bars("ETHUSDT", "1h")["Close"].resample("1D").last().dropna()
btc = bars("BTCUSDT", "1h")["Close"].resample("1D").last().reindex(eth.index)
fx = rl.load_series("KRW=X")["Close"].reindex(eth.index).ffill().shift(1)
ue = up("KRW-ETH")["Close"].reindex(eth.index); ub = up("KRW-BTC")["Close"].reindex(eth.index)
kp = ue / (eth * fx) - 1; kpb = ub / (btc * fx) - 1
print("kimchi premium % by year (ETH mean / max / min):")
print((kp.groupby(kp.index.year).agg(["mean", "max", "min"]) * 100).round(1).T.to_string())
z = lambda x, n=365: (x - x.rolling(n, min_periods=180).mean()) / x.rolling(n, min_periods=180).std()
S = pd.DataFrame({"-kp": -kp, "-kp_z": -z(kp), "-dkp7": -(kp - kp.shift(7)), "dkp7": kp - kp.shift(7),
                  "-kpb": -kpb, "-kp_avg_z": -z((kp + kpb) / 2), "-(kp-kpb)": -(kp - kpb)})
A = "2018-01-01"
rows = []
for H in [1, 7, 30]:
    fwd = np.log(eth.shift(-H) / eth)
    for s in S:
        r = dict(sig=s, H=H)
        for p, (a, b) in {"IS": (A, IS_END), "OOS": (OOS_START, None)}.items():
            x = pd.concat([S[s], fwd], axis=1, keys=["s", "f"]).loc[a:b].dropna()
            r[f"IC_{p}"] = x.s.corr(x.f, method="spearman")
        rows.append(r)
pd.set_option("display.width", 200, "display.max_rows", 200)
print(pd.DataFrame(rows).pivot(index="sig", columns="H", values=["IC_IS", "IC_OOS"]).round(3).to_string())

# froth veto on the live trend filter and on vol-scaled B&H: flat when kp z > thr (a-priori thr 1, 2)
r_ = eth.pct_change(); vs = rl.vol_target_scalar(r_, target=0.5, halflife=20, cap=1.0)
w_tf = trend_filter_weights_daily(eth)
out = []
for base_name, base in [("TF", w_tf), ("vs", vs)]:
    net, _ = rl.backtest(base, eth, cost_bps=10); ref = net.loc[A:]
    out.append(row(ref, ann=365, extra=dict(v=f"{base_name} alone")))
    for thr in [1.0, 2.0]:
        for nm, sig in [("kp_z", z(kp)), ("kp_avg_z", z((kp + kpb) / 2))]:
            veto = (sig > thr).astype(float)
            net, st = rl.backtest(base * (1 - veto), eth, cost_bps=10); net = net.loc[A:]
            out.append(row(net, ann=365, extra=dict(v=f"{base_name} x veto({nm}>{thr})", veto_share=veto.loc[A:].mean(),
                                                     rho=net.corr(ref))))
print(pd.DataFrame(out)[["v", "Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "veto_share", "rho"]].round(3).to_string(index=False))
