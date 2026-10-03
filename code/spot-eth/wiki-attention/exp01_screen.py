"""exp01 — investor attention (Wikipedia pageviews) as a predictor of ETH returns.

Liu & Tsyvinski (RFS 2021): abnormal Google-search attention predicts 1-6 week crypto returns
positively. Wikipedia daily pageviews are the keyless, never-revised stand-in. The count for UTC
day D is published during D+1, so every feature is lagged one full day (LAG = 1): the weight
decided at D+1 00:00 uses views up to D-1.

IS 2017-09 -> 2023, OOS 2024+ (spot-eth convention). 7-day means remove the weekday pattern.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, HERE)
import evalkit as ek  # noqa: E402
import fetch_wiki as fw  # noqa: E402

pd.set_option("display.width", 260)
LAG = 1


def z(x, n):
    return (x - x.rolling(n).mean()) / x.rolling(n).std()


def features(index, lag=LAG):
    v = np.log(fw.load().clip(lower=1))
    e, b, c = v["Ethereum"], v["Bitcoin"], v["Cryptocurrency"]
    m7 = lambda s: s.rolling(7).mean()
    F = {}
    for nm, s in (("eth", e), ("btc", b), ("crypto", c), ("vitalik", v["Vitalik_Buterin"])):
        F[f"{nm}_abn_7_28"] = m7(s) - s.rolling(28).mean().shift(7)       # L&T: this week vs prior 4 weeks
        F[f"{nm}_abn_7_90"] = m7(s) - s.rolling(90).mean()
        F[f"{nm}_z7_365"] = z(m7(s), 365)
    F["eth_abn_1_7"] = e - m7(e).shift(1)                                 # yesterday vs the week before
    F["eth_abn_30_180"] = e.rolling(30).mean() - e.rolling(180).mean()
    F["eth_z7_90"] = z(m7(e), 90)
    F["eth_d7"] = m7(e).diff(7)
    comp = (v[["Ethereum", "Bitcoin", "Cryptocurrency"]].rolling(7).mean()
            - v[["Ethereum", "Bitcoin", "Cryptocurrency"]].rolling(28).mean().shift(7)).mean(axis=1)
    F["composite_abn_7_28"] = comp
    rel = e - b                                                           # ETH share of attention
    F["eth-btc_abn_7_28"] = m7(rel) - rel.rolling(28).mean().shift(7)
    F["eth-btc_z7_365"] = z(m7(rel), 365)
    F["eth-btc_abn_30_180"] = rel.rolling(30).mean() - rel.rolling(180).mean()
    return pd.DataFrame(F).shift(lag).reindex(index)


if __name__ == "__main__":
    eth = ek.daily()["Close"]
    btc = ek.daily("BTCUSDT")["Close"]
    F = features(eth.index)
    ctl = ek.trend_controls(eth)
    H = (1, 7, 14, 30)
    cols = [f"h{h}_{k}{s}" for h in H for k in ("IS", "OOS") for s in ("", "_t")]
    feats = {k: F[k] for k in F}
    raw = ek.ic_table(feats, eth, horizons=H)
    par = ek.ic_table(feats, eth, horizons=H, controls=ctl)
    rel = ek.ic_table(feats, eth / btc, horizons=H)
    print("RAW IC vs forward ETH return (HAC t)"); print(raw[cols].round(3).to_string())
    print("\nPARTIAL IC after trend controls"); print(par[cols].round(3).to_string())
    print("\nRAW IC vs forward ETH/BTC return"); print(rel[cols].round(3).to_string())
    for nm, t in (("raw", raw), ("partial", par), ("ETH/BTC", rel)):
        for h in H:
            a, b = t[f"h{h}_IS_t"], t[f"h{h}_OOS_t"]
            sig = a.abs() >= 2
            same = np.sign(a[sig]) == np.sign(b[sig])
            print(f"{nm} h={h}: IS->OOS Spearman of t {a.corr(b, method='spearman'):+.2f}; IS |t|>=2: {int(sig.sum())}, "
                  f"same sign OOS {int(same.sum())}, also |t_OOS|>=2 {int((same & (b[sig].abs() >= 2)).sum())}")
    raw.to_csv(os.path.join(HERE, "exp01_raw_ic.csv")); par.to_csv(os.path.join(HERE, "exp01_partial_ic.csv"))

    print("\ncorrelation of features with controls (Spearman, full sample)")
    lc = np.log(eth)
    ctl2 = ctl.assign(absret7=(lc - lc.shift(7)).abs())
    print(pd.concat([F, ctl2], axis=1).corr(method="spearman").loc[F.columns, ["ret7", "ret30", "sma40", "rv20", "absret7"]].round(2).to_string())

    print("\nyearly raw IC of eth_abn_7_28 at h=7 and h=30")
    print(pd.DataFrame({h: {y: ek.ic(F["eth_abn_7_28"], eth, h, f"{y}-01-01", f"{y}-12-31")["ic"] for y in range(2018, 2027)} for h in (7, 30)}).T.round(3).to_string())
