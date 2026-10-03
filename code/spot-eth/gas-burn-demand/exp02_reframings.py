"""exp02 — re-framings after the null linear screen.

1. Extreme fee spikes as events, split by what the price did that day (panic vs euphoria).
2. The same ICs inside up-trends and down-trends.
3. ETH-specific demand should move ETH *relative to BTC*: ICs against the forward ETH/BTC return.
4. A-priori costed rules (standalone, gate and veto on the live trend filter).
5. Lag sensitivity of the chain data (0 = not obtainable live, 1 = spec, 2).
"""
import numpy as np
import pandas as pd

import common as c
from common import ek

pd.set_option("display.width", 260)
eth = ek.daily()["Close"]
btc = ek.daily("BTCUSDT")["Close"]
ratio = eth / btc
F = c.features(eth.index)
ctl = ek.trend_controls(eth)
base = ek.baselines(eth)
vol, tf = base["volBH"], base["TF_live"]
sma40 = (eth > eth.rolling(40).mean())
SP = ek.SPLITS

# ------------------------------------------------------------------ 1. spike events
print("1. fee-spike events: forward ETH log return (%), mean and t, by spike size and same-day price move")
r0 = np.log(eth).diff().shift(c.LAG - 0)       # return of the day the chain row covers (D-1 with LAG=1) ...
r0 = np.log(eth).diff().shift(c.LAG)           # ... aligned to the lagged feature
rows = []
for nm, zc in (("fee_z1_30", F["fee_z1_30"]), ("fee_z7_90", F["fee_z7_90"])):
    for lo, hi in ((2, 3), (3, 99), (-99, -2)):
        for side, m in (("any", pd.Series(True, index=eth.index)), ("px down", r0 < -0.03), ("px up", r0 > 0.03)):
            ev = (zc > lo) & (zc <= hi) & m
            for k, (a, b) in SP.items():
                if k == "Full":
                    continue
                row = {"feature": nm, "z": f"({lo},{hi}]", "price": side, "split": k, "n": int(ev.loc[a:b].sum())}
                for h in (1, 3, 7, 30):
                    f = ek.fwd_ret(eth, h)
                    x = f[ev].loc[a:b].dropna()
                    base_mu = f.loc[a:b].mean()
                    # overlapping events: scale the standard error by sqrt(h) as a rough adjustment
                    row[f"h{h}"] = (x.mean() - base_mu) * 100 if len(x) > 4 else np.nan
                    row[f"h{h}_t"] = (x.mean() - base_mu) / (x.std() / np.sqrt(max(len(x) / h, 1))) if len(x) > 4 else np.nan
                rows.append(row)
ev = pd.DataFrame(rows)
print(ev.round(2).to_string(index=False))

# ------------------------------------------------------------------ 2. by trend regime
print("\n2. raw IC h=7 inside up-trend (close > SMA40) and down-trend, IS | OOS")
rows = {}
for k in ("fee_mom_7_30", "fee_mom_30_90", "fee_z1_30", "fee_z7_90", "fee_z7_365", "feeyield30_rank365", "netiss_30", "tx_mom_7_30", "adr_mom_7_30"):
    r = {}
    for reg, m in (("up", sma40), ("down", ~sma40)):
        for s, (a, b) in SP.items():
            if s == "Full":
                continue
            o = ek.ic(F[k].where(m), eth, 7, a, b)
            r[f"{reg}_{s}"] = f"{o['ic']:+.3f} ({o['t']:+.1f})"
    rows[k] = r
print(pd.DataFrame(rows).T.to_string())

# ------------------------------------------------------------------ 3. relative to BTC
print("\n3. IC against the forward ETH/BTC return (HAC t), h = 7 and 30")
t3 = ek.ic_table({k: F[k] for k in F}, ratio, horizons=(7, 30))
print(t3.round(3).to_string())
for h in (7, 30):
    a, b = t3[f"h{h}_IS_t"], t3[f"h{h}_OOS_t"]
    print(f"h={h}: IS->OOS Spearman of t {a.corr(b, method='spearman'):+.2f}; IS |t|>=2: {int((a.abs() >= 2).sum())}")

# ------------------------------------------------------------------ 4. a-priori rules
print("\n4. a-priori costed rules, 10 bp/side, 2017-09 -> 2026-10")
w = {"volBH": vol, "TF_live": tf,
     "fee_mom_30_90 > 0 x vol": (F["fee_mom_30_90"] > 0).astype(float) * vol,
     "fee_mom_7_30 > 0 x vol": (F["fee_mom_7_30"] > 0).astype(float) * vol,
     "fee_z1_30 > 0 x vol (daily spike)": (F["fee_z1_30"] > 0).astype(float) * vol,
     "feeyield rank365 > .5 x vol": (F["feeyield30_rank365"] > 0.5).astype(float) * vol,
     "netiss_30 below 365d median x vol": (F["netiss_30"] < F["netiss_30"].rolling(365).median()).astype(float) * vol,
     "TF AND fee_mom_30_90 > 0": tf * (F["fee_mom_30_90"] > 0),
     "TF AND fee_mom_7_30 > 0": tf * (F["fee_mom_7_30"] > 0),
     "TF veto fee_z7_365 > 2 (froth)": tf * (~(F["fee_z7_365"] > 2)),
     "TF veto fee_z7_90 > 2 (froth)": tf * (~(F["fee_z7_90"] > 2)),
     "TF OR fee_z1_30 > 2 (spike day)": np.maximum(tf, (F["fee_z1_30"] > 2).astype(float) * vol),
     "TF x (0.5 + 0.5*1{fee_mom_30_90>0})": tf * (0.5 + 0.5 * (F["fee_mom_30_90"] > 0)),
     }
t = ek.table(w, eth, start="2018-09-01", bench_w=tf)
print(ek.show(t[["Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Turn", "Expo", "rho_Full", "a_t_Full", "a_t_IS", "a_t_OOS"]]))

# ------------------------------------------------------------------ 5. lag sensitivity
print("\n5. lag sensitivity of the best raw feature (fee_z1_30, h=1) and of fee_mom_30_90 (h=30)")
for lag in (0, 1, 2, 3):
    Fl = c.features(eth.index, lag=lag)
    o1 = [ek.ic(Fl["fee_z1_30"], eth, 1, *SP[s]) for s in ("IS", "OOS")]
    o2 = [ek.ic(Fl["fee_mom_30_90"], eth, 30, *SP[s]) for s in ("IS", "OOS")]
    print(f"  lag {lag}: fee_z1_30 h1 IS {o1[0]['ic']:+.3f} (t {o1[0]['t']:+.1f}) OOS {o1[1]['ic']:+.3f} (t {o1[1]['t']:+.1f});  "
          f"fee_mom_30_90 h30 IS {o2[0]['ic']:+.3f} (t {o2[0]['t']:+.1f}) OOS {o2[1]['ic']:+.3f} (t {o2[1]['t']:+.1f})")
