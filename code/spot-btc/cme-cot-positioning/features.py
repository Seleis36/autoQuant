"""Weekly CME-Bitcoin COT features on the report (as-of Tuesday) grid, and their mapping
onto Binance daily bars at the moment each report became public."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import fetch_cot_btc as cot  # noqa: E402

GROUPS = ["dealer", "am", "lev", "oth", "nonrep"]


def weekly_base():
    """Combined standard + micro positions in BTC, per report date."""
    t = cot.fetch_tff()
    cols = ["oi"] + [f"{g}_{s}" for g in GROUPS for s in ("long", "short")]
    c = cot.combined_btc(t, cols)
    lg = cot.fetch_legacy()
    lcols = ["oi", "nc_long", "nc_short", "c_long", "c_short", "nr_long", "nr_short"]
    l = cot.combined_btc(lg, lcols).add_prefix("leg_")
    c = c.join(l, how="left")
    avail = cot.report_avail(t)
    return c, avail


def weekly_features(c):
    f = {}
    oi = c["oi"]
    for g in GROUPS:
        net = (c[f"{g}_long"] - c[f"{g}_short"]) / oi
        lo = c[f"{g}_long"] / oi
        sh = c[f"{g}_short"] / oi
        f[f"{g}_net"] = net
        for w in (26, 52):
            f[f"{g}_net_z{w}"] = (net - net.rolling(w, min_periods=w // 2).mean()) / \
                net.rolling(w, min_periods=w // 2).std()
        for k in (1, 4, 13):
            f[f"{g}_net_d{k}"] = net.diff(k)
            # position flow in BTC relative to current OI (who added exposure)
            f[f"{g}_flow{k}"] = (c[f"{g}_long"] - c[f"{g}_short"]).diff(k) / oi
        f[f"{g}_long_z52"] = (lo - lo.rolling(52, min_periods=26).mean()) / lo.rolling(52, min_periods=26).std()
        f[f"{g}_short_z52"] = (sh - sh.rolling(52, min_periods=26).mean()) / sh.rolling(52, min_periods=26).std()
    lo = np.log(oi)
    for k in (1, 4, 13):
        f[f"oi_g{k}"] = lo.diff(k)
    f["oi_z52"] = (lo - lo.rolling(52, min_periods=26).mean()) / lo.rolling(52, min_periods=26).std()
    loi = c["leg_oi"]
    for p, a, b in (("nc", "leg_nc_long", "leg_nc_short"), ("nr", "leg_nr_long", "leg_nr_short"),
                    ("cm", "leg_c_long", "leg_c_short")):
        net = (c[a] - c[b]) / loi
        f[f"leg_{p}_net"] = net
        f[f"leg_{p}_net_z52"] = (net - net.rolling(52, min_periods=26).mean()) / net.rolling(52, min_periods=26).std()
        f[f"leg_{p}_net_d1"] = net.diff(1)
        f[f"leg_{p}_net_d4"] = net.diff(4)
    return pd.DataFrame(f)


def daily_features(idx):
    """Features as known at the close of each daily bar in idx (Binance, UTC)."""
    c, avail = weekly_base()
    wf = weekly_features(c)
    return cot.on_daily_rows(wf, idx, avail), avail
