"""exp02 — (1) where does the in-sample attention effect live (yearly ICs), (2) a-priori costed
rules on the Wikipedia features, (3) re-framing: attention measured in the market itself
(abnormal Binance trade count, quote volume, average trade size) since Wikipedia traffic has
collapsed as a proxy (Ethereum article: ~10k views/day in 2021, ~600 in 2026)."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, HERE)
import evalkit as ek  # noqa: E402
import fetch_wiki as fw  # noqa: E402
from exp01_screen import features, z  # noqa: E402

pd.set_option("display.width", 260)
d = ek.daily()
eth = d["Close"]
F = features(eth.index)
ctl = ek.trend_controls(eth)
base = ek.baselines(eth)
vol, tf = base["volBH"], base["TF_live"]

v = fw.load()["Ethereum"]
print("Ethereum article, mean daily views by year:")
print(v.groupby(v.index.year).mean().round(0).astype(int).to_string())

print("\n1. yearly raw IC at h=30 (overlapping; read the signs, not the sizes)")
ks = ["eth_abn_7_90", "eth_z7_365", "btc_z7_365", "eth_abn_30_180", "crypto_z7_365"]
print(pd.DataFrame({k: {y: ek.ic(F[k], eth, 30, f"{y}-01-01", f"{y}-12-31")["ic"] for y in range(2018, 2027)} for k in ks}).T.round(2).to_string())
print("same, partial after trend controls")
print(pd.DataFrame({k: {y: ek.ic(F[k], eth, 30, f"{y}-01-01", f"{y}-12-31", ctl)["ic"] for y in range(2018, 2027)} for k in ks}).T.round(2).to_string())

print("\n2. a-priori rules on Wikipedia attention, 10 bp/side, 2018-09 -> 2026-10")
on = lambda s: (s > 0).astype(float)
w = {"volBH": vol, "TF_live": tf,
     "eth_abn_7_28 > 0 x vol (L&T)": on(F["eth_abn_7_28"]) * vol,
     "eth_abn_7_90 > 0 x vol": on(F["eth_abn_7_90"]) * vol,
     "eth_z7_365 > 0 x vol": on(F["eth_z7_365"]) * vol,
     "eth_abn_30_180 > 0 x vol": on(F["eth_abn_30_180"]) * vol,
     "composite_abn_7_28 > 0 x vol": on(F["composite_abn_7_28"]) * vol,
     "TF AND eth_abn_7_90 > 0": tf * on(F["eth_abn_7_90"]),
     "TF AND eth_z7_365 > 0": tf * on(F["eth_z7_365"]),
     "TF OR eth_z7_365 > 0": np.maximum(tf, on(F["eth_z7_365"]) * ek.vol_scalar(eth, target=0.5)),
     "TF veto eth_z7_365 > 2 (mania)": tf * (~(F["eth_z7_365"] > 2)),
     "TF x (0.5 + 0.5*1{eth_abn_7_90>0})": tf * (0.5 + 0.5 * on(F["eth_abn_7_90"])),
     }
cols = ["Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Turn", "Expo", "rho_Full", "a_t_Full", "a_t_IS", "a_t_OOS"]
print(ek.show(ek.table(w, eth, start="2018-09-01", bench_w=tf)[cols]))

print("\n3. market-measured attention: abnormal trade count / quote volume / trade size (known at the close, no lag needed)")
n, qv = np.log(d["n"]), np.log(d["qv"])
sz = qv - n                                    # log average trade size in USDT
tbs = d["tq"] / d["qv"]                        # taker-buy share of quote volume
M = {}
for nm, s in (("trades", n), ("qvol", qv), ("tradesize", sz)):
    M[f"{nm}_abn_7_28"] = s.rolling(7).mean() - s.rolling(28).mean().shift(7)
    M[f"{nm}_abn_7_90"] = s.rolling(7).mean() - s.rolling(90).mean()
    M[f"{nm}_z7_365"] = z(s.rolling(7).mean(), 365)
    M[f"{nm}_abn_1_30"] = s - s.rolling(30).mean().shift(1)
M["takerbuy_7"] = tbs.rolling(7).mean() - 0.5
M["takerbuy_z7_90"] = z(tbs.rolling(7).mean(), 90)
M = pd.DataFrame(M)
H = (1, 7, 30)
c3 = [f"h{h}_{k}{s}" for h in H for k in ("IS", "OOS") for s in ("", "_t")]
START = "2018-09-01"
sp = {"IS": (START, "2023-12-31"), "OOS": ("2024-01-01", None)}
raw = ek.ic_table({k: M[k] for k in M}, eth, horizons=H, splits=sp)
par = ek.ic_table({k: M[k] for k in M}, eth, horizons=H, controls=ctl, splits=sp)
print("RAW IC"); print(raw[c3].round(3).to_string())
print("PARTIAL IC after trend controls"); print(par[c3].round(3).to_string())
for nm, t in (("raw", raw), ("partial", par)):
    for h in H:
        a, b = t[f"h{h}_IS_t"], t[f"h{h}_OOS_t"]
        sig = a.abs() >= 2
        same = np.sign(a[sig]) == np.sign(b[sig])
        print(f"{nm} h={h}: IS->OOS Spearman of t {a.corr(b, method='spearman'):+.2f}; IS |t|>=2: {int(sig.sum())}, same sign & |t_OOS|>=2: {int((same & (b[sig].abs() >= 2)).sum())}")

w3 = {"TF_live": tf,
      "trades_abn_7_90 > 0 x vol": on(M["trades_abn_7_90"]) * vol,
      "trades_abn_1_30 > 0 x vol (high-volume day)": on(M["trades_abn_1_30"]) * vol,
      "tradesize_z7_365 < 0 x vol (retail mix)": (M["tradesize_z7_365"] < 0).astype(float) * vol,
      "takerbuy_z7_90 > 0 x vol": on(M["takerbuy_z7_90"]) * vol,
      "TF AND trades_abn_7_90 > 0": tf * on(M["trades_abn_7_90"]),
      "TF AND takerbuy_z7_90 > 0": tf * on(M["takerbuy_z7_90"]),
      }
print(ek.show(ek.table(w3, eth, start=START, bench_w=tf)[cols]))
