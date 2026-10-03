"""exp02 — what do the ETH positioning series know? Raw and partial ICs (controls: past returns
1-60d, SMA40 state, 20d realised vol) at h = 1/3/7 days, IS (2022-06 -> 2023) vs OOS (2024+).

Features: the three ETH long/short ratios (global accounts, top-trader accounts, top-trader
positions) as level / expanding rank / rolling z / changes; ETH minus BTC crowding; the BTC
crowd itself; OI growth; taker long/short volume ratio.
"""
import numpy as np
import pandas as pd

import common as c
from common import ek

pd.set_option("display.width", 250)
eth, btc = c.closes()
me, mb = c.metrics("ETHUSDT"), c.metrics("BTCUSDT").loc["2021-12-01":]
idx = eth.index


def z(x, n):
    return (x - x.rolling(n).mean()) / x.rolling(n).std()


F = {}
for k, col in c.RATIOS.items():
    lv = c.daily_level(me[col], idx)
    F[f"{k}_lvl"] = lv
    F[f"{k}_exprank"] = c.btc_spec.expanding_rank(lv, 180)
    F[f"{k}_z90"] = z(lv, 90)
    F[f"{k}_z180"] = z(lv, 180)
    F[f"{k}_rank365"] = lv.rolling(365, min_periods=180).rank(pct=True)
    for d in (1, 3, 7):
        F[f"{k}_d{d}"] = lv.diff(d)
ge, gb = F["glob_lvl"], c.daily_level(mb["count_long_short_ratio"], idx)
F["btc_glob_lvl"] = gb
F["btc_glob_z90"] = z(gb, 90)
F["btc_glob_exprank"] = c.btc_spec.expanding_rank(gb, 180)
F["eth-btc_glob_lvl"] = ge - gb
F["eth-btc_glob_z90"] = z(ge, 90) - z(gb, 90)
F["eth-btc_glob_z180"] = z(ge - gb, 180)
F["top-glob_lvl"] = F["toppos_lvl"] - ge
F["top-glob_z90"] = z(F["toppos_lvl"] - ge, 90)
oi = c.daily_level(me["sum_open_interest"], idx)
for d in (1, 3, 7):
    F[f"oi_g{d}"] = oi.diff(d)
F["oi_z90"] = z(oi, 90)
tk = np.log(me["sum_taker_long_short_vol_ratio"].replace(0, np.nan)).resample("1D").mean().reindex(idx)
for d in (1, 3, 7):
    F[f"taker_{d}"] = tk.rolling(d).mean()

ctl = ek.trend_controls(eth)
splits = {"IS": (c.EVAL_START, "2023-12-31"), "OOS": ("2024-01-01", None)}
raw = ek.ic_table(F, eth, horizons=(1, 3, 7), splits=splits)
par = ek.ic_table(F, eth, horizons=(1, 3, 7), controls=ctl, splits=splits)
cols = [f"h{h}_{k}{s}" for h in (1, 3, 7) for k in ("IS", "OOS") for s in ("", "_t")]
print("RAW IC (Spearman) and HAC t"); print(raw[cols].round(3).to_string())
print("\nPARTIAL IC after trend controls and HAC t"); print(par[cols].round(3).to_string())
for h in (1, 3, 7):
    a, b = par[f"h{h}_IS_t"], par[f"h{h}_OOS_t"]
    sig = a.abs() >= 2
    print(f"h={h}: IS->OOS Spearman of partial t {a.corr(b, method='spearman'):+.2f}; "
          f"IS-significant {int(sig.sum())}, of which same sign OOS {int((np.sign(a[sig]) == np.sign(b[sig])).sum())}, "
          f"and |t_OOS|>=2 {int(((np.sign(a[sig]) == np.sign(b[sig])) & (b[sig].abs() >= 2)).sum())}")
par.to_csv("exp02_partial_ic.csv")

# yearly 3-day raw IC of the headline features
print("\nyearly raw IC, h=3")
rows = {}
for name in ("glob_lvl", "glob_z90", "btc_glob_lvl", "eth-btc_glob_lvl", "topacc_lvl", "toppos_lvl"):
    rows[name] = {y: ek.ic(F[name], eth, 3, f"{y}-01-01", f"{y}-12-31")["ic"] for y in range(2022, 2027)}
print(pd.DataFrame(rows).T.round(3).to_string())
