"""exp01 — pre-registered replication of spot-btc/perp-crowding on ETH.

The BTC spec (`code/spot-btc/perp-crowding/strategy.py :: target_weight`, defaults untouched) is
applied to spot ETHUSDT closes and the ETHUSDT-perp global long/short account ratio. Nothing is
re-fitted. Reported against vol-scaled B&H, the live eth-trend-filter and SMA50 x vol over the
same window, plus the cross-asset variants that tell whether the ETH crowd carries anything the
BTC crowd does not.
"""
import numpy as np
import pandas as pd

import common as c
from common import ek

eth, btc = c.closes()
me, mb = c.metrics("ETHUSDT"), c.metrics("BTCUSDT")
tw = c.btc_spec.target_weight

base = ek.baselines(eth)
w = {
    "volBH": base["volBH"],
    "TF_live": base["TF_live"],
    "SMA50xvol": base["SMA50xvol"],
    "P1 ETH px x ETH crowd (spec)": tw(eth, me["count_long_short_ratio"]),
    "P2 spec + SMA50 gate": tw(eth, me["count_long_short_ratio"], trend_sma=50),
    "X1 ETH px x BTC crowd": tw(eth, mb["count_long_short_ratio"]),
}
# BTC crowd has history from 2020-09; restrict its rank to the same start as ETH for a like-for-like
w["X2 ETH px x BTC crowd (rank from 2021-12)"] = tw(eth, mb["count_long_short_ratio"].loc["2021-12-01":])
both = ((w["P1 ETH px x ETH crowd (spec)"] > 0) & (w["X2 ETH px x BTC crowd (rank from 2021-12)"] > 0)).astype(float)
w["X3 ETH and BTC both uncrowded"] = both * base["volBH"]

print(f"window {c.EVAL_START} -> {eth.index.max().date()}, IS <= 2023, OOS 2024+, 10 bp/side\n")
t = ek.table(w, eth, start=c.EVAL_START, splits=c.SPLITS, bench_w=base["TF_live"])
print(ek.show(t[["Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Vol", "Turn", "Expo",
                 "rho_Full", "a_t_Full", "a_t_IS", "a_t_OOS"]]))

# BTC reference on the identical window: is the ETH result just the BTC result?
bb = ek.baselines(btc)
wb = {"BTC volBH": bb["volBH"], "BTC SMA50xvol": bb["SMA50xvol"],
      "BTC spec (rank from 2020-09)": tw(btc, mb["count_long_short_ratio"]),
      "BTC px x ETH crowd": tw(btc, me["count_long_short_ratio"])}
print("\nBTC on the same window")
print(ek.show(ek.table(wb, btc, start=c.EVAL_START, splits=c.SPLITS)[["Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Turn", "Expo"]]))

# How alike are the two crowd states?
se = (w["P1 ETH px x ETH crowd (spec)"] > 0).loc[c.EVAL_START:]
sb = (w["X2 ETH px x BTC crowd (rank from 2021-12)"] > 0).loc[c.EVAL_START:]
print(f"\nstate agreement ETH vs BTC crowd: {(se == sb).mean():.2f}; ETH on {se.mean():.2f}, BTC on {sb.mean():.2f}")
le = c.daily_level(me["count_long_short_ratio"], eth.index)
lb = c.daily_level(mb["count_long_short_ratio"], eth.index)
print(f"corr of log ratios (level) {le.corr(lb):.2f}, of daily changes {le.diff().corr(lb.diff()):.2f}")

# yearly
net = ek.bt(w["P1 ETH px x ETH crowd (spec)"], eth, start=c.EVAL_START)[0]
tf = ek.bt(base["TF_live"], eth, start=c.EVAL_START)[0]
vb = ek.bt(base["volBH"], eth, start=c.EVAL_START)[0]
yr = pd.DataFrame({k: v.groupby(v.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(365))
                   for k, v in {"P1": net, "TF_live": tf, "volBH": vb}.items()})
yr["P1_ret"] = net.groupby(net.index.year).apply(lambda x: (1 + x).prod() - 1)
print("\nyearly Sharpe"); print(yr.round(2).to_string())
