"""exp01 — do on-chain fee / burn / activity series predict ETH? Raw and partial ICs
(controls: returns 1-60 d, SMA40 state, 20 d realised vol), h = 1/3/7/30 d, IS 2017-09 -> 2023
vs OOS 2024+. Chain data lagged one full day (common.LAG)."""
import numpy as np
import pandas as pd

import common as c
from common import ek

pd.set_option("display.width", 260)
eth = ek.daily()["Close"]
F = c.features(eth.index)
ctl = ek.trend_controls(eth)
H = (1, 3, 7, 30)
feats = {k: F[k] for k in F}
raw = ek.ic_table(feats, eth, horizons=H)
par = ek.ic_table(feats, eth, horizons=H, controls=ctl)
cols = [f"h{h}_{k}{s}" for h in H for k in ("IS", "OOS") for s in ("", "_t")]
print("RAW IC and HAC t"); print(raw[cols].round(3).to_string())
print("\nPARTIAL IC after trend controls and HAC t"); print(par[cols].round(3).to_string())
for nm, t in (("raw", raw), ("partial", par)):
    for h in H:
        a, b = t[f"h{h}_IS_t"], t[f"h{h}_OOS_t"]
        sig = a.abs() >= 2
        same = np.sign(a[sig]) == np.sign(b[sig])
        print(f"{nm} h={h}: IS->OOS Spearman of t {a.corr(b, method='spearman'):+.2f}; IS |t|>=2: {int(sig.sum())}, "
              f"same sign OOS {int(same.sum())}, also |t_OOS|>=2 {int((same & (b[sig].abs() >= 2)).sum())}")
raw.to_csv("exp01_raw_ic.csv"); par.to_csv("exp01_partial_ic.csv")

# how much of each feature is just trend / vol?
print("\ncorrelation of features with controls (full sample)")
cc = pd.concat([F, ctl], axis=1).corr(method="spearman").loc[F.columns, ["ret7", "ret30", "ret60", "sma40", "rv20"]]
print(cc.round(2).to_string())

# sub-period ICs by fee regime for the headline features
print("\nraw IC h=7 by regime: pre-London / London->Merge / Merge->Dencun / post-Dencun")
reg = [("2017-09-01", "2021-08-04"), ("2021-08-05", "2022-09-14"), ("2022-09-15", "2024-03-12"), ("2024-03-13", None)]
rows = {}
for k in ("fee_mom_7_30", "fee_mom_30_90", "fee_z7_90", "fee_z7_365", "feeyield30_rank365", "netiss_30", "burnshare_z7_90", "tx_mom_7_30", "adr_mom_7_30"):
    rows[k] = [ek.ic(F[k], eth, 7, a, b)["ic"] for a, b in reg]
print(pd.DataFrame(rows, index=["preLondon", "London-Merge", "Merge-Dencun", "postDencun"]).T.round(3).to_string())
