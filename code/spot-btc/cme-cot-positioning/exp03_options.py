"""Shen, Li & Luo (FRL 2026): asset managers' OPTION positions on CME Bitcoin predict the
second-week-ahead futures return. Options positions = TFF combined - TFF futures-only
(delta-adjusted, BTC units, standard + micro).

Test, fixed before looking: features = option net / total OI for am, lev, dealer, oth
(level, 1-week change, 52-report z). Targets: week-1 return (days 0-7 after decision)
and week-2 return (days 7-14). IS <= 2022, OOS 2023+. Then the one pre-specified trade:
long BTC in week 2 when the IS-signed feature is positive (hold days 7-14), x inverse-vol.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily, evaluate  # noqa: E402
import research_lib as rl  # noqa: E402
import fetch_cot_btc as cot  # noqa: E402
from exp01_screen import ic_t  # noqa: E402

G = ["dealer", "am", "lev", "oth", "nonrep"]


def option_positions():
    fut = cot.fetch_tff()
    com = cot.fetch_tff_combined()
    cols = ["oi"] + [f"{g}_{s}" for g in G for s in ("long", "short")]
    f = cot.combined_btc(fut, cols)
    c = cot.combined_btc(com, cols)
    o = (c - f)
    feats = {}
    for g in G:
        onet = (o[f"{g}_long"] - o[f"{g}_short"]) / c["oi"]
        feats[f"{g}_opt_net"] = onet
        feats[f"{g}_opt_d1"] = onet.diff()
        feats[f"{g}_opt_z52"] = (onet - onet.rolling(52, min_periods=26).mean()) / onet.rolling(52, min_periods=26).std()
        feats[f"{g}_opt_gross"] = (o[f"{g}_long"] + o[f"{g}_short"]) / c["oi"]
    feats["opt_share_oi"] = (c["oi"] - f["oi"]) / c["oi"]
    return pd.DataFrame(feats), cot.report_avail(fut), o, c


def main():
    d = btc_daily()
    close = d["Close"]
    wf, avail, o, c = option_positions()
    print("option OI share by year:\n", wf["opt_share_oi"].resample("YE").mean().round(3))
    print("am option net/OI by year:\n", wf["am_opt_net"].resample("YE").mean().round(4))
    fd = cot.on_daily_rows(wf, d.index, avail)
    sat = d.index[d.index.dayofweek == 5]
    w1 = close.shift(-7) / close - 1
    w2 = close.shift(-14) / close.shift(-7) - 1
    rows = []
    for col in fd.columns:
        for tn, tgt in (("wk1", w1), ("wk2", w2)):
            r = {"feat": col, "target": tn}
            for k, (a, b) in {"IS": (None, "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
                ic, t, n = ic_t(fd.loc[sat, col].loc[a:b], tgt.loc[sat].loc[a:b], lags=1)
                r[f"IC_{k}"], r[f"t_{k}"], r[f"n_{k}"] = ic, t, n
            rows.append(r)
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(res.round(3).to_string(index=False))
    res.to_csv(os.path.join(HERE, "exp03_options.csv"), index=False)

    # pre-specified trade on the paper's headline feature: am option net (week 2)
    r_ = close.pct_change()
    vs = rl.vol_target_scalar(r_, target=0.40, halflife=20, cap=1.0)
    out = []
    for col in ["am_opt_net", "am_opt_d1", "am_opt_z52"]:
        sgn = np.sign(res[(res.feat == col) & (res.target == "wk2")].IC_IS.iloc[0])
        on_sat = (sgn * fd.loc[sat, col] > 0).astype(float)
        # position held from Saturday+7 close through Saturday+14 close
        pos = pd.Series(np.nan, index=d.index)
        pos.loc[sat] = on_sat.shift(1).values          # the previous week's signal
        pos = pos.ffill().fillna(0)
        _, st = evaluate(pos * vs, close, start="2018-10-01", name=f"wk2 {col} sign {sgn:+.0f}")
        out.append(st)
    print(pd.concat(out).round(2).to_string())


if __name__ == "__main__":
    main()
