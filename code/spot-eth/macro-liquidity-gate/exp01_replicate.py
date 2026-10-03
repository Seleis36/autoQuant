"""exp01 — port of the BULT macro-liquidity regime (spot-btc, 2026-09-06) to spot ETH.

The composite is taken unchanged from code/spot-btc/bult/strategy.py: for HYG (+), LQD (+),
DX-Y.NYB (-), ^GSPC (+), the share of {50,100,150,200,250}-day moving averages the series is
above (below for the dollar), averaged over the four. Nothing is re-fitted on ETH.

Timing: the US session of date D closes at 20:00/21:00 UTC, three hours before the ETH daily bar
D closes (D+1 00:00 UTC). The macro row dated D is therefore usable for the weight held over bar
D+1 -- the same convention as BULT. Weekends and holidays carry the last close forward.
IS 2017-09 -> 2023, OOS 2024+.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import evalkit as ek  # noqa: E402
from ethdata import rl  # noqa: E402

pd.set_option("display.width", 260)
MACRO = {"HYG": +1, "LQD": +1, "DX-Y.NYB": -1, "^GSPC": +1}      # BULT, unchanged
MACRO_LB = (50, 100, 150, 200, 250)
TREND_LB = (20, 50, 100, 150, 200)


def macro_parts(index, lag=0, lbs=MACRO_LB, macro=MACRO):
    out = {}
    for tkr, sgn in macro.items():
        s = rl.load_series(tkr)["Close"]
        m = pd.concat([(s > s.rolling(n).mean()).astype(float).where(s.rolling(n).mean().notna()) for n in lbs], axis=1).mean(axis=1)
        m = m if sgn > 0 else 1.0 - m
        out[tkr] = m.reindex(index, method="ffill").shift(lag)
    return pd.DataFrame(out)


def macro_composite(index, lag=0, lbs=MACRO_LB, macro=MACRO):
    return macro_parts(index, lag, lbs, macro).mean(axis=1)


if __name__ == "__main__":
    eth = ek.daily()["Close"]
    btc = ek.daily("BTCUSDT")["Close"]
    base = ek.baselines(eth)
    vol, tf = base["volBH"], base["TF_live"]
    mac = macro_composite(eth.index)
    parts = macro_parts(eth.index)
    trend_ens = pd.concat([(eth > eth.rolling(n).mean()).astype(float) for n in TREND_LB], axis=1).mean(axis=1)
    sma40 = (eth > eth.rolling(40).mean()).astype(float)
    print(f"macro composite: mean {mac.loc['2017-09':].mean():.2f}; corr with ETH SMA40 state {mac.corr(sma40):.2f}, with trend ensemble {mac.corr(trend_ens):.2f}")

    START = "2018-06-01"       # 200-day ETH trend lookback from the 2017-08 start of the bar store
    w = {"volBH": vol, "TF_live": tf, "SMA50xvol": base["SMA50xvol"],
         "M1 macro x vol(0.40)": mac * vol,
         "M2 macro > 0.5 x vol": (mac > 0.5).astype(float) * vol,
         "B1 BULT base on ETH: trend-ens x macro x vol(0.35)": trend_ens * mac * ek.vol_scalar(eth, target=0.35),
         "B0 trend-ens x vol(0.35) (no macro)": trend_ens * ek.vol_scalar(eth, target=0.35),
         "G1 TF_live x macro": tf * mac,
         "G2 TF_live AND macro > 0.5": tf * (mac > 0.5),
         "G3 TF_live x (0.5 + 0.5 macro)": tf * (0.5 + 0.5 * mac),
         "O1 max(TF_live, macro x vol(0.5))": np.maximum(tf, mac * ek.vol_scalar(eth, target=0.5)),
         "D1 50/50 TF_live + M1": 0.5 * tf + 0.5 * mac * vol,
         }
    cols = ["Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "Vol", "Turn", "Expo", "rho_Full", "a_t_Full", "a_t_IS", "a_t_OOS"]
    print(f"\n10 bp/side, {START} -> {eth.index.max().date()}, IS <= 2023 / OOS 2024+; alpha t = HAC t of the intercept on TF_live")
    print(ek.show(ek.table(w, eth, start=START, bench_w=tf)[cols]))

    print("\ncomponents, each as (share of MAs above) x vol, and as a gate on TF_live")
    wc = {}
    for k in parts:
        wc[f"{k} x vol"] = parts[k] * vol
        wc[f"TF x {k}"] = tf * parts[k]
    print(ek.show(ek.table(wc, eth, start=START, bench_w=tf)[cols]))

    print("\nIC of the composite with forward ETH returns: raw | partial after trend controls (HAC t)")
    ctl = ek.trend_controls(eth)
    for h in (1, 7, 30):
        r = [ek.ic(mac, eth, h, *ek.SPLITS[s]) for s in ("IS", "OOS")]
        q = [ek.ic(mac, eth, h, *ek.SPLITS[s], controls=ctl) for s in ("IS", "OOS")]
        print(f"  h={h:>2}: raw IS {r[0]['ic']:+.3f} ({r[0]['t']:+.1f}) OOS {r[1]['ic']:+.3f} ({r[1]['t']:+.1f}) | "
              f"partial IS {q[0]['ic']:+.3f} ({q[0]['t']:+.1f}) OOS {q[1]['ic']:+.3f} ({q[1]['t']:+.1f})")

    print("\nnext-day ETH return (bp) by SMA40 state x macro state (composite > 0.5)")
    r1 = eth.pct_change().shift(-1) * 1e4
    for k, (a, b) in ek.SPLITS.items():
        d = pd.DataFrame({"r": r1, "up": sma40, "mac": (mac > 0.5).astype(float)}).loc[max(a, START):b].dropna()
        g = d.groupby(["up", "mac"])["r"].agg(["mean", "count", lambda x: x.mean() / x.std() * np.sqrt(len(x))])
        g.columns = ["bp", "n", "t"]
        print(k); print(g.round(2).to_string())

    # the same thing on BTC: is the ETH sleeve the BTC sleeve?
    tb = pd.concat([(btc > btc.rolling(n).mean()).astype(float) for n in TREND_LB], axis=1).mean(axis=1)
    nb = ek.bt(tb * mac * ek.vol_scalar(btc, target=0.35), btc, start=START)[0]
    ne = ek.bt(w["B1 BULT base on ETH: trend-ens x macro x vol(0.35)"], eth, start=START)[0]
    ng = ek.bt(w["G1 TF_live x macro"], eth, start=START)[0]
    nt = ek.bt(tf, eth, start=START)[0]
    sh = lambda x: x.mean() / x.std() * np.sqrt(365)
    print(f"\nBULT base on BTC, same window: {sh(nb):.2f} / IS {sh(nb.loc[:'2023-12-31']):.2f} / OOS {sh(nb.loc['2024-01-01':]):.2f}")
    print(f"corr(B1 ETH, BULT base BTC) {ne.corr(nb):.2f}; corr(G1, BULT base BTC) {ng.corr(nb):.2f}; corr(G1, TF_live) {ng.corr(nt):.2f}; corr(TF_live, BULT base BTC) {nt.corr(nb):.2f}")
    yr = pd.DataFrame({k: v.groupby(v.index.year).apply(sh) for k, v in {"TF_live": nt, "G1 TF x macro": ng, "B1": ne}.items()})
    print("\nyearly Sharpe"); print(yr.round(2).T.to_string())
