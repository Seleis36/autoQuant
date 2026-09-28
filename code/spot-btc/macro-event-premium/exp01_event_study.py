"""Hourly event study: BTC (Binance BTCUSDT) log returns in windows around US macro
release times, by event kind, IS (<= 2022) vs OOS (2023+). Excess = window return minus
the unconditional mean hourly return x window length (same half)."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import btc_data  # noqa: E402,F401  (puts code/shared on the path)
from bars import load_bars  # noqa: E402
from events import event_times  # noqa: E402

WINDOWS = [(-96, -72), (-72, -48), (-48, -24), (-24, -12), (-12, -6), (-6, -1), (-1, 0),
           (0, 1), (1, 6), (6, 24), (24, 48), (48, 72), (-24, 0), (-48, 0), (0, 24)]


def main():
    m = load_bars("BTCUSDT", "1m")["Close"]
    # price AT time t = Close of the 1m bar stamped t - 1min (bar covers [t-1m, t)).
    px = pd.Series(m.values, index=m.index + pd.Timedelta(minutes=1))
    logp = np.log(px)
    lr = logp.resample("1h").last().diff().dropna()   # only for the unconditional baseline
    ev = event_times()
    ev = ev[(ev.t > lr.index[0] + pd.Timedelta(hours=100)) & (ev.t < lr.index[-1] - pd.Timedelta(hours=80))]
    # log price as of any timestamp (last trade at or before it)
    grid = pd.date_range(logp.index[0].ceil("30min"), logp.index[-1], freq="30min")
    cum = logp.reindex(logp.index.union(grid)).ffill().reindex(grid)
    rows = []
    for (a, b) in WINDOWS:
        t_hi = ev.t + pd.Timedelta(hours=b)
        t_lo = ev.t + pd.Timedelta(hours=a)
        v = cum.reindex(t_hi).values - cum.reindex(t_lo).values
        e = ev.assign(ret=v)
        for half, (lo, hi) in {"IS": ("2000", "2022-12-31"), "OOS": ("2023-01-01", "2100")}.items():
            base = lr.loc[lo:hi].mean() * (b - a)
            for kind in ["ALL", "FOMC", "CPI", "NFP"]:
                s = e[(e.t >= lo) & (e.t <= hi)]
                if kind != "ALL":
                    s = s[s.kind == kind]
                x = s.ret.dropna() - base
                rows.append({"win": f"[{a},{b})", "half": half, "kind": kind, "n": len(x),
                             "ex_bp": x.mean() * 1e4, "t": x.mean() / x.std() * np.sqrt(len(x)),
                             "hit": (x > 0).mean()})
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(HERE, "exp01_event_study.csv"), index=False)
    pv = res.pivot_table(index=["kind", "win"], columns="half", values=["ex_bp", "t"], sort=False)
    pd.set_option("display.width", 200)
    print(pv.round(2).to_string())


if __name__ == "__main__":
    main()
