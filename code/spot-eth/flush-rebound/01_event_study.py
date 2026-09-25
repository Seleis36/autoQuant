"""flush-rebound 01: event study of forward ETH returns after extreme short-horizon moves.

Event at hourly close t: z_k = log(C_t / C_{t-k}) / (sigma_1h * sqrt(k)), where sigma_1h is
the EWM (halflife 7d) std of 1h log returns measured up to t-k (so the shock itself does not
inflate its own yardstick). Forward return: log(C_{t+H} / C_t), entered at the close of t.
Non-overlapping: after an event, the next event is counted only after H hours.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import bars, IS_END, OOS_START

h = bars("ETHUSDT", "1h")
c = h["Close"]
lr = np.log(c).diff()
sig = lr.ewm(halflife=24 * 7, min_periods=24 * 7).std()
vol_rel = h["qv"] / h["qv"].rolling(24 * 30, min_periods=24 * 7).mean()

rows = []
for k in [1, 2, 4, 8, 12, 24]:
    rk = np.log(c / c.shift(k))
    z = rk / (sig.shift(k) * np.sqrt(k))
    for Z in [2.0, 2.5, 3.0, 4.0]:
        for side in ["down", "up"]:
            ev = (z < -Z) if side == "down" else (z > Z)
            for H in [4, 12, 24, 48, 96]:
                fwd = np.log(c.shift(-H) / c)
                # de-cluster
                idx = []
                last = None
                for t in ev[ev].index:
                    if last is None or (t - last) >= pd.Timedelta(hours=H):
                        idx.append(t); last = t
                idx = pd.DatetimeIndex(idx)
                f = fwd.reindex(idx).dropna()
                uncond = fwd.dropna().mean()
                for part, (a, b) in {"IS": (None, IS_END), "OOS": (OOS_START, None)}.items():
                    fp = f.loc[a:b]
                    if len(fp) < 5:
                        continue
                    rows.append(dict(k=k, Z=Z, side=side, H=H, part=part, n=len(fp),
                                     mean_bp=fp.mean() * 1e4, med_bp=fp.median() * 1e4,
                                     hit=(fp > 0).mean(), t=fp.mean() / fp.std() * np.sqrt(len(fp)),
                                     uncond_bp=fwd.loc[a:b].mean() * 1e4))
df = pd.DataFrame(rows)
pd.set_option("display.width", 200, "display.max_rows", 500)
piv = df.pivot_table(index=["side", "k", "Z", "H"], columns="part",
                     values=["n", "mean_bp", "t", "hit"]).round(2)
print(piv.to_string())
df.to_csv(os.path.join(os.path.dirname(__file__), "01_event_study.csv"), index=False)
