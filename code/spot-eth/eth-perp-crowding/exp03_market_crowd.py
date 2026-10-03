"""exp03 — the information is in the BTC crowd, not the ETH one (exp02). Is a spot-ETH sleeve
timed by the BTC-perp retail crowd additive to the live ETH trend filter?

Longer window: the BTC ratio starts 2020-09, so ETH px x BTC crowd runs from 2021-03 like the BTC
study. Two splits are reported, both fixed before the run: the BTC study's (IS <= 2022, OOS 2023+)
and the spot-eth convention (IS <= 2023, OOS 2024+).
"""
import numpy as np
import pandas as pd

import common as c
from common import ek

pd.set_option("display.width", 250)
eth, btc = c.closes()
me, mb = c.metrics("ETHUSDT"), c.metrics("BTCUSDT")
tw, er = c.btc_spec.target_weight, c.btc_spec.expanding_rank
base = ek.baselines(eth)
vol = base["volBH"]

START = "2021-03-01"
S_BTC = {"Full": (START, None), "IS": (START, "2022-12-31"), "OOS": ("2023-01-01", None)}
S_ETH = {"Full": (START, None), "IS": (START, "2023-12-31"), "OOS": ("2024-01-01", None)}

rb = er(c.daily_level(mb["count_long_short_ratio"], eth.index), 180)     # BTC crowd rank (live BTC signal)
re_ = er(c.daily_level(me["count_long_short_ratio"], eth.index), 180)    # ETH crowd rank (2022-06+)
unc = (rb < 0.5).astype(float).where(rb.notna(), 0.0)
tf = base["TF_live"]
sma40 = (eth > eth.rolling(40).mean()).astype(float)

w = {
    "volBH": vol, "TF_live": tf, "SMA50xvol": base["SMA50xvol"],
    "A  ETH px x BTC crowd (spec)": tw(eth, mb["count_long_short_ratio"]),
    "A' same, vol target 0.5 like TF": unc * ek.vol_scalar(eth, target=0.5),
    "C1 TF AND BTC-uncrowded": tf * unc,
    "C2 TF tilt x(0.5+0.5 unc)": tf * (0.5 + 0.5 * unc),
    "C3 TF OR uncrowded (max)": np.maximum(tf, unc * ek.vol_scalar(eth, target=0.5)),
    "D  50/50 TF + A'": 0.5 * tf + 0.5 * unc * ek.vol_scalar(eth, target=0.5),
}
for nm, sp in (("BTC-study split: IS<=2022 / OOS 2023+", S_BTC), ("spot-eth split: IS<=2023 / OOS 2024+", S_ETH)):
    t = ek.table(w, eth, start=START, splits=sp, bench_w=tf)
    print(f"\n{nm}   window {START} -> {eth.index.max().date()}, 10 bp/side")
    print(ek.show(t[["Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Turn", "Expo", "rho_Full", "a_t_Full", "a_t_IS", "a_t_OOS"]]))

# conditional next-day ETH return by trend state x crowd state (bp/day), per half
r1 = eth.pct_change().shift(-1) * 1e4
print("\nnext-day ETH return (bp) by SMA40 state x BTC-crowd state")
for k, (a, b) in S_ETH.items():
    d = pd.DataFrame({"r": r1, "up": sma40, "unc": unc}).loc[a:b].dropna()
    g = d.groupby(["up", "unc"])["r"].agg(["mean", "count", lambda x: x.mean() / x.std() * np.sqrt(len(x))])
    g.columns = ["bp", "n", "t"]
    print(k); print(g.round(2).to_string())

# P&L correlation with the BTC sleeve the book already runs
netA = ek.bt(w["A  ETH px x BTC crowd (spec)"], eth, start=START)[0]
netB = ek.bt(tw(btc, mb["count_long_short_ratio"]), btc, start=START)[0]
netTF = ek.bt(tf, eth, start=START)[0]
print(f"\ncorr(A, BTC perp-crowding sleeve) {netA.corr(netB):.2f}; corr(A, TF_live) {netA.corr(netTF):.2f}; "
      f"corr(BTC sleeve, TF_live) {netB.corr(netTF):.2f}")
# alpha of A on [TF_live, BTC sleeve]
import numpy.linalg as la
for k, (a, b) in S_ETH.items():
    d = pd.DataFrame({"y": netA, "tf": netTF, "b": netB}).loc[a:b].dropna()
    X = np.column_stack([np.ones(len(d)), d[["tf", "b"]].to_numpy()])
    coef = la.lstsq(X, d["y"].to_numpy(), rcond=None)[0]
    e = d["y"].to_numpy() - X @ coef
    Xe = X * e[:, None]; S = Xe.T @ Xe
    for L in range(1, 22):
        G = Xe[L:].T @ Xe[:-L]; S += (1 - L / 22) * (G + G.T)
    V = la.inv(X.T @ X) @ S @ la.inv(X.T @ X)
    print(f"{k}: A = {coef[0]*365:+.3f}/yr (t {coef[0]/np.sqrt(V[0,0]):+.2f}) + {coef[1]:.2f} TF + {coef[2]:.2f} BTCsleeve")

yr = pd.DataFrame({k: v.groupby(v.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(365))
                   for k, v in {"A": netA, "TF_live": netTF, "C1": ek.bt(w["C1 TF AND BTC-uncrowded"], eth, start=START)[0],
                                "D": ek.bt(w["D  50/50 TF + A'"], eth, start=START)[0]}.items()})
print("\nyearly Sharpe"); print(yr.round(2).to_string())
