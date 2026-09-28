"""Strategy expressions of the BTC variance-risk-premium signal, with RV-only controls.

Signals (all known at the close of bar D = D+1 00:00 UTC):
  IVRV>0      log(DVOL / RV30) > 0            canonical, parameter-free
  IVRVz180>0  180d z-score of log(IV/RV30) > 0
  VRPz180>0   180d z-score of IV^2 - RV30^2 > 0
  IVRV_hyst   enter log(IV/RV) > +0.05, exit < -0.05   (turnover control)
Controls (the ETH study's failure mode: RV in disguise):
  RVz180<0    low-realized-vol regime only
  dRV<0       RV30 falling over 20 days
Forms (10 bp/side): A standalone x inv-vol(40%, hl 20, cap 1); B x SMA50 trend gate;
C trend tilt 0.5 + 0.5 x signal. Evaluation window 2021-10-01 -> (z180 warm-up), IS <= 2022.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import evaluate  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import build  # noqa: E402

START = "2021-10-01"


def hysteresis(x, enter, exit_):
    out = np.zeros(len(x))
    on = False
    for i, v in enumerate(x.values):
        if np.isnan(v):
            on = False
        elif not on and v > enter:
            on = True
        elif on and v < exit_:
            on = False
        out[i] = on
    return pd.Series(out, index=x.index)


def signals(f):
    s = pd.DataFrame(index=f.index)
    s["IVRV>0"] = (f.IVRV30 > 0).astype(float)
    s["IVRVz180>0"] = (f.IVRVz180 > 0).astype(float)
    s["VRPz180>0"] = (f.VRPz180 > 0).astype(float)
    s["IVRV_hyst"] = hysteresis(f.IVRV30, 0.05, -0.05)
    s["CTRL RVz180<0"] = (f.RVz180 < 0).astype(float)
    s["CTRL dRV<0"] = (f.RV30.diff(20) < 0).astype(float)
    return s.where(f.IVRV30.notna(), 0.0)


def main():
    d, f = build()
    close = d.Close
    r = close.pct_change()
    vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    trend = (close > close.rolling(50).mean()).astype(float)
    sig = signals(f)
    rows = []
    for nm, w in (("vol B&H", vs), ("SMA50 x vol", trend * vs)):
        _, st = evaluate(w, close, start=START, name=nm); rows.append(st)
    for k in sig.columns:
        on = sig[k]
        for form, w in (("A", on * vs), ("B", trend * vs * on), ("C", trend * vs * (0.5 + 0.5 * on))):
            _, st = evaluate(w, close, start=START, name=f"{form} {k}"); rows.append(st)
    res = pd.concat(rows)
    pd.set_option("display.width", 200)
    print(res.round(2).to_string())
    res.to_csv(os.path.join(HERE, "exp02_backtest.csv"))


if __name__ == "__main__":
    main()
