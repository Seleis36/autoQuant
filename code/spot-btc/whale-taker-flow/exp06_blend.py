"""Correlation and blend of the IS-selected hourly whale-flow sleeve with the live-style
sleeves: SMA50d x vol (hourly), coinbase-premium (its own strategy.py, default params).

Daily P&L correlations (hourly net returns summed per UTC day) and 50/50 weight blends
(average of target weights, one book, costs on the blended turnover).
"""
import importlib.util
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


def load_cbp():
    spec = importlib.util.spec_from_file_location("cbp", os.path.join(REPO, "code", "spot-btc", "coinbase-premium", "strategy.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def whale_weight(close, fl, W=24, enter=0.0, exit_=-1.0):
    x, _, _ = lms(fl, W)
    z = (x - x.rolling(720, min_periods=360).mean()) / x.rolling(720, min_periods=360).std()
    r = close.pct_change()
    ewv = r.ewm(halflife=480, min_periods=480).std() * np.sqrt(HPY)
    vs = (0.40 / ewv).clip(0, 1).fillna(0)
    return hysteresis(z, enter, exit_) * vs, vs


def main():
    h = btc_hourly().loc[:OOS[1]]
    close = h.Close
    fl = hourly_groups().reindex(close.index)
    ww, vs = whale_weight(close, fl)
    trend = (close > close.rolling(1200).mean()).astype(float)
    wt = trend * vs
    cb = pd.read_parquet(os.path.join(REPO, "data", "COINBASE_BTCUSD_1h.parquet"))
    cbc = cb["Close"] if "Close" in cb else cb["close"]
    cbc.index = pd.to_datetime(cbc.index).tz_localize(None) if getattr(cbc.index, "tz", None) else pd.to_datetime(cbc.index)
    wc = load_cbp().target_weight(close, cbc.reindex(close.index).ffill(limit=3))
    books = {"whale": ww, "trend": wt, "cbprem": wc,
             "whale+trend": 0.5 * (ww + wt), "whale+cbprem": 0.5 * (ww + wc),
             "trend+cbprem": 0.5 * (wt + wc), "all3": (ww + wt + wc) / 3}
    rows, nets = [], {}
    for k, w in books.items():
        nets[k], st = stats(w, close)
        rows.append(pd.Series(st, name=k))
    print(pd.DataFrame(rows).round(2).to_string())
    daily = pd.DataFrame({k: nets[k].loc[IS[0]:OOS[1]].resample("1D").sum() for k in ("whale", "trend", "cbprem")})
    for half, (a, b) in {"full": (IS[0], OOS[1]), "IS": IS, "OOS": OOS}.items():
        print(half, "daily P&L corr:\n", daily.loc[a:b].corr().round(2).to_string())
    print("weight corr:", pd.DataFrame({"whale": ww, "trend": wt, "cbprem": wc}).loc[IS[0]:].corr().round(2).to_string())


if __name__ == "__main__":
    main()
