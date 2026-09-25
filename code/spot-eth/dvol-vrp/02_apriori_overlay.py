"""dvol-vrp 02: a-priori VRP gates on the trend filter (no threshold search).

G1: 1{iv > rv30}                 (positive variance risk premium: the market pays for insurance)
G2: 1{vrp > rolling-180d median} (premium above its own recent norm)
G3: continuous tilt clip(0.5 + 0.5*vrp_z, 0, 1)
Each applied to the live trend filter weight and as a standalone gate on the vol scalar.
Also: RV-only control (1{rv30 < rolling median}), to check the gate is not just 'low realised vol'.
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
rv30 = np.sqrt((lr1 ** 2).rolling(720, min_periods=600).sum() * (365 * 24 / 720)).resample("1D").last()
eth = c.resample("1D").last().dropna(); rv30 = rv30.reindex(eth.index)
iv = (load("1d")["Close"] / 100).reindex(eth.index)
vrp = iv - rv30
vrp_z = (vrp - vrp.rolling(180, min_periods=90).mean()) / vrp.rolling(180, min_periods=90).std()
A = "2021-05-01"
r = eth.pct_change()
vs = rl.vol_target_scalar(r, target=0.5, halflife=20, cap=1.0)
w_tf = trend_filter_weights_daily(eth)
tf, _ = rl.backtest(w_tf, eth, cost_bps=10); tf = tf.loc[A:]
gates = {
    "G1 iv>rv30": (iv > rv30).astype(float),
    "G2 vrp>med180": (vrp > vrp.rolling(180, min_periods=90).median()).astype(float),
    "G3 tilt": (0.5 + 0.5 * vrp_z).clip(0, 1).fillna(0),
    "ctrl rv30<med180": (rv30 < rv30.rolling(180, min_periods=90).median()).astype(float),
    "ctrl iv<med180": (iv < iv.rolling(180, min_periods=90).median()).astype(float),
}
rows = [row(tf, ann=365, extra=dict(v="TF (live)"))]
nets = {}
for g, G in gates.items():
    for sized, w in [("TF x", w_tf * G), ("vs x", vs * G)]:
        for cb in [10]:
            net, st = rl.backtest(w, eth, cost_bps=cb); net = net.loc[A:]
            nets[f"{sized} {g}"] = net
            x = row(net, ann=365, extra=dict(v=f"{sized} {g}", TIM=st["TimeInMkt"], Turn=st["Turnover_ann"],
                                             rho_tf=net.corr(tf)))
            for p, (a, b) in {"IS": (A, IS_END), "OOS": (OOS_START, None)}.items():
                Y, X = net.loc[a:b], tf.loc[a:b]
                beta = np.cov(Y, X)[0, 1] / X.var()
                x[f"alpha_t_{p}"] = rl.newey_west_t((Y - beta * X).values)
            rows.append(x)
pd.set_option("display.width", 250)
df = pd.DataFrame(rows)
print(df[["v", "Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "TIM", "Turn", "rho_tf", "alpha_t_IS", "alpha_t_OOS"]].round(2).to_string(index=False))
yr = pd.DataFrame({k: v.groupby(v.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(365))
                   for k, v in {"TF": tf, "TF x G1": nets["TF x G1 iv>rv30"], "TF x G2": nets["TF x G2 vrp>med180"],
                                "vs x G1": nets["vs x G1 iv>rv30"]}.items()})
print(yr.round(2).to_string())
print("share of days with iv>rv30:", round(float(gates["G1 iv>rv30"].loc[A:].mean()), 2))
