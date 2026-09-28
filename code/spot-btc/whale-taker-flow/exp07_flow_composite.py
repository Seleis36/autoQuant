"""Pre-specified composite: z_comp = (z_premium + z_whale) / sqrt(2), fed to coinbase-premium's
own state machine with its parameters UNCHANGED (enter 0, exit -1.5, SMA 1200 h, vol 40% hl
480 h, cap 1). z_whale = 720 h z-score of LmS_W (W = 24 h, the IS-selected window of exp05).
Also: whale state as an AND / OR with the premium state. Four configs total, no grid.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_hourly  # noqa: E402
from exp04_hourly_ic import hourly_groups, lms  # noqa: E402
from exp05_hourly_state import HPY, IS, OOS, hysteresis, stats  # noqa: E402
from exp06_blend import load_cbp  # noqa: E402


def main():
    h = btc_hourly().loc[:OOS[1]]
    close = h.Close
    fl = hourly_groups().reindex(close.index)
    cbp = load_cbp()
    cb = pd.read_parquet(os.path.join(REPO, "data", "COINBASE_BTCUSD_1h.parquet"))["Close"]
    cbc = cb.reindex(close.index).ffill(limit=3)
    zp = cbp.premium_zscore(close, cbc, 720)
    x, _, _ = lms(fl, 24)
    zw = (x - x.rolling(720, min_periods=360).mean()) / x.rolling(720, min_periods=360).std()
    trend = (close > close.rolling(1200).mean()).astype(float)
    r = close.pct_change()
    ewv = r.ewm(halflife=480, min_periods=480).std() * np.sqrt(HPY)
    vs = (0.40 / ewv).clip(0, 1).fillna(0)
    sp = cbp.hysteresis_state(zp, 0.0, -1.5)
    sw = hysteresis(zw, 0.0, -1.5)
    sw1 = hysteresis(zw, 0.0, -1.0)
    zc = (zp + zw) / np.sqrt(2)
    books = {
        "cbprem (live spec)": sp * trend * vs,
        "composite z (0,-1.5)": cbp.hysteresis_state(zc, 0.0, -1.5) * trend * vs,
        "premium AND whale": sp * sw * trend * vs,
        "premium OR whale": np.maximum(sp, sw) * trend * vs,
        "whale (0,-1.5) x trend": sw * trend * vs,
        "whale (0,-1) no trend": sw1 * vs,
    }
    rows = []
    for k, w in books.items():
        _, st = stats(w, close)
        rows.append(pd.Series(st, name=k))
    for c in (0.0, 5.0, 20.0):
        for k in ("cbprem (live spec)", "composite z (0,-1.5)"):
            _, st = stats(books[k], close, cost=c)
            rows.append(pd.Series(st, name=f"{k} @{c:g}bp"))
    pd.set_option("display.width", 200)
    print(pd.DataFrame(rows).round(2).to_string())
    print("corr(zp, zw):", round(zp.corr(zw), 3))


if __name__ == "__main__":
    main()
