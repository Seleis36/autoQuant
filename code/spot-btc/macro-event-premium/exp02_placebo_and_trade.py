"""(1) Clock-time placebo: same UTC time-of-day window on the same weekday one and two
weeks before/after each event (non-event days), to separate the pre-release drift from
the hour-of-day / weekday pattern. (2) Costed event trade: long BTC from T-k hours to T
(exit before the release print), 10 bp/side, standalone and trend-gated."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import btc_data  # noqa: E402
import research_lib as rl  # noqa: E402
from bars import load_bars  # noqa: E402
from events import event_times  # noqa: E402

COST = 10.0


def price_grid():
    m = load_bars("BTCUSDT", "1m")["Close"]
    px = pd.Series(m.values, index=m.index + pd.Timedelta(minutes=1))
    grid = pd.date_range(px.index[0].ceil("30min"), px.index[-1], freq="30min")
    return np.log(px.reindex(px.index.union(grid)).ffill().reindex(grid))


def win_ret(logp, times, a, b):
    return logp.reindex(times + pd.Timedelta(hours=b)).values - logp.reindex(times + pd.Timedelta(hours=a)).values


def main():
    logp = price_grid()
    ev = event_times()
    ev = ev[(ev.t > logp.index[0] + pd.Timedelta(days=20)) & (ev.t < logp.index[-1] - pd.Timedelta(days=20))]
    evset = set(ev.t.dt.normalize())
    print("=== (1) event vs clock-time placebo (same weekday/time +-1,2 weeks, non-event days) ===")
    rows = []
    for (a, b) in [(-1, 0), (-3, 0), (-6, 0), (-6, -1), (-12, 0), (-24, 0)]:
        r_ev = win_ret(logp, ev.t, a, b)
        pl = []
        for k in (-14, -7, 7, 14):
            tt = ev.t + pd.Timedelta(days=k)
            ok = ~tt.dt.normalize().isin(evset)
            v = win_ret(logp, tt, a, b)
            v[~ok.values] = np.nan
            pl.append(v)
        pl = np.nanmean(np.vstack(pl), axis=0)
        e = ev.assign(ev=r_ev, pl=pl)
        for half, (lo, hi) in {"IS": ("2000", "2022-12-31"), "OOS": ("2023-01-01", "2100")}.items():
            for kind in ["ALL", "FOMC", "CPI", "NFP"]:
                s = e[(e.t >= lo) & (e.t <= hi)]
                if kind != "ALL":
                    s = s[s.kind == kind]
                d = (s.ev - s.pl).dropna()
                rows.append({"win": f"[{a},{b})", "half": half, "kind": kind, "n": len(d),
                             "event_bp": s.ev.mean() * 1e4, "placebo_bp": s.pl.mean() * 1e4,
                             "diff_bp": d.mean() * 1e4, "t_diff": d.mean() / d.std() * np.sqrt(len(d))})
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(res.pivot_table(index=["win", "kind"], columns="half",
                          values=["event_bp", "placebo_bp", "diff_bp", "t_diff"], sort=False).round(1).to_string())

    print("\n=== (2) costed trade: long [T-k, T), 10 bp/side, per-event and annualised ===")
    d = btc_data.btc_daily()
    trend = (d.Close > d.Close.rolling(50).mean())
    tr_known = trend.shift(1)          # trend known at the previous daily close
    out = []
    for k, cost in [(k, c) for k in (1, 2, 3, 6, 12, 24) for c in (0.0, 5.0, COST)]:
        r = win_ret(logp, ev.t, -k, 0)
        e = ev.assign(r=np.expm1(r) - 2 * cost / 1e4, day=ev.t.dt.normalize())
        e["trend"] = tr_known.reindex(e.day).values
        for gate in ("none", "trend"):
            s = e if gate == "none" else e[e.trend == True]  # noqa: E712
            for half, (lo, hi) in {"full": ("2000", "2100"), "IS": ("2000", "2022-12-31"),
                                   "OOS": ("2023-01-01", "2100")}.items():
                x = s[(s.t >= lo) & (s.t <= hi)].r.dropna()
                yrs = (min(pd.Timestamp(hi), ev.t.max()) - max(pd.Timestamp(lo), ev.t.min())).days / 365
                # annualised Sharpe of the daily P&L stream (flat on non-event days)
                ndays = yrs * 365
                mu = x.sum() / ndays
                sd = np.sqrt((x ** 2).sum() / ndays - mu ** 2)
                sh = mu / sd * np.sqrt(365) if len(x) else np.nan
                out.append({"k": k, "cost": cost, "gate": gate, "half": half, "n": len(x), "net_bp": x.mean() * 1e4,
                            "ann_ret": x.sum() / yrs, "Sharpe": sh})
    o = pd.DataFrame(out)
    o.to_csv(os.path.join(HERE, "exp02_trade.csv"), index=False)
    print(o.pivot_table(index=["gate", "cost", "k"], columns="half", values=["net_bp", "ann_ret", "Sharpe"]).round(3).to_string())


if __name__ == "__main__":
    main()
