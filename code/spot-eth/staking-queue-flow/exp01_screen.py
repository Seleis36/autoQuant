"""exp01 — validator entry/exit queues as a staking-flow signal for spot ETH.

Data: validatorqueue.com daily history, 2023-05-21 -> 2026-10-03 (1,221 rows). The row dated D
is committed between 00:07 and 04:50 UTC on D (GitHub history of historical_data.json), so it is
known ~20 h before the D+1 00:00 decision: lag 0 is legitimate; lag 1 is shown as a check.

Split fixed before the run (the sample is too short for the spot-eth 2024 convention):
IS 2023-05-21 -> 2024-12-31, OOS 2025-01-01 -> 2026-10-02.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, HERE)
import evalkit as ek  # noqa: E402
import fetch_queue as fq  # noqa: E402

pd.set_option("display.width", 260)
START = "2023-05-21"
SP = {"Full": (START, None), "IS": (START, "2024-12-31"), "OOS": ("2025-01-01", None)}


def z(x, n):
    return (x - x.rolling(n, min_periods=n // 2).mean()) / x.rolling(n, min_periods=n // 2).std()


def features(index, lag=0):
    q = fq.load().reindex(pd.date_range(START, index.max())).ffill(limit=5)
    st = q["staked_amount"]
    eq, xq = q["entry_queue"] / st, q["exit_queue"] / st          # queues as a share of staked ETH
    nq = eq - xq
    F = {"entry_q": eq, "exit_q": xq, "net_q": nq,
         "log_entry_q": np.log1p(q["entry_queue"]), "log_exit_q": np.log1p(q["exit_queue"]),
         "net_q_sign": np.sign(q["entry_queue"] - q["exit_queue"])}
    for k in (7, 30):
        F[f"net_q_d{k}"] = nq.diff(k)
        F[f"entry_q_d{k}"] = eq.diff(k)
        F[f"exit_q_d{k}"] = xq.diff(k)
        F[f"staked_g{k}"] = st.pct_change(k)                       # realised net staking flow
    F["net_q_z90"] = z(nq, 90)
    F["exit_q_z90"] = z(xq, 90)
    F["entry_q_z90"] = z(eq, 90)
    F["staked_g30_z180"] = z(st.pct_change(30), 180)
    return pd.DataFrame(F).shift(lag).reindex(index), q


eth = ek.daily()["Close"]
btc = ek.daily("BTCUSDT")["Close"]
F, q = features(eth.index)
ctl = ek.trend_controls(eth)
H = (1, 7, 30)
cols = [f"h{h}_{k}{s}" for h in H for k in ("IS", "OOS") for s in ("", "_t")]
raw = ek.ic_table({k: F[k] for k in F}, eth, horizons=H, splits=SP)
par = ek.ic_table({k: F[k] for k in F}, eth, horizons=H, controls=ctl, splits=SP)
rel = ek.ic_table({k: F[k] for k in F}, eth / btc, horizons=H, splits=SP)
print("RAW IC vs forward ETH return (HAC t)"); print(raw[cols].round(3).to_string())
print("\nPARTIAL IC after trend controls"); print(par[cols].round(3).to_string())
print("\nRAW IC vs forward ETH/BTC return"); print(rel[cols].round(3).to_string())
for nm, t in (("raw", raw), ("partial", par), ("ETH/BTC", rel)):
    for h in H:
        a, b = t[f"h{h}_IS_t"], t[f"h{h}_OOS_t"]
        sig = a.abs() >= 2
        print(f"{nm} h={h}: IS->OOS Spearman of t {a.corr(b, method='spearman'):+.2f}; IS |t|>=2: {int(sig.sum())}, "
              f"same sign & |t_OOS|>=2: {int(((np.sign(a[sig]) == np.sign(b[sig])) & (b[sig].abs() >= 2)).sum())}")
raw.to_csv(os.path.join(HERE, "exp01_raw_ic.csv"))

# how many independent queue episodes are there?
xq = q["exit_queue"]; nq_ = q["entry_queue"] - q["exit_queue"]
flips = (np.sign(nq_) != np.sign(nq_.shift(1))).sum()
print(f"\nnet-queue sign flips in {len(q)} days: {int(flips)}; days with exit queue > entry queue: {(nq_ < 0).mean():.2f}")
ep = (xq > 100_000).astype(int)
starts = q.index[(ep.diff() == 1)]
print("exit-queue episodes (> 100k ETH) start dates:", [d.strftime("%Y-%m-%d") for d in starts])
for d in starts:
    if d in eth.index:
        f = {h: (eth.shift(-h).get(d, np.nan) / eth.get(d) - 1) * 100 for h in (7, 30, 60)}
        print(f"  {d.date()}: ETH {eth.get(d):.0f}, fwd 7/30/60 d {f[7]:+.1f}% / {f[30]:+.1f}% / {f[60]:+.1f}%, "
              f"past 30 d {(eth.get(d) / eth.shift(30).get(d) - 1) * 100:+.1f}%")

# a-priori rules
base = ek.baselines(eth)
vol, tf = base["volBH"], base["TF_live"]
w = {"volBH": vol, "TF_live": tf,
     "net queue > 0 x vol": (F["net_q"] > 0).astype(float) * vol,
     "net queue rising 30d x vol": (F["net_q_d30"] > 0).astype(float) * vol,
     "net queue rising 7d x vol": (F["net_q_d7"] > 0).astype(float) * vol,
     "exit queue z90 < 1 x vol": (F["exit_q_z90"] < 1).astype(float) * vol,
     "contrarian: net queue < 0 x vol": (F["net_q"] < 0).astype(float) * vol,
     "TF AND net queue > 0": tf * (F["net_q"] > 0),
     "TF AND net queue rising 30d": tf * (F["net_q_d30"] > 0),
     "TF veto exit queue z90 > 1": tf * (~(F["exit_q_z90"] > 1)),
     "TF veto net queue < 0": tf * (~(F["net_q"] < 0)),
     }
t = ek.table(w, eth, start="2023-06-01", splits={"Full": ("2023-06-01", None), "IS": ("2023-06-01", "2024-12-31"), "OOS": ("2025-01-01", None)}, bench_w=tf)
print("\na-priori rules, 10 bp/side, 2023-06 -> 2026-10 (z-score rules need 45 d of warm-up)")
print(ek.show(t[["Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Turn", "Expo", "rho_Full", "a_t_Full", "a_t_IS", "a_t_OOS"]]))

print("\nlag check on net_q_d30 and exit_q_z90 at h=30")
for lag in (0, 1, 3):
    Fl, _ = features(eth.index, lag=lag)
    for k in ("net_q_d30", "exit_q_z90", "net_q"):
        o = [ek.ic(Fl[k], eth, 30, *SP[s]) for s in ("IS", "OOS")]
        print(f"  lag {lag} {k}: IS {o[0]['ic']:+.3f} (t {o[0]['t']:+.1f})  OOS {o[1]['ic']:+.3f} (t {o[1]['t']:+.1f})")
